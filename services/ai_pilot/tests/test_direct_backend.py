"""Offline tests for the direct surface-control backend.

No simulator, no network: a fake client records dataref writes and replays
telemetry. The emphasis is on the fail-safe properties, because this backend
writes to primary flight controls.
"""

from __future__ import annotations

import math
import time
import unittest

from services.ai_pilot.direct_backend import Gains, TestInput, XPlaneDirectBackend
from services.ai_pilot.maneuvers import Limits


class FakeClient:
    def __init__(self):
        self.callbacks = {}
        self.writes = []
        self.commands = []
        self.paused = False

    def subscribe_dref(self, ref, freq_hz=10, callback=None):
        if callback:
            self.callbacks[ref] = callback

    def send_dref(self, ref, value):
        self.writes.append((ref, value))

    def set_paused(self, paused):
        self.paused = paused

    def send_command(self, command):
        self.commands.append(command)

    def feed(self, backend, **values):
        """Push a telemetry frame through the subscription callbacks."""
        for name, ref in {**backend.DATAREFS, **backend.AUX_DATAREFS}.items():
            if name in values:
                self.callbacks[ref](ref, values[name], )

    def written(self, ref):
        for written_ref, value in reversed(self.writes):
            if written_ref == ref:
                return value
        return None


def steady_frame(**overrides):
    frame = {
        "heading_mag": 90.0,
        "altitude_indicated_ft": 4500.0,
        "agl_ft": 1200.0 / 3.28084,   # backend converts metres -> feet
        "kias": 110.0,
        "roll_deg": 0.0,
        "vvi_fpm": 0.0,
        "pitch_deg": 2.0,
        "beta_deg": 0.0,
        "roll_rate": 0.0,
        "pitch_rate": 0.0,
        "elevator_trim": 0.0,
        "aileron_position": 0.0,
        "elevator_position": 0.0,
        "rudder_position": 0.0,
        "throttle_position": 0.55,
    }
    frame.update(overrides)
    return frame


class ObservationTests(unittest.TestCase):
    def test_observe_converts_agl_to_feet(self):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, clock=lambda: 100.0)
        client.feed(backend, **steady_frame())
        observation = backend.observe()
        self.assertAlmostEqual(observation.agl_ft, 1200.0, places=1)
        self.assertAlmostEqual(observation.kias, 110.0, places=3)

    def test_observe_reports_age_for_missing_telemetry(self):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, clock=lambda: 100.0)
        self.assertFalse(math.isfinite(backend.observe().age_seconds))


class RefusalTests(unittest.TestCase):
    def test_select_refuses_without_fresh_telemetry(self):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, clock=lambda: 100.0)
        with self.assertRaisesRegex(ValueError, "fresh telemetry"):
            backend.select(90.0, 4500.0)
        self.assertFalse(backend.flying)
        self.assertEqual(client.writes, [], "must not touch controls before taking control")


class AutopilotExclusivityTests(unittest.TestCase):
    """A direct surface controller must own the controls exclusively.

    If the aircraft's own autopilot stays engaged, its servos drive toward the
    GFC 700's targets while this loop writes yoke ratios, and the two fight.
    """

    def _armed(self):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame())
        return client, backend

    def test_select_disengages_the_aircraft_autopilot_first(self):
        client, backend = self._armed()
        backend.select(90.0, 4500.0)
        try:
            self.assertIn(backend.AUTOPILOT_OFF_COMMAND, client.commands)
        finally:
            backend.release()

    def test_refused_select_does_not_disengage_anything(self):
        # No telemetry: the refusal must happen before touching the aircraft.
        client = FakeClient()
        backend = XPlaneDirectBackend(client, clock=lambda: 100.0)
        with self.assertRaises(ValueError):
            backend.select(90.0, 4500.0)
        self.assertEqual(client.commands, [])


class EngagementTests(unittest.TestCase):
    """Never write to controls this backend did not take.

    Found in flight: an aborted run called release() on a backend that had never
    engaged, which centred the yoke and set cruise throttle on an aircraft the
    pilot was flying - it cost 22 knots and put a wing down.
    """

    def test_release_without_engaging_touches_nothing(self):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame())
        backend.release()
        self.assertEqual(client.writes, [],
                         "must not neutralize an aircraft it never commanded")

    def test_pause_without_engaging_touches_no_controls(self):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame())
        backend.pause()
        self.assertEqual(client.writes, [])

    def test_release_after_engaging_emits_no_handoff_step(self):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame())
        backend.select(90.0, 4500.0)
        before = list(client.writes)
        backend.release()
        self.assertEqual(client.writes, before)


class ControlLawTests(unittest.TestCase):
    """_step is pure enough to drive directly, without starting the thread."""

    def _backend(self, **frame):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=lambda: 100.0)
        client.feed(backend, **steady_frame(**frame))
        return client, backend

    def test_right_turn_commands_right_aileron(self):
        client, backend = self._backend(heading_mag=90.0)
        backend._step(backend.observe(), 120.0, 4500.0)
        self.assertGreater(client.written(backend.CONTROL_DREFS["aileron"]), 0.0)

    def test_left_turn_commands_left_aileron(self):
        client, backend = self._backend(heading_mag=90.0)
        backend._step(backend.observe(), 60.0, 4500.0)
        self.assertLess(client.written(backend.CONTROL_DREFS["aileron"]), 0.0)

    def test_turn_takes_the_short_way_across_north(self):
        client, backend = self._backend(heading_mag=350.0)
        backend._step(backend.observe(), 10.0, 4500.0)
        self.assertGreater(
            client.written(backend.CONTROL_DREFS["aileron"]), 0.0,
            "350 -> 010 is a 20 degree RIGHT turn, not 340 degrees left",
        )

    def test_climb_command_pitches_up(self):
        client, backend = self._backend(altitude_indicated_ft=4000.0, pitch_deg=0.0)
        backend._step(backend.observe(), 90.0, 4500.0)
        self.assertGreater(client.written(backend.CONTROL_DREFS["elevator"]), 0.0)

    def test_outputs_are_clamped_under_extreme_error(self):
        client, backend = self._backend(
            heading_mag=90.0, altitude_indicated_ft=0.0, pitch_deg=-30.0
        )
        backend._step(backend.observe(), 270.0, 6000.0)
        aileron = client.written(backend.CONTROL_DREFS["aileron"])
        elevator = client.written(backend.CONTROL_DREFS["elevator"])
        rudder = client.written(backend.CONTROL_DREFS["rudder"])
        throttle = client.written(backend.CONTROL_DREFS["throttle"])
        self.assertLessEqual(abs(aileron), Gains.MAX_AILERON + 1e-9)
        self.assertLessEqual(abs(elevator), Gains.MAX_ELEVATOR + 1e-9)
        self.assertLessEqual(abs(rudder), Gains.MAX_RUDDER + 1e-9)
        self.assertGreaterEqual(throttle, Gains.MIN_THROTTLE - 1e-9)
        self.assertLessEqual(throttle, Gains.MAX_THROTTLE + 1e-9)

    def test_commanded_bank_stays_inside_the_gate_bank_limit(self):
        # A backend that commanded up to the gate's own 35 deg limit would trip
        # the gate's envelope check as a matter of routine.
        self.assertLess(Gains.MAX_BANK_DEG, Limits().max_bank_deg)


