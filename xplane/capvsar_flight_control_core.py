"""Deterministic simulator-side actuator arbiter. No X-Plane import here.

The plugin supplies a sink; tests supply a stateful fake. Independent SITL DREF
packets are never treated as an atomic frame. A session namespace is fixed for
one plugin start and retired permanently after takeover or fault.
"""
from __future__ import annotations

import math
import time

try:
    from .capvsar_flight_control_mapping import candidate_prefix
except ImportError:  # XPPython3 loads sibling modules without a package.
    from capvsar_flight_control_mapping import candidate_prefix

CHANNELS = ("roll", "pitch", "yaw", "throttle", "flap", "trim")
ARDUPLANE_CHANNELS = CHANNELS[:-1]
RANGES = {"roll": (-1.0, 1.0), "pitch": (-1.0, 1.0),
          "yaw": (-1.0, 1.0), "throttle": (0.0, 1.0), "flap": (0.0, 1.0),
          "trim": (-1.0, 1.0), "brake": (0.0, .35), "prop": (0.0, 1.0)}


class ControlBridge:
    CANDIDATE_AGE_S = 0.20
    CANDIDATE_SKEW_S = 0.08
    EXECUTIVE_AGE_S = 0.40
    TRANSFER_TIMEOUT_S = 1.0
    ATOMIC_STALL_GAP_S = 0.20
    MAX_CONSECUTIVE_STALL_GRACES = 3

    def __init__(self, sink, session: str, clock=time.monotonic, *, atomic=False,
                 channels=CHANNELS, brake_max=.35):
        self.sink, self.session, self.clock = sink, session, clock
        self.channels = tuple(channels)
        if (not set(CHANNELS) <= set(self.channels) or len(set(self.channels)) != len(self.channels)
                or not set(self.channels) <= set(RANGES) or (set(self.channels) & {"brake", "prop"} and not atomic)):
            raise ValueError("Invalid actuator channel set")
        if (type(brake_max) not in (int, float) or not math.isfinite(brake_max)
                or not .35 <= brake_max <= 1.0):
            raise ValueError("Invalid brake limit")
        self.brake_max = float(brake_max)
        self.prefix = candidate_prefix(session)
        self.generation = 0
        self.state = "MANUAL"
        self.owner = "HUMAN"
        self.candidates = {}
        self.last_heartbeat = None
        self.transfer_deadline = None
        self.retired = False
        self.fault_reason = None
        self.trim_hold = None
        self.used_sessions = {session}
        self.atomic = atomic
        self.frame_sequence = -1
        self.frame_deadline = None
        self.frame_generation = None
        self.last_tick_time = None
        self.last_tick_gap_s = 0.
        self.frame_stall_graces = 0
        self.heartbeat_stall_graces = 0
        self.pause_confirmed = False

    def candidate(self, session: str, channel: str, value: float) -> None:
        if self.atomic:
            return  # Independent packets cannot modify an atomic session.
        if session != self.session or channel not in CHANNELS or self.retired:
            return
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            self.candidates.pop(channel, None)
            return
        low, high = RANGES[channel]
        if not low <= value <= high:
            self.candidates.pop(channel, None)
            return
        self.candidates[channel] = (float(value), self.clock())

    def submit_frame(self, session, generation, sequence, expires_at, controls):
        """Accept an entire frame or nothing. Expiry uses host monotonic seconds.

        Both endpoints run on the same host (Unix socket); no remote wall clocks.
        Validation never extends a lease or changes previously accepted output.
        A prepare increments generation, requiring a new frame before activation.
        """
        now = self.clock()
        if not self.atomic or self.retired or session != self.session:
            raise ValueError("Invalid atomic session")
        if type(generation) is not int or generation != self.generation:
            raise ValueError("Wrong frame generation")
        if type(sequence) is not int or sequence <= self.frame_sequence:
            raise ValueError("Frame sequence must increase")
        if (type(expires_at) not in (int, float) or not math.isfinite(expires_at)
                or not now < expires_at <= now + self.CANDIDATE_AGE_S):
            raise ValueError("Frame expiry outside lease window")
        if not isinstance(controls, dict) or set(controls) != set(self.channels):
            raise ValueError("Complete actuator frame required")
        for channel, value in controls.items():
            low, high = (0., self.brake_max) if channel == "brake" else RANGES[channel]
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not low <= value <= high):
                raise ValueError("Invalid actuator: %s" % channel)
        # Timely replacement frames break a stall streak; late replacements
        # keep it so a slow controller cannot renew grace indefinitely.
        if self.frame_deadline is None or now < self.frame_deadline:
            self.frame_stall_graces = 0
        self.candidates = {c: (float(controls[c]), now) for c in self.channels}
        self.frame_sequence = sequence
        self.frame_deadline = expires_at
        self.frame_generation = generation
        return self.status()

    def renew_session(self, session: str, expected_generation: int) -> dict:
        """Allow a new managed writer only while Garmin alone has authority.

        A retired DREF namespace is never reused. The caller must stage a new
        SITL mapping and wait for that session's candidate readiness before
        attempting the next transfer.
        """
        prefix = candidate_prefix(session)
        if (self.state != "GFC700" or self.owner != "GFC700" or not self.retired
                or expected_generation != self.generation or session in self.used_sessions):
            raise ValueError("Fresh session requires verified Garmin authority and generation")
        if self.sink.ap_engaged() is not True or self.sink.override_state() is not False:
            raise ValueError("Garmin ownership readback unavailable for new session")
        self.session, self.prefix = session, prefix
        self.used_sessions.add(session)
        self.candidates.clear()
        self.retired = False
        self.frame_sequence = -1
        self.frame_deadline = None
        self.frame_generation = None
        self.frame_stall_graces = 0
        self.generation += 1
        self.last_heartbeat = self.clock()
        self.heartbeat_stall_graces = 0
        return self.status()

    def _fresh(self):
        if self.atomic:
            if self.frame_generation != self.generation:
                raise ValueError("No frame for current generation")
            if self.frame_deadline is None:
                raise ValueError("Atomic frame expired")
            if self.clock() >= self.frame_deadline:
                # A few late callbacks are tolerated for cold-start and brief
                # stalls. Only an in-time replacement frame resets the streak.
                if (self.last_tick_gap_s <= self.ATOMIC_STALL_GAP_S
                        or self.frame_stall_graces >= self.MAX_CONSECUTIVE_STALL_GRACES):
                    raise ValueError("Atomic frame expired")
                self.frame_stall_graces += 1
        required = self.channels if self.owner == "DIRECT" else ARDUPLANE_CHANNELS
        if not set(required) <= set(self.candidates):
            raise ValueError("Incomplete candidate output")
        if not self.atomic:
            stamps = [self.candidates[c][1] for c in required]
            if self.clock() - min(stamps) > self.CANDIDATE_AGE_S:
                raise ValueError("Stale candidate output")
            if max(stamps) - min(stamps) > self.CANDIDATE_SKEW_S:
                raise ValueError("Skewed independent candidate packets")
        return {c: self.candidates[c][0] for c in required}

    def prepare(self, owner: str, session: str, expected_generation: int) -> dict:
        if self.retired or session != self.session or owner not in ("ARDUPLANE", "DIRECT"):
            raise ValueError("Invalid or retired output session")
        if self.state not in ("MANUAL", "GFC700") or expected_generation != self.generation:
            raise ValueError("Control generation or transfer state changed")
        prior_owner = self.owner
        self.owner = owner
        try:
            self._fresh()
        except Exception:
            self.owner = prior_owner
            raise
        self.generation += 1
        self.state = "PREPARING"
        now = self.clock()
        if (self.last_heartbeat is None
                or now - self.last_heartbeat <= self.EXECUTIVE_AGE_S):
            self.heartbeat_stall_graces = 0
        self.last_heartbeat = now
        return self.status()

    def heartbeat(self, session: str, generation: int) -> None:
        if (session != self.session or generation != self.generation
                or (self.retired and self.state != "GFC700")
                or self.state not in ("PREPARING", "WAIT_AP_OFF", "ACTIVE", "WAIT_GFC", "GFC700")):
            raise ValueError("Revoked executive heartbeat")
        now = self.clock()
        if (self.last_heartbeat is None
                or now - self.last_heartbeat <= self.EXECUTIVE_AGE_S):
            self.heartbeat_stall_graces = 0
        self.last_heartbeat = now

    def activate(self, session: str, generation: int) -> dict:
        if session != self.session or generation != self.generation or self.state != "PREPARING":
            raise ValueError("Transfer is not prepared for this generation")
        self._fresh()
        ap = self.sink.ap_engaged()
        if ap is None:
            self._fault("Garmin servo readback unknown")
            raise ValueError("Garmin servo readback unknown")
        if ap:
            self.sink.command_ap_off()
            self.state = "WAIT_AP_OFF"
            self.transfer_deadline = self.clock() + self.TRANSFER_TIMEOUT_S
        else:
            try:
                self._activate_external()
            except Exception as error:
                self._fault("External controller activation failed: %s" % error)
                raise
        return self.status()

    def _activate_external(self):
        outputs = self._fresh()
        if self.sink.ap_engaged() is not False:
            raise ValueError("Garmin servos not confirmed off")
        if self.owner == "ARDUPLANE":
            self.trim_hold = self.sink.read_trim()
            if not isinstance(self.trim_hold, (int, float)) or not math.isfinite(self.trim_hold):
                raise ValueError("Measured trim unavailable for ArduPlane handoff")
            outputs["trim"] = self.trim_hold
        try:
            self.sink.set_override(True)
            confirmed = self.sink.override_state() is True
        except Exception as error:
            self._fault("Native control override request failed: %s" % error)
            return
        if not confirmed:
            self._fault("Native control override not confirmed")
            return
        self.state = "ACTIVE"
        try:
            for channel, value in outputs.items():
                self.sink.write_control(channel, value)
        except Exception as error:
            self._fault("Actuator write failed: %s" % error)

    def transfer_gfc(self, generation: int, ready: bool) -> dict:
        if generation != self.generation or self.state not in ("ACTIVE", "MANUAL") or not ready:
            raise ValueError("Garmin transfer not ready for this generation")
        if self.state == "ACTIVE":
            self.sink.set_override(False)
        if self.sink.override_state() is not False:
            self._fault("External override did not release")
            return self.status()
        self.candidates.clear()
        self.trim_hold = None
        ap = self.sink.ap_engaged()
        if ap is None:
            self._fault("Garmin servo readback unknown")
            return self.status()
        if not ap:
            self.sink.command_ap_on()
        self.state = "WAIT_GFC"
        self.last_heartbeat = self.clock()
        self.transfer_deadline = self.clock() + self.TRANSFER_TIMEOUT_S
        return self.status()

    def set_virtual_aux(self, channel: str, value: float, session: str,
                        expected_generation: int) -> dict:
        """GFC-owned power/configuration output through the same bridge fence."""
        if (self.state != "GFC700" or self.owner != "GFC700"
                or session != self.session or expected_generation != self.generation):
            raise ValueError("Virtual pilot has no current Garmin authority")
        if (channel not in ("throttle", "flap") or type(value) not in (int, float)
                or not math.isfinite(value) or not 0 <= value <= 1):
            raise ValueError("Invalid bounded virtual-pilot action")
        if self.sink.ap_engaged() is not True or self.sink.override_state() is not False:
            self._fault("Garmin authority changed during virtual-pilot action")
            raise ValueError("Garmin authority readback lost")
        try:
            self.sink.write_control(channel, float(value))
            actual = self.sink.read_control(channel)
        except Exception as error:
            self._fault("Virtual-pilot output failed: %s" % error)
            raise
        if (not isinstance(actual, (int, float)) or not math.isfinite(actual)
                or abs(actual - value) > 0.05):
            self._fault("Virtual-pilot output readback mismatch")
            raise ValueError("Virtual-pilot output not observed")
        return {**self.status(), "channel": channel, "requested": float(value),
                "observed": float(actual)}

    def gfc_select(self, session: str, expected_generation: int, *, heading_mag=None,
                   altitude_ft=None, vs_fpm=None) -> dict:
        """Point the GFC 700 at a heading and/or altitude while it owns the airplane.

        The same fence as set_virtual_aux: only in GFC700 state, for the current
        session and generation, with Garmin authority re-read from the sink. The
        bridge accepts typed, bounded selections and nothing else, and reads the
        selected values back; a mismatch pauses the simulator. `vs_fpm` needs an
        `altitude_ft` to capture, and without it the autopilot holds altitude.
        """
        if (self.state != "GFC700" or self.owner != "GFC700"
                or session != self.session or expected_generation != self.generation):
            raise ValueError("GFC selection has no current Garmin authority")
        if heading_mag is None and altitude_ft is None:
            raise ValueError("GFC selection needs a heading or an altitude")
        for name, value, low, high in (("heading", heading_mag, 0., 360.),
                                       ("altitude", altitude_ft, 500., 12000.),
                                       ("vertical speed", vs_fpm, -1000., 1000.)):
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)
                                      or not low <= value <= high):
                raise ValueError("GFC %s outside bounds" % name)
        if vs_fpm is not None and altitude_ft is None:
            raise ValueError("A vertical speed needs an altitude to capture")
        if self.sink.ap_engaged() is not True or self.sink.override_state() is not False:
            self._fault("Garmin authority changed during GFC selection")
            raise ValueError("Garmin authority readback lost")
        try:
            observed = self.sink.gfc_select(heading_mag, altitude_ft, vs_fpm)
        except Exception as error:
            self._fault("GFC selection failed: %s" % error)
            raise
        expected = (("heading_bug", heading_mag, 1.0), ("altitude_bug", altitude_ft, 1.0),
                    ("vs_bug", vs_fpm, 1.0))
        for key, wanted, tolerance in expected:
            if wanted is None:
                continue
            got = observed.get(key)
            if (not isinstance(got, (int, float)) or not math.isfinite(got)
                    or abs((got - wanted + 180) % 360 - 180 if key == "heading_bug" else got - wanted) > tolerance):
                self._fault("GFC selection readback mismatch: %s" % key)
                raise ValueError("GFC selection not observed")
        return {**self.status(), "selected": observed}

    def human_takeover(self, reason: str) -> dict:
        prior = self.state
        self.generation += 1
        self.retired = True
        self.candidates.clear()
        self.trim_hold = None
        self.owner = "HUMAN"
        self.state = "WAIT_HUMAN"
        self.transfer_deadline = self.clock() + self.TRANSFER_TIMEOUT_S
        if prior in ("ACTIVE", "WAIT_GFC", "WAIT_AP_OFF"):
            try:
                self.sink.set_override(False)
                if self.sink.override_state() is not False:
                    raise RuntimeError("Native override still active")
            except Exception as error:
                self._fault("Human takeover not confirmed: %s" % error)
                return self.status()
        if prior in ("GFC700", "WAIT_GFC") or self.sink.ap_engaged() is True:
            self.sink.command_ap_off()
        if self.sink.override_state() is False and self.sink.ap_engaged() is False:
            self.state = "MANUAL"
        return self.status()

    def fault_pause(self, reason: str) -> dict:
        self._fault(reason)
        return self.status()

    def _fault(self, reason: str):
        if self.state in ("PAUSED_FAULT", "FAULT_PAUSE_PENDING"):
            return
        self.generation += 1
        self.retired = True
        self.candidates.clear()
        self.fault_reason = reason
        self.owner = "FAULT"
        self.state = "FAULT_PAUSE_PENDING"
        try:
            self.sink.pause()
        except Exception as error:
            self.fault_reason += "; pause request failed: %s" % error
        finally:
            try:
                self.sink.set_override(False)
            except Exception as error:
                self.fault_reason += "; override release failed: %s" % error
        self._confirm_pause()

    def _confirm_pause(self):
        try:
            self.pause_confirmed = self.sink.is_paused() is True
        except Exception:
            self.pause_confirmed = False
        self.state = "PAUSED_FAULT" if self.pause_confirmed else "FAULT_PAUSE_PENDING"

    def tick(self) -> dict:
        now = self.clock()
        self.last_tick_gap_s = (0. if self.last_tick_time is None else now - self.last_tick_time)
        self.last_tick_time = now
        if self.state in ("FAULT_PAUSE_PENDING", "PAUSED_FAULT"):
            self._confirm_pause()
        if self.state in ("PREPARING", "WAIT_AP_OFF", "ACTIVE", "WAIT_GFC", "GFC700"):
            if self.last_heartbeat is None or now - self.last_heartbeat > self.EXECUTIVE_AGE_S:
                if (self.state in ("ACTIVE", "WAIT_GFC", "GFC700")
                        and self.last_tick_gap_s > self.ATOMIC_STALL_GAP_S
                        and self.heartbeat_stall_graces < self.MAX_CONSECUTIVE_STALL_GRACES
                        and (self.state != "ACTIVE"
                             or self.frame_stall_graces < self.MAX_CONSECUTIVE_STALL_GRACES)):
                    # A few cold-start or resumed callbacks are allowed; an
                    # in-time heartbeat and frame must arrive to reset a streak.
                    self.heartbeat_stall_graces += 1
                    if self.state == "ACTIVE":
                        # DIRECT also needs the frame lease to get one fresh
                        # packet on the resumed callback; _fresh enforces the
                        # hard stop on the following normal callback.
                        self.last_heartbeat = now
                else:
                    self._fault("Executive heartbeat expired")
                    return self.status()
        if self.state == "WAIT_AP_OFF":
            if self.sink.ap_engaged() is False:
                try:
                    self._activate_external()
                except ValueError as error:
                    self._fault(str(error))
            elif now > self.transfer_deadline:
                self._fault("Garmin disengagement not observed")
        elif self.state == "ACTIVE":
            try:
                outputs = self._fresh()
            except ValueError as error:
                self._fault(str(error))
            else:
                if self.sink.ap_engaged() is not False or self.sink.override_state() is not True:
                    self._fault("Actuator ownership readback changed")
                else:
                    if self.owner == "ARDUPLANE":
                        outputs["trim"] = self.trim_hold
                    try:
                        for channel, value in outputs.items():
                            self.sink.write_control(channel, value)
                    except Exception as error:
                        self._fault("Actuator write failed: %s" % error)
        elif self.state == "WAIT_GFC":
            if self.sink.ap_engaged() is True and self.sink.override_state() is False:
                self.state = "GFC700"
                self.owner = "GFC700"
                self.generation += 1
                self.retired = True
            elif now > self.transfer_deadline:
                self._fault("Garmin engagement not observed")
        elif self.state == "WAIT_HUMAN":
            if self.sink.override_state() is False and self.sink.ap_engaged() is False:
                self.state = "MANUAL"
            elif now > self.transfer_deadline:
                self._fault("Human takeover servo/override release not observed")
        return self.status()

    def status(self) -> dict:
        return {"state": self.state, "owner": self.owner,
                "generation": self.generation, "session": self.session,
                "retired": self.retired, "fault": self.fault_reason,
                "atomic": self.atomic, "frame_sequence": self.frame_sequence,
                "pause_confirmed": self.pause_confirmed}
