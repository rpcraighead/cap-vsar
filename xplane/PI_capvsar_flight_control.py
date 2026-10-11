"""XPPython3 flight-control boundary. Inert until an attended configuration is installed.

The fixed session-specific datarefs accept SITL candidate DREF packets. A local
Unix control socket carries authenticated, bounded authority requests. Only the
flight loop touches X-Plane SDK state. This plugin has not been live qualified.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import socket
import threading
import time

import xp

from capvsar_flight_control_core import CHANNELS, ControlBridge
from capvsar_flight_control_mapping import candidate_prefix
from capvsar_telemetry import Telemetry
from capvsar_qualification import QualificationLab
try:
    from capvsar_landing import LandingLab
except ModuleNotFoundError as error:
    if error.name != "capvsar_landing":
        raise
    class LandingLab:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("Landing laboratory module is not installed")
try:
    from capvsar_surface import SurfaceLab
except ModuleNotFoundError as error:
    if error.name != "capvsar_surface":
        raise
    class SurfaceLab:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("Surface laboratory module is not installed")
try:
    from capvsar_mission import MissionLab
except ModuleNotFoundError as error:
    if error.name != "capvsar_mission":
        raise
    class MissionLab:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("Mission laboratory module is not installed")

CONFIG = Path(__file__).with_name("capvsar_flight_control_config.json")
LIVE_PLUGIN_QUALIFIED = False
NATIVE = {
    "roll": "sim/joystick/yoke_roll_ratio",
    "pitch": "sim/joystick/yoke_pitch_ratio",
    "yaw": "sim/joystick/yoke_heading_ratio",
    "throttle": "sim/flightmodel/engine/ENGN_thro_use",
    "flap": "sim/cockpit2/controls/flap_handle_request_ratio",
    "trim": "sim/cockpit2/controls/elevator_trim",
}


class XPlaneSink:
    def __init__(self, landing=False, toe_brakes=False):
        self.controls = {key: xp.findDataRef(ref) for key, ref in NATIVE.items()}
        self.brakes = None
        self.toe_brake_override = (xp.findDataRef("sim/operation/override/override_toe_brakes")
                                   if toe_brakes else None)
        if landing:
            names = (("sim/cockpit2/controls/left_brake_ratio",
                      "sim/cockpit2/controls/right_brake_ratio") if toe_brakes else
                     ("sim/flightmodel/controls/l_brake_add",
                      "sim/flightmodel/controls/r_brake_add"))
            self.brakes = tuple(xp.findDataRef(name) for name in names)
            if not all(self.brakes):
                raise RuntimeError("Required landing brake datarefs missing")
            self.controls["brake"] = self.brakes[0]
        if toe_brakes and not self.toe_brake_override:
            raise RuntimeError("Required toe-brake override missing")
        self.cockpit_throttle = xp.findDataRef("sim/cockpit2/engine/actuators/throttle_ratio")
        self.joystick = xp.findDataRef("sim/operation/override/override_joystick")
        self.throttles = xp.findDataRef("sim/operation/override/override_throttles")
        self.ap_mode = xp.findDataRef("sim/cockpit2/autopilot/flight_director_mode")
        self.servos = xp.findDataRef("sim/cockpit2/autopilot/servos_on")
        self.paused = xp.findDataRef("sim/time/paused")
        self.pause_on = xp.findCommand("sim/operation/pause_on")
        self.off = xp.findCommand("sim/autopilot/servos_off_any")
        self.ap_toggle = xp.findCommand("sim/GPS/g1000n1_ap")
        if not all(self.controls.values()) or not all((self.cockpit_throttle, self.joystick, self.throttles,
                self.ap_mode, self.servos, self.paused, self.pause_on, self.off, self.ap_toggle)):
            raise RuntimeError("Required flight-control dataref/command missing")

    def ap_engaged(self):
        servos, mode = xp.getDatai(self.servos), xp.getDatai(self.ap_mode)
        if servos == 1 and mode == 2:
            return True
        if servos == 0 and mode in (0, 1):
            return False
        return None

    def override_state(self):
        a, b = xp.getDatai(self.joystick), xp.getDatai(self.throttles)
        states = (a, b) + ((xp.getDatai(self.toe_brake_override),)
                           if self.toe_brake_override else ())
        return True if all(value == 1 for value in states) else False if all(value == 0 for value in states) else None

    def set_override(self, enabled):
        if not enabled and self.brakes:
            for ref in self.brakes:
                xp.setDataf(ref, 0.0)
        value = 1 if enabled else 0
        xp.setDatai(self.joystick, value)
        xp.setDatai(self.throttles, value)
        if self.toe_brake_override:
            xp.setDatai(self.toe_brake_override, value)

    def write_control(self, channel, value):
        if channel == "brake":
            for ref in self.brakes:
                xp.setDataf(ref, value)
        elif channel == "throttle":
            # ENGN_thro_use only drives the engine while override_throttles=1.
            # Garmin ownership leaves overrides off and moves the cockpit lever.
            ref = self.controls[channel] if xp.getDatai(self.throttles) else self.cockpit_throttle
            xp.setDatavf(ref, [value], 0, 1)
        else:
            xp.setDataf(self.controls[channel], value)

    def read_trim(self):
        return xp.getDataf(self.controls["trim"])

    def read_control(self, channel):
        if channel == "throttle":
            ref = self.controls[channel] if xp.getDatai(self.throttles) else self.cockpit_throttle
            values = [0.0]
            if xp.getDatavf(ref, values, 0, 1) != 1:
                raise RuntimeError("Throttle readback unavailable")
            return values[0]
        return xp.getDataf(self.controls[channel])

    def read_brakes(self):
        if not self.brakes:
            raise RuntimeError("Landing brake readback unavailable")
        return tuple(xp.getDataf(ref) for ref in self.brakes)

    def command_ap_off(self):
        xp.commandOnce(self.off)

    def command_ap_on(self):
        xp.commandOnce(self.ap_toggle)

    def pause(self):
        xp.commandOnce(self.pause_on)

    def is_paused(self):
        return xp.getDatai(self.paused) == 1


class PythonInterface:
    def __init__(self):
        self.accessors = []
        self.core = None
        self.loop = None
        self.telemetry_loop = None
        self.telemetry = None
        self.snapshot = None
        self.telemetry_error = None
        self.actuator_readback = None
        self.observe_only = False
        self.lab = None
        self.lab_sessions = set()
        self.config = None
        self.requests = queue.Queue(maxsize=16)
        self.stop_event = threading.Event()
        self.server = None
        self.server_thread = None
        self.bound_socket = False

    def XPluginStart(self):
        config = json.loads(CONFIG.read_text()) if CONFIG.is_file() else None
        if config and (LIVE_PLUGIN_QUALIFIED or config.get("mode") in ("observe", "qualification", "landing", "surface", "mission")):
            self.observe_only = config.get("mode") == "observe"
            session = config["session"]
            candidate_prefix(session)
            if not isinstance(config.get("secret"), str) or len(config["secret"]) < 32:
                raise ValueError("Flight-control socket secret missing")
            if not str(config.get("socket_path", "")).startswith("/tmp/capvsar-flight-control-"):
                raise ValueError("Flight-control socket path must be task-specific under /tmp")
            self.config = config
            landing = config.get("mode") == "landing"
            surface = config.get("mode") == "surface"
            mission = config.get("mode") == "mission"
            braked = landing or surface or mission
            self.core = ControlBridge(XPlaneSink(landing=braked, toe_brakes=surface or mission), session,
                                      atomic=config.get("protocol") == "atomic-v1",
                                      channels=CHANNELS + ("brake",) if braked else CHANNELS,
                                      brake_max=1. if surface or mission else .35)
            self.telemetry = Telemetry(xp, self.core.sink, session)
            if config.get("mode") in ("qualification", "landing", "surface", "mission"):
                if not self.core.atomic:
                    raise ValueError("Qualification requires atomic-v1 protocol")
                lab_type = MissionLab if mission else SurfaceLab if surface else LandingLab if landing else QualificationLab
                self.lab = lab_type(xp, self.core.sink, config)
                self.lab_sessions.add(session)
            if not self.observe_only and not self.core.atomic:
                self._register_candidates(session)
        else:
            xp.log("CAP V-SAR flight control: attended activation unqualified; inactive")
        return "CAP V-SAR Flight Control", "org.cap.vsar.flight_control", "Flight authority boundary"

    def _register_candidates(self, session):
        prefix = candidate_prefix(session)
        for channel in CHANNELS:
            name = prefix + channel
            accessor = xp.registerDataAccessor(
                name, xp.Type_Float, 1,
                readFloat=lambda r, c=channel, s=session: (
                    self.core.candidates.get(c, (0.0,))[0]
                    if self.core.session == s else 0.0),
                writeFloat=lambda r, value, c=channel, s=session: self.core.candidate(s, c, value))
            if accessor is None:
                raise RuntimeError("Candidate dataref registration failed")
            self.accessors.append(accessor)

    def XPluginEnable(self):
        if self.core is None:
            return 1
        self.stop_event.clear()
        self.loop = xp.createFlightLoop(self.flight_loop, xp.FlightLoop_Phase_BeforeFlightModel)
        xp.scheduleFlightLoop(self.loop, -1)
        self.telemetry_loop = xp.createFlightLoop(self.capture_loop, xp.FlightLoop_Phase_AfterFlightModel)
        xp.scheduleFlightLoop(self.telemetry_loop, -1)
        self.server_thread = threading.Thread(target=self._serve, daemon=True)
        self.server_thread.start()
        return 1

    def XPluginDisable(self):
        self.stop_event.set()
        if self.core and not self.observe_only and self.core.state not in ("MANUAL", "PAUSED_FAULT", "FAULT_PAUSE_PENDING"):
            self.core.fault_pause("Flight-control plugin disabled")
        if self.core and self.core.sink.brakes:
            self.core.sink.write_control("brake", 0.0)
        if self.loop:
            xp.destroyFlightLoop(self.loop)
            self.loop = None
        if self.telemetry_loop:
            xp.destroyFlightLoop(self.telemetry_loop)
            self.telemetry_loop = None
        if self.server:
            self.server.close()
            self.server = None
        if self.server_thread:
            self.server_thread.join(timeout=0.5)
            self.server_thread = None
        if self.config and self.bound_socket:
            path = self.config["socket_path"]
            if os.path.exists(path):
                os.unlink(path)
            self.bound_socket = False

    def XPluginStop(self):
        self.XPluginDisable()
        for accessor in self.accessors:
            xp.unregisterDataAccessor(accessor)
        self.accessors.clear()

    def XPluginReceiveMessage(self, inFrom, inMsg, inParam):
        pass

    def _serve(self):
        path = self.config["socket_path"]
        if os.path.exists(path):
            return
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server = server
        try:
            server.bind(path)
            self.bound_socket = True
            os.chmod(path, 0o600)
            server.listen(4)
            server.settimeout(0.1)
            while not self.stop_event.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with conn:
                    conn.settimeout(0.25)
                    try:
                        raw = bytearray()
                        while b"\n" not in raw and len(raw) <= 4096:
                            part = conn.recv(4096)
                            if not part:
                                break
                            raw.extend(part)
                        if len(raw) > 4096 or b"\n" not in raw:
                            raise ValueError("Control request too large")
                        request = json.loads(raw.partition(b"\n")[0])
                        if not isinstance(request, dict) or request.pop("secret", None) != self.config["secret"]:
                            raise ValueError("Unauthorized control request")
                        answer = queue.Queue(maxsize=1)
                        reply_timeout = 20.0 if request.get("action") == "lab_reset" else 0.25
                        self.requests.put_nowait((request, answer, time.monotonic() + 0.20))
                        result = answer.get(timeout=reply_timeout)
                    except (ValueError, queue.Empty, queue.Full, OSError) as error:
                        result = {"error": str(error)}
                    try:
                        conn.sendall(json.dumps(result, allow_nan=False).encode() + b"\n")
                    except OSError:
                        pass  # A disconnected client must not kill the server.
        finally:
            server.close()

    def flight_loop(self, sinceLast, elapsed, counter, refCon):
        for _ in range(8):
            try:
                item = self.requests.get_nowait()
                request, answer = item[:2]
            except queue.Empty:
                break
            try:
                if len(item) == 3 and time.monotonic() >= item[2]:
                    raise ValueError("Control request expired in queue")
                action = request.pop("action")
                if self.observe_only and action not in ("status", "snapshot", "manifest"):
                    raise ValueError("Observe mode has no control authority")
                if self.lab and action not in ("status", "snapshot", "manifest", "lab_reset", "lab_resume",
                        "lab_start", "submit_frame", "prepare", "activate", "exchange", "fault_pause", "human_takeover"):
                    raise ValueError("Action unavailable during qualification")
                if self.lab and action in ("prepare", "activate", "submit_frame", "exchange", "lab_resume", "lab_start"):
                    self.lab.verify_identity()
                    if action == "prepare" and request.get("owner") != "DIRECT":
                        raise ValueError("Qualification only supports DIRECT ownership")
                    if action in ("submit_frame", "exchange", "lab_start"):
                        self.lab.validate_controls(request["controls"])
                if action == "lab_reset" and self.lab:
                    new_session = request.pop("session")
                    candidate_prefix(new_session)
                    if new_session in self.lab_sessions:
                        raise ValueError("Reset must use a new session")
                    result = self.lab.reset(self.core, **request)
                    self.lab_sessions.add(new_session)
                    self.core = ControlBridge(self.core.sink, new_session, atomic=True,
                                              channels=CHANNELS + ("brake",) if isinstance(self.lab, (LandingLab, SurfaceLab, MissionLab)) else CHANNELS,
                                              brake_max=1. if isinstance(self.lab, (SurfaceLab, MissionLab)) else .35)
                    self.telemetry.session = new_session
                    self.snapshot = None
                    answer.put_nowait({**result, "bridge": self.core.status()})
                    continue
                if action == "lab_resume" and self.lab:
                    if request:
                        raise ValueError("Unexpected resume arguments")
                    self.lab.resume(self.core)
                    answer.put_nowait(self.core.status())
                    continue
                if action == "lab_start" and self.lab:
                    # The first control frame, ownership transfer and unpause
                    # share one simulator callback. Separate socket round trips
                    # can consume the 200 ms actuator lease while still paused.
                    if set(request) != {"session", "controls", "snapshot_frame", "snapshot_wall_time_s"}:
                        raise ValueError("Unexpected qualification start arguments")
                    now = time.monotonic()
                    if (self.snapshot is None or self.telemetry_error
                            or type(request["snapshot_frame"]) is not int
                            or request["snapshot_frame"] > self.snapshot["frame"]
                            or type(request["snapshot_wall_time_s"]) not in (int, float)
                            or not 0 <= now - request["snapshot_wall_time_s"] <= 0.20
                            or not 0 <= now - self.snapshot["wall_time_s"] <= 0.20):
                        raise ValueError("Fresh qualification snapshot required")
                    if (self.core.state != "MANUAL" or self.core.owner != "HUMAN"
                            or self.core.retired or self.core.generation != 0
                            or self.core.frame_sequence != -1
                            or request["session"] != self.core.session
                            or self.core.sink.is_paused() is not True
                            or self.core.sink.override_state() is not False
                            or self.core.sink.ap_engaged() is not False):
                        raise ValueError("Qualification start requires paused manual ownership")
                    started = False
                    try:
                        controls = request["controls"]
                        session = request["session"]
                        started = True
                        self.core.submit_frame(session, 0, 1,
                                               self.core.clock() + .18, controls)
                        prepared = self.core.prepare("DIRECT", session, 0)
                        self.core.submit_frame(session, prepared["generation"], 2,
                                               self.core.clock() + .18, controls)
                        self.core.activate(session, prepared["generation"])
                        if self.core.state != "ACTIVE":
                            raise ValueError("Qualification activation not confirmed")
                        self.lab.resume(self.core)
                    except Exception:
                        if started:
                            self.core.fault_pause("Qualification start failed")
                        raise
                    answer.put_nowait(self.core.status())
                    continue
                if action == "exchange":
                    if self.core.state != "ACTIVE":
                        raise ValueError("Exchange requires active authority")
                    self.core.submit_frame(**request)
                    self.core.heartbeat(request["session"], request["generation"])
                    answer.put_nowait({"snapshot": self.snapshot, "bridge": self.core.status()})
                    continue
                if action in ("snapshot", "manifest"):
                    if request:
                        raise ValueError("Unexpected observation arguments")
                    if action == "manifest":
                        result = self.telemetry.manifest()
                    elif self.snapshot is None or self.telemetry_error:
                        raise ValueError(self.telemetry_error or "Telemetry not ready")
                    else:
                        result = {**self.snapshot, "age_s": time.monotonic() - self.snapshot["wall_time_s"]}
                    answer.put_nowait(result)
                    continue
                methods = {"status": self.core.status, "prepare": self.core.prepare,
                           "submit_frame": self.core.submit_frame,
                           "heartbeat": self.core.heartbeat, "activate": self.core.activate,
                           "transfer_gfc": self.core.transfer_gfc,
                           "set_virtual_aux": self.core.set_virtual_aux,
                           "human_takeover": self.core.human_takeover,
                           "fault_pause": self.core.fault_pause}
                if action == "renew_session":
                    if len(self.core.used_sessions) >= 4:
                        raise ValueError("Plugin session rotation limit reached")
                    new_session = request["session"]
                    candidate_prefix(new_session)
                    if new_session in self.core.used_sessions:
                        raise ValueError("Candidate session already retired")
                    result = self.core.renew_session(**request)
                    self.telemetry.session = new_session
                    if not self.core.atomic:
                        self._register_candidates(new_session)
                    answer.put_nowait(result)
                    continue
                if action not in methods:
                    raise ValueError("Unknown flight-control action")
                result = methods[action](**request)
                answer.put_nowait(result if isinstance(result, dict) else self.core.status())
            except (ValueError, TypeError, KeyError) as error:
                answer.put_nowait({"error": str(error), "status": self.core.status()})
            except Exception as error:
                if not self.observe_only:
                    self.core.fault_pause("Bridge action failed: %s" % error)
                answer.put_nowait({"error": str(error), "status": self.core.status()})
        try:
            if not self.observe_only:
                if self.lab and self.core.state == "ACTIVE":
                    self.lab.verify_identity()
                self.core.tick()
                if isinstance(self.lab, (LandingLab, SurfaceLab, MissionLab)):
                    left, right = self.core.sink.read_brakes()
                    self.actuator_readback = {
                        "wall_time_s": time.monotonic(), "frame_sequence": self.core.frame_sequence,
                        "bridge_state": self.core.state, "brake_left": left, "brake_right": right}
        except Exception as error:
            self.core.fault_pause("Bridge loop failed: %s" % error)
        return -1

    def capture_loop(self, sinceLast, elapsed, counter, refCon):
        try:
            self.snapshot = self.telemetry.capture(counter)
            if isinstance(self.lab, (LandingLab, SurfaceLab, MissionLab)) and self.actuator_readback:
                self.snapshot["actuator_readback"] = dict(self.actuator_readback)
            if self.lab:
                self.lab.check_flight(self.snapshot, self.core)
            self.telemetry_error = None
        except Exception as error:
            self.snapshot = None
            self.telemetry_error = str(error)
            if not self.observe_only and self.core.state == "ACTIVE":
                self.core.fault_pause("Telemetry capture failed: %s" % error)
        return -1
