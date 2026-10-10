"""Restrict direct-controller writes to private bridge candidates.

This wrapper never forwards a native control DREF or autopilot command to the
simulator. It does not grant authority; the plugin arbiter makes that decision.
"""
from __future__ import annotations

import math
import time

from xplane.capvsar_flight_control_mapping import candidate_prefix

NATIVE_CHANNEL = {
    "sim/cockpit2/controls/yoke_roll_ratio": "roll",
    "sim/cockpit2/controls/yoke_pitch_ratio": "pitch",
    "sim/cockpit2/controls/yoke_heading_ratio": "yaw",
    "sim/cockpit2/engine/actuators/throttle_ratio[0]": "throttle",
    "sim/cockpit2/controls/flap_ratio": "flap",
    "sim/cockpit2/controls/elevator_trim": "trim",
}


class CandidateClient:
    def __init__(self, raw_client, bridge, *, clock=time.monotonic):
        self.raw = raw_client
        self.bridge = bridge
        self.clock = clock
        self.prefix = candidate_prefix(bridge.session)
        self.pending = {}
        self.aux = {}
        for channel, ref in (("flap", "sim/cockpit2/controls/flap_ratio"),
                             ("trim", "sim/cockpit2/controls/elevator_trim")):
            def received(dataref, value, name=channel):
                self.aux[name] = (value, self.clock())
            raw_client.subscribe_dref(ref, freq_hz=10, callback=received)

    def subscribe_dref(self, *args, **kwargs):
        return self.raw.subscribe_dref(*args, **kwargs)

    def unsubscribe_dref(self, *args, **kwargs):
        return self.raw.unsubscribe_dref(*args, **kwargs)

    def get_all_cached(self):
        return self.raw.get_all_cached()

    @property
    def mock(self):
        return getattr(self.raw, "mock", False)

    def send_dref(self, ref, value):
        channel = NATIVE_CHANNEL.get(ref)
        if channel is None:
            raise ValueError("Unmediated direct-controller DREF: %s" % ref)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Nonfinite control candidate")
        self.pending[channel] = (float(value), self.clock())
        if channel == "throttle":
            # Direct backend sends throttle last. Reject an incomplete tick
            # before any candidate packet can reach the simulator plugin.
            required = ("roll", "pitch", "yaw", "throttle")
            if any(name not in self.pending or self.clock() - self.pending[name][1] > 0.1
                   for name in required):
                self.pending.clear()
                raise ValueError("Complete fresh direct control tick required")
            frame = {name: self.pending[name][0] for name in required}
            for auxiliary in ("flap", "trim"):
                latest = self.pending.get(auxiliary)
                if latest is None or self.clock() - latest[1] > 0.1:
                    latest = self.aux.get(auxiliary)
                if latest is None or self.clock() - latest[1] > 0.2 or not math.isfinite(latest[0]):
                    self.pending.clear()
                    raise ValueError("Fresh %s candidate unavailable" % auxiliary)
                frame[auxiliary] = float(latest[0])
            self.pending.clear()
            for name in (*required, "flap", "trim"):
                self.raw.send_dref(self.prefix + name, frame[name])

    def send_command(self, command):
        if command == "sim/autopilot/servos_off_any":
            # Bridge performs and verifies this transition during commit.
            return
        raise ValueError("Unmediated direct-controller command: %s" % command)

    def set_paused(self, paused):
        if paused:
            self.bridge.fault_pause("Direct controller requested fault pause")
        else:
            raise ValueError("Direct controller cannot unpause simulator")

    def stop(self):
        self.raw.stop()
