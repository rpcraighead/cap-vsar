"""Direct surface-control FlightBackend: flies aircraft that have no autopilot.

`XPlaneAutopilotBackend` commands the simulated aircraft's own autopilot, so it
only works on aircraft that have one. This backend closes the loop on the primary
flight controls instead, which makes the same maneuver contract usable on any
aircraft — a Cub, a glider, an older CAP airframe.

It deliberately implements the EXISTING `maneuvers.FlightBackend` protocol —
``observe`` / ``select(heading_mag, altitude_indicated_ft)`` / ``release`` /
``pause`` — rather than widening it. Two reasons:

* `ManeuverGate` validates *targets* against the exercise envelope. A target is
  checkable ("is 4,500 ft inside the altitude block, is it above the clearance
  floor?"); a raw surface deflection is not. Exposing surfaces through the gate
  would keep the lease and sequencing but hollow out the envelope check.
* A future ArduPlane adapter fits the same shape: command modes and targets, let
  the controller fly the surfaces. Widening the contract to surfaces would make
  ArduPlane harder to adopt, not easier.

So the gate, the control lease, the strictly increasing sequence, the envelope
and the capture detection are all unchanged and still meaningful.

SAFETY. This backend writes to primary flight controls, which is what tracker
item AI-1 retired the legacy scripted entrypoints for. It is therefore built to
fail safe:

* controls are only written while a `select` is active; `release` and `pause`
  stop the loop and neutralize;
* a telemetry watchdog neutralizes and stops if observations go stale;
* the loop re-checks the exercise envelope itself, so a fault does not depend
  on the gate noticing first;
* every output is hard clamped, and the commanded bank is limited well inside
  the gate's own bank limit.

NOT YET FLOWN. The control laws below are unvalidated in the simulator. They are
deliberately gentle and are expected to need tuning against CAP 487.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

from .maneuvers import Observation


@dataclass(frozen=True)
class TestInput:
    """A bounded, self-terminating control input for airframe characterization.

    Card H0 needs discrete single-axis inputs, which a target-holding loop cannot
    express. A raw surface command is not something the gate can validate - but a
    test input IS: both its magnitude and its duration are checkable, and it ends
    by itself. That is the difference between exposing the controls and exposing a
    bounded probe of them.
    """

    # Not a pytest test class. A bare assignment is not a dataclass field,
    # so this silences collection without becoming part of the frozen record.
    __test__ = False

    axis: str                 # "pitch" | "roll" | "yaw"
    magnitude: float          # signed control ratio, the plateau value
    duration_s: float
    ramp_s: float = 0.5       # rise and fall time
    reference: str = "absolute"  # "absolute" surface ratio or "delta" from hold output

    AXES = ("pitch", "roll", "yaw")
    MAX_MAGNITUDE = 0.25      # well inside the per-axis clamps
    MAX_DURATION_S = 5.0

    def shaped(self, elapsed_s: float) -> float:
        """Trapezoidal input: ramp in, hold, ramp out.

        A step input is not what a pilot applies and not what card H0 asks for -
        it says "small, smooth". A discontinuity also excites transients that say
        more about the step than about the airframe. If the input is too short for
        a full plateau the shape degenerates to a triangle rather than a step.
        """
        if elapsed_s <= 0.0:
            return 0.0
        if elapsed_s >= self.duration_s:
            return 0.0
        ramp = min(self.ramp_s, self.duration_s / 2.0)
        if ramp <= 0.0:
            return self.magnitude
        if elapsed_s < ramp:
            return self.magnitude * (elapsed_s / ramp)
        if elapsed_s > self.duration_s - ramp:
            return self.magnitude * ((self.duration_s - elapsed_s) / ramp)
        return self.magnitude

    def validate(self) -> None:
        if self.axis not in self.AXES:
            raise ValueError("axis must be one of %s" % (self.AXES,))
        if not math.isfinite(self.magnitude) or abs(self.magnitude) > self.MAX_MAGNITUDE:
            raise ValueError("magnitude must be finite and within +/-%.2f" % self.MAX_MAGNITUDE)
        if not math.isfinite(self.duration_s) or not 0.0 < self.duration_s <= self.MAX_DURATION_S:
            raise ValueError("duration must be >0 and <= %.1f s" % self.MAX_DURATION_S)
        if not math.isfinite(self.ramp_s) or self.ramp_s < 0.0:
            raise ValueError("ramp must be finite and non-negative")
        if self.reference not in ("absolute", "delta"):
            raise ValueError("test input reference must be absolute or delta")


def _wrap180(degrees: float) -> float:
    return (degrees + 180.0) % 360.0 - 180.0


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


class Gains:
    """Cascaded outer/inner loop gains and authority limits.

    Conservative by intent: this has to be safe before it is quick.
    """

    # heading -> bank -> aileron
    HEADING_TO_BANK = 1.2
    MAX_BANK_DEG = 25.0          # inside ManeuverGate's own 35 deg limit
    BANK_TO_AILERON = 0.020
    MAX_AILERON = 0.35

    # altitude -> vertical speed -> pitch -> elevator
    ALT_TO_VS = 3.0
    MAX_VS_FPM = 700.0
    # Tuned from the first flight 2026-09-11: 0.004 commanded only 2.8 deg for a
    # 700 fpm deficit and the aircraft climbed ~200 fpm against a 900+ fpm
    # capability. 700 fpm at 125 KTAS is a 3.0 deg flight path angle, so ~7 deg
    # of commanded pitch is the right order. The pitch->elevator loop tracked
    # its command adequately, so only the outer gain changed.
    VS_TO_PITCH = 0.010
    # Altitude trim. The cascade above is proportional throughout, and a pure
    # proportional cascade reaches equilibrium the moment pitch equals its
    # command - which it can do at a standing altitude error, because the pitch
    # that the VS loop asks for at that error is also the attitude that flies
    # level. Card H0 run 4 held 100.0 KIAS, -3 fpm and -0.2 deg of bank for two
    # minutes, 107 ft low, correcting none of it: every loop was satisfied and
    # the aircraft was in the wrong place. This is the term a pilot supplies
    # with the trim wheel, and without it the card's reference condition is not
    # reachable at all.
    ALT_TO_PITCH_I = 0.0002      # deg of pitch bias per ft of error per tick
    ALT_PITCH_I_LIMIT = 4.0      # deg
    MIN_PITCH_DEG = -8.0
    MAX_PITCH_DEG = 10.0
    PITCH_TO_ELEVATOR = 0.030
    MAX_ELEVATOR = 0.40

    # airspeed -> pitch, for speed-on-pitch (cards H1/H3). Pitching up slows down,
    # so a positive speed error (too slow) must pitch DOWN: the gain is negative.
    SPEED_TO_PITCH = -0.55

    # airspeed -> throttle, PI. The first version was a PURE INTEGRATOR at 0.010
    # per tick and 10 Hz, i.e. 0.1 throttle per second per knot of error. An
    # integrator has no way to stop: by the time speed reaches target the throttle
    # is already at a limit and the error must reverse to unwind it. In flight it
    # went bang-bang, 0.150 to 1.000, swinging speed 94.7-108.8 KIAS about a 100
    # target. Proportional gives the immediate response; the integral only trims
    # out what is left.
    SPEED_TO_THROTTLE_P = 0.020      # per knot, immediate
    SPEED_TO_THROTTLE_I = 0.0015     # per knot per tick, trim only
    THROTTLE_I_LIMIT = 0.35          # anti-windup on the integral term alone
    MIN_THROTTLE = 0.15
    MAX_THROTTLE = 1.00

    # Turn coordination. The feedforward alone is open loop and leaves residual
    # sideslip, which changes the lift distribution and biases a roll measurement -
    # left and right then respond differently for reasons that are not the airframe.
    # Closing the loop on sideslip keeps the ball centred so the numbers mean
    # something.
    # Rate damping on the inner loops. The bank loop was pure proportional on
    # bank ANGLE, which has no way to know the aircraft is already rolling: it
    # keeps commanding aileron all the way to wings level and then overshoots
    # through it. Measured on card H0 run 3, the recovery from a -20.7 deg bank
    # saturated the aileron for 1.2 s, reached 14.3 deg/s of roll rate and
    # overshot to +9.2 deg the other way. The rate term is what a pilot does
    # instinctively - lead the roll out - and it is also what makes the response
    # a measurement rather than a pilot-induced oscillation.
    ROLL_RATE_TO_AILERON = 0.022     # per deg/s
    PITCH_RATE_TO_ELEVATOR = 0.030   # per deg/s

    # Surface rate limits, per second of commanded travel. A test input is
    # already ramped, so these never bind during one; what they bind on is the
    # TRANSITION at each end of it, where the command previously stepped from the
    # shaped value straight to whatever the outer loop had accumulated - which
    # after a four-second upset is the clamp. That step is the "abrupt" the pilot
    # saw, and no amount of ramping the input fixes it, because the step is on
    # the other side of the input. A hand on a yoke cannot move full travel in a
    # 100 ms control tick; neither should this.
    AILERON_RATE_PER_S = 0.40
    ELEVATOR_RATE_PER_S = 0.40
    RUDDER_RATE_PER_S = 0.60

    # Elevator trim. Card H0 run 5 engaged on an aircraft the autopilot had left
    # trimmed to +0.432 nose-up. The backend has no trim authority, so it
    # inherited that and fought it with the yoke: full nose-DOWN elevator,
    # saturated at -0.400 for seven seconds, while the aircraft pitched UP to
    # 11.5 deg and climbed at 1,533 fpm. The loop was not wrong, it was
    # out-trimmed - and it had no way to know, because a saturated surface and a
    # slow one look identical from the response alone.
    #
    # This also supplies the card's "trim confidence" observable directly: trim
    # position and trim RATE are what the card asks for, and an autotrim that
    # unloads the yoke measures exactly the trim demand a pilot would feel.
    # Frozen during a pitch test input - trimming out a deliberate input is
    # trimming out the measurement.
    ELEVATOR_TO_TRIM = 0.35         # trim units per second per unit of elevator
    TRIM_DEADBAND = 0.02            # do not chase noise around neutral
    MAX_TRIM_RATE_PER_S = 0.06      # C182 electric trim is roughly full travel in 10 s
    MAX_TRIM = 1.0

    AILERON_TO_RUDDER = 0.25        # adverse-yaw feedforward
    BETA_TO_RUDDER = 0.045          # sideslip feedback, proportional
    BETA_TO_RUDDER_I = 0.0020       # sideslip feedback, integral
    BETA_I_LIMIT = 0.20

    # Left-turning tendency feedforward. A clockwise-turning propeller yaws the
    # aircraft LEFT under power - P-factor, torque, and the slipstream striking
    # the fin - and the effect grows with power and with angle of attack, so it is
    # worst slow and at full throttle: the climb. Proportional feedback alone
    # always lags it and leaves a standing sideslip, which the heading loop then
    # masks by holding a wing down. Anticipating it keeps the ball centred.
    # Scales with throttle and inversely with dynamic pressure.
    RIGHT_RUDDER_FF = 0.070
    RUDDER_FF_REF_KIAS = 100.0
    MAX_RUDDER = 0.35


class XPlaneDirectBackend:
    """Flies heading and altitude targets using the primary flight controls."""

    LOOP_HZ = 10.0
    STALE_AFTER_SECONDS = 2.0

    CONTROL_DREFS = {
        "elevator": "sim/cockpit2/controls/yoke_pitch_ratio",
        "aileron": "sim/cockpit2/controls/yoke_roll_ratio",
        "rudder": "sim/cockpit2/controls/yoke_heading_ratio",
        "throttle": "sim/cockpit2/engine/actuators/throttle_ratio[0]",
    }

    DATAREFS = {
        "heading_mag": "sim/flightmodel/position/mag_psi",
        "altitude_indicated_ft": "sim/cockpit2/gauges/indicators/altitude_ft_pilot",
        "agl_ft": "sim/flightmodel/position/y_agl",
        "kias": "sim/flightmodel/position/indicated_airspeed",
        "roll_deg": "sim/flightmodel/position/phi",
        "vvi_fpm": "sim/flightmodel/position/vh_ind_fpm",
        "pitch_deg": "sim/flightmodel/position/theta",
        "beta_deg": "sim/flightmodel/position/beta",
    }

    # Body rates. Damping terms only: the control law is stable without them,
    # just less well damped, so they are deliberately NOT part of the freshness
    # gate. Letting a missing damping channel declare the whole telemetry stale
    # would neutralize the controls on an airborne aircraft over a signal the
    # loop can fly without. Their age is reported in `last_commands` instead, so
    # a degraded run is visible in the trace rather than silent.
    # Deliberately outside CONTROL_DREFS, which is the set `_neutralize` zeroes.
    # Handing an aircraft back with the trim slammed to neutral is an upset, not
    # a release; the aircraft is left trimmed where it was flying.
    TRIM_DREF = "sim/cockpit2/controls/elevator_trim"

    AUX_DATAREFS = {
        "roll_rate": "sim/flightmodel/position/P",
        "pitch_rate": "sim/flightmodel/position/Q",
        # Read back rather than assumed: the backend does not own the aircraft
        # before it engages, and trim is exactly the surface someone else will
        # have left somewhere unexpected.
        "elevator_trim": TRIM_DREF,
        "aileron_position": CONTROL_DREFS["aileron"],
        "elevator_position": CONTROL_DREFS["elevator"],
        "rudder_position": CONTROL_DREFS["rudder"],
        "throttle_position": CONTROL_DREFS["throttle"],
    }

    def __init__(self, client, limits=None, target_kias=110.0, clock=time.monotonic):
        self.client = client
        self.clock = clock
        self.limits = limits
        # Exercise cruise target. Like the autopilot backend's FLC bug, this is an
        # exercise setting, not a POH performance figure.
        self.target_kias = float(target_kias)
        self.samples = {}
        self.lock = threading.Lock()
        self._targets = None
        self._thread = None
        self._stop = threading.Event()
        self._throttle = 0.55
        self._throttle_i = 0.0
        self._beta_i = 0.0
        self._alt_i = 0.0
        # None until a fresh trim position has been read back from the aircraft.
        # The backend will not write trim it has not first measured: guessing at
        # the trim of an aircraft somebody else has been flying is how run 5
        # started.
        self._trim = None
        self._last_fault = None
        self._engaged = False   # has this backend ever actually taken the controls?
        self._last_commands = {}
        self._test_input = None          # active TestInput, or None
        self._test_input_until = 0.0
        self._test_input_started = 0.0
        self._test_baseline = 0.0
        self._bank_target = None         # commanded bank (card H2), or None
        self._speed_mode = False         # speed-on-pitch (cards H1/H3), or None
        self._speed_target_kias = None
        self._climb_throttle = None
        # Previous commanded surface positions and the time they were sent, for
        # rate limiting. None means "no previous command": the first tick after
        # engaging starts from the limited value rather than slewing from zero.
        self._surface = {"aileron": None, "elevator": None, "rudder": None}
        self._surface_t = None
        self._transfer_baseline = None

        for name, ref in {**self.DATAREFS, **self.AUX_DATAREFS}.items():
            def received(ref, value, name=name):
                with self.lock:
                    self.samples[name] = (value, self.clock())
            client.subscribe_dref(ref, freq_hz=10, callback=received)

    # -- FlightBackend ----------------------------------------------------

    def observe(self) -> Observation:
        with self.lock:
            values = {
                name: self.samples.get(name, (float("nan"), -float("inf")))
                for name in self.DATAREFS
            }
        age = max(self.clock() - sample[1] for sample in values.values())
        return Observation(
            heading_mag=values["heading_mag"][0],
            altitude_indicated_ft=values["altitude_indicated_ft"][0],
            agl_ft=values["agl_ft"][0] * 3.28084,
            kias=values["kias"][0],
            roll_deg=values["roll_deg"][0],
            vvi_fpm=values["vvi_fpm"][0],
            age_seconds=age,
        )

    def select(self, heading_mag: float, altitude_indicated_ft: float) -> None:
        """Arm the control loop on a new target pair.

        Disengages the aircraft's autopilot first. This backend drives the
        primary flight controls directly, so it must own them exclusively: an
        engaged GFC 700 would be driving the servos toward its own targets while
        this loop writes yoke ratios, and the two would fight. The autopilot
        backend hands control back the same way, via servos_off_any.
        """
        observation = self.observe()
        if not math.isfinite(observation.age_seconds) or observation.age_seconds > self.STALE_AFTER_SECONDS:
            raise ValueError("Refusing to take control without fresh telemetry")
        self._transfer_baseline = self._measured_controls()
        self._disengage_autopilot()
        with self.lock:
            self._targets = (float(heading_mag) % 360.0, float(altitude_indicated_ft))
            self._speed_mode = False
            self._bank_target = None
            self._last_fault = None
            self._engaged = True
        self._ensure_running()

    def select_bank(self, bank_deg: float, altitude_indicated_ft: float) -> None:
        """Hold a COMMANDED bank angle and altitude - card H2.

        The heading/altitude mode reaches a bank angle only as a byproduct of
        heading error, so it cannot fly "30 degrees left". This commands it
        directly, still bounded by the same limit the gate enforces.
        """
        if not math.isfinite(bank_deg) or abs(bank_deg) > Gains.MAX_BANK_DEG:
            raise ValueError("commanded bank must be within +/-%.0f degrees" % Gains.MAX_BANK_DEG)
        observation = self.observe()
        if not math.isfinite(observation.age_seconds) or observation.age_seconds > self.STALE_AFTER_SECONDS:
            raise ValueError("Refusing to take control without fresh telemetry")
        self._transfer_baseline = self._measured_controls()
        self._disengage_autopilot()
        with self.lock:
            self._bank_target = float(bank_deg)
            self._targets = (observation.heading_mag, float(altitude_indicated_ft))
            self._speed_mode = False
            self._last_fault = None
            self._engaged = True
        self._ensure_running()

    def select_airspeed(self, kias: float, throttle: float | None = None) -> None:
        """Hold a COMMANDED airspeed on pitch - cards H1 and H3.

        This is the inverse of the cruise mode. Normally altitude is held on pitch
        and speed on throttle; a speed ladder and a Vy climb both need the
        opposite - pitch controls speed, throttle is set and left alone. It is the
        same technique the GFC 700 flies as FLC.

        `throttle` fixed and `kias` held gives a climb or descent at a chosen
        speed; omit `throttle` to keep the current setting.
        """
        limits = self.limits
        if limits is not None and not limits.min_kias <= kias <= limits.max_kias:
            raise ValueError(
                "commanded airspeed %.0f is outside the exercise envelope %.0f-%.0f KIAS"
                % (kias, limits.min_kias, limits.max_kias))
        observation = self.observe()
        if not math.isfinite(observation.age_seconds) or observation.age_seconds > self.STALE_AFTER_SECONDS:
            raise ValueError("Refusing to take control without fresh telemetry")
        self._transfer_baseline = self._measured_controls()
        self._disengage_autopilot()
        with self.lock:
            self._speed_mode = True
            self._speed_target_kias = float(kias)
            self._climb_throttle = None if throttle is None else _clamp(
                float(throttle), Gains.MIN_THROTTLE, Gains.MAX_THROTTLE)
            self._targets = (observation.heading_mag, observation.altitude_indicated_ft)
            self._bank_target = None
            self._last_fault = None
            self._engaged = True
        self._ensure_running()

    def set_flaps(self, ratio: float) -> None:
        """Select flaps - card H4. Configuration, not a flight control."""
        if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
            raise ValueError("flap ratio must be between 0 and 1")
        self.client.send_dref("sim/cockpit2/controls/flap_ratio", float(ratio))

    def apply_test_input(self, test_input: TestInput) -> None:
        """Superimpose a bounded single-axis input, then return to the hold - card H0.

        The other two axes keep holding throughout, so the response measured is
        the response to this axis. The input removes itself after `duration_s`
        whatever else happens, including if the caller goes away.
        """
        test_input.validate()
        with self.lock:
            if self._targets is None:
                raise ValueError("take control with select() before applying a test input")
            axis = {"pitch": "elevator", "roll": "aileron", "yaw": "rudder"}[test_input.axis]
            self._test_baseline = self._last_commands.get(axis, self._surface.get(axis) or 0.0)
            self._test_input = test_input
            self._test_input_started = self.clock()
            self._test_input_until = self.clock() + test_input.duration_s

    @property
    def test_input_active(self) -> bool:
        with self.lock:
            return self._test_input is not None

    def release(self) -> None:
        """Stop emitting controls; the executive/bridge owns the handoff."""
        self._shutdown()

    def pause(self) -> None:
        """Fault path: stop emitting controls, then request a simulator pause."""
        self._shutdown()
        try:
            self.client.set_paused(True)
        except Exception:
            pass

    # -- control loop -----------------------------------------------------

    AUTOPILOT_OFF_COMMAND = "sim/autopilot/servos_off_any"

    def _disengage_autopilot(self) -> None:
        """Drop the aircraft's own autopilot so this backend owns the controls."""
        try:
            self.client.send_command(self.AUTOPILOT_OFF_COMMAND)
        except Exception:
            # Never let an autopilot that is already off block taking control.
            pass

    def _ensure_running(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        # The first demand slews from the measured transfer positions.
        with self.lock:
            self._surface = {k: self._transfer_baseline[k]
                             for k in ("aileron", "elevator", "rudder")}
            self._surface_t = self.clock()
            self._throttle = self._transfer_baseline["throttle"]
        self._thread = threading.Thread(
            target=self._run, name="direct-backend", daemon=True
        )
        self._thread.start()

    def _shutdown(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        with self.lock:
            self._targets = None
            self._test_input = None
            self._bank_target = None
            self._speed_mode = False
            self._surface = {"aileron": None, "elevator": None, "rudder": None}
            self._surface_t = None
            self._alt_i = 0.0
            self._throttle_i = 0.0
            self._trim = None
            engaged, self._engaged = self._engaged, False
        # Only hand back controls this backend actually took. Neutralizing an
        # aircraft that was never commanded is not a safe default - it writes the
        # yoke to centre and the throttle to cruise on an aircraft somebody else
        # is flying, which disturbs their trim for no reason.
        # Revoking the candidate session at the bridge removes native output.
        # An unconditional centre/0.45 write here would disturb a trimmed handoff.

    def _measured_controls(self):
        with self.lock:
            samples = {name: self.samples.get(name)
                       for name in ("aileron_position", "elevator_position",
                                    "rudder_position", "throttle_position")}
        baseline = {}
        for name, sample in samples.items():
            if sample is None or self.clock() - sample[1] > 0.5 or not math.isfinite(sample[0]):
                raise ValueError("Fresh measured control positions required for direct transfer")
            baseline[name.removesuffix("_position")] = sample[0]
        return baseline

    def _neutralize(self) -> None:
        """Centre the controls and close the throttle to idle-cruise.

        Deliberately does NOT cut the throttle to zero: this runs on an airborne
        aircraft, and dropping to idle without warning is its own hazard.
        """
        for name, ref in self.CONTROL_DREFS.items():
            try:
                self.client.send_dref(ref, self.MIN_THROTTLE_ON_RELEASE if name == "throttle" else 0.0)
            except Exception:
                pass

    MIN_THROTTLE_ON_RELEASE = 0.45

    def _envelope_fault(self, observation) -> str | None:
        """Second line of defence: do not rely on the gate noticing first."""
        if not all(
            math.isfinite(v)
            for v in (
                observation.heading_mag,
                observation.altitude_indicated_ft,
                observation.agl_ft,
                observation.kias,
                observation.roll_deg,
                observation.vvi_fpm,
            )
        ):
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

    def _run(self) -> None:
        period = 1.0 / self.LOOP_HZ
        while not self._stop.is_set():
            with self.lock:
                targets = self._targets
            if targets is None:
                break
            observation = self.observe()
            fault = self._envelope_fault(observation)
            if fault:
                with self.lock:
                    self._last_fault = fault
                self.client.set_paused(True)
                break
            try:
                self._step(observation, *targets)
            except Exception as error:  # never let a control loop die noisily mid-air
                with self.lock:
                    self._last_fault = str(error)
                self.client.set_paused(True)
                break
            time.sleep(period)

    def _body_rates(self) -> tuple:
        """Body roll and pitch rates for the damping terms, and their age.

        Returns zero for a channel that is absent, stale or non-finite, which
        degrades the damping rather than the loop. The age is returned so the
        caller can record that the run was flown degraded - a zero that means
        "not rolling" and a zero that means "no data" must never look alike in a
        flight-test trace.
        """
        out = {}
        age = 0.0
        with self.lock:
            now = self.clock()
            for name in ("roll_rate", "pitch_rate"):
                value, stamp = self.samples.get(name, (float("nan"), -float("inf")))
                sample_age = now - stamp
                if not math.isfinite(value) or sample_age > self.STALE_AFTER_SECONDS:
                    out[name] = 0.0
                    age = float("inf")
                else:
                    out[name] = value
                    age = max(age, sample_age)
        return out, age

    def _step(self, observation, target_heading: float, target_altitude: float) -> None:
        g = Gains

        # Resolve any active test input up front, so the outer loops can see that
        # a deliberate disturbance is in progress rather than integrating against
        # it. Expiry is checked here rather than by a timer, so the input cannot
        # outlive the control loop that is applying it.
        with self.lock:
            test_input = self._test_input
            started = self._test_input_started
            if test_input is not None and self.clock() >= self._test_input_until:
                self._test_input = test_input = None
        test_axis = test_input.axis if test_input else None
        shaped = test_input.shaped(self.clock() - started) if test_input else 0.0

        # lateral: either a commanded bank (H2) or bank derived from heading error
        with self.lock:
            bank_target = self._bank_target
        if bank_target is None:
            heading_error = _wrap180(target_heading - observation.heading_mag)
            bank_command = _clamp(
                heading_error * g.HEADING_TO_BANK, -g.MAX_BANK_DEG, g.MAX_BANK_DEG
            )
        else:
            bank_command = _clamp(bank_target, -g.MAX_BANK_DEG, g.MAX_BANK_DEG)
        rates, rate_age = self._body_rates()
        roll_rate, pitch_rate = rates["roll_rate"], rates["pitch_rate"]
        aileron = _clamp(
            (bank_command - observation.roll_deg) * g.BANK_TO_AILERON
            - roll_rate * g.ROLL_RATE_TO_AILERON,
            -g.MAX_AILERON,
            g.MAX_AILERON,
        )

        with self.lock:
            speed_mode = self._speed_mode
            speed_target = self._speed_target_kias
            climb_throttle = self._climb_throttle
        if speed_mode:
            # H1/H3: pitch holds SPEED, throttle is set and left alone. Pitching
            # up slows the aircraft, so the sign is inverted relative to the
            # altitude loop.
            speed_error = speed_target - observation.kias
            vs_command = None
            self._alt_i = 0.0          # altitude is not being held in this mode
            pitch_command = _clamp(
                speed_error * g.SPEED_TO_PITCH, g.MIN_PITCH_DEG, g.MAX_PITCH_DEG)
        else:
            # cruise: altitude -> vertical speed -> pitch -> elevator
            altitude_error = target_altitude - observation.altitude_indicated_ft
            vs_command = _clamp(altitude_error * g.ALT_TO_VS, -g.MAX_VS_FPM, g.MAX_VS_FPM)
            raw_pitch = (vs_command - observation.vvi_fpm) * g.VS_TO_PITCH + self._alt_i
            pitch_command = _clamp(raw_pitch, g.MIN_PITCH_DEG, g.MAX_PITCH_DEG)
            # Conditional integration, as on the throttle: do not accumulate
            # trim while the pitch command is already against a stop, and do not
            # integrate against a pitch test input, which is a deliberate
            # altitude excursion about to be removed.
            if test_axis != "pitch":
                candidate_alt_i = _clamp(
                    self._alt_i + altitude_error * g.ALT_TO_PITCH_I,
                    -g.ALT_PITCH_I_LIMIT, g.ALT_PITCH_I_LIMIT)
                if g.MIN_PITCH_DEG < raw_pitch < g.MAX_PITCH_DEG or (
                        raw_pitch >= g.MAX_PITCH_DEG and candidate_alt_i < self._alt_i) or (
                        raw_pitch <= g.MIN_PITCH_DEG and candidate_alt_i > self._alt_i):
                    self._alt_i = candidate_alt_i
        with self.lock:
            pitch = self.samples.get("pitch_deg", (0.0, 0.0))[0]
        if not math.isfinite(pitch):
            pitch = 0.0
        elevator = _clamp(
            (pitch_command - pitch) * g.PITCH_TO_ELEVATOR
            - pitch_rate * g.PITCH_RATE_TO_ELEVATOR,
            -g.MAX_ELEVATOR,
            g.MAX_ELEVATOR,
        )

        if speed_mode:
            # throttle is the independent variable in speed-on-pitch
            if climb_throttle is not None:
                self._throttle = climb_throttle
        else:
            speed_error = self.target_kias - observation.kias
            # A pitch input is a deliberate speed excursion. Integrating against
            # it winds the trim term up against a disturbance that is about to be
            # removed, and the throttle then has to unwind before the reference
            # condition can be re-established. Hold the integral; the
            # proportional term still responds.
            if test_axis != "pitch":
                candidate = _clamp(
                    self._throttle_i + speed_error * g.SPEED_TO_THROTTLE_I,
                    -g.THROTTLE_I_LIMIT, g.THROTTLE_I_LIMIT)
                # Conditional integration. Clamping the integral TERM is not
                # anti-windup: on card H0 run 3 the aircraft entered 22 knots
                # fast, the throttle went to the idle stop, and the integral wound
                # to its -0.35 limit and stayed there for ten seconds while the
                # throttle could not go any lower anyway. When speed finally
                # reached 100 the trim term still had to unwind from the stop, so
                # the throttle stayed near idle and the speed sailed on through
                # to 94. The reference condition was never established and the
                # data taken after it is not attributable to a test point.
                # Integrating only when it can actually change the output is what
                # anti-windup means.
                trial = 0.55 + speed_error * g.SPEED_TO_THROTTLE_P + candidate
                unsaturated = g.MIN_THROTTLE < trial < g.MAX_THROTTLE
                unwinding = (
                    (trial >= g.MAX_THROTTLE and candidate < self._throttle_i)
                    or (trial <= g.MIN_THROTTLE and candidate > self._throttle_i)
                )
                if unsaturated or unwinding:
                    self._throttle_i = candidate
            self._throttle = _clamp(
                0.55 + speed_error * g.SPEED_TO_THROTTLE_P + self._throttle_i,
                g.MIN_THROTTLE, g.MAX_THROTTLE)

        # H0: superimpose a bounded single-axis input over the loop output.
        if test_axis == "pitch":
            elevator = _clamp((self._test_baseline if test_input.reference == "delta" else 0.0) + shaped,
                              -g.MAX_ELEVATOR, g.MAX_ELEVATOR)
        elif test_axis == "roll":
            aileron = _clamp((self._test_baseline if test_input.reference == "delta" else 0.0) + shaped,
                             -g.MAX_AILERON, g.MAX_AILERON)

        # Turn coordination: adverse-yaw feedforward plus sideslip feedback, so a
        # roll input is measured coordinated rather than sideslipping. Suspended
        # for a YAW test input, where the sideslip is the thing being commanded.
        with self.lock:
            beta = self.samples.get("beta_deg", (0.0, 0.0))[0]
        if not math.isfinite(beta):
            beta = 0.0
        if test_axis == "yaw":
            rudder = _clamp(self._test_baseline + shaped
                            if test_input.reference == "delta" else shaped,
                            -g.MAX_RUDDER, g.MAX_RUDDER)
            self._beta_i = 0.0          # do not wind up against a commanded slip
        else:
            # Right-rudder feedforward for the left-turning tendency, strongest
            # slow and at high power, plus PI on sideslip to null what is left.
            speed_ratio = g.RUDDER_FF_REF_KIAS / max(observation.kias, 40.0)
            feedforward = g.RIGHT_RUDDER_FF * self._throttle * speed_ratio * speed_ratio
            self._beta_i = _clamp(
                self._beta_i - beta * g.BETA_TO_RUDDER_I, -g.BETA_I_LIMIT, g.BETA_I_LIMIT)
            rudder = _clamp(
                feedforward
                + aileron * g.AILERON_TO_RUDDER
                - beta * g.BETA_TO_RUDDER
                + self._beta_i,
                -g.MAX_RUDDER, g.MAX_RUDDER,
            )

        # Rate-limit every surface. This is the last thing before the wire, so
        # nothing upstream - loop, clamp or test input - can produce a step at
        # the controls. A ramped test input passes through untouched (0.10 of
        # travel per second against a 0.40 limit); what gets limited is the
        # recovery transition, where the command used to jump straight to the
        # authority limit the instant the input expired.
        now = self.clock()
        dt = 0.0 if self._surface_t is None else max(0.0, now - self._surface_t)
        self._surface_t = now
        limited = {}
        for axis, value, rate in (
            ("aileron", aileron, g.AILERON_RATE_PER_S),
            ("elevator", elevator, g.ELEVATOR_RATE_PER_S),
            ("rudder", rudder, g.RUDDER_RATE_PER_S),
        ):
            previous = self._surface[axis]
            if previous is None or dt <= 0.0:
                limited[axis] = value
            else:
                step = rate * dt
                limited[axis] = _clamp(value, previous - step, previous + step)
            self._surface[axis] = limited[axis]
        aileron_command, elevator_command, rudder_command = aileron, elevator, rudder
        aileron = limited["aileron"]
        elevator = limited["elevator"]
        rudder = limited["rudder"]

        # Elevator trim, driven off the elevator the loop is actually holding.
        # Adopt the aircraft's real trim position before moving it, and if that
        # readback is missing or stale, do not write trim at all - flying
        # out-of-trim is recoverable, writing a guessed trim position is not.
        with self.lock:
            trim_value, trim_stamp = self.samples.get(
                "elevator_trim", (float("nan"), -float("inf")))
        trim_fresh = (math.isfinite(trim_value)
                      and now - trim_stamp <= self.STALE_AFTER_SECONDS)
        if not trim_fresh:
            self._trim = None
        if self._trim is None and trim_fresh:
            self._trim = _clamp(trim_value, -g.MAX_TRIM, g.MAX_TRIM)
        trim_rate = 0.0
        if trim_fresh and self._trim is not None and dt > 0.0 and test_axis != "pitch":
            held = elevator if abs(elevator) > g.TRIM_DEADBAND else 0.0
            trim_rate = _clamp(held * g.ELEVATOR_TO_TRIM,
                               -g.MAX_TRIM_RATE_PER_S, g.MAX_TRIM_RATE_PER_S)
            self._trim = _clamp(self._trim + trim_rate * dt, -g.MAX_TRIM, g.MAX_TRIM)
            self.client.send_dref(self.TRIM_DREF, self._trim)

        self._surface.update(limited)
        self.client.send_dref(self.CONTROL_DREFS["aileron"], limited["aileron"])
        self.client.send_dref(self.CONTROL_DREFS["elevator"], limited["elevator"])
        self.client.send_dref(self.CONTROL_DREFS["rudder"], limited["rudder"])
        self.client.send_dref(self.CONTROL_DREFS["throttle"], self._throttle)

        # Keep the last command set so a caller can record it. Tuning needs the
        # outputs, not just the response: a loop that is saturated and one that
        # is merely slow look identical from the telemetry alone.
        with self.lock:
            self._last_commands = {
                "aileron": limited["aileron"],
                "elevator": limited["elevator"],
                "rudder": limited["rudder"],
                "throttle": self._throttle,
                "bank_command_deg": bank_command,
                "vs_command_fpm": vs_command,
                "speed_mode": speed_mode,
                "speed_target_kias": speed_target,
                "pitch_command_deg": pitch_command,
                "pitch_deg": pitch,
                "bank_target_deg": bank_target,
                "test_input_axis": test_axis,
                "test_input_magnitude": test_input.magnitude if test_input else None,
                "test_input_shaped": shaped if test_input else None,
                "test_input_reference": test_input.reference if test_input else None,
                "test_input_baseline": self._test_baseline if test_input else None,
                "beta_deg": beta,
                "rudder_ff": None if test_axis == "yaw" else feedforward,
                "beta_i": self._beta_i,
                "throttle_i": self._throttle_i,
                "alt_i_deg": self._alt_i,
                # The card's trim-confidence observables. Trim RATE is the one
                # that matters: a trim still running is an aircraft still out of
                # trim, whatever the elevator happens to read at that instant.
                "elevator_trim": self._trim,
                "elevator_trim_rate": trim_rate,
                "elevator_trim_measured": trim_value if trim_fresh else None,
                "roll_rate": roll_rate,
                "pitch_rate": pitch_rate,
                # inf means the damping terms were flown as zero for want of data
                "body_rate_age_s": rate_age,
                # Pre-rate-limit demands. When these differ from the commands
                # above the slew limiter is binding, which is the difference
                # between a loop that is slow and one that is being held back.
                "aileron_demand": aileron_command,
                "elevator_demand": elevator_command,
                "rudder_demand": rudder_command,
            }

    # -- introspection ----------------------------------------------------

    @property
    def last_fault(self) -> str | None:
        with self.lock:
            return self._last_fault

    @property
    def last_commands(self) -> dict:
        with self.lock:
            return dict(self._last_commands)

    @property
    def flying(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())