class TestInputTests(unittest.TestCase):
    """Card H0: bounded single-axis inputs.

    The point of bounding magnitude AND duration is that both are checkable,
    unlike a raw surface command - and the input ends itself, so it cannot
    outlive the loop applying it.
    """

    def _flying(self):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame())
        backend.select(90.0, 4500.0)
        return client, backend

    def test_rejects_an_unknown_axis(self):
        with self.assertRaises(ValueError):
            TestInput(axis="yaw_left", magnitude=0.1, duration_s=1.0).validate()

    def test_rejects_an_oversized_input(self):
        with self.assertRaises(ValueError):
            TestInput(axis="pitch", magnitude=0.9, duration_s=1.0).validate()

    def test_rejects_an_overlong_input(self):
        with self.assertRaises(ValueError):
            TestInput(axis="pitch", magnitude=0.1, duration_s=30.0).validate()

    def test_rejects_a_non_finite_input(self):
        with self.assertRaises(ValueError):
            TestInput(axis="roll", magnitude=float("nan"), duration_s=1.0).validate()

    def test_refuses_before_control_is_taken(self):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame())
        with self.assertRaisesRegex(ValueError, "take control"):
            backend.apply_test_input(TestInput("pitch", 0.1, 1.0))

    def test_input_drives_only_its_own_axis(self):
        client, backend = self._flying()
        try:
            ticks = [100.0]
            backend.clock = lambda: ticks[0]
            backend.apply_test_input(TestInput("roll", 0.2, 5.0, ramp_s=0.5))
            ticks[0] = 102.0                       # on the plateau
            backend._step(backend.observe(), 90.0, 4500.0)
            self.assertAlmostEqual(
                client.written(backend.CONTROL_DREFS["aileron"]), 0.2, places=6)
            # the other axes keep holding, so the measured response is this axis
            self.assertIsNotNone(client.written(backend.CONTROL_DREFS["elevator"]))
        finally:
            backend.release()

    def test_input_is_ramped_not_a_step(self):
        # Card H0 asks for smooth inputs; a discontinuity excites transients that
        # describe the step rather than the airframe.
        ti = TestInput("pitch", 0.20, 4.0, ramp_s=1.0)
        self.assertAlmostEqual(ti.shaped(0.0), 0.0, places=6)
        self.assertAlmostEqual(ti.shaped(0.5), 0.10, places=6)    # mid ramp-in
        self.assertAlmostEqual(ti.shaped(2.0), 0.20, places=6)    # plateau
        self.assertAlmostEqual(ti.shaped(3.5), 0.10, places=6)    # mid ramp-out
        self.assertAlmostEqual(ti.shaped(4.0), 0.0, places=6)
        self.assertAlmostEqual(ti.shaped(9.9), 0.0, places=6)

    def test_short_input_degenerates_to_a_triangle_not_a_step(self):
        ti = TestInput("roll", 0.2, 1.0, ramp_s=5.0)
        self.assertAlmostEqual(ti.shaped(0.5), 0.2, places=6)     # peak at midpoint
        self.assertLess(ti.shaped(0.1), 0.2)
        self.assertLess(ti.shaped(0.9), 0.2)

    def test_input_expires_by_itself(self):
        client, backend = self._flying()
        try:
            ticks = [100.0]
            backend.clock = lambda: ticks[0]
            backend.apply_test_input(TestInput("pitch", 0.2, 2.0))
            self.assertTrue(backend.test_input_active)
            ticks[0] = 103.0                      # past the duration
            backend._step(backend.observe(), 90.0, 4500.0)
            self.assertFalse(backend.test_input_active, "input must remove itself")
        finally:
            backend.release()

    def test_release_clears_a_live_test_input(self):
        client, backend = self._flying()
        backend.apply_test_input(TestInput("yaw", 0.1, 5.0))
        backend.release()
        self.assertFalse(backend.test_input_active)


