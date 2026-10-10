"""Observable controller adapters for the deterministic flight executive.

The ArduPlane mission adapter accepts an injected telemetry feed. Its real
readiness remains closed until effective parameters, estimator, and candidate
outputs have been qualified on the installed rig.
"""
from __future__ import annotations

import math
import time

from . import mavlink_min as mav
from .arduplane_mission import MissionUploader
from .flight_executive import TaskKind, Phase
from .direct_backend import TestInput


class ArduPlaneMissionAdapter:
    def __init__(self, backend, link, telemetry, *, offline_protocol=False):
        self.backend, self.link, self.telemetry = backend, link, telemetry
        self.uploader = MissionUploader(link)
        # A production link cannot be made ready with a constructor switch.
        self.offline_protocol = offline_protocol and isinstance(link, mav.MockLink)
        self.prepared = False
        self.started = False

    def prepare(self, phase, profile):
        if phase not in (Phase.TAKEOFF, Phase.CLIMB, Phase.TRANSIT, Phase.SEARCH,
                         Phase.APPROACH, Phase.LAND, Phase.ROLLOUT, Phase.TEST):
            raise ValueError("ArduPlane unsupported in this phase")
        self.prepared = True

    def ready(self):
        if not self.prepared or not self.offline_protocol:
            return False
        observed = self.observed_status()
        return (self.link.heartbeat_age() <= 2.0
                and observed.get("telemetry_fresh") is True
                and observed.get("candidate_ready") is True)

    def activate(self):
        if not self.ready():
            raise ValueError("ArduPlane readiness lost at commit")

    def resume_on_new_link(self, link, items, seq):
        """Offline protocol rejoin; live restart/readiness is still disabled."""
        uploader = self.prepare_return_link(link, items, seq)
        self.adopt_return_link(link, uploader)

    def prepare_return_link(self, link, items, seq):
        if (not self.offline_protocol or not isinstance(link, mav.MockLink)
                or link is self.link):
            raise ValueError("Fresh offline ArduPlane link required for rejoin")
        uploader = MissionUploader(link)
        uploader.resume_at(tuple(items), seq)
        return uploader

    def adopt_return_link(self, link, uploader):
        if (not self.offline_protocol or not isinstance(link, mav.MockLink)
                or link is self.link or uploader.link is not link
                or not uploader.uploaded or link.custom_mode() != mav.PLANE_MODE_AUTO):
            raise ValueError("Prepared ArduPlane return link not verified")
        self.link, self.uploader = link, uploader
        self.started = True

    def execute(self, task):
        kind, params = task.kind, task.parameters
        if kind == TaskKind.UPLOAD_MISSION:
            self.uploader.upload(tuple(params["items"]))
        elif kind == TaskKind.START_AUTO:
            self.uploader.start_auto()
            self.started = True
        elif kind == TaskKind.HEADING_ALTITUDE:
            self.backend.select(params["heading_mag"], params["altitude_indicated_ft"])
        elif kind == TaskKind.GO_AROUND:
            self.uploader.go_around(params["altitude_m_msl"])
        elif kind in (TaskKind.TAKEOFF, TaskKind.WAYPOINT, TaskKind.APPROACH, TaskKind.LAND):
            if not self.started or self.link.custom_mode() != mav.PLANE_MODE_AUTO:
                raise ValueError("Mission phase requires observed AUTO mode")
        else:
            raise ValueError("ArduPlane task unsupported")

    def observed_status(self):
        observed = dict(self.telemetry())
        observed["mavlink_mode"] = self.link.custom_mode()
        observed["heartbeat_age_s"] = self.link.heartbeat_age()
        try:
            observed["mission"] = self.uploader.progress()
        except ValueError:
            observed["mission"] = None
        return observed

    def achieved(self, task, observed):
        kind, p = task.kind, task.parameters
        if kind == TaskKind.UPLOAD_MISSION:
            return self.uploader.uploaded
        if kind == TaskKind.START_AUTO:
            return observed.get("mavlink_mode") == mav.PLANE_MODE_AUTO
        if kind == TaskKind.TAKEOFF:
            return observed.get("on_ground") is False and observed.get("agl_ft", -1) >= p["min_agl_ft"]
        if kind == TaskKind.WAYPOINT:
            mission = observed.get("mission") or {}
            return (mission.get("reached_seq") == p["seq"]
                    and observed.get("within_fix_m", float("inf")) <= p["max_distance_m"])
        if kind == TaskKind.APPROACH:
            mission = observed.get("mission") or {}
            return (mission.get("current_seq", -1) >= p["seq"]
                    and observed.get("approach_stable") is True)
        if kind == TaskKind.LAND:
            if p.get("rollout", False):
                return (observed.get("on_ground") is True
                        and observed.get("groundspeed_kt", float("inf")) <= p["max_groundspeed_kt"]
                        and observed.get("ground_stop_confirmed") is True)
            return observed.get("on_ground") is True and observed.get("agl_ft", float("inf")) <= p["max_agl_ft"]
        if kind == TaskKind.GO_AROUND:
            return (observed.get("on_ground") is False
                    and observed.get("agl_ft", -1) >= p["min_agl_ft"]
                    and observed.get("vvi_fpm", -float("inf")) > 0)
        if kind == TaskKind.HEADING_ALTITUDE:
            heading_error = abs((observed["heading_mag"] - p["heading_mag"] + 180) % 360 - 180)
            return (heading_error <= 3 and abs(observed["altitude_indicated_ft"] - p["altitude_indicated_ft"]) <= 100
                    and abs(observed["vvi_fpm"]) <= 150)
        return False

    def abort(self, task, behavior):
        if behavior == "go_around":
            self.uploader.go_around(task.parameters["go_around_altitude_m_msl"])
        elif behavior == "hold":
            raise ValueError("ArduPlane hold requires an explicit qualified route/mode")
        elif behavior != "human":
            raise ValueError("Unsupported ArduPlane abort")


