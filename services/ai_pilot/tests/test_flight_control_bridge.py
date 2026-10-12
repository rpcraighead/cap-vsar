"""Stateful offline checks of the simulator-side output boundary."""
import json
from pathlib import Path

import pytest

from xplane.capvsar_flight_control_core import CHANNELS, ControlBridge
from xplane.capvsar_flight_control_mapping import generate_mapping, stage_bundle, validate_mapping

SESSION = "a" * 32
OTHER = "b" * 32


class Simulator:
    def __init__(self):
        self.ap = False
        self.override = False
        self.controls = {}
        self.writes = []
        self.paused = False
        self.off_requests = 0
        self.on_requests = 0

    def ap_engaged(self): return self.ap
    def read_trim(self): return 0.05
    def override_state(self): return self.override
    def command_ap_off(self): self.off_requests += 1
    def command_ap_on(self): self.on_requests += 1
    def set_override(self, value): self.override = value
    def write_control(self, channel, value):
        self.controls[channel] = value
        self.writes.append((channel, value))
    def read_control(self, channel): return self.controls.get(channel)
    def pause(self): self.paused = True
    def is_paused(self): return self.paused


def ready(b):
    for channel in CHANNELS:
        b.candidate(SESSION, channel, 0.3 if channel in ("throttle", "flap") else 0.0)


def test_stock_mapping_becomes_private_candidates_only():
    stock = json.loads((Path(__file__).parents[3] / "xplane/ardupilot/xplane_plane_cap487.json").read_text())
    result = generate_mapping(stock, SESSION)
    assert all(not key.startswith("sim/") for key in result)
    assert len([k for k in result if k.startswith("cap/flight_control/candidate/")]) == 5
    result["sim/joystick/yoke_roll_ratio"] = {"type": "fixed", "value": 1}
    with pytest.raises(ValueError, match="Unmediated"):
        validate_mapping(result, SESSION)


def test_staging_bundle_uses_unique_private_session_and_refuses_overwrite(tmp_path):
    stock = Path(__file__).parents[3] / "xplane/ardupilot/xplane_plane_cap487.json"
    result = stage_bundle(stock, tmp_path, SESSION)
    mapping = json.loads(Path(result["mapping"]).read_text())
    config = json.loads(Path(result["plugin_config"]).read_text())
    validate_mapping(mapping, SESSION)
    assert config["session"] == SESSION
    assert len(config["secret"]) >= 32
    assert Path(result["plugin_config"]).stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        stage_bundle(stock, tmp_path, OTHER)


def test_standby_never_writes_native_controls_and_partial_set_cannot_activate():
    sim = Simulator()
    b = ControlBridge(sim, SESSION, clock=lambda: 0.0)
    b.candidate(SESSION, "roll", 0.2)
    with pytest.raises(ValueError, match="Incomplete"):
        b.prepare("ARDUPLANE", SESSION, 0)
    assert not sim.writes and not sim.override and b.status()["owner"] == "HUMAN"
    ready(b)
    b.prepare("ARDUPLANE", SESSION, 0)
    assert not sim.writes and not sim.override
    b.activate(SESSION, 1)
    assert sim.override and len(sim.writes) == 6


def test_old_session_and_old_generation_cannot_regain_authority():
    sim = Simulator()
    t = [0.0]
    b = ControlBridge(sim, SESSION, clock=lambda: t[0])
    ready(b)
    b.prepare("DIRECT", SESSION, 0)
    b.activate(SESSION, 1)
    count = len(sim.writes)
    b.human_takeover("pilot yoke")
    assert not sim.override and b.status()["owner"] == "HUMAN"
    b.candidate(SESSION, "roll", 1.0)
    b.candidate(OTHER, "roll", 1.0)
    with pytest.raises(ValueError, match="Revoked"):
        b.heartbeat(SESSION, 1)
    with pytest.raises(ValueError, match="retired"):
        b.prepare("ARDUPLANE", SESSION, 2)
    b.tick()
    assert len(sim.writes) == count and sim.controls["roll"] == 0.0
    assert sim.on_requests == 0


def test_delayed_or_skewed_independent_packets_fail_closed():
    sim = Simulator()
    t = [0.0]
    b = ControlBridge(sim, SESSION, clock=lambda: t[0])
    b.candidate(SESSION, "roll", 0)
    t[0] = 0.1
    for channel in CHANNELS[1:]:
        b.candidate(SESSION, channel, 0)
    with pytest.raises(ValueError, match="Skewed"):
        b.prepare("ARDUPLANE", SESSION, 0)
    assert not sim.override


def test_ap_toggle_requires_observed_off_then_on():
    sim = Simulator()
    sim.ap = True
    t = [0.0]
    b = ControlBridge(sim, SESSION, clock=lambda: t[0])
    ready(b)
    b.prepare("ARDUPLANE", SESSION, 0)
    assert b.activate(SESSION, 1)["state"] == "WAIT_AP_OFF"
    assert sim.off_requests == 1 and not sim.override
    b.heartbeat(SESSION, 1)
    sim.ap = False
    b.tick()
    assert b.status()["state"] == "ACTIVE" and sim.override
    b.transfer_gfc(1, ready=True)
    assert not sim.override and sim.on_requests == 1
    assert b.status()["state"] == "WAIT_GFC"
    sim.ap = True
    b.tick()
    assert b.status()["state"] == "GFC700"