class CoordinationTests(unittest.TestCase):
    """Rudder coordination. An uncoordinated roll biases the measurement.

    Residual sideslip changes the lift distribution, so left and right rolls
    respond differently for reasons that have nothing to do with the airframe.
    The first H0 run showed a consistent 1.7x left/right asymmetry with only an
    open-loop adverse-yaw feedforward in place.
    """

    def _backend(self, **frame):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame(**frame))
        return client, backend

    def test_right_sideslip_commands_left_rudder(self):
        client, backend = self._backend(beta_deg=5.0)
        backend._step(backend.observe(), 90.0, 4500.0)
        self.assertLess(client.written(backend.CONTROL_DREFS["rudder"]), 0.0)

    def test_left_sideslip_commands_right_rudder(self):
        client, backend = self._backend(beta_deg=-5.0)
        backend._step(backend.observe(), 90.0, 4500.0)
        self.assertGreater(client.written(backend.CONTROL_DREFS["rudder"]), 0.0)

    def test_coordination_is_suspended_during_a_yaw_test_input(self):
        # A yaw input commands sideslip deliberately; coordinating it away would
        # cancel the very thing being measured.
        client, backend = self._backend(beta_deg=5.0)
        try:
            backend.select(90.0, 4500.0)
            ticks = [100.0]
            backend.clock = lambda: ticks[0]
            backend.apply_test_input(TestInput("yaw", 0.15, 4.0, ramp_s=0.5))
            ticks[0] = 102.0
            backend._step(backend.observe(), 90.0, 4500.0)
            self.assertAlmostEqual(
                client.written(backend.CONTROL_DREFS["rudder"]), 0.15, places=6)
        finally:
            backend.release()

    def test_coordinated_roll_input_still_gets_rudder(self):
        client, backend = self._backend(beta_deg=0.0)
        try:
            backend.select(90.0, 4500.0)
            ticks = [100.0]
            backend.clock = lambda: ticks[0]
            backend.apply_test_input(TestInput("roll", 0.2, 4.0, ramp_s=0.5))
            ticks[0] = 102.0
            backend._step(backend.observe(), 90.0, 4500.0)
            rudder = client.written(backend.CONTROL_DREFS["rudder"])
            self.assertGreater(rudder, 0.0, "adverse-yaw feedforward must still act")
        finally:
            backend.release()


class ThrottleControlTests(unittest.TestCase):
    """Speed loop must be PI, not a pure integrator.

    The first version integrated at 0.010/tick at 10 Hz - 0.1 throttle per second
    per knot. In flight it went bang-bang between 0.150 and 1.000 and swung speed
    94.7-108.8 KIAS about a 100 target.
    """

    def _backend(self, kias):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(),
                                      target_kias=100.0, clock=time.monotonic)
        client.feed(backend, **steady_frame(kias=kias))
        return client, backend

    def test_slow_adds_power_immediately_without_integrating_up(self):
        client, backend = self._backend(kias=97.0)
        backend._step(backend.observe(), 90.0, 4500.0)
        first = client.written(backend.CONTROL_DREFS["throttle"])
        self.assertGreater(first, 0.55, "proportional term must act on the first tick")
        self.assertLess(first, 0.75, "a 3 kt error must not slam the throttle")

    def test_a_small_error_does_not_saturate_over_many_ticks(self):
        client, backend = self._backend(kias=97.0)
        for _ in range(40):
            backend._step(backend.observe(), 90.0, 4500.0)
        throttle = client.written(backend.CONTROL_DREFS["throttle"])
        self.assertLess(throttle, Gains.MAX_THROTTLE - 1e-6,
                        "a 3 kt error must not drive the throttle to the stop")

    def test_integral_term_is_bounded(self):
        client, backend = self._backend(kias=60.0)   # large persistent error
        for _ in range(500):
            backend._step(backend.observe(), 90.0, 4500.0)
        self.assertLessEqual(abs(backend._throttle_i), Gains.THROTTLE_I_LIMIT + 1e-9)


class RightRudderTests(unittest.TestCase):
    """Left-turning tendency needs anticipating, not just correcting.

    A clockwise propeller yaws the aircraft left under power, worst slow and at
    full throttle. Proportional feedback alone lags it and leaves a standing
    sideslip, which the heading loop hides by holding a wing down - seen in a
    climb as a steady +1.6 degrees of right bank.
    """

    def _backend(self, **frame):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame(**frame))
        return client, backend

    def test_climb_power_commands_right_rudder(self):
        client, backend = self._backend(kias=95.0, beta_deg=0.0)
        backend._throttle = 1.0
        backend._step(backend.observe(), 90.0, 4500.0)
        self.assertGreater(client.written(backend.CONTROL_DREFS["rudder"]), 0.0,
                           "full power at climb speed needs right rudder")

    def test_more_rudder_when_slower(self):
        # The tendency grows as dynamic pressure falls.
        rudders = []
        for kias in (130.0, 90.0):
            client, backend = self._backend(kias=kias, beta_deg=0.0)
            backend._throttle = 1.0
            backend._step(backend.observe(), 90.0, 4500.0)
            rudders.append(client.written(backend.CONTROL_DREFS["rudder"]))
        self.assertGreater(rudders[1], rudders[0])

    def test_more_rudder_at_higher_power(self):
        # Throttle must be pinned via speed mode: setting _throttle directly does
        # not work, because the cruise PI loop recomputes it inside _step.
        rudders = []
        for throttle in (0.2, 1.0):
            client, backend = self._backend(kias=95.0, beta_deg=0.0)
            backend._start = lambda: None  # isolate the single step from the loop thread
            backend.select_airspeed(95.0, throttle=throttle)
            try:
                backend._step(backend.observe(), 90.0, 4500.0)
                # The actual first output now slews from measured rudder, so
                # compare the control-law demand independent of elapsed clock.
                rudders.append(backend.last_commands["rudder_demand"])
            finally:
                backend.release()
        self.assertGreater(rudders[1], rudders[0],
                           "more power means more left-turning tendency to counter")

    def test_sideslip_integral_is_bounded(self):
        client, backend = self._backend(beta_deg=10.0)
        for _ in range(500):
            backend._step(backend.observe(), 90.0, 4500.0)
        self.assertLessEqual(abs(backend._beta_i), Gains.BETA_I_LIMIT + 1e-9)


class CommandedBankTests(unittest.TestCase):
    """Card H2: a commanded bank angle, which heading-hold cannot express."""

    def _flying(self):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame())
        return client, backend

    def test_rejects_bank_beyond_the_limit(self):
        client, backend = self._flying()
        with self.assertRaises(ValueError):
            backend.select_bank(60.0, 4500.0)

    def test_commanded_right_bank_rolls_right(self):
        client, backend = self._flying()
        try:
            backend.select_bank(20.0, 4500.0)
            backend._step(backend.observe(), 90.0, 4500.0)
            self.assertGreater(client.written(backend.CONTROL_DREFS["aileron"]), 0.0)
        finally:
            backend.release()

    def test_commanded_bank_ignores_heading_error(self):
        # wings-level target but a large heading error: heading-hold would roll,
        # commanded bank must not.
        client, backend = self._flying()
        try:
            backend.select_bank(0.0, 4500.0)
            backend._step(backend.observe(), 270.0, 4500.0)
            self.assertAlmostEqual(
                client.written(backend.CONTROL_DREFS["aileron"]), 0.0, places=3)
        finally:
            backend.release()

    def test_bank_selection_after_speed_mode_restores_altitude_hold(self):
        client, backend = self._flying()
        try:
            backend.select_airspeed(110.0, throttle=0.8)
            backend.select_bank(20.0, 4600.0)
            backend._step(backend.observe(), 90.0, 4600.0)
            self.assertFalse(backend.last_commands["speed_mode"])
            self.assertIsNotNone(backend.last_commands["vs_command_fpm"])
        finally:
            backend.release()


