"""Test Pilot recovery and attribution checks against independent observations."""
from services.ai_pilot.flight_adapters import DirectTestAdapter
from services.ai_pilot.flight_executive import Controller, FlightExecutive, TaskKind
from services.ai_pilot.test_pilot_script import (
    TestPilotScript as CardScript, TestPoint as CardPoint, TestReference as CardReference,
)
from services.ai_pilot.tests.test_flight_executive import Sim, candidates, SESSION
from xplane.capvsar_flight_control_core import ControlBridge


class DirectBackend:
    def __init__(self):
        self.client = type("MockClient", (), {"mock": True})()
        self.test_input_active = False
        self.inputs = []
        self.targets = None
    def select(self, heading, altitude): self.targets = (heading, altitude)
    def apply_test_input(self, input):
        self.test_input_active = True
        self.inputs.append(input)
    def release(self): self.test_input_active = False


def setup_script():
    clock = [0.0]
    sim = Sim()
    bridge = ControlBridge(sim, SESSION, clock=lambda: clock[0])
    candidates(bridge)
    backend = DirectBackend()
    observed = {"telemetry_fresh": True, "candidate_ready": True,
                "kias": 100.0, "altitude_indicated_ft": 4500.0,
                "agl_ft": 1500.0, "age_seconds": 0.0,
                "vvi_fpm": 0.0, "roll_deg": 0.0,
                "commanded_deflection": 0.05, "actual_deflection": 0.04}
    adapter = DirectTestAdapter(backend, lambda: observed, clock=lambda: clock[0])
    executive = FlightExecutive(bridge, {Controller.DIRECT: adapter},
                                clock=lambda: clock[0])
    reference = CardReference(heading_mag=270, altitude_indicated_ft=4500,
        kias=100, max_kias_error=2, max_altitude_error_ft=60,
        max_abs_vvi_fpm=120, max_abs_bank_deg=2, settle_s=1)
    provenance = {"aircraft_hash": "abc", "configuration_hash": "def",
                  "weight_kg": 1200, "cg_offset": 0.1,
                  "weight_cg_evidence": "fixture load sheet",
                  "test_category": "AIRFRAME_RESPONSE",
                  "active_loops": "heading/altitude hold; tested axis open",
                  "control_baseline": {"roll": 0, "pitch": 0, "yaw": 0}}
    script = CardScript(executive, reference,
        (CardPoint("roll", 0.05, 1.0, 0.2, "delta"),), provenance,
        recovery_timeout_s=2.0)
    script.start()
    return clock, sim, bridge, backend, observed, executive, script


def test_test_point_requires_stable_reference_and_measured_recovery():
    clock, sim, bridge, backend, observed, executive, script = setup_script()
    script.tick()  # commit + establish
    assert backend.targets == (270, 4500)
    clock[0] = 1.1
    candidates(bridge)
    script.tick()  # begin stable interval
    clock[0] = 2.2
    candidates(bridge)
    script.tick()  # stable -> input
    assert backend.inputs and backend.inputs[0].reference == "delta"
    assert executive.status()["test_state"] == "EXCITE"
    clock[0] = 3.3
    backend.test_input_active = False
    candidates(bridge)
    script.tick()  # input ended -> recovery
    assert executive.status()["test_state"] == "RECOVER"
    clock[0] = 4.4
    candidates(bridge)
    script.tick()  # begin stable hold
    clock[0] = 5.5
    candidates(bridge)
    script.tick()  # recovered -> complete
    assert script.state == "COMPLETE"
    assert script.point_results[0]["aircraft_acceptance"] == "NOT_EVALUATED"
    assert script.samples and script.samples[-1]["active_loops"] == script.provenance["active_loops"]
    assert not sim.paused


def test_recovery_timeout_invalidates_card_and_stops_progression():
    clock, sim, bridge, backend, observed, executive, script = setup_script()
    script.tick()
    clock[0] = 1.1
    candidates(bridge)
    script.tick()
    clock[0] = 2.2
    candidates(bridge)
    script.tick()
    clock[0] = 3.3
    backend.test_input_active = False
    candidates(bridge)
    script.tick()
    observed["vvi_fpm"] = -500
    clock[0] = 5.4
    candidates(bridge)
    script.tick()
    assert script.state == "FAULTED"
    assert sim.paused and not script.point_results
    assert not any(e["status"] == "achieved" and e.get("task") == TaskKind.TEST_RECOVER.value
                   for e in executive.events)


def test_human_takeover_during_recovery_ends_card_without_reacquiring():
    clock, sim, bridge, backend, observed, executive, script = setup_script()
    script.tick()
    clock[0] = 1.1
    candidates(bridge)
    script.tick()
    clock[0] = 2.2
    candidates(bridge)
    script.tick()
    clock[0] = 3.3
    backend.test_input_active = False
    candidates(bridge)
    script.tick()
    assert executive.status()["test_state"] == "RECOVER"
    executive.human_takeover("pilot yoke")
    script.tick()
    assert script.state == "CANCELED_TO_HUMAN"
    assert not sim.override and not sim.ap
    assert not script.point_results


def test_missing_measured_deflection_invalidates_point_even_after_recovery():
    clock, sim, bridge, backend, observed, executive, script = setup_script()
    script.tick()
    clock[0] = 1.1
    candidates(bridge)
    script.tick()
    clock[0] = 2.2
    candidates(bridge)
    script.tick()
    observed.pop("actual_deflection")
    clock[0] = 3.3
    backend.test_input_active = False
    candidates(bridge)
    script.tick()
    clock[0] = 4.4
    candidates(bridge)
    script.tick()
    clock[0] = 5.5
    candidates(bridge)
    script.tick()
    assert script.state == "INVALID"
    assert script.point_results[0]["aircraft_acceptance"] == "INSUFFICIENT_DEFLECTION_EVIDENCE"
