"""Whole-frame rejection, lease fencing and observed fault containment."""
import copy
import math

import pytest

from xplane.capvsar_flight_control_core import CHANNELS, ControlBridge
from .test_flight_control_bridge import SESSION, Simulator
from .test_flight_control_plugin import load_plugin
import queue


def setup():
    wall = [10.0]
    sim = Simulator()
    bridge = ControlBridge(sim, SESSION, clock=lambda: wall[0], atomic=True)
    frame = dict(session=SESSION, generation=0, sequence=0, expires_at=10.15,
                 controls={c: 0.2 if c == "throttle" else 0.0 for c in CHANNELS})
    return wall, sim, bridge, frame


def test_surface_profile_can_command_full_rejected_takeoff_braking_only_when_explicit():
    wall = [10.]
    frame = {"session": SESSION, "generation": 0, "sequence": 0,
             "expires_at": 10.15,
             "controls": {**{c: 0. for c in CHANNELS}, "brake": 1.}}
    restricted = ControlBridge(Simulator(), SESSION, clock=lambda: wall[0],
                               atomic=True, channels=CHANNELS+("brake",))
    with pytest.raises(ValueError, match="brake"):
        restricted.submit_frame(**frame)
    surface = ControlBridge(Simulator(), SESSION, clock=lambda: wall[0],
                            atomic=True, channels=CHANNELS+("brake",),
                            brake_max=1.)
    surface.submit_frame(**frame)
    assert surface.candidates["brake"][0] == 1.


@pytest.mark.parametrize("change", [
    {"session": "b" * 32}, {"generation": 1}, {"generation": False},
    {"sequence": -1}, {"sequence": True}, {"expires_at": 10.0},
    {"expires_at": 10.3}, {"expires_at": math.nan},
    {"controls": {"roll": 0.2}},
    {"controls": {c: math.nan for c in CHANNELS}},
    {"controls": {c: True for c in CHANNELS}},
    {"controls": {c: 1.1 for c in CHANNELS}},
])
def test_invalid_frame_cannot_partially_update_or_extend_lease(change):
    _, sim, bridge, frame = setup()
    bridge.submit_frame(**frame)
    before = copy.deepcopy(bridge.candidates)
    with pytest.raises(ValueError):
        bridge.submit_frame(**{**frame, "sequence": 1, **change})
    assert bridge.candidates == before
    assert bridge.frame_deadline == 10.15 and bridge.frame_sequence == 0
    assert not sim.writes


def test_prepare_requires_fresh_generation_and_old_packets_cannot_mix():
    wall, sim, bridge, frame = setup()
    bridge.submit_frame(**frame)
    bridge.prepare("DIRECT", SESSION, 0)
    with pytest.raises(ValueError, match="generation"):
        bridge.activate(SESSION, 1)
    frame.update(generation=1, sequence=1)
    bridge.submit_frame(**frame)
    bridge.candidate(SESSION, "roll", 0.9)
    bridge.activate(SESSION, 1)
    assert sim.controls["roll"] == 0.0
    writes = list(sim.writes)
    with pytest.raises(ValueError, match="sequence"):
        bridge.submit_frame(**frame)
    wall[0] = 10.16
    bridge.heartbeat(SESSION, 1)
    bridge.tick()
    assert sim.writes == writes and not sim.override
    assert bridge.status()["pause_confirmed"] and bridge.retired
    with pytest.raises(ValueError, match="session"):
        bridge.submit_frame(**{**frame, "sequence": 2, "expires_at": 10.3})


def test_pause_request_is_not_pause_confirmation():
    _, sim, bridge, _ = setup()
    sim.pause = lambda: None
    bridge.fault_pause("test")
    assert bridge.state == "FAULT_PAUSE_PENDING"
    assert not bridge.pause_confirmed
    sim.paused = True
    bridge.tick()
    assert bridge.state == "PAUSED_FAULT" and bridge.pause_confirmed
    sim.paused = False
    bridge.tick()
    assert bridge.state == "FAULT_PAUSE_PENDING" and bridge.retired