class SpeedOnPitchTests(unittest.TestCase):
    """Cards H1/H3: commanded airspeed held on pitch, throttle independent."""

    def _backend(self, **frame):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame(**frame))
        return client, backend

    def test_refuses_a_speed_outside_the_envelope(self):
        client, backend = self._backend()
        with self.assertRaisesRegex(ValueError, "outside the exercise envelope"):
            backend.select_airspeed(45.0)          # below Limits.min_kias 90
        with self.assertRaises(ValueError):
            backend.select_airspeed(200.0)

    def test_too_slow_commands_nose_down(self):
        # Flying slower than target: pitch DOWN to accelerate. This sign is the
        # inverse of the altitude loop and is easy to get backwards.
        client, backend = self._backend(kias=95.0)
        try:
            backend.select_airspeed(120.0)
            backend._step(backend.observe(), 90.0, 4500.0)
            self.assertLess(client.written(backend.CONTROL_DREFS["elevator"]), 0.0)
        finally:
            backend.release()

    def test_too_fast_commands_nose_up(self):
        client, backend = self._backend(kias=135.0)
        try:
            backend.select_airspeed(100.0)
            backend._step(backend.observe(), 90.0, 4500.0)
            self.assertGreater(client.written(backend.CONTROL_DREFS["elevator"]), 0.0)
        finally:
            backend.release()

    def test_fixed_throttle_is_held_not_modulated(self):
        # In speed-on-pitch the throttle is the independent variable: a Vy climb
        # is full power held while pitch flies the speed.
        client, backend = self._backend(kias=95.0)
        try:
            backend.select_airspeed(90.0, throttle=1.0)
            for _ in range(3):
                backend._step(backend.observe(), 90.0, 4500.0)
            self.assertAlmostEqual(
                client.written(backend.CONTROL_DREFS["throttle"]), 1.0, places=6)
        finally:
            backend.release()

    def test_selecting_heading_altitude_clears_speed_mode(self):
        client, backend = self._backend()
        backend.select_airspeed(110.0)
        backend.select(90.0, 4500.0)
        try:
            backend._step(backend.observe(), 90.0, 4000.0)
            commands = backend.last_commands
            self.assertFalse(commands["speed_mode"])
            self.assertIsNotNone(commands["vs_command_fpm"])
        finally:
            backend.release()


class FlapTests(unittest.TestCase):
    """Card H4. Configuration, not a flight control."""

    def _backend(self):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame())
        return client, backend

    def test_rejects_an_out_of_range_ratio(self):
        client, backend = self._backend()
        for bad in (-0.1, 1.5, float("nan")):
            with self.assertRaises(ValueError):
                backend.set_flaps(bad)

    def test_selects_a_valid_ratio(self):
        client, backend = self._backend()
        backend.set_flaps(0.5)
        self.assertAlmostEqual(
            client.written("sim/cockpit2/controls/flap_ratio"), 0.5, places=6)


class FailSafeTests(unittest.TestCase):
    def _armed(self, **frame):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=time.monotonic)
        client.feed(backend, **steady_frame(**frame))
        return client, backend

    def test_envelope_fault_on_low_airspeed(self):
        client, backend = self._armed(kias=60.0)     # below Limits.min_kias 90
        self.assertEqual(backend._envelope_fault(backend.observe()),
                         "Airspeed outside exercise envelope")

    def test_envelope_fault_below_clearance_floor(self):
        client, backend = self._armed(agl_ft=500.0 / 3.28084)
        self.assertEqual(backend._envelope_fault(backend.observe()),
                         "Below clearance floor")

    def test_envelope_fault_on_excessive_bank(self):
        client, backend = self._armed(roll_deg=50.0)
        self.assertEqual(backend._envelope_fault(backend.observe()),
                         "Bank outside exercise envelope")

    def test_no_envelope_fault_when_steady(self):
        client, backend = self._armed()
        self.assertIsNone(backend._envelope_fault(backend.observe()))

    def test_release_stops_flying_without_forcing_new_surface_positions(self):
        client, backend = self._armed()
        backend.select(90.0, 4500.0)
        before = len(client.writes)
        backend.release()
        self.assertFalse(backend.flying)
        self.assertEqual(len(client.writes), before)

    def test_pause_stops_flying_and_pauses_the_simulator(self):
        client, backend = self._armed()
        backend.select(90.0, 4500.0)
        backend.pause()
        self.assertFalse(backend.flying)
        self.assertTrue(client.paused)

    def test_release_does_not_chop_the_throttle_to_idle(self):
        # Neutralizing an airborne aircraft at zero thrust is its own hazard.
        client, backend = self._armed()
        backend.select(90.0, 4500.0)
        backend.release()
        self.assertGreater(client.written(backend.CONTROL_DREFS["throttle"]), 0.0)

    def test_backend_satisfies_the_existing_flight_backend_contract(self):
        # The whole point: the gate, lease, envelope and capture logic are unchanged.
        for method in ("observe", "select", "release", "pause"):
            self.assertTrue(callable(getattr(XPlaneDirectBackend, method)))


if __name__ == "__main__":
    unittest.main()


