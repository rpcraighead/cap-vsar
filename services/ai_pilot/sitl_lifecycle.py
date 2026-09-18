"""Own the ArduPlane SITL process and the X-Plane side of attaching and
detaching it, in the one order that is safe.

SITL writes the throttle and yoke datarefs every frame in every mode and
re-sends X-Plane's joystick/throttle overrides every frame; it has no exit
hook. So the overrides can only be cleared after the process is gone, and the
aircraft must be parked - ArduPlane first, then the aircraft's own autopilot -
around that gap, because CAP 487 does not hold itself for more than a few
seconds (AI-21, docs/ARDUPLANE_TRIAL.md).
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

OVERRIDE_DREFS = (
    "sim/operation/override/override_joystick",
    "sim/operation/override/override_throttles",
)


class SitlProcess:
    """Start and stop the arduplane binary running the X-Plane model."""

    def __init__(self, binary, cwd, parm, log_path, mavlink_port=5760, sim_port_in=None,
                 popen=subprocess.Popen, clock=time.monotonic, sleep=time.sleep):
        self.binary, self.cwd, self.parm = str(binary), str(cwd), str(parm)
        self.log_path, self.mavlink_port = str(log_path), mavlink_port
        # X-Plane binds its own data-output port, so on a single machine SITL
        # must be told to listen somewhere else or it receives nothing.
        self.sim_port_in = sim_port_in
        self._popen, self.clock, self.sleep = popen, clock, sleep
        self.process = None
        self._log = None

    def command(self):
        argv = [self.binary, "--model", "xplane", "--defaults", self.parm]
        if self.sim_port_in is not None:
            argv += ["--sim-port-in", str(self.sim_port_in)]
        return argv

    def start(self):
        Path(self.cwd).mkdir(parents=True, exist_ok=True)
        self._log = open(self.log_path, "ab")
        self.process = self._popen(
            self.command(), cwd=self.cwd,
            stdout=self._log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        )
        return self.process

    def wait_for_mavlink(self, timeout=20.0, probe=None):
        """True once the MAVLink port accepts a connection."""
        probe = probe or self._tcp_open
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            if self.process is not None and self.process.poll() is not None:
                return False
            if probe(self.mavlink_port):
                return True
            self.sleep(0.25)
        return False

    @staticmethod
    def _tcp_open(port):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            return False

    def stop(self, grace=3.0):
        """SIGTERM, wait, SIGKILL. True once the process is gone."""
        process = self.process
        if process is None:
            self._close_log()
            return True
        if process.poll() is None:
            process.terminate()
            deadline = self.clock() + grace
            while process.poll() is None and self.clock() < deadline:
                self.sleep(0.1)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2.0)
        self.process = None
        self._close_log()
        return True

    def _close_log(self):
        if self._log is not None:
            try:
                self._log.close()
            except OSError:
                pass
            self._log = None

    @property
    def alive(self):
        return self.process is not None and self.process.poll() is None


def clear_overrides(client):
    """Only meaningful once SITL is gone - alive, it re-asserts them every frame."""
    for ref in OVERRIDE_DREFS:
        client.send_dref(ref, 0)


def park_on_gfc700(client, state, heading_mag, altitude_ft):
    """Engage the aircraft's own autopilot in HDG + ALT at the given targets.

    `state` carries 'servos_on' and 'ap_state' read from X-Plane just before
    the call. g1000n1_ap TOGGLES, so it is pressed only when the servos are
    off; g1000n1_hdg only when heading mode (bit 2) is not already set.
    Returns the commands sent, for the trace.
    """
    sent = []
    client.send_dref("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot", float(heading_mag) % 360.0)
    client.send_dref("sim/cockpit2/autopilot/altitude_dial_ft", float(round(altitude_ft / 100.0) * 100))
    client.send_dref("sim/cockpit2/autopilot/servos_on", 1)
    if not state.get("servos_on"):
        client.send_command("sim/GPS/g1000n1_ap")
        sent.append("sim/GPS/g1000n1_ap")
    if not (int(state.get("ap_state", 0)) & 2):
        client.send_command("sim/GPS/g1000n1_hdg")
        sent.append("sim/GPS/g1000n1_hdg")
    client.send_command("sim/GPS/g1000n1_alt")
    sent.append("sim/GPS/g1000n1_alt")
    return sent


def detach(backend, client, sitl, state, heading_mag, altitude_ft, release=None):
    """Release, stop SITL, clear the overrides, hand to the GFC 700 - in that
    order. Any other order leaves either two writers on the surfaces or an
    aircraft nobody is flying."""
    (release or backend.release)()
    stopped = sitl.stop() if sitl is not None else True
    clear_overrides(client)
    commands = park_on_gfc700(client, state, heading_mag, altitude_ft)
    return {
        "sitl_stopped": stopped,
        "gfc700_commands": commands,
        "hand_back_mode": backend.last_commands.get("hand_back_mode"),
    }
