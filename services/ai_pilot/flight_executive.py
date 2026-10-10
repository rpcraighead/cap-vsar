"""Deterministic authority, controller transfer, and typed flight task runner.

This is the offline integration boundary. The language model may propose tasks;
only typed tasks and observed state can advance a flight. Live capability is
held closed in control_ownership until the bridge and aircraft are qualified.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import time
from types import MappingProxyType
from uuid import uuid4

from .maneuvers import EntryStability


class Role(str, Enum):
    HUMAN = "HUMAN"
    AI_MISSION = "AI_MISSION"
    AI_TEST = "AI_TEST"


class Phase(str, Enum):
    GROUND = "GROUND"
    TAKEOFF = "TAKEOFF"
    CLIMB = "CLIMB"
    TRANSIT = "TRANSIT"
    SEARCH = "SEARCH"
    APPROACH = "APPROACH"
    LAND = "LAND"
    ROLLOUT = "ROLLOUT"
    TEST = "TEST"
    PAUSED_FAULT = "PAUSED_FAULT"


class Controller(str, Enum):
    HUMAN = "HUMAN"
    GFC700 = "GFC700"
    DIRECT = "DIRECT"
    ARDUPLANE = "ARDUPLANE"


class TransferState(str, Enum):
    ACTIVE = "ACTIVE"
    REQUESTED = "REQUESTED"
    PREPARING = "PREPARING"
    READY = "READY"
    COMMITTING = "COMMITTING"
    VERIFYING = "VERIFYING"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    PAUSED_FAULT = "PAUSED_FAULT"


class TestState(str, Enum):
    ESTABLISH = "ESTABLISH"
    STABILIZE = "STABILIZE"
    EXCITE = "EXCITE"
    MEASURE = "MEASURE"
    RECOVER = "RECOVER"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class TaskKind(str, Enum):
    UPLOAD_MISSION = "UPLOAD_MISSION"
    START_AUTO = "START_AUTO"
    HEADING_ALTITUDE = "HEADING_ALTITUDE"
    TAKEOFF = "TAKEOFF"
    WAYPOINT = "WAYPOINT"
    APPROACH = "APPROACH"
    LAND = "LAND"
    GO_AROUND = "GO_AROUND"
    TEST_INPUT = "TEST_INPUT"
    TEST_RECOVER = "TEST_RECOVER"
    CONFIGURE = "CONFIGURE"
    SET_POWER = "SET_POWER"
    SET_FLAPS = "SET_FLAPS"


MISSION_ARDU = frozenset((Phase.TAKEOFF, Phase.CLIMB, Phase.TRANSIT,
                          Phase.SEARCH, Phase.APPROACH, Phase.LAND, Phase.ROLLOUT))
MISSION_GFC = frozenset((Phase.TRANSIT, Phase.SEARCH, Phase.APPROACH))
DOMAINS = ("primary", "trim", "throttle", "configuration", "ground")


def domain_allocation(controller: Controller) -> dict:
    if controller == Controller.HUMAN:
        return {domain: "HUMAN" for domain in DOMAINS}
    if controller == Controller.ARDUPLANE:
        return {"primary": "ARDUPLANE", "trim": "BRIDGE_HOLD",
                "throttle": "ARDUPLANE", "configuration": "ARDUPLANE",
                "ground": "HUMAN"}
    if controller == Controller.GFC700:
        return {"primary": "GFC700", "trim": "GFC700",
                "throttle": "VIRTUAL_PILOT", "configuration": "VIRTUAL_PILOT",
                "ground": "HUMAN"}
    return {"primary": "DIRECT", "trim": "DIRECT", "throttle": "DIRECT",
            "configuration": "DIRECT", "ground": "HUMAN"}


@dataclass(frozen=True)
class FlightTask:
    kind: TaskKind
    parameters: dict
    timeout_s: float
    on_timeout: str = "fault_pause"

    def __post_init__(self):
        if not isinstance(self.kind, TaskKind) or not isinstance(self.parameters, dict):
            raise ValueError("Typed flight task required")
        allowed = {
            TaskKind.UPLOAD_MISSION: {"items"},
            TaskKind.START_AUTO: set(),
            TaskKind.HEADING_ALTITUDE: {"heading_mag", "altitude_indicated_ft",
                "kias", "max_kias_error", "max_altitude_error_ft", "max_abs_vvi_fpm",
                "max_abs_bank_deg", "settle_s"},
            TaskKind.TAKEOFF: {"min_agl_ft"},
            TaskKind.WAYPOINT: {"seq", "max_distance_m"},
            TaskKind.APPROACH: {"seq", "go_around_altitude_m_msl",
                "go_around_min_agl_ft", "go_around_timeout_s"},
            TaskKind.LAND: {"rollout", "max_groundspeed_kt", "max_agl_ft",
                "go_around_altitude_m_msl", "go_around_min_agl_ft", "go_around_timeout_s"},
            TaskKind.GO_AROUND: {"min_agl_ft", "altitude_m_msl"},
            TaskKind.TEST_INPUT: {"axis", "magnitude", "duration_s", "ramp_s",
                "reference", "point_index", "active_loops"},
            TaskKind.TEST_RECOVER: {"heading_mag", "altitude_indicated_ft",
                "kias", "max_kias_error", "max_altitude_error_ft", "max_abs_vvi_fpm",
                "max_abs_bank_deg", "settle_s"},
            TaskKind.CONFIGURE: {"flap_ratio"},
            TaskKind.SET_POWER: {"fraction"},
            TaskKind.SET_FLAPS: {"fraction"},
        }
        required = {
            TaskKind.UPLOAD_MISSION: {"items"},
            TaskKind.HEADING_ALTITUDE: {"heading_mag", "altitude_indicated_ft"},
            TaskKind.TAKEOFF: {"min_agl_ft"},
            TaskKind.WAYPOINT: {"seq", "max_distance_m"},
            TaskKind.APPROACH: {"seq"},
            TaskKind.GO_AROUND: {"min_agl_ft", "altitude_m_msl"},
            TaskKind.TEST_INPUT: {"axis", "magnitude", "duration_s", "ramp_s", "reference"},
            TaskKind.TEST_RECOVER: {"kias", "altitude_indicated_ft", "settle_s"},
            TaskKind.CONFIGURE: {"flap_ratio"},
            TaskKind.SET_POWER: {"fraction"},
            TaskKind.SET_FLAPS: {"fraction"},
        }.get(self.kind, set())
        if set(self.parameters) - allowed[self.kind] or not required <= set(self.parameters):
            raise ValueError("Unknown or missing typed task parameters")
        if self.kind == TaskKind.LAND:
            key = "max_groundspeed_kt" if self.parameters.get("rollout") is True else "max_agl_ft"
            if key not in self.parameters:
                raise ValueError("Landing task lacks measured completion threshold")
        for key, value in self.parameters.items():
            if key not in ("items", "axis", "reference", "active_loops", "rollout"):
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("Nonfinite or nonnumeric task parameter: %s" % key)
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        if not math.isfinite(self.timeout_s) or self.timeout_s <= 0:
            raise ValueError("Positive finite task timeout required")
        if self.on_timeout not in ("fault_pause", "go_around", "human"):
            raise ValueError("Unsupported timeout action")
        if self.on_timeout == "go_around":
            for key in ("go_around_altitude_m_msl", "go_around_min_agl_ft"):
                value = self.parameters.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError("Go-around requires positive %s" % key)


class FlightExecutive:
    """One authority ledger above adapters and the simulator-side bridge."""

    def __init__(self, bridge, adapters: dict, *, power=None, phase_profiles=None,
                 entry_stability: EntryStability = EntryStability(),
                 clock=time.monotonic):
        self.bridge, self.adapters, self.power, self.clock = bridge, adapters, power, clock
        if phase_profiles is None:
            from .phase_profiles import PhaseProfiles
            phase_profiles = PhaseProfiles()
        self.phase_profiles = phase_profiles
        self.entry_stability = entry_stability
        self.role = Role.HUMAN
        self.phase = Phase.GROUND
        self.controller = Controller.HUMAN
        self.profile = "manual"
        self.transfer = TransferState.ACTIVE
        self.requested = None
        self.lease = None
        self.bridge_generation = None
        self.sequence = 0
        self.active_task = None
        self.active_task_actor = None
        self.task_started = None
        self.events = []
        self.latched_takeover = False
        self.test_state = None
        self.last_achieved_phase = None

    def _event(self, status, **fields):
        entry = {"event_id": uuid4().hex, "status": status,
                 "monotonic_time": self.clock(), "wall_time": time.time(),
                 "sequence": self.sequence, **fields}
        self.events.append(entry)
        return entry

    @staticmethod
    def _valid(role, phase, controller):
        if role == Role.HUMAN:
            return controller == Controller.HUMAN
        if role == Role.AI_MISSION:
            return ((controller == Controller.ARDUPLANE and phase in MISSION_ARDU)
                    or (controller == Controller.GFC700 and phase in MISSION_GFC))
        return role == Role.AI_TEST and phase == Phase.TEST and controller in (
            Controller.DIRECT, Controller.GFC700, Controller.ARDUPLANE)

    def request_mode(self, role: Role, phase: Phase, controller: Controller, profile: str):
        if not all((isinstance(role, Role), isinstance(phase, Phase),
                    isinstance(controller, Controller), isinstance(profile, str))):
            raise ValueError("Typed mode request required")
        if not self._valid(role, phase, controller):
            raise ValueError("Unsupported role/phase/controller combination")
        if self.phase_profiles is not None:
            self.phase_profiles.require_phase(phase)
        if self.transfer != TransferState.ACTIVE or self.active_task:
            raise ValueError("Complete or cancel current transfer/task first")
        if controller == Controller.HUMAN:
            return self.human_takeover("explicit manual mode")
        if self.lease and controller != self.controller:
            observed = self.adapters[self.controller].observed_status()
            numbers = tuple(observed.get(key) for key in ("vvi_fpm", "roll_deg", "age_seconds"))
            if (any(type(value) not in (int, float) or not math.isfinite(value)
                    for value in numbers)
                    or not 0 <= numbers[2] <= 2.0
                    or abs(numbers[0]) > self.entry_stability.max_abs_vvi_fpm
                    or abs(numbers[1]) > self.entry_stability.max_abs_bank_deg):
                raise ValueError("Aircraft not stable for ordinary controller transfer")
        if controller == Controller.GFC700 and role == Role.AI_MISSION:
            if self.power is None or not self.power.ready_for(phase):
                raise ValueError("Virtual pilot power/configuration not qualified")
        adapter = self.adapters[controller]
        adapter.prepare(phase, profile)
        self.requested = (role, phase, controller, profile)
        self.transfer = TransferState.PREPARING
        return self._event("preparing", controller=controller.value, phase=phase.value)

    def transfer_control(self, destination: Controller, expected_generation: int):
        if self.transfer != TransferState.PREPARING or self.requested is None:
            raise ValueError("No prepared transfer")
        role, phase, controller, profile = self.requested
        if (destination != controller or expected_generation != self.bridge.generation
                or (self.lease and expected_generation != self.bridge_generation)):
            raise ValueError("Destination or bridge generation changed")
        adapter = self.adapters[controller]
        if not adapter.ready():
            raise ValueError("Destination controller has no observed readiness")
        self.transfer = TransferState.READY
        self._event("transfer_ready", controller=controller.value)
        self.transfer = TransferState.COMMITTING
        try:
            if controller in (Controller.ARDUPLANE, Controller.DIRECT):
                self.bridge.prepare(controller.value, self.bridge.session, expected_generation)
                self.bridge.activate(self.bridge.session, self.bridge.generation)
            else:
                self.bridge.transfer_gfc(expected_generation, ready=True)
        except Exception as error:
            self.fault_pause("Control transfer failed: %s" % error)
            raise
        self.transfer = TransferState.VERIFYING
        self.bridge_generation = self.bridge.generation
        return self._event("committing", controller=controller.value,
                           generation=self.bridge.generation)

    def renew_candidate_session(self, session: str, expected_generation: int):
        """Fence a retired ArduPlane writer before a planned Garmin return."""
        if (self.controller != Controller.GFC700 or self.role != Role.AI_MISSION
                or self.transfer != TransferState.ACTIVE or not self.lease
                or self.active_task or expected_generation != self.bridge_generation):
            raise ValueError("Fresh candidate session requires idle AI Mission Garmin authority")
        result = self.bridge.renew_session(session, expected_generation)
        self.bridge_generation = result["generation"]
        self._event("candidate_session_renewed", session=session,
                    generation=self.bridge_generation)
        return result

    def _complete_transfer(self):
        role, phase, controller, profile = self.requested
        self.adapters[controller].activate()
        self.role, self.phase, self.controller, self.profile = role, phase, controller, profile
        self.transfer = TransferState.ACTIVE
        self.requested = None
        self.lease = uuid4().hex
        self.bridge_generation = self.bridge.generation
        self.sequence = 0
        self.latched_takeover = False
        self.test_state = TestState.ESTABLISH if role == Role.AI_TEST else None
        self.last_achieved_phase = None
        return self._event("control_active", controller=controller.value,
                           phase=phase.value, lease=self.lease)

    def _validate_task(self, task: FlightTask):
        if not isinstance(task, FlightTask):
            raise ValueError("Typed flight task required")
        allowed = {
            Phase.TAKEOFF: {TaskKind.UPLOAD_MISSION, TaskKind.START_AUTO, TaskKind.TAKEOFF},
            Phase.CLIMB: {TaskKind.WAYPOINT},
            Phase.TRANSIT: {TaskKind.HEADING_ALTITUDE, TaskKind.WAYPOINT},
            Phase.SEARCH: {TaskKind.HEADING_ALTITUDE, TaskKind.WAYPOINT},
            Phase.APPROACH: {TaskKind.APPROACH, TaskKind.GO_AROUND},
            Phase.LAND: {TaskKind.LAND, TaskKind.GO_AROUND},
            Phase.ROLLOUT: {TaskKind.LAND},
            Phase.TEST: {TaskKind.HEADING_ALTITUDE, TaskKind.TEST_INPUT,
                         TaskKind.TEST_RECOVER, TaskKind.CONFIGURE},
        }
        if task.kind not in allowed.get(self.phase, set()):
            if not (task.kind in (TaskKind.SET_POWER, TaskKind.SET_FLAPS)
                    and self.phase in (Phase.TRANSIT, Phase.SEARCH, Phase.APPROACH)):
                raise ValueError("Task is not permitted in this flight phase")
        if task.kind in (TaskKind.SET_POWER, TaskKind.SET_FLAPS):
            if (self.controller != Controller.GFC700 or self.power is None
                    or not self.power.ready_for(self.phase)):
                raise ValueError("Virtual-pilot action requires qualified Garmin ownership")
        if self.controller == Controller.GFC700 and task.kind in (
                TaskKind.UPLOAD_MISSION, TaskKind.START_AUTO, TaskKind.TAKEOFF,
                TaskKind.LAND, TaskKind.GO_AROUND):
            raise ValueError("Garmin adapter cannot execute ArduPlane mission command")
        if self.phase_profiles is not None and task.kind == TaskKind.HEADING_ALTITUDE:
            self.phase_profiles.validate_target(self.phase,
                                                task.parameters.get("altitude_indicated_ft", float("nan")))

    def advance_phase(self, phase: Phase, expected_lease: str):
        """Change task phase under the same controller after an observed gate.

        A script supplies no new actuator authority here. Controller changes
        must use the explicit transfer transaction.
        """
        if not isinstance(phase, Phase):
            raise ValueError("Typed phase required")
        if expected_lease != self.lease or self.active_task or self.transfer != TransferState.ACTIVE:
            raise ValueError("Phase change requires idle active authority")
        if not self._valid(self.role, phase, self.controller):
            raise ValueError("Controller is not valid in requested phase")
        if self.phase_profiles is not None:
            self.phase_profiles.require_phase(phase)
        if self.last_achieved_phase != self.phase:
            raise ValueError("Measured task achievement for current phase absent")
        self.phase = phase
        self.last_achieved_phase = None
        return self._event("phase_changed", phase=phase.value)

    def submit_task(self, lease: str, sequence: int, task: FlightTask):
        if self.transfer != TransferState.ACTIVE or self.latched_takeover:
            raise ValueError("No active automated authority")
        if lease != self.lease or not self.lease or type(sequence) is not int or sequence != self.sequence + 1:
            raise ValueError("Revoked lease or repeated/out-of-order sequence")
        if self.active_task:
            raise ValueError("Current task requires explicit cancel or completion")
        self._validate_task(task)
        self.sequence = sequence  # consumed even if adapter partially fails
        task_id = uuid4().hex
        try:
            if task.kind == TaskKind.SET_POWER:
                self.power.set_power(task.parameters["fraction"], owner="VIRTUAL_PILOT")
                actor = "power"
            elif task.kind == TaskKind.SET_FLAPS:
                self.power.set_flaps(task.parameters["fraction"], owner="VIRTUAL_PILOT")
                actor = "power"
            else:
                self.adapters[self.controller].execute(task)
                actor = "controller"
        except Exception as error:
            self.fault_pause("Controller task start failed: %s" % error)
            raise
        self.active_task = (task_id, task)
        self.active_task_actor = actor
        self.task_started = self.clock()
        if task.kind == TaskKind.TEST_INPUT:
            self.test_state = TestState.EXCITE
        elif task.kind == TaskKind.TEST_RECOVER:
            self.test_state = TestState.RECOVER
        elif task.kind == TaskKind.HEADING_ALTITUDE and self.role == Role.AI_TEST:
            self.test_state = TestState.STABILIZE
        return self._event("executing", task_id=task_id, task=task.kind.value)

    def cancel_task(self, lease: str, sequence: int, behavior: str):
        if lease != self.lease or sequence != self.sequence + 1 or not self.active_task:
            raise ValueError("No current task under that lease/sequence")
        if behavior not in ("hold", "go_around", "human"):
            raise ValueError("Explicit hold, go-around, or human abort required")
        task_id, task = self.active_task
        self.sequence = sequence
        try:
            if self.active_task_actor == "power":
                if behavior != "human":
                    raise ValueError("Virtual-pilot action has no qualified automatic hold")
            else:
                self.adapters[self.controller].abort(task, behavior)
        except Exception as error:
            self.fault_pause("Task abort failed: %s" % error)
            raise
        self.active_task = None
        self.active_task_actor = None
        self._event("canceled", task_id=task_id, behavior=behavior)
        if behavior == "human":
            self.human_takeover("task canceled to human")
        return self.status()

    def tick(self):
        if self.transfer == TransferState.VERIFYING or self.lease:
            try:
                self.bridge.heartbeat(self.bridge.session, self.bridge_generation)
            except ValueError:
                bridge_state = self.bridge.status()
                if (bridge_state.get("state") in ("MANUAL", "WAIT_HUMAN")
                        and bridge_state.get("owner") == "HUMAN"):
                    self.active_task = None
                    self.active_task_actor = None
                    self.lease = None
                    self.bridge_generation = None
                    self.requested = None
                    self.role, self.controller = Role.HUMAN, Controller.HUMAN
                    self.transfer = TransferState.ACTIVE
                    self.latched_takeover = True
                    self._event("human_takeover", reason="independent bridge takeover")
                    return self.status()
                self.fault_pause("Executive heartbeat rejected by bridge")
                return self.status()
        bridge = self.bridge.tick()
        if bridge["state"] in ("PAUSED_FAULT", "FAULT_PAUSE_PENDING"):
            self.fault_pause(bridge["fault"] or "Bridge fault")
            return self.status()
        if self.transfer == TransferState.VERIFYING:
            requested_controller = self.requested[2]
            expected = "GFC700" if requested_controller == Controller.GFC700 else "ACTIVE"
            if bridge["state"] == expected:
                try:
                    self._complete_transfer()
                except Exception as error:
                    self.fault_pause("Controller activation failed: %s" % error)
                    return self.status()
        if self.transfer == TransferState.ACTIVE and self.lease and self.phase_profiles is not None:
            try:
                observation = self.adapters[self.controller].observed_status()
                self.phase_profiles.validate_observation(self.phase, observation)
            except Exception as error:
                self.fault_pause("Phase envelope fault: %s" % error)
                return self.status()
        if self.active_task:
            task_id, task = self.active_task
            try:
                if self.active_task_actor == "power":
                    observed = self.power.readback()
                    achieved = self.power.achieved(task, observed)
                else:
                    observed = self.adapters[self.controller].observed_status()
                    achieved = self.adapters[self.controller].achieved(task, observed)
            except Exception as error:
                self.fault_pause("Controller observation failed: %s" % error)
                return self.status()
            if achieved:
                self.active_task = None
                self.active_task_actor = None
                self.last_achieved_phase = self.phase
                self._event("achieved", task_id=task_id, task=task.kind.value,
                            observed=observed)
                if task.kind == TaskKind.TEST_RECOVER:
                    self.test_state = TestState.ACCEPT
                elif task.kind == TaskKind.TEST_INPUT:
                    self.test_state = TestState.MEASURE
            elif self.clock() - self.task_started >= task.timeout_s:
                self.active_task = None
                self.active_task_actor = None
                self._event("timed_out", task_id=task_id, task=task.kind.value)
                if task.on_timeout == "go_around" and self.phase in (Phase.APPROACH, Phase.LAND):
                    try:
                        self.adapters[self.controller].abort(task, "go_around")
                    except Exception as error:
                        self.fault_pause("Go-around command failed: %s" % error)
                    else:
                        self.active_task = (uuid4().hex, FlightTask(
                            TaskKind.GO_AROUND,
                            {"min_agl_ft": task.parameters["go_around_min_agl_ft"],
                             "altitude_m_msl": task.parameters["go_around_altitude_m_msl"]},
                            task.parameters.get("go_around_timeout_s", 30.0)))
                        self.active_task_actor = "controller"
                        self.task_started = self.clock()
                        self._event("go_around_pending", task_id=self.active_task[0])
                elif task.on_timeout == "human":
                    self.human_takeover("Task timed out: %s" % task.kind.value)
                else:
                    self.fault_pause("Task timed out: %s" % task.kind.value)
        return self.status()

    def human_takeover(self, reason: str):
        if self.active_task:
            self._event("canceled", task_id=self.active_task[0], reason=reason)
        self.active_task = None
        self.active_task_actor = None
        self.lease = None
        self.bridge_generation = None
        self.requested = None
        self.bridge.human_takeover(reason)
        self.role, self.controller = Role.HUMAN, Controller.HUMAN
        self.transfer = TransferState.ACTIVE
        self.latched_takeover = True
        return self._event("human_takeover", reason=reason)

    def fault_pause(self, reason: str):
        if self.transfer == TransferState.PAUSED_FAULT:
            return self.status()
        self.bridge.fault_pause(reason)
        self.lease = None
        self.bridge_generation = None
        self.requested = None
        self.active_task = None
        self.active_task_actor = None
        self.phase = Phase.PAUSED_FAULT
        self.transfer = TransferState.PAUSED_FAULT
        self._event("fault", reason=reason)
        return self.status()

    def status(self):
        return {"role": self.role.value, "phase": self.phase.value,
                "controller": self.controller.value, "profile": self.profile,
                "transfer": self.transfer.value, "bridge": self.bridge.status(),
                "lease": self.lease, "sequence": self.sequence,
                "bridge_generation": self.bridge_generation,
                "task": self.active_task[1].kind.value if self.active_task else None,
                "test_state": self.test_state.value if self.test_state else None,
                "allocation": domain_allocation(self.controller),
                "events": list(self.events)}