class SlewRateTests(unittest.TestCase):
    """No commanded surface may step, whatever the loop asks for.

    Card H0 run 3 flew with a correctly ramped test input and the pilot still
    called the roll response abrupt. The ramp was working - it was verified on
    the trace, climbing 0.008 to 0.100 over a full second with the aileron
    command tracking it to four decimals. The step was at the OTHER end: the
    instant the input expired, the heading loop saw a 20.7 degree bank and
    commanded the aileron limit in a single 100 ms tick, holding it saturated
    for 1.2 s. Ramping the input can never fix that, because the step is not in
    the input.
    """

    class Clock:
        def __init__(self, start=100.0):
            self.t = start

        def __call__(self):
            return self.t

    def _backend(self, clock, **frame):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=clock)
        client.feed(backend, **steady_frame(**frame))
        return client, backend

    def test_first_wire_output_slews_from_measured_transfer_position(self):
        clock = self.Clock()
        client, backend = self._backend(clock, aileron_position=0.2)
        backend._surface["aileron"] = 0.2
        backend._surface_t = clock.t
        clock.t += 0.1
        backend._step(backend.observe(), 130.0, 4500.0)
        wire = client.written(backend.CONTROL_DREFS["aileron"])
        self.assertLessEqual(abs(wire - 0.2), Gains.AILERON_RATE_PER_S * 0.1 + 1e-9)
        self.assertAlmostEqual(wire, backend.last_commands["aileron"])

    def test_delta_probe_records_and_uses_fixed_control_baseline(self):
        clock = self.Clock()
        client, backend = self._backend(clock)
        backend._targets = (90.0, 4500.0)
        backend._last_commands = {"aileron": 0.08}
        backend.apply_test_input(TestInput("roll", 0.10, 4.0, ramp_s=1.0,
                                           reference="delta"))
        clock.t += 1.0
        backend._step(backend.observe(), 90.0, 4500.0)
        self.assertAlmostEqual(backend.last_commands["aileron_demand"], 0.18)
        self.assertEqual(backend.last_commands["test_input_reference"], "delta")
        self.assertAlmostEqual(backend.last_commands["test_input_baseline"], 0.08)

    def test_recovery_from_a_banked_upset_does_not_step_the_aileron(self):
        clock = self.Clock()
        # A large bank with the heading loop demanding the opposite limit: the
        # geometry of the H0 roll recovery.
        client, backend = self._backend(clock, roll_deg=-20.0, heading_mag=90.0)
        backend._step(backend.observe(), 130.0, 4500.0)   # first tick, no history
        previous = client.written(backend.CONTROL_DREFS["aileron"])
        for _ in range(5):
            clock.t += 0.1
            client.feed(backend, **steady_frame(roll_deg=-20.0, heading_mag=90.0))
            backend._step(backend.observe(), 130.0, 4500.0)
            value = client.written(backend.CONTROL_DREFS["aileron"])
            self.assertLessEqual(
                abs(value - previous), Gains.AILERON_RATE_PER_S * 0.1 + 1e-9,
                "aileron stepped %.4f in one 100 ms tick" % abs(value - previous),
            )
            previous = value

    def test_the_limiter_still_reaches_the_demand(self):
        # Rate limiting must delay authority, never withhold it.
        clock = self.Clock()
        client, backend = self._backend(clock, roll_deg=-20.0, heading_mag=90.0)
        for _ in range(40):
            client.feed(backend, **steady_frame(roll_deg=-20.0, heading_mag=90.0))
            backend._step(backend.observe(), 130.0, 4500.0)
            clock.t += 0.1
        commands = backend.last_commands
        self.assertAlmostEqual(
            commands["aileron"], commands["aileron_demand"], places=6,
            msg="the limiter never caught up with a steady demand",
        )

    def test_a_ramped_test_input_passes_through_unlimited(self):
        # The input ramp is 0.10 of travel per second; the limit is 0.40 per
        # second. If the limiter were biting here it would be distorting the
        # very measurement the card exists to take.
        clock = self.Clock()
        client, backend = self._backend(clock)
        backend.select(90.0, 4500.0)
        backend.apply_test_input(TestInput("roll", 0.10, 4.0, ramp_s=1.0))
        for _ in range(10):
            client.feed(backend, **steady_frame())
            backend._step(backend.observe(), 90.0, 4500.0)
            commands = backend.last_commands
            self.assertAlmostEqual(commands["aileron"], commands["aileron_demand"], places=6)
            clock.t += 0.1

    def test_slew_history_is_cleared_between_engagements(self):
        # Otherwise the first tick of a new engagement slews from a surface
        # position left over from the last one, which may be minutes old.
        clock = self.Clock()
        client, backend = self._backend(clock)
        backend.select(90.0, 4500.0)
        backend._step(backend.observe(), 130.0, 4500.0)
        self.assertIsNotNone(backend._surface["aileron"])
        backend.release()
        self.assertEqual(
            backend._surface, {"aileron": None, "elevator": None, "rudder": None})


