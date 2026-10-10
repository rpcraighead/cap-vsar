"""Observation-driven ArduPlane runway-to-runway task sequence.

The script never sleeps through a phase or marks upload/mode ACK as aircraft
success. Its thresholds come from a reviewed mission plan, not defaults here.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from . import mavlink_min as mav
from .flight_executive import (
    Controller, FlightTask, Phase, Role, TaskKind, TransferState,
)


@dataclass(frozen=True)
class SortieCriteria:
    takeoff_min_agl_ft: float
    waypoint_max_distance_m: float
    landing_max_agl_ft: float
    stop_max_groundspeed_kt: float
    go_around_altitude_m_msl: float
    go_around_min_agl_ft: float

    def __post_init__(self):
        if any(not math.isfinite(value) or value <= 0 for value in vars(self).values()):
            raise ValueError("Reviewed positive mission criteria required")


@dataclass(frozen=True)
class GarminSegment:
    """Planned cruise segment after an achieved ArduPlane waypoint.

    ``prepare_return`` must renew the bridge with a distinct managed session,
    stage its candidate outputs, and return its identity. It is supplied by
    the caller: this offline runner cannot restart SITL or qualify the rig.
    """

    after_step: int
    heading_mag: float
    altitude_indicated_ft: float
    min_transfer_agl_ft: float
    prepare_return: Callable[[object], str]
    task_timeout_s: float = 60.0

    def __post_init__(self):
        if type(self.after_step) is not int or self.after_step < 0:
            raise ValueError("Garmin transfer requires a planned step index")
        values = (self.heading_mag, self.altitude_indicated_ft,
                  self.min_transfer_agl_ft, self.task_timeout_s)
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
                or not 0 <= self.heading_mag < 360
                or self.altitude_indicated_ft <= 0
                or self.min_transfer_agl_ft <= 0 or self.task_timeout_s <= 0
                or not callable(self.prepare_return)):
            raise ValueError("Reviewed Garmin segment and return procedure required")


class MissionScript:
    def __init__(self, executive, items, criteria: SortieCriteria, *, task_timeout_s=60.0,
                 garmin_segment: GarminSegment | None = None):
        if len(items) < 6:
            raise ValueError("Full sortie needs takeoff, two route fixes, approach, land")
        self.executive = executive
        self.items = tuple(items)
        self.criteria = criteria
        self.task_timeout_s = task_timeout_s
        self.steps = [
            (Phase.TAKEOFF, FlightTask(TaskKind.UPLOAD_MISSION, {"items": self.items}, task_timeout_s)),
            (Phase.TAKEOFF, FlightTask(TaskKind.START_AUTO, {}, task_timeout_s)),
            (Phase.TAKEOFF, FlightTask(TaskKind.TAKEOFF,
                                       {"min_agl_ft": criteria.takeoff_min_agl_ft}, task_timeout_s)),
        ]
        for seq in range(1, len(items) - 3):
            phase = Phase.CLIMB if seq == 1 else Phase.TRANSIT
            self.steps.append((phase, FlightTask(TaskKind.WAYPOINT,
                {"seq": seq, "max_distance_m": criteria.waypoint_max_distance_m}, task_timeout_s)))
        self.steps += [
            (Phase.APPROACH, FlightTask(TaskKind.APPROACH,
                {"seq": len(items) - 2,
                 "go_around_altitude_m_msl": criteria.go_around_altitude_m_msl,
                 "go_around_min_agl_ft": criteria.go_around_min_agl_ft},
                task_timeout_s, on_timeout="go_around")),
            (Phase.LAND, FlightTask(TaskKind.LAND,
                {"max_agl_ft": criteria.landing_max_agl_ft,
                 "go_around_altitude_m_msl": criteria.go_around_altitude_m_msl,
                 "go_around_min_agl_ft": criteria.go_around_min_agl_ft},
                task_timeout_s, on_timeout="go_around")),
            (Phase.ROLLOUT, FlightTask(TaskKind.LAND,
                {"rollout": True, "max_groundspeed_kt": criteria.stop_max_groundspeed_kt},
                task_timeout_s)),
        ]
        if garmin_segment is not None:
            index = garmin_segment.after_step
            if (index >= len(self.steps) or self.steps[index][0] not in
                    (Phase.CLIMB, Phase.TRANSIT) or self.steps[index][1].kind != TaskKind.WAYPOINT):
                raise ValueError("Garmin segment must follow a planned climb/transit waypoint")
            if index + 1 >= len(self.steps) or self.steps[index + 1][0] != Phase.TRANSIT:
                raise ValueError("Garmin segment must return before a transit waypoint")
        self.garmin_segment = garmin_segment
        self.segment_state = None
        self.departure_link = None
        self.return_operation = None
        self.return_origin = None
        self.stop_errors = []
        self.index = 0
        self.waiting_id = None
        self.state = "NEW"

    def start(self):
        if self.state != "NEW":
            raise ValueError("Sortie already started")
        readiness = self.executive.adapters[Controller.ARDUPLANE].observed_status()
        required = ("runway_ready", "configuration_verified", "engine_ready",
                    "home_verified", "estimator_origin_verified",
                    "human_clearance_confirmed", "telemetry_fresh")
        if (not all(readiness.get(key) is True for key in required)
                or readiness.get("on_ground") is not True
                or readiness.get("groundspeed_kt", float("inf")) > 1):
            raise ValueError("Ground configuration/runway clearance readiness not observed")
        self.executive.request_mode(Role.AI_MISSION, Phase.TAKEOFF,
                                    Controller.ARDUPLANE, "runway_sortie")
        self.departure_link = self.executive.adapters[Controller.ARDUPLANE].link
        self.executive.transfer_control(Controller.ARDUPLANE,
                                        self.executive.bridge.generation)
        self.state = "TRANSFERRING"
        return self.status()

    def tick(self):
        if self.state not in ("TRANSFERRING", "RUNNING", "ABORTING",
                              "TRANSFERRING_GARMIN", "RUNNING_GARMIN",
                              "TRANSFERRING_ARDUPLANE", "PREPARING_RETURN"):
            return self.status()
        status = self.executive.tick()
        if status["transfer"] == TransferState.PAUSED_FAULT.value:
            if self.return_operation is not None:
                self.return_operation.cancel()
            self.state = "FAULTED"
            return self.status()
        if self.executive.latched_takeover:
            if self.return_operation is not None:
                self.return_operation.cancel()
            self.state = "CANCELED_TO_HUMAN"
            self.waiting_id = None
            return self.status()
        if self.waiting_id:
            outcome = next((event["status"] for event in reversed(status["events"])
                            if event.get("task_id") == self.waiting_id
                            and event["status"] in ("achieved", "timed_out", "canceled")), None)
            if outcome == "achieved":
                self.waiting_id = None
                if self.state == "ABORTING":
                    self.state = "GO_AROUND_COMPLETE"
                    return self.status()
                if self.segment_state == "GARMIN_TASK":
                    self._return_to_arduplane()
                    return self.status()
                self.index += 1
                if (self.garmin_segment is not None and self.segment_state is None
                        and self.index == self.garmin_segment.after_step + 1):
                    self._enter_garmin()
                    return self.status()
            elif outcome in ("timed_out", "canceled"):
                if status["task"] == TaskKind.GO_AROUND.value:
                    self.state = "ABORTING"
                    self.waiting_id = status["events"][-1]["task_id"]
                else:
                    self.state = "FAULTED"
                return self.status()
            else:
                return self.status()
        if status["transfer"] != TransferState.ACTIVE.value:
            return self.status()
        if not self.executive.lease:
            self.state = "FAULTED"
            return self.status()
        if self.segment_state == "PREPARING_RETURN":
            try:
                session = self.return_operation.poll(self.executive)
                if session is None:
                    return self.status()
                self._commit_return(session, *self.return_origin)
            except Exception as error:
                self._abort_segment("Planned ArduPlane return failed: %s" % error)
            return self.status()
        if self.segment_state == "TO_GARMIN":
            if self.executive.controller != Controller.GFC700:
                return self.status()
            segment = self.garmin_segment
            try:
                result = self.executive.submit_task(self.executive.lease,
                    self.executive.sequence + 1,
                    FlightTask(TaskKind.HEADING_ALTITUDE,
                        {"heading_mag": segment.heading_mag,
                         "altitude_indicated_ft": segment.altitude_indicated_ft},
                        segment.task_timeout_s))
            except Exception as error:
                self._abort_segment("Garmin task could not start: %s" % error)
                return self.status()
            self.waiting_id = result["task_id"]
            self.segment_state = "GARMIN_TASK"
            self.state = "RUNNING_GARMIN"
            return self.status()
        if self.segment_state == "TO_ARDUPLANE":
            if self.executive.controller != Controller.ARDUPLANE:
                return self.status()
            self.segment_state = "DONE"
            self.state = "RUNNING"
        if self.index >= len(self.steps):
            self.executive.human_takeover("Observed rollout complete")
            if self.return_operation is not None:
                errors = self.return_operation.cancel()
                if errors:
                    self.stop_errors = list(errors)
                    self.state = "STOP_UNCONFIRMED"
                    return self.status()
            self.state = "COMPLETE"
            return self.status()
        phase, task = self.steps[self.index]
        if self.executive.phase != phase:
            self.executive.advance_phase(phase, self.executive.lease)
        try:
            result = self.executive.submit_task(self.executive.lease,
                                                self.executive.sequence + 1, task)
        except Exception:
            self.state = "FAULTED"
            return self.status()
        self.waiting_id = result["task_id"]
        self.state = "RUNNING"
        return self.status()

    def _abort_segment(self, reason):
        if self.return_operation is not None:
            self.return_operation.cancel()
        self.executive.human_takeover(reason)
        self.waiting_id = None
        self.state = "ABORTED_TO_HUMAN"

    def _enter_garmin(self):
        segment = self.garmin_segment
        observed = self.executive.adapters[Controller.ARDUPLANE].observed_status()
        if (observed.get("age_seconds", float("inf")) > 0.5
                or observed.get("agl_ft", float("-inf")) < segment.min_transfer_agl_ft):
            self._abort_segment("Planned Garmin transfer floor or telemetry not met")
            return
        try:
            self.executive.request_mode(Role.AI_MISSION, Phase.TRANSIT,
                                        Controller.GFC700, "cruise")
            self.executive.transfer_control(Controller.GFC700,
                                            self.executive.bridge.generation)
        except Exception as error:
            self._abort_segment("Planned Garmin transfer failed: %s" % error)
            return
        self.segment_state = "TO_GARMIN"
        self.state = "TRANSFERRING_GARMIN"

    def _return_to_arduplane(self):
        try:
            old_session = self.executive.bridge.session
            old_generation = self.executive.bridge_generation
            result = self.garmin_segment.prepare_return(self.executive)
            if hasattr(result, "poll") and hasattr(result, "cancel"):
                self.return_operation = result
                self.return_origin = (old_session, old_generation)
                self.segment_state = "PREPARING_RETURN"
                self.state = "PREPARING_RETURN"
                return
            self._commit_return(result, old_session, old_generation)
        except Exception as error:
            self._abort_segment("Planned ArduPlane return failed: %s" % error)

    def _commit_return(self, session, old_session, old_generation):
        try:
            if (not isinstance(session, str) or not session or session == old_session
                    or session != self.executive.bridge.session
                    or self.executive.bridge_generation <= old_generation):
                raise ValueError("Fresh candidate session was not confirmed")
            next_task = self.steps[self.index][1]
            adapter = self.executive.adapters[Controller.ARDUPLANE]
            if adapter.link is self.departure_link or not adapter.started:
                raise ValueError("Restarted ArduPlane mission has not been rejoined")
            observed = adapter.observed_status()
            progress = observed.get("mission") or {}
            next_seq = next_task.parameters["seq"]
            current_seq = progress.get("current_seq")
            reached_seq = progress.get("reached_seq")
            if (next_task.kind != TaskKind.WAYPOINT
                    or observed.get("mavlink_mode") != mav.PLANE_MODE_AUTO
                    or observed.get("telemetry_fresh") is not True
                    or observed.get("candidate_ready") is not True
                    or type(current_seq) is not int or current_seq > next_seq
                    or (reached_seq is not None and
                        (type(reached_seq) is not int or reached_seq >= next_seq))):
                raise ValueError("ArduPlane mission progressed beyond planned rejoin")
            self.executive.request_mode(Role.AI_MISSION, Phase.TRANSIT,
                                        Controller.ARDUPLANE, "cruise")
            self.executive.transfer_control(Controller.ARDUPLANE,
                                            self.executive.bridge.generation)
        except Exception as error:
            self._abort_segment("Planned ArduPlane return failed: %s" % error)
            return
        self.return_origin = None
        self.segment_state = "TO_ARDUPLANE"
        self.state = "TRANSFERRING_ARDUPLANE"

    def status(self):
        return {"state": self.state, "step": self.index, "total_steps": len(self.steps),
                "task_id": self.waiting_id, "garmin_segment": self.segment_state,
                "stop_errors": list(self.stop_errors),
                "executive": self.executive.status()}
