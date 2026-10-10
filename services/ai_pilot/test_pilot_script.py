"""Typed Test Pilot card with measured stabilization and recovery gates."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from .flight_executive import (
    Controller, FlightTask, Phase, Role, TaskKind, TransferState,
)


class TestCategory(str, Enum):
    AIRFRAME_PERFORMANCE = "AIRFRAME_PERFORMANCE"
    AIRFRAME_RESPONSE = "AIRFRAME_RESPONSE"
    CONTROLLER_TRACKING = "CONTROLLER_TRACKING"


@dataclass(frozen=True)
class TestPoint:
    axis: str
    magnitude: float
    duration_s: float
    ramp_s: float
    reference: str = "delta"

    def __post_init__(self):
        if self.axis not in ("pitch", "roll", "yaw") or self.reference not in ("absolute", "delta"):
            raise ValueError("Invalid test axis/reference")
        if not all(math.isfinite(x) for x in (self.magnitude, self.duration_s, self.ramp_s)):
            raise ValueError("Nonfinite test input")
        if abs(self.magnitude) > 0.25 or not 0 < self.duration_s <= 5 or self.ramp_s < 0:
            raise ValueError("Test input outside bounded H0 range")


@dataclass(frozen=True)
class TestReference:
    heading_mag: float
    altitude_indicated_ft: float
    kias: float
    max_kias_error: float
    max_altitude_error_ft: float
    max_abs_vvi_fpm: float
    max_abs_bank_deg: float
    settle_s: float

    def __post_init__(self):
        if any(not math.isfinite(x) for x in vars(self).values()):
            raise ValueError("Nonfinite test reference")
        if self.settle_s <= 0 or self.max_kias_error <= 0 or self.max_altitude_error_ft <= 0:
            raise ValueError("Invalid test stabilization thresholds")


class TestPilotScript:
    def __init__(self, executive, reference: TestReference, points: tuple[TestPoint, ...],
                 provenance: dict, *, recovery_timeout_s: float):
        required = {"aircraft_hash", "configuration_hash", "weight_kg", "cg_offset",
                    "weight_cg_evidence", "active_loops", "control_baseline",
                    "test_category"}
        if not required <= provenance.keys() or not points:
            raise ValueError("Test provenance and points required")
        if provenance["test_category"] not in {kind.value for kind in TestCategory}:
            raise ValueError("Explicit airframe/controller test category required")
        if not math.isfinite(recovery_timeout_s) or recovery_timeout_s <= 0:
            raise ValueError("Positive recovery timeout required")
        self.executive = executive
        self.provenance = dict(provenance)
        self.points = tuple(points)
        self.steps = [("establish", FlightTask(TaskKind.HEADING_ALTITUDE,
                       vars(reference), 120.0))]
        for index, point in enumerate(points):
            self.steps.append(("excite", FlightTask(TaskKind.TEST_INPUT,
                {**vars(point), "point_index": index, "active_loops": provenance["active_loops"]},
                point.duration_s + 2.0)))
            self.steps.append(("recover", FlightTask(TaskKind.TEST_RECOVER,
                vars(reference), recovery_timeout_s)))
        self.index = 0
        self.waiting_id = None
        self.state = "NEW"
        self.point_results = []
        self.samples = []

    def start(self):
        if self.state != "NEW":
            raise ValueError("Test card already started")
        self.executive.request_mode(Role.AI_TEST, Phase.TEST, Controller.DIRECT, "H0")
        self.executive.transfer_control(Controller.DIRECT, self.executive.bridge.generation)
        self.state = "TRANSFERRING"

    def tick(self):
        if self.state not in ("TRANSFERRING", "RUNNING"):
            return self.status()
        before_state = self.executive.test_state
        status = self.executive.tick()
        if status["transfer"] == TransferState.PAUSED_FAULT.value:
            self.state = "FAULTED"
            return self.status()
        if self.executive.latched_takeover:
            self.state = "CANCELED_TO_HUMAN"
            self.waiting_id = None
            return self.status()
        if status["transfer"] == TransferState.ACTIVE.value and self.executive.lease:
            observed = self.executive.adapters[Controller.DIRECT].observed_status()
            self.samples.append({"monotonic_time": self.executive.clock(),
                                 "test_state": before_state.value if before_state else status["test_state"],
                                 "point_index": max(0, (self.index - 1) // 2),
                                 "actual_deflection": observed.get("actual_deflection"),
                                 "commanded_deflection": observed.get("commanded_deflection"),
                                 "active_loops": self.provenance["active_loops"],
                                 "control_baseline": self.provenance["control_baseline"]})
        if self.waiting_id:
            outcome = next((e for e in reversed(status["events"])
                            if e.get("task_id") == self.waiting_id
                            and e["status"] in ("achieved", "timed_out", "canceled")), None)
            if outcome is None:
                return self.status()
            if outcome["status"] != "achieved":
                self.state = "INVALID"
                return self.status()
            kind, _task = self.steps[self.index]
            if kind == "recover":
                point_index = (self.index - 2) // 2
                evidence = [sample for sample in self.samples
                            if sample["point_index"] == point_index
                            and sample["test_state"] == "EXCITE"
                            and type(sample["actual_deflection"]) in (int, float)
                            and math.isfinite(sample["actual_deflection"])
                            and type(sample["commanded_deflection"]) in (int, float)
                            and math.isfinite(sample["commanded_deflection"])]
                if not evidence:
                    self.point_results.append({"point_index": point_index,
                                               "software_recovery": "achieved",
                                               "aircraft_acceptance": "INSUFFICIENT_DEFLECTION_EVIDENCE"})
                    self.state = "INVALID"
                    return self.status()
                self.point_results.append({"point_index": (self.index - 2) // 2,
                                           "software_recovery": "achieved",
                                           "aircraft_acceptance": "NOT_EVALUATED"})
            self.waiting_id = None
            self.index += 1
        if status["transfer"] != TransferState.ACTIVE.value:
            return self.status()
        if not self.executive.lease:
            self.state = "FAULTED"
            return self.status()
        if self.index >= len(self.steps):
            self.state = "COMPLETE"
            return self.status()
        _label, task = self.steps[self.index]
        try:
            result = self.executive.submit_task(self.executive.lease,
                                                self.executive.sequence + 1, task)
        except Exception:
            self.state = "FAULTED"
            return self.status()
        self.waiting_id = result["task_id"]
        self.state = "RUNNING"
        return self.status()

    def status(self):
        return {"state": self.state, "step": self.index, "total_steps": len(self.steps),
                "point_results": list(self.point_results), "samples": list(self.samples),
                "provenance": self.provenance,
                "executive": self.executive.status()}