class RateDampingTests(unittest.TestCase):
    """The bank and pitch loops need to know the aircraft is already moving.

    Proportional-only on ANGLE keeps commanding correction all the way to the
    target and then overshoots through it. On H0 run 3 the roll recovery reached
    14.3 deg/s and overshot from -20.7 to +9.2 degrees.
    """

    def _backend(self, **frame):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=lambda: 100.0)
        client.feed(backend, **steady_frame(**frame))
        return client, backend

    def test_rolling_toward_the_target_reduces_aileron(self):
        undamped, _ = None, None
        client_a, backend_a = self._backend(roll_deg=-20.0, roll_rate=0.0)
        backend_a._step(backend_a.observe(), 90.0, 4500.0)
        still = client_a.written(backend_a.CONTROL_DREFS["aileron"])

        client_b, backend_b = self._backend(roll_deg=-20.0, roll_rate=10.0)
        backend_b._step(backend_b.observe(), 90.0, 4500.0)
        rolling = client_b.written(backend_b.CONTROL_DREFS["aileron"])

        self.assertLess(
            rolling, still,
            "already rolling right out of a left bank, yet commanding as much "
            "right aileron as if the wing were parked there",
        )

    def test_pitching_toward_the_target_reduces_elevator(self):
        client_a, backend_a = self._backend(altitude_indicated_ft=4000.0, pitch_rate=0.0)
        backend_a._step(backend_a.observe(), 90.0, 4500.0)
        still = client_a.written(backend_a.CONTROL_DREFS["elevator"])

        client_b, backend_b = self._backend(altitude_indicated_ft=4000.0, pitch_rate=5.0)
        backend_b._step(backend_b.observe(), 90.0, 4500.0)
        pitching = client_b.written(backend_b.CONTROL_DREFS["elevator"])

        self.assertLess(pitching, still)

    def test_missing_body_rates_degrade_damping_not_telemetry(self):
        # A damping channel is not flight-critical: losing it must not neutralize
        # the controls on an airborne aircraft.
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=lambda: 100.0)
        frame = steady_frame()
        frame.pop("roll_rate")
        frame.pop("pitch_rate")
        client.feed(backend, **frame)
        self.assertLess(backend.observe().age_seconds, backend.STALE_AFTER_SECONDS)
        self.assertIsNone(backend._envelope_fault(backend.observe()))
        backend._step(backend.observe(), 130.0, 4500.0)
        self.assertEqual(backend.last_commands["roll_rate"], 0.0)

    def test_a_degraded_run_is_visible_in_the_trace(self):
        # A zero that means "not rolling" and a zero that means "no data" must
        # not look alike in flight-test evidence.
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=lambda: 100.0)
        frame = steady_frame()
        frame.pop("roll_rate")
        client.feed(backend, **frame)
        backend._step(backend.observe(), 130.0, 4500.0)
        self.assertEqual(backend.last_commands["body_rate_age_s"], float("inf"))

        client2 = FakeClient()
        backend2 = XPlaneDirectBackend(client2, limits=Limits(), clock=lambda: 100.0)
        client2.feed(backend2, **steady_frame())
        backend2._step(backend2.observe(), 130.0, 4500.0)
        self.assertTrue(math.isfinite(backend2.last_commands["body_rate_age_s"]))


class SpeedIntegralTests(unittest.TestCase):
    """Do not integrate against a disturbance you are deliberately applying."""

    def _backend(self, clock):
        client = FakeClient()
        backend = XPlaneDirectBackend(
            client, limits=Limits(), target_kias=100.0, clock=clock)
        client.feed(backend, **steady_frame(kias=90.0))
        return client, backend

    def test_pitch_input_freezes_the_speed_integral(self):
        clock = SlewRateTests.Clock()
        client, backend = self._backend(clock)
        backend.select(90.0, 4500.0)
        for _ in range(5):
            client.feed(backend, **steady_frame(kias=90.0))
            backend._step(backend.observe(), 90.0, 4500.0)
            clock.t += 0.1
        wound = backend._throttle_i
        self.assertGreater(wound, 0.0, "a 10 knot deficit should wind the trim term")

        backend.apply_test_input(TestInput("pitch", 0.10, 4.0, ramp_s=1.0))
        for _ in range(10):
            client.feed(backend, **steady_frame(kias=90.0))
            backend._step(backend.observe(), 90.0, 4500.0)
            clock.t += 0.1
        self.assertAlmostEqual(backend._throttle_i, wound, places=9)

    def test_roll_input_does_not_freeze_it(self):
        # Only the pitch axis is a deliberate speed excursion.
        clock = SlewRateTests.Clock()
        client, backend = self._backend(clock)
        backend.select(90.0, 4500.0)
        client.feed(backend, **steady_frame(kias=90.0))
        backend._step(backend.observe(), 90.0, 4500.0)
        wound = backend._throttle_i
        backend.apply_test_input(TestInput("roll", 0.10, 4.0, ramp_s=1.0))
        for _ in range(5):
            clock.t += 0.1
            client.feed(backend, **steady_frame(kias=90.0))
            backend._step(backend.observe(), 90.0, 4500.0)
        self.assertGreater(backend._throttle_i, wound)


class ThrottleAntiWindupTests(unittest.TestCase):
    """Clamping the integral term is not anti-windup.

    Card H0 run 3 entered 22 knots fast against a 100 KIAS reference. The
    throttle sat on the idle stop for ten seconds while the integral wound to
    its -0.35 limit, which changed nothing - the throttle could not go lower.
    When speed reached the target the trim term still had to unwind off the
    stop, so the throttle stayed near idle and speed continued through to 94.
    The run produced no valid reference condition.
    """

    def _backend(self, clock, kias):
        client = FakeClient()
        backend = XPlaneDirectBackend(
            client, limits=Limits(), target_kias=100.0, clock=clock)
        client.feed(backend, **steady_frame(kias=kias))
        return client, backend

    def _fly(self, backend, client, kias, seconds, clock):
        for _ in range(int(seconds * 10)):
            client.feed(backend, **steady_frame(kias=kias))
            backend._step(backend.observe(), 90.0, 4500.0)
            clock.t += 0.1

    def test_integral_does_not_wind_against_the_idle_stop(self):
        clock = SlewRateTests.Clock()
        client, backend = self._backend(clock, 122.0)
        self._fly(backend, client, 122.0, 10.0, clock)
        self.assertAlmostEqual(
            client.written(backend.CONTROL_DREFS["throttle"]), Gains.MIN_THROTTLE,
            places=6, msg="22 knots fast should command idle")
        self.assertGreater(
            backend._throttle_i, -Gains.THROTTLE_I_LIMIT + 1e-6,
            "the trim term wound to its limit while the throttle was already "
            "on the stop, where integrating could not change the output",
        )

    def test_throttle_responds_the_moment_the_speed_is_reached(self):
        # The failure this guards is a DELAYED response, not a wrong one: the
        # throttle must come off the stop as the error crosses zero, not after
        # an accumulated trim term has unwound.
        clock = SlewRateTests.Clock()
        client, backend = self._backend(clock, 122.0)
        self._fly(backend, client, 122.0, 10.0, clock)
        self._fly(backend, client, 100.0, 0.5, clock)
        self.assertGreater(
            client.written(backend.CONTROL_DREFS["throttle"]),
            Gains.MIN_THROTTLE + 0.2,
            "throttle still near idle half a second after reaching the target "
            "speed - the trim term is unwinding off a stop it should never "
            "have been driven to",
        )

    def test_the_integral_still_trims_out_a_standing_error(self):
        # Conditional integration must not disable the integral in the regime it
        # exists for: a small error the proportional term alone cannot remove.
        clock = SlewRateTests.Clock()
        client, backend = self._backend(clock, 97.0)
        self._fly(backend, client, 97.0, 4.0, clock)
        self.assertGreater(backend._throttle_i, 0.0)
        self.assertLess(backend._throttle_i, Gains.THROTTLE_I_LIMIT)


