"""ArduPlane FlightBackend: command modes and targets, let ArduPilot fly the surfaces.

Third implementation of the EXISTING `maneuvers.FlightBackend` protocol, after
the G1000 autopilot backend and the direct surface-control backend. The gate,
the control lease, the strictly increasing sequence, the envelope and the
capture detection are unchanged and still apply; this module only decides how
a heading/altitude target reaches the aircraft.

Here the aircraft is flown by an ArduPilot ArduPlane SITL attached to X-Plane
(the DRef-based `SIM_XPlane` backend). This backend never writes a control
surface. It puts ArduPlane in GUIDED and sends MAV_CMD_GUIDED_CHANGE_ALTITUDE /
_HEADING; ArduPilot closes the loops and writes the yoke datarefs itself.

Two frames of reference are reconciled here rather than assumed:

* Heading. The gate speaks magnetic; ArduPilot's guided heading is true. The
  offset is measured live from X-Plane (`psi - mag_psi`), never taken from a
  table.
* Altitude. The gate measures INDICATED altitude (the pilot's altimeter,
  Kollsman-dependent); ArduPilot flies true MSL, because SITL synthesises a
  standard-atmosphere baro from X-Plane's true position. The offset
  (`elevation - indicated`) is measured at engagement and re-measured whenever
  the aircraft has levelled short of the target, so a wrong altimeter setting
  shows up as a re-target, not as a capture that never comes.

Observation still comes from X-Plane over RREF, exactly as for the other two
backends. X-Plane is what the gate and the capture check already trust;
ArduPilot's own telemetry is used only for sanity checks and for the pilot's
RC input.

SAFETY. Fail-closed rules, each of which is a named test:

* nothing is sent until the aircraft's own autopilot has been disengaged (one
  writer on the surfaces, CONOPS 7.2);
* `select` refuses stale X-Plane telemetry or a missing ArduPilot heartbeat,
  and every ArduPilot command must be ACKed ACCEPTED or the select raises and
  the gate faults;
* the supervisory loop re-checks the envelope itself (second line of defence),
  and pauses the simulator on a lost heartbeat - there is then nobody flying;
* on a lost heartbeat it ALSO clears X-Plane's joystick/throttle overrides,
  because SITL's mapping sets override_joystick=1 and a dead SITL would leave
  the physical yoke disconnected from the aircraft;
* the pilot always wins the yoke: RC input seen by ArduPilot, or raw joystick
  movement seen by X-Plane, releases immediately (D-3 / AI-12), and a new
  `select` is refused until `release()` has acknowledged the takeover;
* release parks ArduPlane in LOITER, which flies itself with no RC, or in
  FBWA when a valid centred stick was measured at engagement. MANUAL is never
  used: it is raw passthrough, and an unmapped joystick axis reads as full
  aileron and full throttle (AI-21);
* `pause` never changes ArduPilot's mode and never forgets that this backend
  engaged, so the explicit hand-back after a fault still reaches ArduPilot;
* `release` never pauses, and hands back only what this backend took - if it
  never engaged it sends nothing.
"""

from __future__ import annotations

import math
import threading
import time

from . import mavlink_min as mav
from .maneuvers import Observation

FT_PER_M = 3.28084
M_PER_FT = 0.3048


