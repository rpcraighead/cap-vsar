"""Managed SITL process lifecycle and explicit detach targets.

The stock XPlane mapping writes native controls before any MAVLink command.
Callers must qualify a separate output bridge before starting this process.
"""

from __future__ import annotations

import socket
import subprocess
import time
import json
import math
from pathlib import Path

from xplane.capvsar_flight_control_mapping import validate_mapping

OVERRIDE_DREFS = (
    "sim/operation/override/override_joystick",
    "sim/operation/override/override_throttles",
)


class SitlProcess:
    """Start and stop the arduplane binary running the X-Plane model."""

    def __init__(self, binary, cwd, parm, log_path, mavlink_port=5760, sim_port_in=None,
                 popen=subprocess.Popen, clock=time.monotonic, sleep=time.sleep,
                 candidate_session=None, mapping_validator=validate_mapping,
                 mapping_loader=None):
        self.binary, self.cwd, self.parm = str(binary), str(cwd), str(parm)
        self.log_path, self.mavlink_port = str(log_path), mavlink_port
        # X-Plane binds its own data-output port, so on a single machine SITL
        # must be told to listen somewhere else or it receives nothing.
        self.sim_port_in = sim_port_in
        self._popen, self.clock, self.sleep = popen, clock, sleep
        self.candidate_session = candidate_session
        self.mapping_validator = mapping_validator
        self.mapping_loader = mapping_loader or (lambda path: json.loads(path.read_text()))
        self.process = None
        self._log = None

    def command(self):
        argv = [self.binary, "--model", "xplane", "--defaults", self.parm]
        # The pinned SIM_XPlane class uses fixed 49001/49000 ports and inherits
        # an empty set_interface_ports(), so --sim-port-in is ineffective here.
        return argv

    def start(self):
        if self.candidate_session is None:
            raise ValueError("Managed SITL requires a session-specific mediated mapping")
        mapping_path = Path(self.cwd) / "xplane_plane.json"
        self.mapping_validator(self.mapping_loader(mapping_path), self.candidate_session)
        Path(self.cwd).mkdir(parents=True, exist_ok=True)
        self._log = open(self.log_path, "ab")
        try:
            self.process = self._popen(
                self.command(), cwd=self.cwd,
                stdout=self._log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            )
        except BaseException:
            self._close_log()
            raise
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
        try:
            if process.poll() is None:
                process.terminate()
                deadline = self.clock() + grace
                while process.poll() is None and self.clock() < deadline:
                    self.sleep(0.1)
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2.0)
            stopped = process.poll() is not None
            if stopped:
                self.process = None
            return stopped
        finally:
            self._close_log()

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


def cleanup_startup(client, sitl=None, link=None):
    """Close partial startup resources, continuing after a teardown failure."""
    result = {"sitl_stopped": None, "overrides_clear_requested": False, "errors": []}
    try:
        if sitl is not None:
            result["sitl_stopped"] = sitl.stop()
    except Exception as error:
        result["errors"].append("SITL stop: %s" % error)
    if result["sitl_stopped"] is True:
        for ref in OVERRIDE_DREFS:
            try:
                client.send_dref(ref, 0)
                result["overrides_clear_requested"] = True
            except Exception as error:
                result["errors"].append("override %s: %s" % (ref, error))
    elif sitl is not None:
        result["errors"].append("SITL not confirmed stopped")
    try:
        if link is not None:
            link.close()
    except Exception as error:
        result["errors"].append("MAVLink close: %s" % error)
    try:
        client.stop()
    except Exception as error:
        result["errors"].append("X-Plane client close: %s" % error)
    return result


def park_on_gfc700(client, state, heading_mag, altitude_ft):
    """Engage the aircraft's own autopilot in HDG + ALT at the given targets.

    `state` carries 'servos_on' and 'ap_state' read from X-Plane just before
    the call. g1000n1_ap TOGGLES, so it is pressed only when the servos are
    off; g1000n1_hdg only when heading mode (bit 2) is not already set.
    Returns the commands sent, for the trace.
    """
    if (state.get("servos_on") not in (0, 1) or state.get("ap_state") is None
            or state.get("flight_director_mode") not in (0, 1, 2)
            or state.get("age_seconds", float("inf")) > 0.5):
        raise ValueError("Fresh Garmin servo and mode readback required")
    sent = []
    client.send_dref("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot", float(heading_mag) % 360.0)
    client.send_dref("sim/cockpit2/autopilot/altitude_dial_ft", float(round(altitude_ft / 100.0) * 100))
    if not state.get("servos_on"):
        client.send_command("sim/GPS/g1000n1_ap")
        sent.append("sim/GPS/g1000n1_ap")
    if not (int(state.get("ap_state", 0)) & 2):
        client.send_command("sim/GPS/g1000n1_hdg")
        sent.append("sim/GPS/g1000n1_hdg")
    if not (int(state["ap_state"]) & 16384):
        client.send_command("sim/GPS/g1000n1_alt")
        sent.append("sim/GPS/g1000n1_alt")
    return sent


def confirmed_gfc700(state, heading_mag, altitude_ft):
    if not isinstance(state, dict):
        return False
    try:
        heading_error = abs((state["heading_selected_deg"] - heading_mag + 180) % 360 - 180)
        return (state["age_seconds"] <= 0.5 and state["servos_on"] == 1
                and state["flight_director_mode"] == 2
                and int(state["ap_state"]) & 2 != 0
                and int(state["ap_state"]) & 16384 != 0
                and heading_error <= 2
                and abs(state["altitude_selected_ft"] - round(altitude_ft / 100) * 100) <= 50)
    except (KeyError, TypeError, ValueError):
        return False


def detach(backend, client, sitl, state, heading_mag, altitude_ft, release=None,
           target="human", verify_gfc=None):
    """Best-effort idempotent teardown; report requested versus confirmed work.

    An unmanaged SITL is *unknown*, never implicitly stopped. A Garmin transfer
    must be requested and verified explicitly. Fault pause never engages Garmin.
    """
    if target not in ("human", "gfc700", "fault_pause", "ground_stop"):
        raise ValueError("Unsupported detach target")
    result = {"target": target, "sitl_stopped": None, "overrides_clear_requested": False,
              "gfc700_commands": [], "gfc700_verified": False, "errors": [],
              "hand_back_mode": None}
    try:
        (release or backend.release)()
    except Exception as error:
        result["errors"].append("release: %s" % error)
    try:
        result["sitl_stopped"] = sitl.stop() if sitl is not None else None
    except Exception as error:
        result["errors"].append("SITL stop: %s" % error)
    if result["sitl_stopped"] is True:
        for ref in OVERRIDE_DREFS:
            try:
                client.send_dref(ref, 0)
                result["overrides_clear_requested"] = True
            except Exception as error:
                result["errors"].append("override %s: %s" % (ref, error))
    else:
        result["errors"].append("SITL writer not confirmed stopped; overrides not cleared")
    if target == "gfc700":
        if result["sitl_stopped"] is not True or verify_gfc is None:
            result["errors"].append("Garmin transfer lacks confirmed writer stop or readback")
        else:
            try:
                result["gfc700_commands"] = park_on_gfc700(client, state, heading_mag, altitude_ft)
                result["gfc700_verified"] = confirmed_gfc700(
                    verify_gfc(), heading_mag, altitude_ft)
                if not result["gfc700_verified"]:
                    result["errors"].append("Garmin servo/mode readback did not confirm transfer")
            except Exception as error:
                result["errors"].append("Garmin transfer: %s" % error)
    result["hand_back_mode"] = getattr(backend, "last_commands", {}).get("hand_back_mode")
    return result