class AltitudeTrimTests(unittest.TestCase):
    """A proportional cascade can sit at a standing altitude error forever.

    Card H0 run 4 held 100.0 KIAS, -3 fpm and -0.2 deg of bank for two full
    minutes while 107 ft below the target, correcting none of it. Nothing was
    saturated and nothing was oscillating: the VS loop asked for the pitch that
    flies level, the pitch loop delivered it, and every loop was satisfied with
    the aircraft in the wrong place. Without a trim term the card's reference
    condition is not reachable, so the card cannot be flown at all.
    """

    def _backend(self, clock, **frame):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=clock)
        client.feed(backend, **steady_frame(**frame))
        return client, backend

    def test_a_standing_low_altitude_builds_nose_up_trim(self):
        clock = SlewRateTests.Clock()
        # Level, on speed, 107 ft low: run 4's dead end exactly.
        frame = dict(altitude_indicated_ft=3993.0, vvi_fpm=0.0, pitch_deg=3.2, kias=100.0)
        client, backend = self._backend(clock, **frame)
        first = None
        for _ in range(300):          # 30 s
            client.feed(backend, **steady_frame(**frame))
            backend._step(backend.observe(), 90.0, 4100.0)
            if first is None:
                first = backend.last_commands["pitch_command_deg"]
            clock.t += 0.1
        self.assertGreater(
            backend.last_commands["pitch_command_deg"], first + 0.5,
            "pitch command unchanged after 30 s of standing altitude error - "
            "the loop is satisfied with the aircraft in the wrong place",
        )
        self.assertGreater(backend._alt_i, 0.0)

    def test_trim_is_bounded(self):
        clock = SlewRateTests.Clock()
        frame = dict(altitude_indicated_ft=0.0, vvi_fpm=0.0, pitch_deg=0.0)
        client, backend = self._backend(clock, **frame)
        for _ in range(600):
            client.feed(backend, **steady_frame(**frame))
            backend._step(backend.observe(), 90.0, 6000.0)
            clock.t += 0.1
        self.assertLessEqual(abs(backend._alt_i), Gains.ALT_PITCH_I_LIMIT + 1e-9)
        self.assertLessEqual(
            backend.last_commands["pitch_command_deg"], Gains.MAX_PITCH_DEG + 1e-9)

    def test_a_pitch_test_input_does_not_wind_the_trim(self):
        clock = SlewRateTests.Clock()
        frame = dict(altitude_indicated_ft=3993.0, vvi_fpm=0.0, pitch_deg=3.2)
        client, backend = self._backend(clock, **frame)
        backend.select(90.0, 4100.0)
        for _ in range(50):
            client.feed(backend, **steady_frame(**frame))
            backend._step(backend.observe(), 90.0, 4100.0)
            clock.t += 0.1
        wound = backend._alt_i
        backend.apply_test_input(TestInput("pitch", 0.10, 4.0, ramp_s=1.0))
        for _ in range(30):
            client.feed(backend, **steady_frame(**frame))
            backend._step(backend.observe(), 90.0, 4100.0)
            clock.t += 0.1
        self.assertAlmostEqual(backend._alt_i, wound, places=9)

    def test_speed_on_pitch_does_not_inherit_altitude_trim(self):
        # In H1/H3 pitch holds SPEED. Altitude trim left over from cruise would
        # be a hidden bias on the speed loop.
        clock = SlewRateTests.Clock()
        frame = dict(altitude_indicated_ft=3993.0, vvi_fpm=0.0, pitch_deg=3.2)
        client, backend = self._backend(clock, **frame)
        backend.select(90.0, 4100.0)
        for _ in range(50):
            client.feed(backend, **steady_frame(**frame))
            backend._step(backend.observe(), 90.0, 4100.0)
            clock.t += 0.1
        self.assertGreater(backend._alt_i, 0.0)
        backend.select_airspeed(90.0, throttle=0.8)
        client.feed(backend, **steady_frame(**frame))
        backend._step(backend.observe(), 90.0, 4100.0)
        self.assertEqual(backend._alt_i, 0.0)

    def test_trim_is_cleared_between_engagements(self):
        clock = SlewRateTests.Clock()
        frame = dict(altitude_indicated_ft=3993.0, vvi_fpm=0.0, pitch_deg=3.2)
        client, backend = self._backend(clock, **frame)
        backend.select(90.0, 4100.0)
        for _ in range(50):
            client.feed(backend, **steady_frame(**frame))
            backend._step(backend.observe(), 90.0, 4100.0)
            clock.t += 0.1
        self.assertGreater(backend._alt_i, 0.0)
        backend.release()
        self.assertEqual(backend._alt_i, 0.0)
        self.assertEqual(backend._throttle_i, 0.0)


