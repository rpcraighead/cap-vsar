"""Direct controller writes are staged as candidates, never native DREFs."""
import pytest

from services.ai_pilot.candidate_client import CandidateClient, NATIVE_CHANNEL

SESSION = "e" * 32


class Raw:
    def __init__(self):
        self.callbacks = {}
        self.writes = []
    def subscribe_dref(self, ref, freq_hz, callback):
        self.callbacks[ref] = callback
    def send_dref(self, ref, value): self.writes.append((ref, value))
    def feed(self, ref, value): self.callbacks[ref](ref, value)


def test_direct_tick_emits_complete_private_set_and_never_native_controls():
    raw = Raw()
    clock = [0.0]
    bridge = type("Bridge", (), {"session": SESSION})()
    client = CandidateClient(raw, bridge, clock=lambda: clock[0])
    raw.feed("sim/cockpit2/controls/flap_ratio", 0.1)
    raw.feed("sim/cockpit2/controls/elevator_trim", 0.05)
    for ref, channel in NATIVE_CHANNEL.items():
        if channel in ("flap", "trim"):
            continue
        client.send_dref(ref, 0.5 if channel == "throttle" else 0.0)
    assert len(raw.writes) == 6
    assert all(ref.startswith(f"cap/flight_control/candidate/{SESSION}/")
               for ref, _ in raw.writes)
    assert raw.writes[-1][0].endswith("/trim")


def test_missing_fresh_flap_or_trim_cannot_complete_candidate_set():
    raw = Raw()
    clock = [0.0]
    client = CandidateClient(raw, type("Bridge", (), {"session": SESSION})(),
                             clock=lambda: clock[0])
    raw.feed("sim/cockpit2/controls/flap_ratio", 0.0)
    raw.feed("sim/cockpit2/controls/elevator_trim", 0.0)
    clock[0] = 0.3
    for ref, channel in NATIVE_CHANNEL.items():
        if channel in ("roll", "pitch", "yaw"):
            client.send_dref(ref, 0.0)
    with pytest.raises(ValueError, match="Fresh flap"):
        client.send_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]", 0.5)
    assert not raw.writes
    with pytest.raises(ValueError, match="Unmediated"):
        client.send_dref("sim/operation/override/override_joystick", 1)


def test_partial_direct_tick_emits_no_candidate_packets():
    raw = Raw()
    clock = [0.0]
    client = CandidateClient(raw, type("Bridge", (), {"session": SESSION})(),
                             clock=lambda: clock[0])
    client.send_dref("sim/cockpit2/controls/yoke_roll_ratio", 0.1)
    with pytest.raises(ValueError, match="Complete fresh"):
        client.send_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]", 0.4)
    assert raw.writes == []