class GFC700Adapter:
    def __init__(self, backend, readback, *, clock=time.monotonic):
        self.backend, self.readback, self.clock = backend, readback, clock
        self.prepared = False
        self.current_task = None
        self.settled_since = None

    def prepare(self, phase, profile):
        if phase not in (Phase.TRANSIT, Phase.SEARCH, Phase.APPROACH, Phase.TEST):
            raise ValueError("Garmin unsupported in this phase")
        self.prepared = True

    def ready(self):
        state = self.readback()
        return (self.prepared and state.get("age_seconds", float("inf")) <= 0.5
                and state.get("servos_on") in (0, 1)
                and state.get("flight_director_mode") in (0, 1, 2)
                and state.get("lateral_selected") is True
                and state.get("vertical_selected") is True)

    def activate(self):
        state = self.readback()
        if (state.get("age_seconds", float("inf")) > 0.5
                or state.get("servos_on") != 1 or state.get("flight_director_mode") != 2
                or state.get("lateral_active") is not True
                or state.get("vertical_active") is not True):
            raise ValueError("Garmin active mode/FD/servo readback did not confirm AP engagement")

    def execute(self, task):
        if task.kind != TaskKind.HEADING_ALTITUDE:
            raise ValueError("Garmin task unsupported")
        p = task.parameters
        self.backend.select(p["heading_mag"], p["altitude_indicated_ft"])
        self.current_task = task
        self.settled_since = None

    def observed_status(self):
        o = self.backend.observe()
        return {"heading_mag": o.heading_mag, "altitude_indicated_ft": o.altitude_indicated_ft,
                "agl_ft": o.agl_ft, "kias": o.kias,
                "roll_deg": o.roll_deg, "vvi_fpm": o.vvi_fpm,
                "age_seconds": o.age_seconds, "garmin": self.readback()}

    def achieved(self, task, observed):
        if task != self.current_task or observed["age_seconds"] > 2.0:
            return False
        p = task.parameters
        heading_error = abs((observed["heading_mag"] - p["heading_mag"] + 180) % 360 - 180)
        captured = (heading_error <= 3 and abs(observed["altitude_indicated_ft"] - p["altitude_indicated_ft"]) <= 100
                    and abs(observed["roll_deg"]) <= 5 and abs(observed["vvi_fpm"]) <= 150
                    and observed["garmin"].get("servos_on") == 1
                    and observed["garmin"].get("flight_director_mode") == 2
                    and observed["garmin"].get("lateral_active") is True
                    and observed["garmin"].get("vertical_active") is True)
        if not captured:
            self.settled_since = None
            return False
        if self.settled_since is None:
            self.settled_since = self.clock()
            return False
        return self.clock() - self.settled_since >= 3.0

    def abort(self, task, behavior):
        if behavior != "human":
            raise ValueError("Garmin hold/abort procedure not qualified")