class ArduPlaneBackend:
    """Flies heading and altitude targets through ArduPlane's GUIDED mode."""

    LOOP_HZ = 5.0
    STALE_AFTER_SECONDS = 2.0
    HEARTBEAT_STALE_SECONDS = 2.0
    ACK_TIMEOUT = 0.6
    MODE_CHANGE_TIMEOUT = 1.2     # heartbeats are requested at 5 Hz, see MavlinkLink.STREAMS
    # MAV_CMD_GUIDED_CHANGE_HEADING param3 is a maximum centripetal
    # acceleration, m/s^2 - not a turn rate. 3 m/s^2 is ~17 deg of bank, which
    # is ~3 deg/s at 110 KIAS and well inside the gate's 35 deg.
    HEADING_ACCEL_M_S2 = 3.0
    CLIMB_RATE_M_S = 2.5
    RC_DEADBAND_US = 40           # from the position read at engagement, not from 1500
    RC_VALID_US = (800, 2200)
    RC_HOLD_SECONDS = 0.3
    AXIS_DEADBAND = 0.08          # raw X-Plane joystick axis, 0..1
    ALT_SANITY_FT = 100.0
    ALT_RETARGET_FT = 40.0
    RETARGET_VVI_FPM = 150.0
    RETARGET_MIN_INTERVAL = 5.0

    AUTOPILOT_OFF_COMMAND = "sim/autopilot/servos_off_any"
    OVERRIDE_DREFS = (
        "sim/operation/override/override_joystick",
        "sim/operation/override/override_throttles",
    )
    RC_CHANNELS = ("chan1_raw", "chan2_raw", "chan4_raw")   # roll, pitch, yaw

    DATAREFS = {
        "heading_mag": "sim/flightmodel/position/mag_psi",
        "altitude_indicated_ft": "sim/cockpit2/gauges/indicators/altitude_ft_pilot",
        "agl_ft": "sim/flightmodel/position/y_agl",
        "kias": "sim/flightmodel/position/indicated_airspeed",
        "roll_deg": "sim/flightmodel/position/phi",
        "vvi_fpm": "sim/flightmodel/position/vh_ind_fpm",
    }

    # Outside the freshness gate, as the direct backend keeps its damping
    # terms: losing one of these must not declare the whole picture stale.
    AUX_DATAREFS = {
        "elevation_m": "sim/flightmodel/position/elevation",
        "heading_true": "sim/flightmodel/position/psi",
        # 0 off, 1 flight director, 2 autopilot servos engaged.
        "ap_mode": "sim/cockpit2/autopilot/flight_director_mode",
        "override_joystick": "sim/operation/override/override_joystick",
    }

    def __init__(self, client, link, limits=None, clock=time.monotonic, joystick_axes=None):
        """
        joystick_axes: optional {"pitch": i, "roll": j} indices into
        sim/joystick/joystick_axis_values, the raw axes that keep updating
        while ArduPilot holds the joystick override. Rig-specific, so it is
        supplied by the launcher, not guessed here.
        """
        self.client, self.link, self.clock, self.limits = client, link, clock, limits
        self.samples = {}
        self.lock = threading.Lock()
        # Serialises arm/send/wait on the link: the gate thread's select and
        # the supervisor's re-target must never race for the same ACK.
        self._command_lock = threading.Lock()
        self._targets = None
        self._thread = None
        self._stop = threading.Event()
        self._engaged = False
        self._takeover_pending = False
        self._last_fault = None
        self._last_commands = {}
        self._mag_offset = 0.0
        self._alt_offset_m = 0.0
        self._axis_rest = {}
        self._rc_rest = None
        self._rc_deviation_since = None
        self._last_retarget = -float("inf")
        self._released_at = None

        self.axis_datarefs = {
            "axis_%s" % name: "sim/joystick/joystick_axis_values[%d]" % int(index)
            for name, index in (joystick_axes or {}).items()
        }
        for name, ref in {**self.DATAREFS, **self.AUX_DATAREFS, **self.axis_datarefs}.items():
            def received(ref, value, name=name):
                with self.lock:
                    self.samples[name] = (value, self.clock())
            client.subscribe_dref(ref, freq_hz=10, callback=received)

    # -- FlightBackend ----------------------------------------------------

    def observe(self) -> Observation:
        with self.lock:
            values = {name: self.samples.get(name, (float("nan"), -float("inf")))
                      for name in self.DATAREFS}
        age = max(self.clock() - sample[1] for sample in values.values())
        return Observation(
            heading_mag=values["heading_mag"][0],
            altitude_indicated_ft=values["altitude_indicated_ft"][0],
            agl_ft=values["agl_ft"][0] * FT_PER_M,
            kias=values["kias"][0],
            roll_deg=values["roll_deg"][0],
            vvi_fpm=values["vvi_fpm"][0],
            age_seconds=age,
        )

    def select(self, heading_mag: float, altitude_indicated_ft: float) -> None:
        """Put ArduPlane in GUIDED and hand it the targets. Bounded to ~3 s.

        The gate holds its lock across this call, so every wait in here has a
        short timeout and a failure raises rather than blocks.
        """
        with self.lock:
            if self._takeover_pending:
                raise ValueError("Pilot took over; release control before commanding again")
        observation = self.observe()
        if not math.isfinite(observation.age_seconds) or observation.age_seconds > self.STALE_AFTER_SECONDS:
            raise ValueError("Refusing to take control without fresh telemetry")
        if self.link.heartbeat_age() > self.HEARTBEAT_STALE_SECONDS:
            raise ValueError("Refusing to take control without an ArduPilot heartbeat")
        heading_true, _ = self._aux("heading_true")
        elevation_m, _ = self._aux("elevation_m")
        if not (math.isfinite(heading_true) and math.isfinite(elevation_m)):
            raise ValueError("Missing true heading or elevation telemetry")

        # One writer on the surfaces. Before any MAVLink write, so a failure
        # further down never leaves two controllers engaged.
        self._disengage_autopilot()

        with self._command_lock:
            if self.link.custom_mode() != mav.PLANE_MODE_GUIDED:
                self._enter_guided()

            mag_offset = (heading_true - observation.heading_mag + 180.0) % 360.0 - 180.0
            alt_offset_m = elevation_m - observation.altitude_indicated_ft * M_PER_FT
            target_true = (float(heading_mag) + mag_offset) % 360.0
            target_alt_m = float(altitude_indicated_ft) * M_PER_FT + alt_offset_m

            self._command_altitude(target_alt_m)
            self._command_heading(target_true)

        rc, rc_age = self.link.latest(mav.MSG_RC_CHANNELS)
        with self.lock:
            self._targets = (float(heading_mag) % 360.0, float(altitude_indicated_ft))
            self._mag_offset = mag_offset
            self._alt_offset_m = alt_offset_m
            self._engaged = True
            self._last_fault = None
            self._released_at = None
            self._rc_deviation_since = None
            self._last_retarget = self.clock()
            self._axis_rest = {name: self.samples.get(name, (float("nan"), 0))[0]
                               for name in self.axis_datarefs}
            # The pilot's stick at rest is wherever ArduPilot's RC mapping
            # puts it - not 1500 us - so deviation is measured from here.
            self._rc_rest = self._rc_position(rc) if rc is not None and rc_age < 1.0 else None
            self._last_commands = {
                "mode": mav.PLANE_MODE_GUIDED,
                "heading_true": target_true,
                "altitude_true_m": target_alt_m,
                "mag_offset_deg": mag_offset,
                "alt_offset_ft": alt_offset_m * FT_PER_M,
                "rc_rest_us": self._rc_rest,
            }
        self._ensure_running()

    def secure_on_attach(self, timeout: float = 3.0):
        """Park ArduPlane the instant it attaches, before anything else runs.

        SITL boots with ArduPilot's built-in default Home (Canberra) and may
        come up in a navigating mode: on the first live attach it was in RTL
        and flew CAP 487 to 80 degrees of bank and -4370 fpm within seconds of
        taking the override (AI-23). LOITER holds the current position and
        altitude on auto-throttle and does not use Home, so it is what the
        aircraft should be in while the pre-flight checks run. Home is set to
        the aircraft's own position as well, so a later mode that does use it
        cannot fly to the other side of the planet.

        Raises if ArduPilot will not take the mode - the caller must then
        detach rather than continue.
        """
        with self._command_lock:
            self.link.arm_ack(mav.MAV_CMD_DO_SET_HOME)
            self.link.send(*mav.set_home_here())
            self.link.wait_ack(mav.MAV_CMD_DO_SET_HOME, self.ACK_TIMEOUT)
            if self.link.custom_mode() != mav.PLANE_MODE_LOITER:
                self.link.arm_ack(mav.MAV_CMD_DO_SET_MODE)
                self.link.send(*mav.set_mode(mav.PLANE_MODE_LOITER))
                deadline = self.clock() + timeout
                while self.link.custom_mode() != mav.PLANE_MODE_LOITER:
                    if self.clock() >= deadline:
                        raise ValueError("ArduPilot would not enter LOITER on attach (mode %s)"
                                         % self.link.custom_mode())
                    time.sleep(0.02)
        with self.lock:
            self._last_commands["secured_mode"] = mav.PLANE_MODE_LOITER
        return self.link.custom_mode()

    def release(self) -> None:
        """Hand the aircraft back: clear the heading hold, park ArduPlane.

        The parking mode is LOITER, or FBWA when a valid centred RC position
        was measured at engagement - see `_hand_back`. The X-Plane joystick
        override is left alone here: SITL re-asserts it every frame while it
        lives, so only the launcher, which owns the process, can clear it
        after stopping SITL. Never pauses. Also the acknowledgement of a pilot
        takeover: clears the latch that refuses `select` after one.
        """
        self._hand_back()
        with self.lock:
            self._takeover_pending = False
        self._shutdown()

    def pause(self) -> None:
        """Fault path: stop supervising and freeze the simulator.

        Never touches ArduPilot's mode - on lost telemetry a blind mode change
        is exactly the wrong reflex, the same rule the gate applies. Keeps
        `_engaged`, so a later explicit `release()` still hands back.
        """
        self._shutdown()
        try:
            self.client.set_paused(True)
        except Exception:
            pass

    # -- status -----------------------------------------------------------

    @property
    def flying(self) -> bool:
        with self.lock:
            return self._targets is not None and bool(self._thread and self._thread.is_alive())

    @property
    def last_fault(self):
        with self.lock:
            return self._last_fault

    @property
    def last_commands(self) -> dict:
        with self.lock:
            return dict(self._last_commands)

    def preflight(self) -> dict:
        """What the launcher prints before asking for control. Sends nothing."""
        observation = self.observe()
        heading_true, _ = self._aux("heading_true")
        elevation_m, _ = self._aux("elevation_m")
        gpi, gpi_age = self.link.latest(mav.MSG_GLOBAL_POSITION_INT)
        rc, rc_age = self.link.latest(mav.MSG_RC_CHANNELS)
        hb, _hb_age = self.link.latest(mav.MSG_HEARTBEAT)
        override, _ = self._aux("override_joystick")
        with self.lock:
            axes = {name: self.samples.get(name, (float("nan"), 0))[0] for name in self.axis_datarefs}
        return {
            "xplane_age_s": observation.age_seconds,
            "heartbeat_age_s": self.link.heartbeat_age(),
            "ardupilot_mode": self.link.custom_mode(),
            "armed": bool(hb["base_mode"] & mav.MAV_MODE_FLAG_SAFETY_ARMED) if hb else False,
            "mag_offset_deg": ((heading_true - observation.heading_mag + 180.0) % 360.0 - 180.0)
                              if math.isfinite(heading_true) else float("nan"),
            "alt_offset_ft": (elevation_m * FT_PER_M - observation.altitude_indicated_ft)
                             if math.isfinite(elevation_m) else float("nan"),
            "ardupilot_minus_xplane_true_ft": ((gpi["alt"] / 1000.0 - elevation_m) * FT_PER_M
                                               if gpi and math.isfinite(elevation_m) else float("nan")),
            "gpi_age_s": gpi_age,
            "rc_age_s": rc_age,
            "rc_position_us": self._rc_position(rc) if rc is not None else None,
            "override_joystick": override,
            "joystick_axes": axes,
        }

    def readback_after_release(self):
        """(override_joystick value, seconds since release) - trial case T4 evidence."""
        with self.lock:
            released = self._released_at
        value, _age = self._aux("override_joystick")
        return value, (self.clock() - released) if released is not None else None

    # -- ArduPilot commands ----------------------------------------------

    def _disengage_autopilot(self) -> None:
        try:
            self.client.send_command(self.AUTOPILOT_OFF_COMMAND)
        except Exception:
            # An autopilot that is already off must never block taking control.
            pass

    def _enter_guided(self) -> None:
        """DO_SET_MODE GUIDED, confirmed by a heartbeat reporting the mode.

        Caller holds `_command_lock`. The ACK comes first, so a refusal is
        reported as such; then the mode is polled, which is why the link asks
        for heartbeats at 5 Hz rather than the 1 Hz default.
        """
        self.link.arm_ack(mav.MAV_CMD_DO_SET_MODE)
        self.link.send(*mav.set_mode(mav.PLANE_MODE_GUIDED))
        result = self.link.wait_ack(mav.MAV_CMD_DO_SET_MODE, self.ACK_TIMEOUT)
        if result is not None and result != mav.MAV_RESULT_ACCEPTED:
            raise ValueError("ArduPilot refused GUIDED (MAV_RESULT %d)" % result)
        deadline = self.clock() + self.MODE_CHANGE_TIMEOUT
        while self.link.custom_mode() != mav.PLANE_MODE_GUIDED:
            if self.clock() >= deadline:
                raise ValueError("ArduPilot did not enter GUIDED")
            time.sleep(0.02)

    def _acked(self, command: int, msgid: int, fields: dict, what: str) -> None:
        """Caller holds `_command_lock`."""
        self.link.arm_ack(command)
        self.link.send(msgid, fields)
        result = self.link.wait_ack(command, self.ACK_TIMEOUT)
        if result is None:
            raise ValueError("ArduPilot did not acknowledge %s" % what)
        if result != mav.MAV_RESULT_ACCEPTED:
            raise ValueError("ArduPilot refused %s (MAV_RESULT %d)" % (what, result))

    def _command_altitude(self, alt_true_m: float) -> None:
        if not math.isfinite(alt_true_m) or math.isclose(alt_true_m, 0.0, abs_tol=0.01) \
                or math.isclose(alt_true_m, -1.0, abs_tol=0.01):
            # ArduPlane answers DENIED to a z of exactly 0 or -1; refuse before
            # sending so the failure is ours to explain, not a bare MAV_RESULT.
            raise ValueError("Altitude target %.2f m is not accepted by ArduPilot" % alt_true_m)
        msgid, fields = mav.guided_change_altitude(alt_true_m, mav.MAV_FRAME_GLOBAL, self.CLIMB_RATE_M_S)
        self._acked(mav.MAV_CMD_GUIDED_CHANGE_ALTITUDE, msgid, fields, "altitude")

    def _command_heading(self, heading_true: float) -> None:
        msgid, fields = mav.guided_change_heading(mav.HEADING_TYPE_HEADING, heading_true % 360.0,
                                                  self.HEADING_ACCEL_M_S2)
        self._acked(mav.MAV_CMD_GUIDED_CHANGE_HEADING, msgid, fields, "heading")

    def _hand_back(self) -> None:
        """Clear the heading hold and leave ArduPlane in a mode that is safe
        for whatever holds the aircraft next - only if this backend engaged,
        and only once, whichever thread gets here first.

        LOITER flies itself with no RC input. FBWA hands the pilot a
        stabilised, limited aircraft but takes throttle from the stick, so it
        is offered only when a valid, centred RC position was measured at
        engagement. MANUAL is never used: it passes the raw stick to the
        surfaces, and an unmapped axis reads as full aileron and full throttle.
        """
        with self.lock:
            engaged, self._engaged = self._engaged, False
            rc_proven = self._rc_rest is not None
        if not engaged:
            return
        mode = mav.PLANE_MODE_FBWA if rc_proven else mav.PLANE_MODE_LOITER
        for msgid, fields in (
            mav.guided_change_heading(mav.HEADING_TYPE_DEFAULT, 0.0, 0.0),
            mav.set_mode(mode),
        ):
            try:
                self.link.send(msgid, fields)
            except OSError:
                pass
        with self.lock:
            self._released_at = self.clock()
            self._last_commands["mode"] = mode
            self._last_commands["hand_back_mode"] = "FBWA" if rc_proven else "LOITER"

    # -- supervision ------------------------------------------------------

    def _aux(self, name: str):
        with self.lock:
            value, stamp = self.samples.get(name, (float("nan"), -float("inf")))
        return value, self.clock() - stamp

    def _ensure_running(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="arduplane-backend", daemon=True)
        self._thread.start()

    def _shutdown(self) -> None:
        self._stop.set()
        thread = self._thread
        # release() and pause() are called from the supervisory thread itself
        # on a detected fault or takeover; a thread cannot join itself.
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        with self.lock:
            self._targets = None
            self._rc_deviation_since = None

    def _fault(self, reason: str) -> None:
        with self.lock:
            self._last_fault = reason
        self.pause()

    def _lost_ardupilot(self) -> None:
        """No heartbeat: nobody is flying, and SITL's joystick override would
        leave the yoke dead. Give the yoke back to X-Plane, then freeze."""
        with self.lock:
            self._last_fault = "ArduPilot heartbeat lost"
        for ref in self.OVERRIDE_DREFS:
            try:
                self.client.send_dref(ref, 0)
            except Exception:
                pass
        self.pause()

    def _takeover(self, reason: str) -> None:
        """The pilot (or another controller) has the aircraft: hand back and
        refuse further commands until `release()` acknowledges it."""
        with self.lock:
            self._last_fault = reason
            self._takeover_pending = True
        self._hand_back()
        self._shutdown()

    def _envelope_fault(self, observation) -> str | None:
        """Second line of defence: do not rely on the gate noticing first."""
        if not all(math.isfinite(v) for v in (
            observation.heading_mag, observation.altitude_indicated_ft, observation.agl_ft,
            observation.kias, observation.roll_deg, observation.vvi_fpm,
        )):
            return "Missing or invalid telemetry"
        if observation.age_seconds > self.STALE_AFTER_SECONDS:
            return "Stale telemetry"
        limits = self.limits
        if limits is None:
            return None
        if not limits.min_kias <= observation.kias <= limits.max_kias:
            return "Airspeed outside exercise envelope"
        if observation.agl_ft < limits.min_agl_ft:
            return "Below clearance floor"
        if abs(observation.roll_deg) > limits.max_bank_deg:
            return "Bank outside exercise envelope"
        return None

    def _rc_position(self, rc: dict):
        """The three primary channels, or None when ArduPilot has no usable
        RC (no receiver, fewer than four channels, values off the PWM scale)."""
        if rc is None or rc.get("chancount", 0) < 4:
            return None
        low, high = self.RC_VALID_US
        position = tuple(rc[name] for name in self.RC_CHANNELS)
        if not all(low <= value <= high for value in position):
            return None
        return position

    def _rc_deviation(self, rc: dict, rest) -> float:
        position = self._rc_position(rc)
        if position is None or rest is None:
            return float("nan")
        return max(abs(now - then) for now, then in zip(position, rest))

    def _pilot_input(self) -> str | None:
        """Either detector, independently: ArduPilot's view of the RC input,
        and X-Plane's raw joystick axes that keep moving under the override."""
        now = self.clock()
        rc, rc_age = self.link.latest(mav.MSG_RC_CHANNELS)
        with self.lock:
            rest = self._rc_rest
        deviation = self._rc_deviation(rc, rest) if rc_age < 1.0 else float("nan")
        if math.isfinite(deviation) and deviation > self.RC_DEADBAND_US:
            with self.lock:
                since = self._rc_deviation_since
                if since is None:
                    self._rc_deviation_since = since = now
            if now - since >= self.RC_HOLD_SECONDS:
                return "pilot input on RC channels"
        else:
            with self.lock:
                self._rc_deviation_since = None
        with self.lock:
            axis_rest = dict(self._axis_rest)
            axes = {name: self.samples.get(name, (float("nan"), 0))[0] for name in self.axis_datarefs}
        for name, value in axes.items():
            baseline = axis_rest.get(name, float("nan"))
            if math.isfinite(value) and math.isfinite(baseline) and abs(value - baseline) > self.AXIS_DEADBAND:
                return "pilot moved the yoke (%s)" % name
        return None

    def _retarget_altitude_if_drifted(self, observation, targets) -> None:
        _heading, target_alt_ft = targets
        now = self.clock()
        if abs(observation.vvi_fpm) >= self.RETARGET_VVI_FPM:
            return
        if abs(observation.altitude_indicated_ft - target_alt_ft) <= self.ALT_RETARGET_FT:
            return
        if now - self._last_retarget < self.RETARGET_MIN_INTERVAL:
            return
        elevation_m, age = self._aux("elevation_m")
        if not math.isfinite(elevation_m) or age > self.STALE_AFTER_SECONDS:
            return
        if not self._command_lock.acquire(blocking=False):
            return      # the gate thread is mid-command; try again next tick
        try:
            alt_offset_m = elevation_m - observation.altitude_indicated_ft * M_PER_FT
            target_alt_m = target_alt_ft * M_PER_FT + alt_offset_m
            self._command_altitude(target_alt_m)
        finally:
            self._command_lock.release()
        with self.lock:
            self._alt_offset_m = alt_offset_m
            self._last_retarget = now
            self._last_commands["altitude_true_m"] = target_alt_m
            self._last_commands["alt_offset_ft"] = alt_offset_m * FT_PER_M
            self._last_commands["retargets"] = self._last_commands.get("retargets", 0) + 1

    def _step(self, observation, targets) -> bool:
        """One supervisory pass. Returns False when the loop must stop.

        Pilot input is checked before the envelope: a takeover that briefly
        exceeds the bank limit must release, not pause.
        """
        reason = self._pilot_input()
        if reason:
            self._takeover(reason)
            return False
        fault = self._envelope_fault(observation)
        if fault:
            self._fault(fault)
            return False
        if self.link.heartbeat_age() > self.HEARTBEAT_STALE_SECONDS:
            self._lost_ardupilot()
            return False
        mode = self.link.custom_mode()
        if mode != mav.PLANE_MODE_GUIDED:
            self._takeover("ArduPilot left GUIDED (mode %s)" % mode)
            return False
        ap_mode, ap_age = self._aux("ap_mode")
        if math.isfinite(ap_mode) and ap_age < 1.0 and int(ap_mode) == 2:
            self._takeover("aircraft autopilot engaged while ArduPilot was flying")
            return False
        gpi, gpi_age = self.link.latest(mav.MSG_GLOBAL_POSITION_INT)
        elevation_m, elevation_age = self._aux("elevation_m")
        if gpi is not None and gpi_age < 1.0 and math.isfinite(elevation_m) and elevation_age < 1.0:
            disagreement_ft = abs(gpi["alt"] / 1000.0 - elevation_m) * FT_PER_M
            if disagreement_ft > self.ALT_SANITY_FT:
                self._fault("ArduPilot altitude disagrees with X-Plane by %.0f ft" % disagreement_ft)
                return False
        self._retarget_altitude_if_drifted(observation, targets)
        rc, _ = self.link.latest(mav.MSG_RC_CHANNELS)
        override, _ = self._aux("override_joystick")
        with self.lock:
            self._last_commands["rc_deviation_us"] = self._rc_deviation(rc, self._rc_rest)
            self._last_commands["override_joystick"] = override
        return True

    def _run(self) -> None:
        period = 1.0 / self.LOOP_HZ
        while not self._stop.is_set():
            with self.lock:
                targets = self._targets
            if targets is None:
                break
            try:
                if not self._step(self.observe(), targets):
                    break
            except Exception as error:  # a supervisor must never die silently mid-air
                self._fault(str(error))
                break
            time.sleep(period)