class ElevatorTrimTests(unittest.TestCase):
    """Card H0 run 5: out-trimmed, saturated, and climbing away from the loop.

    The backend engaged on an aircraft the autopilot had left trimmed to +0.432
    nose-up. It held full nose-DOWN elevator, saturated at -0.400 for seven
    seconds, while the aircraft pitched UP to 11.5 deg and climbed at 1,533 fpm.
    Nothing in the control law was wrong; it simply had no trim authority and no
    way to know it was being out-trimmed, because a saturated surface and a slow
    one look the same from the response.
    """

    def _backend(self, clock, trim=0.0, **frame):
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=clock)
        client.feed(backend, **steady_frame(elevator_trim=trim, **frame))
        return client, backend

    def _fly(self, backend, client, clock, ticks, trim=0.0, **frame):
        for _ in range(ticks):
            client.feed(backend, **steady_frame(elevator_trim=trim, **frame))
            backend._step(backend.observe(), 90.0, 4500.0)
            clock.t += 0.1

    def test_trim_is_adopted_from_the_aircraft_not_assumed(self):
        clock = SlewRateTests.Clock()
        client, backend = self._backend(clock, trim=0.4322)
        backend._step(backend.observe(), 90.0, 4500.0)
        self.assertAlmostEqual(backend._trim, 0.4322, places=6)

    def test_no_trim_is_written_without_a_readback(self):
        # Flying out of trim is recoverable. Writing a guessed trim position to
        # an aircraft whose trim you have never read is not.
        clock = SlewRateTests.Clock()
        client = FakeClient()
        backend = XPlaneDirectBackend(client, limits=Limits(), clock=clock)
        frame = steady_frame()
        frame.pop("elevator_trim")
        for _ in range(20):
            client.feed(backend, **frame)
            backend._step(backend.observe(), 90.0, 4500.0)
            clock.t += 0.1
        self.assertIsNone(backend._trim)
        self.assertIsNone(client.written(backend.TRIM_DREF))
        self.assertEqual(backend.last_commands["elevator_trim_measured"], None)

    def test_trim_writes_stop_when_feedback_stales_after_adoption(self):
        clock = SlewRateTests.Clock()
        client, backend = self._backend(clock, trim=0.2)
        backend._step(backend.observe(), 90.0, 4500.0)
        clock.t += 0.1
        client.feed(backend, **steady_frame(elevator_trim=0.2))
        backend._step(backend.observe(), 90.0, 4500.0)
        self.assertIsNotNone(client.written(backend.TRIM_DREF))
        first_count = sum(ref == backend.TRIM_DREF for ref, _ in client.writes)
        clock.t += backend.STALE_AFTER_SECONDS + 0.1
        frame = steady_frame()
        frame.pop("elevator_trim")
        client.feed(backend, **frame)
        backend._step(backend.observe(), 90.0, 4500.0)
        self.assertEqual(sum(ref == backend.TRIM_DREF for ref, _ in client.writes), first_count)
        self.assertIsNone(backend._trim)

    def test_sustained_nose_up_elevator_trims_nose_up(self):
        clock = SlewRateTests.Clock()
        # Holding a climb: the elevator loop demands nose-up and keeps demanding.
        client, backend = self._backend(
            clock, trim=0.0, altitude_indicated_ft=4000.0, pitch_deg=0.0)
        self._fly(backend, client, clock, 50,
                  trim=0.0, altitude_indicated_ft=4000.0, pitch_deg=0.0)
        self.assertGreater(backend._trim, 0.0)
        self.assertGreater(client.written(backend.TRIM_DREF), 0.0)

    def test_sustained_nose_down_elevator_trims_nose_down(self):
        clock = SlewRateTests.Clock()
        frame = dict(altitude_indicated_ft=5000.0, pitch_deg=8.0)
        client, backend = self._backend(clock, trim=0.0, **frame)
        self._fly(backend, client, clock, 50, trim=0.0, **frame)
        self.assertLess(backend._trim, 0.0)

    def test_trim_does_not_chase_a_centred_elevator(self):
        clock = SlewRateTests.Clock()
        # On altitude, on speed, pitch already at the commanded attitude: the
        # elevator loop has nothing to hold, so the trim has nothing to chase.
        client, backend = self._backend(clock, trim=0.2, pitch_deg=0.0)
        self._fly(backend, client, clock, 50, trim=0.2, pitch_deg=0.0)
        self.assertAlmostEqual(
            backend.last_commands["elevator"], 0.0, places=6,
            msg="fixture is not actually at a centred elevator")
        self.assertAlmostEqual(backend._trim, 0.2, places=6)

    def test_trim_rate_is_limited(self):
        clock = SlewRateTests.Clock()
        frame = dict(altitude_indicated_ft=0.0, pitch_deg=-20.0)
        client, backend = self._backend(clock, trim=0.0, **frame)
        previous = None
        for _ in range(30):
            client.feed(backend, **steady_frame(elevator_trim=0.0, **frame))
            backend._step(backend.observe(), 90.0, 6000.0)
            if previous is not None:
                self.assertLessEqual(
                    abs(backend._trim - previous),
                    Gains.MAX_TRIM_RATE_PER_S * 0.1 + 1e-9)
            previous = backend._trim
            clock.t += 0.1

    def test_a_pitch_test_input_is_not_trimmed_out(self):
        # Trimming out a deliberate input trims out the measurement.
        clock = SlewRateTests.Clock()
        client, backend = self._backend(clock, trim=0.1)
        backend.select(90.0, 4500.0)
        self._fly(backend, client, clock, 10, trim=0.1)
        before = backend._trim
        backend.apply_test_input(TestInput("pitch", 0.20, 4.0, ramp_s=1.0))
        self._fly(backend, client, clock, 30, trim=0.1)
        self.assertAlmostEqual(backend._trim, before, places=9)

    def test_release_leaves_the_aircraft_trimmed(self):
        # _neutralize centres the yoke. Slamming trim to neutral as well would
        # hand back an aircraft in an upset rather than a trimmed one.
        clock = SlewRateTests.Clock()
        client, backend = self._backend(
            clock, trim=0.0, altitude_indicated_ft=4000.0, pitch_deg=0.0)
        backend.select(90.0, 4500.0)
        self._fly(backend, client, clock, 50,
                  trim=0.0, altitude_indicated_ft=4000.0, pitch_deg=0.0)
        trimmed = client.written(backend.TRIM_DREF)
        self.assertGreater(trimmed, 0.0)
        backend.release()
        self.assertNotIn(backend.TRIM_DREF, backend.CONTROL_DREFS.values())
        self.assertAlmostEqual(client.written(backend.TRIM_DREF), trimmed, places=6)

    def test_trim_is_re_adopted_on_the_next_engagement(self):
        clock = SlewRateTests.Clock()
        client, backend = self._backend(clock, trim=0.3)
        backend.select(90.0, 4500.0)
        self._fly(backend, client, clock, 5, trim=0.3)
        backend.release()
        self.assertIsNone(backend._trim)