def test_fd_only_or_unknown_readback_never_claims_ap():
    sim = Simulator()
    t = [0.0]
    b = ControlBridge(sim, SESSION, clock=lambda: t[0])
    ready(b)
    b.prepare("ARDUPLANE", SESSION, 0)
    sim.ap = None
    with pytest.raises(ValueError, match="unknown"):
        b.activate(SESSION, 1)
    assert not sim.override


def test_executive_watchdog_is_independent_of_model_service():
    sim = Simulator()
    t = [0.0]
    b = ControlBridge(sim, SESSION, clock=lambda: t[0])
    ready(b)
    b.prepare("ARDUPLANE", SESSION, 0)
    b.activate(SESSION, 1)
    t[0] = 0.5
    b.tick()
    assert b.status()["state"] == "PAUSED_FAULT"
    assert sim.paused and not sim.override


def test_partial_native_write_failure_pauses_and_releases_override():
    class FailingSimulator(Simulator):
        def write_control(self, channel, value):
            super().write_control(channel, value)
            if channel == "pitch":
                raise OSError("SDK write rejected")
    sim = FailingSimulator()
    b = ControlBridge(sim, SESSION, clock=lambda: 0.0)
    ready(b)
    b.prepare("ARDUPLANE", SESSION, 0)
    b.activate(SESSION, 1)
    assert b.status()["state"] == "PAUSED_FAULT"
    assert sim.paused and not sim.override


def test_human_takeover_with_override_still_active_falls_back_to_fault_pause():
    class StickySimulator(Simulator):
        def set_override(self, value):
            if value:
                self.override = True
    sim = StickySimulator()
    b = ControlBridge(sim, SESSION, clock=lambda: 0.0)
    ready(b)
    b.prepare("DIRECT", SESSION, 0)
    b.activate(SESSION, 1)
    b.human_takeover("pilot")
    assert b.status()["state"] == "PAUSED_FAULT"
    assert sim.paused


def test_garmin_return_to_arduplane_needs_new_session_and_drops_old_packets():
    sim = Simulator()
    b = ControlBridge(sim, SESSION, clock=lambda: 0.0)
    ready(b)
    b.prepare("ARDUPLANE", SESSION, 0)
    b.activate(SESSION, 1)
    b.transfer_gfc(1, ready=True)
    sim.ap = True
    b.tick()
    assert b.status()["state"] == "GFC700"
    with pytest.raises(ValueError, match="retired"):
        b.prepare("ARDUPLANE", SESSION, b.generation)
    new_generation = b.generation
    b.renew_session(OTHER, new_generation)
    assert b.session == OTHER and b.generation == new_generation + 1
    b.candidate(SESSION, "roll", 1.0)  # retired SITL packet
    with pytest.raises(ValueError, match="Incomplete"):
        b.prepare("ARDUPLANE", OTHER, b.generation)
    for channel in CHANNELS:
        b.candidate(OTHER, channel, 0.2 if channel in ("throttle", "flap") else 0.0)
    b.prepare("ARDUPLANE", OTHER, b.generation)
    assert b.activate(OTHER, b.generation)["state"] == "WAIT_AP_OFF"
    sim.ap = False
    b.tick()
    assert b.status()["state"] == "ACTIVE" and sim.override
    assert sim.controls["roll"] == 0.0
    with pytest.raises(ValueError, match="Fresh session"):
        b.renew_session(SESSION, b.generation)


def test_virtual_pilot_power_and_flap_are_fenced_by_garmin_generation():
    sim = Simulator()
    b = ControlBridge(sim, SESSION, clock=lambda: 0.0)
    with pytest.raises(ValueError, match="no current Garmin authority"):
        b.set_virtual_aux("throttle", 0.5, SESSION, 0)
    assert not sim.writes
    ready(b)
    b.prepare("ARDUPLANE", SESSION, 0)
    b.activate(SESSION, 1)
    b.transfer_gfc(1, ready=True)
    sim.ap = True
    b.tick()
    generation = b.generation
    assert b.set_virtual_aux("throttle", 0.4, SESSION, generation)["observed"] == 0.4
    assert b.set_virtual_aux("flap", 0.2, SESSION, generation)["observed"] == 0.2
    with pytest.raises(ValueError, match="no current Garmin authority"):
        b.set_virtual_aux("throttle", 0.6, SESSION, generation - 1)
    assert sim.controls["throttle"] == 0.4


def test_human_takeover_waits_for_servo_disconnect_readback():
    class DelayedSimulator(Simulator):
        def command_ap_off(self): self.off_requests += 1
    sim = DelayedSimulator()
    sim.ap = True
    t = [0.0]
    b = ControlBridge(sim, SESSION, clock=lambda: t[0])
    assert b.human_takeover("pilot switch")["state"] == "WAIT_HUMAN"
    assert sim.off_requests == 1 and sim.on_requests == 0
    t[0] = 0.4
    sim.ap = False
    assert b.tick()["state"] == "MANUAL"
    assert not sim.paused


def test_unconfirmed_human_servo_disconnect_faults_instead_of_claiming_manual():
    class StuckSimulator(Simulator):
        def command_ap_off(self): self.off_requests += 1
    sim = StuckSimulator()
    sim.ap = True
    t = [0.0]
    b = ControlBridge(sim, SESSION, clock=lambda: t[0])
    assert b.human_takeover("pilot switch")["state"] == "WAIT_HUMAN"
    t[0] = 1.1
    assert b.tick()["state"] == "PAUSED_FAULT"
    assert sim.paused and sim.on_requests == 0