def test_late_frame_graces_are_bounded_and_only_timely_frames_reset_them():
    wall, _, bridge, frame = setup()
    bridge.submit_frame(**frame)
    bridge.last_tick_time = wall[0]

    wall[0] += .3
    bridge.tick()
    bridge._fresh()
    assert bridge.frame_stall_graces == 1

    # A late replacement gets a new lease but does not erase the stall streak.
    frame.update(sequence=1, expires_at=wall[0] + .15)
    bridge.submit_frame(**frame)
    assert bridge.frame_stall_graces == 1
    wall[0] += .05
    frame.update(sequence=2, expires_at=wall[0] + .15)
    bridge.submit_frame(**frame)
    assert bridge.frame_stall_graces == 0

    for sequence in range(3, 6):
        wall[0] += .3
        bridge.tick()
        bridge._fresh()
        frame.update(sequence=sequence, expires_at=wall[0] + .15)
        bridge.submit_frame(**frame)
    assert bridge.frame_stall_graces == 3
    wall[0] += .3
    bridge.tick()
    with pytest.raises(ValueError, match="Atomic frame expired"):
        bridge._fresh()


def test_in_time_heartbeat_resets_stall_grace_but_late_heartbeats_do_not():
    wall, _, bridge, _ = setup()
    bridge.state = "WAIT_GFC"
    bridge.transfer_deadline = 100.
    bridge.last_heartbeat = wall[0]
    bridge.last_tick_time = wall[0]

    wall[0] += .5
    bridge.tick()
    assert bridge.heartbeat_stall_graces == 1
    bridge.heartbeat(SESSION, bridge.generation)
    assert bridge.heartbeat_stall_graces == 1

    wall[0] += .1
    bridge.heartbeat(SESSION, bridge.generation)
    assert bridge.heartbeat_stall_graces == 0
    wall[0] += .5
    bridge.tick()
    assert bridge.heartbeat_stall_graces == 1


def request(plugin, **payload):
    answer = queue.Queue(maxsize=1)
    plugin.requests.put((payload, answer))
    plugin.flight_loop(0, 0, 1, None)
    return answer.get_nowait()


def test_observer_mode_denies_every_mutation_even_without_live_gate(monkeypatch, tmp_path):
    xp, plugin = load_plugin(monkeypatch, tmp_path, activate_fake=False, mode="observe")
    assert plugin.core is not None and xp.accessors == {}
    for action in ("prepare", "activate", "submit_frame", "heartbeat", "human_takeover",
                   "fault_pause", "renew_session", "set_virtual_aux", "transfer_gfc"):
        assert "no control authority" in request(plugin, action=action)["error"]
    plugin.capture_loop(0, 0, 20, None)
    snapshot = request(plugin, action="snapshot")
    assert snapshot["sdk_counter"] == 20 and snapshot["frame"] == 1
    assert snapshot["aircraft"]["name"] == "Cessna_172SP_G1000.acf"
    assert request(plugin, action="manifest")["units"]["agl_m"] == "m AGL"
    plugin.XPluginStop()
    assert not xp.writes and not xp.commands


def test_queued_timeout_cannot_apply_a_late_authority_request(monkeypatch, tmp_path):
    xp, plugin = load_plugin(monkeypatch, tmp_path)
    answer = queue.Queue(maxsize=1)
    plugin.requests.put(({"action": "fault_pause", "reason": "late"}, answer, -1))
    plugin.flight_loop(0, 0, 1, None)
    assert "expired" in answer.get_nowait()["error"]
    assert not xp.writes and not xp.commands


def test_fault_uses_pause_command_and_verifies_sdk_readback(monkeypatch, tmp_path):
    xp, plugin = load_plugin(monkeypatch, tmp_path)
    status = plugin.core.fault_pause("test")
    assert status["pause_confirmed"]
    assert "sim/operation/pause_on" in xp.commands