class VirtualPilotPower:
    """Typed power/configuration API; disabled until aircraft readbacks qualify."""
    def __init__(self, bridge, readback, *, qualified=False):
        self.bridge, self.readback, self.qualified = bridge, readback, qualified

    def ready_for(self, phase):
        return self.qualified and phase in (Phase.TRANSIT, Phase.SEARCH, Phase.APPROACH)

    def set_power(self, fraction, *, owner):
        if not self.qualified or owner != "VIRTUAL_PILOT":
            raise ValueError("Virtual pilot does not own qualified throttle")
        if type(fraction) not in (int, float) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
            raise ValueError("Power fraction outside 0–1")
        self.bridge.set_virtual_aux("throttle", fraction, self.bridge.session,
                                    self.bridge.generation)
        observed = self.readback()
        if observed.get("age_seconds", float("inf")) > 0.5 or abs(observed.get("throttle", -10) - fraction) > 0.05:
            raise ValueError("Power change not observed")
        return observed

    def set_flaps(self, fraction, *, owner):
        if not self.qualified or owner != "VIRTUAL_PILOT":
            raise ValueError("Virtual pilot does not own qualified configuration")
        if type(fraction) not in (int, float) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
            raise ValueError("Flap fraction outside 0–1")
        self.bridge.set_virtual_aux("flap", fraction, self.bridge.session,
                                    self.bridge.generation)
        observed = self.readback()
        if observed.get("age_seconds", float("inf")) > 0.5 or abs(observed.get("flap_ratio", -10) - fraction) > 0.03:
            raise ValueError("Configuration change not observed")
        return observed

    def achieved(self, task, observed):
        if observed.get("age_seconds", float("inf")) > 0.5:
            return False
        fraction = task.parameters["fraction"]
        if task.kind == TaskKind.SET_POWER:
            return abs(observed.get("throttle", -10) - fraction) <= 0.05
        if task.kind == TaskKind.SET_FLAPS:
            return abs(observed.get("flap_ratio", -10) - fraction) <= 0.03
        return False


class DirectTestAdapter:
    """Typed H0 task surface; only fake-client workflows can report ready yet."""
    def __init__(self, backend, telemetry, *, clock=time.monotonic):
        self.backend, self.telemetry, self.clock = backend, telemetry, clock
        self.prepared = False
        self.current = None
        self.settled_since = None
        self.task_started = None

    def prepare(self, phase, profile):
        if phase != Phase.TEST:
            raise ValueError("Direct test adapter requires TEST phase")
        self.prepared = True

    def ready(self):
        observed = self.observed_status()
        return (self.prepared and getattr(self.backend.client, "mock", False) is True
                and observed.get("telemetry_fresh") is True
                and observed.get("candidate_ready") is True)

    def activate(self):
        if not self.ready():
            raise ValueError("Direct test readiness lost")

    def execute(self, task):
        p = task.parameters
        if task.kind == TaskKind.HEADING_ALTITUDE:
            self.backend.select(p["heading_mag"], p["altitude_indicated_ft"])
        elif task.kind == TaskKind.TEST_INPUT:
            self.backend.apply_test_input(TestInput(
                p["axis"], p["magnitude"], p["duration_s"],
                ramp_s=p["ramp_s"], reference=p["reference"]))
        elif task.kind == TaskKind.TEST_RECOVER:
            pass
        elif task.kind == TaskKind.CONFIGURE:
            self.backend.set_flaps(p["flap_ratio"])
        else:
            raise ValueError("Direct test task unsupported")
        self.current = task
        self.settled_since = None
        self.task_started = self.clock()

    def observed_status(self):
        observed = dict(self.telemetry())
        command = getattr(self.backend, "last_commands", {})
        if "commanded_deflection" not in observed:
            observed["commanded_deflection"] = command.get("test_input_shaped")
        return observed

    def _reference_stable(self, p, o):
        if not o.get("telemetry_fresh"):
            return False
        return (abs(o["kias"] - p["kias"]) <= p["max_kias_error"]
                and abs(o["altitude_indicated_ft"] - p["altitude_indicated_ft"]) <= p["max_altitude_error_ft"]
                and abs(o["vvi_fpm"]) <= p["max_abs_vvi_fpm"]
                and abs(o["roll_deg"]) <= p["max_abs_bank_deg"])

    def achieved(self, task, observed):
        if task != self.current:
            return False
        p = task.parameters
        if task.kind in (TaskKind.HEADING_ALTITUDE, TaskKind.TEST_RECOVER):
            if not self._reference_stable(p, observed):
                self.settled_since = None
                return False
            if self.settled_since is None:
                self.settled_since = self.clock()
                return False
            return self.clock() - self.settled_since >= p["settle_s"]
        if task.kind == TaskKind.TEST_INPUT:
            return (not self.backend.test_input_active
                    and self.clock() - self.task_started >= p["duration_s"])
        if task.kind == TaskKind.CONFIGURE:
            return abs(observed.get("flap_ratio", -10) - p["flap_ratio"]) <= 0.03
        return False

    def abort(self, task, behavior):
        if behavior == "human":
            self.backend.release()
            return
        raise ValueError("Test point has no qualified hold/automatic abort")
