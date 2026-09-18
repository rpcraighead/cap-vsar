"""Offline tests for the ArduPlane backend.

No simulator, no SITL, no sockets: a fake X-Plane client replays telemetry and
records writes, a mock MAVLink link records frames and auto-ACKs. The emphasis
is the fail-closed contract - the ordering of what is sent, what is refused,
and which of release / pause each fault takes - because this backend hands an
airborne aircraft to a controller that then writes the yoke.
"""

from __future__ import annotations

import math
import time
import unittest

from services.ai_pilot import mavlink_min as mav
from services.ai_pilot.arduplane_backend import ArduPlaneBackend, M_PER_FT
from services.ai_pilot.maneuvers import Limits
from services.ai_pilot.tests.test_direct_backend import FakeClient


def frame(**overrides):
    base = dict(
        heading_mag=90.0,
        altitude_indicated_ft=4500.0,
        agl_ft=1200.0 / 3.28084,
        kias=110.0,
        roll_deg=0.0,
        vvi_fpm=0.0,
        elevation_m=4500.0 * M_PER_FT,   # altimeter set correctly: indicated == true
        heading_true=102.0,              # 12 degrees east variation
        ap_mode=0.0,
        override_joystick=1.0,
    )
    base.update(overrides)
    return base


def feed(client, backend, **values):
    refs = {**backend.DATAREFS, **backend.AUX_DATAREFS, **backend.axis_datarefs}
    for name, value in values.items():
        client.callbacks[refs[name]](refs[name], value)


def rc_frame(**chans):
    fields = {"time_boot_ms": 1000, "chancount": 8, "rssi": 90}
    for i in range(1, 19):
        fields["chan%d_raw" % i] = 1500 if i <= 4 else 0
    fields.update(chans)
    return fields


def gpi_frame(alt_m):
    return {"time_boot_ms": 1000, "lat": 0, "lon": 0, "alt": int(alt_m * 1000),
            "relative_alt": 0, "vx": 0, "vy": 0, "vz": 0, "hdg": 0}


class Timeline:
    """One ordered log across the X-Plane client and the MAVLink link."""

    def __init__(self, client, link):
        self.events = []
        original_command, original_send = client.send_command, link.send

        def send_command(command):
            self.events.append(("xplane", command))
            original_command(command)

        def send(msgid, fields):
            self.events.append(("mavlink", fields.get("command", msgid)))
            original_send(msgid, fields)

        client.send_command, link.send = send_command, send


class Rig:
    """A backend with fake telemetry and a mock link, on a controllable clock."""

    def __init__(self, mode=mav.PLANE_MODE_MANUAL, limits=Limits(), real_clock=False,
                 joystick_axes=None, auto_ack=mav.MAV_RESULT_ACCEPTED):
        self.t = [100.0]
        self.clock = time.monotonic if real_clock else (lambda: self.t[0])
        self.client = FakeClient()
        self.link = mav.MockLink(clock=self.clock, auto_ack=auto_ack)
        self.backend = ArduPlaneBackend(self.client, self.link, limits=limits,
                                        clock=self.clock, joystick_axes=joystick_axes)
        self.timeline = Timeline(self.client, self.link)
        if mode is not None:
            self.link.inject_heartbeat(mode)

    def advance(self, seconds):
        self.t[0] += seconds

    def commands(self):
        return self.link.sent_commands()

    def step(self):
        backend = self.backend
        with backend.lock:
            targets = backend._targets
        return backend._step(backend.observe(), targets)

    def close(self):
        self.backend.release()


class RefusalTests(unittest.TestCase):
    def test_select_refuses_stale_telemetry(self):
        rig = Rig()
        with self.assertRaisesRegex(ValueError, "fresh telemetry"):
            rig.backend.select(90.0, 4500.0)
        self.assertEqual(rig.timeline.events, [], "must send nothing without telemetry")
        self.assertFalse(rig.backend.flying)

    def test_select_refuses_without_heartbeat(self):
        rig = Rig(mode=None)
        feed(rig.client, rig.backend, **frame())
        with self.assertRaisesRegex(ValueError, "heartbeat"):
            rig.backend.select(90.0, 4500.0)
        self.assertEqual(rig.timeline.events, [])

    def test_select_refuses_without_true_heading_or_elevation(self):
        rig = Rig()
        values = frame()
        del values["heading_true"]
        feed(rig.client, rig.backend, **values)
        with self.assertRaisesRegex(ValueError, "true heading"):
            rig.backend.select(90.0, 4500.0)
        self.assertEqual(rig.timeline.events, [])


class SelectOrderingTests(unittest.TestCase):
    def test_select_servos_off_before_any_mavlink(self):
        rig = Rig()
        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        try:
            self.assertEqual(rig.timeline.events[0], ("xplane", ArduPlaneBackend.AUTOPILOT_OFF_COMMAND))
            self.assertTrue(all(kind == "mavlink" for kind, _ in rig.timeline.events[1:]))
        finally:
            rig.close()

    def test_select_order_guided_alt_hdg(self):
        rig = Rig(mode=mav.PLANE_MODE_MANUAL)
        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        try:
            self.assertEqual(rig.commands(), [
                mav.MAV_CMD_DO_SET_MODE,
                mav.MAV_CMD_GUIDED_CHANGE_ALTITUDE,
                mav.MAV_CMD_GUIDED_CHANGE_HEADING,
            ])
            mode_change = rig.link.sent_messages[0][1]
            self.assertEqual(mode_change["param2"], float(mav.PLANE_MODE_GUIDED))
            self.assertTrue(rig.backend.flying)
        finally:
            rig.close()

    def test_select_skips_mode_change_when_already_guided(self):
        rig = Rig(mode=mav.PLANE_MODE_GUIDED)
        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        try:
            self.assertEqual(rig.commands(), [
                mav.MAV_CMD_GUIDED_CHANGE_ALTITUDE, mav.MAV_CMD_GUIDED_CHANGE_HEADING])
        finally:
            rig.close()

    def test_select_bounded_time_and_ack_timeout_raises_no_thread(self):
        rig = Rig(mode=mav.PLANE_MODE_GUIDED, real_clock=True, auto_ack=None)
        feed(rig.client, rig.backend, **frame())
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "did not acknowledge altitude"):
            rig.backend.select(120.0, 4500.0)
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertFalse(rig.backend.flying)
        self.assertIsNone(rig.backend._thread)
        self.assertEqual(rig.commands(), [mav.MAV_CMD_GUIDED_CHANGE_ALTITUDE],
                         "heading must not be sent once altitude was not acknowledged")

    def test_select_refused_by_ardupilot_raises(self):
        rig = Rig(mode=mav.PLANE_MODE_GUIDED)
        rig.link.ack_overrides[mav.MAV_CMD_GUIDED_CHANGE_HEADING] = mav.MAV_RESULT_DENIED
        feed(rig.client, rig.backend, **frame())
        with self.assertRaisesRegex(ValueError, "refused heading"):
            rig.backend.select(120.0, 4500.0)
        self.assertFalse(rig.backend.flying)

    def test_mode_change_refused_raises_at_once(self):
        rig = Rig(mode=mav.PLANE_MODE_MANUAL, real_clock=True)
        rig.link.ack_overrides[mav.MAV_CMD_DO_SET_MODE] = mav.MAV_RESULT_FAILED
        feed(rig.client, rig.backend, **frame())
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "refused GUIDED"):
            rig.backend.select(120.0, 4500.0)
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(rig.commands(), [mav.MAV_CMD_DO_SET_MODE])

    def test_mode_change_not_confirmed_by_heartbeat_raises_bounded(self):
        rig = Rig(mode=mav.PLANE_MODE_MANUAL, real_clock=True)
        rig.link.honour_mode_changes = False     # ACKed, but the heartbeat never says GUIDED
        feed(rig.client, rig.backend, **frame())
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "did not enter GUIDED"):
            rig.backend.select(120.0, 4500.0)
        self.assertLess(time.monotonic() - started, ArduPlaneBackend.MODE_CHANGE_TIMEOUT + 0.5)
        self.assertEqual(rig.commands(), [mav.MAV_CMD_DO_SET_MODE])
        self.assertFalse(rig.backend.flying)

    def test_reselect_while_engaged_does_not_restart_thread(self):
        rig = Rig()
        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        try:
            thread = rig.backend._thread
            rig.backend.select(200.0, 5000.0)
            self.assertIs(rig.backend._thread, thread)
            self.assertEqual(rig.commands().count(mav.MAV_CMD_DO_SET_MODE), 1)
        finally:
            rig.close()


class FrameConversionTests(unittest.TestCase):
    def test_altitude_command_uses_true_offset(self):
        rig = Rig(mode=mav.PLANE_MODE_GUIDED)
        # The altimeter reads 120 ft low: true MSL is 4620 ft while it says 4500.
        feed(rig.client, rig.backend, **frame(altitude_indicated_ft=4500.0, elevation_m=4620.0 * M_PER_FT))
        rig.backend.select(90.0, 5000.0)
        try:
            _msgid, fields = rig.link.sent_messages[0]
            self.assertEqual(fields["command"], mav.MAV_CMD_GUIDED_CHANGE_ALTITUDE)
            self.assertEqual(fields["frame"], mav.MAV_FRAME_GLOBAL)
            self.assertAlmostEqual(fields["z"], 5120.0 * M_PER_FT, places=3)
            self.assertAlmostEqual(fields["param3"], ArduPlaneBackend.CLIMB_RATE_M_S)
            self.assertAlmostEqual(rig.backend.last_commands["alt_offset_ft"], 120.0, places=3)
        finally:
            rig.close()

    def test_heading_mag_to_true(self):
        rig = Rig(mode=mav.PLANE_MODE_GUIDED)
        feed(rig.client, rig.backend, **frame(heading_mag=90.0, heading_true=102.0))
        rig.backend.select(180.0, 4500.0)
        try:
            _msgid, fields = rig.link.sent_messages[1]
            self.assertEqual(fields["command"], mav.MAV_CMD_GUIDED_CHANGE_HEADING)
            self.assertEqual(fields["param1"], float(mav.HEADING_TYPE_HEADING))
            self.assertAlmostEqual(fields["param2"], 192.0, places=3)
            self.assertAlmostEqual(fields["param3"], ArduPlaneBackend.HEADING_ACCEL_M_S2)
        finally:
            rig.close()

    def test_heading_wraps_through_north(self):
        rig = Rig(mode=mav.PLANE_MODE_GUIDED)
        feed(rig.client, rig.backend, **frame(heading_mag=350.0, heading_true=2.0))  # +12 E across 360
        rig.backend.select(355.0, 4500.0)
        try:
            self.assertAlmostEqual(rig.link.sent_messages[1][1]["param2"], 7.0, places=3)
        finally:
            rig.close()


class ReleaseTests(unittest.TestCase):
    def test_release_sends_default_heading_then_loiter_only_if_engaged(self):
        rig = Rig()
        rig.backend.release()
        self.assertEqual(rig.timeline.events, [], "never engaged: hand back nothing")

        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        before = len(rig.link.sent_messages)
        rig.backend.release()
        after = rig.link.sent_messages[before:]
        self.assertEqual([f["command"] for _m, f in after],
                         [mav.MAV_CMD_GUIDED_CHANGE_HEADING, mav.MAV_CMD_DO_SET_MODE])
        self.assertEqual(after[0][1]["param1"], float(mav.HEADING_TYPE_DEFAULT))
        self.assertEqual(after[1][1]["param2"], float(mav.PLANE_MODE_LOITER))
        self.assertFalse(rig.client.paused, "release never pauses")
        self.assertFalse(rig.backend.flying)
        self.assertEqual(rig.client.writes, [], "release never touches X-Plane controls or overrides")

    def test_release_is_idempotent(self):
        rig = Rig()
        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        rig.backend.release()
        count = len(rig.link.sent_messages)
        rig.backend.release()
        self.assertEqual(len(rig.link.sent_messages), count)

    def test_pause_never_changes_mode(self):
        rig = Rig()
        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        commands = rig.commands()
        rig.backend.pause()
        self.assertTrue(rig.client.paused)
        self.assertEqual(rig.commands(), commands, "pause must not send a MAVLink mode change")
        self.assertFalse(rig.backend.flying)

    def test_release_after_pause_still_hands_back(self):
        # A fault pauses the sim with ArduPlane still in GUIDED holding the
        # joystick override. The pilot's explicit hand-back afterwards must
        # still reach ArduPilot, or un-pausing leaves a dead yoke.
        rig = Rig()
        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        rig.backend.pause()
        before = len(rig.link.sent_messages)
        rig.backend.release()
        after = [f["command"] for _m, f in rig.link.sent_messages[before:]]
        self.assertEqual(after, [mav.MAV_CMD_GUIDED_CHANGE_HEADING, mav.MAV_CMD_DO_SET_MODE])
        self.assertEqual(rig.link.sent_messages[-1][1]["param2"], float(mav.PLANE_MODE_LOITER))

    def test_select_refused_after_takeover_until_release(self):
        rig = Rig(joystick_axes={"pitch": 1, "roll": 0})
        feed(rig.client, rig.backend, **frame(), axis_pitch=0.0, axis_roll=0.0)
        rig.backend.select(120.0, 4500.0)
        rig.backend._stop.set()
        rig.backend._thread.join(timeout=2.0)
        feed(rig.client, rig.backend, axis_pitch=0.4)
        self.assertFalse(rig.step())
        sent = len(rig.link.sent_messages)
        with self.assertRaisesRegex(ValueError, "took over"):
            rig.backend.select(130.0, 4500.0)
        self.assertEqual(len(rig.link.sent_messages), sent, "a refused select sends nothing")
        rig.backend.release()
        feed(rig.client, rig.backend, **frame(), axis_pitch=0.4, axis_roll=0.0)
        rig.link.inject_heartbeat(mav.PLANE_MODE_MANUAL)
        rig.backend.select(130.0, 4500.0)
        try:
            self.assertTrue(rig.backend.flying)
        finally:
            rig.close()


class SupervisionTests(unittest.TestCase):
    def engaged(self, rc=None, **kwargs):
        rig = Rig(**kwargs)
        feed(rig.client, rig.backend, **frame())
        rig.link.inject(mav.MSG_RC_CHANNELS, rc_frame() if rc is None else rc)
        rig.backend.select(120.0, 4500.0)
        rig.backend._stop.set()          # tests drive _step directly
        rig.backend._thread.join(timeout=2.0)
        return rig

    def test_rc_rest_is_measured_at_engagement_not_assumed_1500(self):
        # A rudder axis mapped 0.2-0.9 sits at 1429 us at rest. Measured from
        # 1500 that is 71 us and would release 0.3 s after every select.
        rig = self.engaged(rc=rc_frame(chan4_raw=1429, chan1_raw=1494))
        self.assertEqual(rig.backend.last_commands["rc_rest_us"], (1494, 1500, 1429))
        rig.advance(0.4)
        rig.link.inject_heartbeat(mav.PLANE_MODE_GUIDED)
        rig.link.inject(mav.MSG_RC_CHANNELS, rc_frame(chan4_raw=1429, chan1_raw=1494))
        feed(rig.client, rig.backend, **frame())
        self.assertTrue(rig.step())
        self.assertIsNone(rig.backend.last_fault)

    def test_rc_without_a_receiver_is_ignored(self):
        for rc in (rc_frame(chancount=0), rc_frame(chan1_raw=0, chan2_raw=0, chan4_raw=0)):
            with self.subTest(rc=rc["chancount"]):
                rig = self.engaged(rc=rc)
                self.assertIsNone(rig.backend.last_commands["rc_rest_us"])
                rig.advance(0.4)
                rig.link.inject_heartbeat(mav.PLANE_MODE_GUIDED)
                rig.link.inject(mav.MSG_RC_CHANNELS, rc_frame(chan1_raw=1900))
                feed(rig.client, rig.backend, **frame())
                self.assertTrue(rig.step(), "no baseline means the RC detector is inactive, not trigger-happy")

    def test_step_keeps_flying_when_healthy(self):
        rig = self.engaged()
        rig.link.inject(mav.MSG_RC_CHANNELS, rc_frame())
        rig.link.inject(mav.MSG_GLOBAL_POSITION_INT, gpi_frame(4500.0 * M_PER_FT))
        self.assertTrue(rig.step())
        self.assertIsNone(rig.backend.last_fault)

    def test_rc_yoke_input_releases(self):
        rig = self.engaged()
        rig.link.inject(mav.MSG_RC_CHANNELS, rc_frame(chan1_raw=1600))
        self.assertTrue(rig.step(), "a momentary deviation is not yet pilot input")
        rig.advance(0.4)
        rig.link.inject_heartbeat(mav.PLANE_MODE_GUIDED)
        rig.link.inject(mav.MSG_RC_CHANNELS, rc_frame(chan1_raw=1600))
        feed(rig.client, rig.backend, **frame())
        self.assertFalse(rig.step())
        self.assertIn("RC", rig.backend.last_fault)
        self.assertEqual(rig.commands()[-1], mav.MAV_CMD_DO_SET_MODE)
        self.assertEqual(rig.link.sent_messages[-1][1]["param2"], float(mav.PLANE_MODE_FBWA))
        self.assertFalse(rig.client.paused, "a takeover is a release, not a fault")

    def test_rc_deviation_below_deadband_is_ignored(self):
        rig = self.engaged()
        rig.link.inject(mav.MSG_RC_CHANNELS, rc_frame(chan2_raw=1530))
        rig.advance(0.4)
        rig.link.inject_heartbeat(mav.PLANE_MODE_GUIDED)
        rig.link.inject(mav.MSG_RC_CHANNELS, rc_frame(chan2_raw=1530))
        feed(rig.client, rig.backend, **frame())
        self.assertTrue(rig.step())

    def test_xplane_axis_input_releases(self):
        rig = Rig(joystick_axes={"pitch": 1, "roll": 0})
        feed(rig.client, rig.backend, **frame(), axis_pitch=0.02, axis_roll=-0.01)
        rig.backend.select(120.0, 4500.0)
        rig.backend._stop.set()
        rig.backend._thread.join(timeout=2.0)
        feed(rig.client, rig.backend, axis_pitch=0.30)
        self.assertFalse(rig.step())
        self.assertIn("yoke", rig.backend.last_fault)
        self.assertEqual(rig.link.sent_messages[-1][1]["param2"], float(mav.PLANE_MODE_LOITER))
        self.assertFalse(rig.client.paused)

    def test_heartbeat_loss_pauses_and_clears_override(self):
        rig = self.engaged()
        commands = rig.commands()
        rig.advance(3.0)
        feed(rig.client, rig.backend, **frame())    # X-Plane still fresh; only ArduPilot is silent
        self.assertFalse(rig.step())
        self.assertTrue(rig.client.paused)
        self.assertEqual(rig.commands(), commands, "no mode change to a controller that is not answering")
        self.assertIn(("sim/operation/override/override_joystick", 0), rig.client.writes)
        self.assertIn(("sim/operation/override/override_throttles", 0), rig.client.writes)
        self.assertIn("heartbeat", rig.backend.last_fault)

    def test_true_altitude_crosscheck_faults(self):
        rig = self.engaged()
        commands = rig.commands()
        rig.link.inject(mav.MSG_GLOBAL_POSITION_INT, gpi_frame((4500.0 + 200.0) * M_PER_FT))
        self.assertFalse(rig.step())
        self.assertTrue(rig.client.paused)
        self.assertEqual(rig.commands(), commands)
        self.assertIn("disagrees", rig.backend.last_fault)

    def test_envelope_fault_pauses(self):
        rig = self.engaged()
        feed(rig.client, rig.backend, **frame(kias=80.0))
        self.assertFalse(rig.step())
        self.assertTrue(rig.client.paused)
        self.assertIn("Airspeed", rig.backend.last_fault)

    def test_altitude_retarget_on_indicated_drift(self):
        rig = self.engaged()
        rig.advance(6.0)
        rig.link.inject_heartbeat(mav.PLANE_MODE_GUIDED)
        # Levelled 60 ft short: the altimeter setting drifted, ArduPilot thinks it is there.
        feed(rig.client, rig.backend, **frame(altitude_indicated_ft=4440.0, vvi_fpm=0.0,
                                              elevation_m=4500.0 * M_PER_FT))
        self.assertTrue(rig.step())
        self.assertEqual(rig.commands()[-1], mav.MAV_CMD_GUIDED_CHANGE_ALTITUDE)
        _msgid, fields = rig.link.sent_messages[-1]
        self.assertAlmostEqual(fields["z"], 4560.0 * M_PER_FT, places=2)
        self.assertEqual(rig.backend.last_commands["retargets"], 1)
        self.assertTrue(rig.step(), "no second retarget inside the minimum interval")
        self.assertEqual(rig.backend.last_commands["retargets"], 1)

    def test_no_retarget_while_still_climbing(self):
        rig = self.engaged()
        rig.advance(6.0)
        rig.link.inject_heartbeat(mav.PLANE_MODE_GUIDED)
        feed(rig.client, rig.backend, **frame(altitude_indicated_ft=4300.0, vvi_fpm=400.0))
        self.assertTrue(rig.step())
        self.assertNotIn("retargets", rig.backend.last_commands)

    def test_external_mode_change_releases(self):
        rig = self.engaged()
        rig.link.inject_heartbeat(mav.PLANE_MODE_LOITER)
        self.assertFalse(rig.step())
        self.assertIn("left GUIDED", rig.backend.last_fault)
        self.assertEqual(rig.link.sent_messages[-1][1]["param2"], float(mav.PLANE_MODE_FBWA))
        self.assertFalse(rig.client.paused)

    def test_g1000_engaged_releases(self):
        rig = self.engaged()
        feed(rig.client, rig.backend, ap_mode=2.0)
        self.assertFalse(rig.step())
        self.assertIn("autopilot engaged", rig.backend.last_fault)
        self.assertFalse(rig.client.paused)
        self.assertEqual(rig.link.sent_messages[-1][1]["param2"], float(mav.PLANE_MODE_FBWA))


class ThreadTests(unittest.TestCase):
    def test_release_from_supervisor_thread_does_not_self_join(self):
        rig = Rig(real_clock=True, joystick_axes={"pitch": 1, "roll": 0})
        feed(rig.client, rig.backend, **frame(), axis_pitch=0.0, axis_roll=0.0)
        rig.backend.select(120.0, 4500.0)
        thread = rig.backend._thread
        self.assertTrue(thread.is_alive())
        feed(rig.client, rig.backend, **frame(), axis_pitch=0.5)
        thread.join(timeout=3.0)
        self.assertFalse(thread.is_alive(), "supervisor must exit cleanly after releasing from its own thread")
        self.assertFalse(rig.backend.flying)
        self.assertEqual(rig.link.sent_messages[-1][1]["param2"], float(mav.PLANE_MODE_LOITER))
        self.assertIn("yoke", rig.backend.last_fault)

    def test_preflight_sends_nothing(self):
        rig = Rig(mode=mav.PLANE_MODE_MANUAL)
        feed(rig.client, rig.backend, **frame())
        rig.link.inject(mav.MSG_GLOBAL_POSITION_INT, gpi_frame(4500.0 * M_PER_FT))
        report = rig.backend.preflight()
        self.assertEqual(rig.timeline.events, [])
        self.assertEqual(report["ardupilot_mode"], mav.PLANE_MODE_MANUAL)
        self.assertAlmostEqual(report["mag_offset_deg"], 12.0, places=3)
        self.assertAlmostEqual(report["alt_offset_ft"], 0.0, places=3)
        self.assertAlmostEqual(report["ardupilot_minus_xplane_true_ft"], 0.0, places=2)
        self.assertIsNone(report["rc_position_us"])

    def test_takeover_that_also_breaks_the_envelope_releases_not_pauses(self):
        rig = Rig(joystick_axes={"pitch": 1, "roll": 0})
        feed(rig.client, rig.backend, **frame(), axis_pitch=0.0, axis_roll=0.0)
        rig.backend.select(120.0, 4500.0)
        rig.backend._stop.set()
        rig.backend._thread.join(timeout=2.0)
        feed(rig.client, rig.backend, **frame(roll_deg=42.0), axis_roll=0.6)
        self.assertFalse(rig.step())
        self.assertFalse(rig.client.paused, "the pilot rolling past the limit is a takeover, not a fault")
        self.assertEqual(rig.link.sent_messages[-1][1]["param2"], float(mav.PLANE_MODE_LOITER))


class HandBackModeTests(unittest.TestCase):
    """AI-21: MANUAL is never a hand-back mode. LOITER flies itself with no RC;
    FBWA is offered only when a valid centred stick was measured at engagement."""

    def test_release_uses_fbwa_when_rc_was_valid_at_engagement(self):
        rig = Rig()
        feed(rig.client, rig.backend, **frame())
        rig.link.inject(mav.MSG_RC_CHANNELS, rc_frame())
        rig.backend.select(120.0, 4500.0)
        rig.backend.release()
        self.assertEqual(rig.link.sent_messages[-1][1]["param2"], float(mav.PLANE_MODE_FBWA))
        self.assertEqual(rig.backend.last_commands["hand_back_mode"], "FBWA")

    def test_release_uses_loiter_when_rc_unproven(self):
        rig = Rig()
        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        rig.backend.release()
        self.assertEqual(rig.link.sent_messages[-1][1]["param2"], float(mav.PLANE_MODE_LOITER))
        self.assertEqual(rig.backend.last_commands["hand_back_mode"], "LOITER")

    def test_release_never_sends_manual(self):
        for rc in (None, rc_frame(), rc_frame(chancount=0), rc_frame(chan1_raw=0, chan2_raw=0, chan4_raw=0)):
            with self.subTest(rc=rc and rc["chancount"]):
                rig = Rig()
                feed(rig.client, rig.backend, **frame())
                if rc is not None:
                    rig.link.inject(mav.MSG_RC_CHANNELS, rc)
                rig.backend.select(120.0, 4500.0)
                rig.backend.release()
                modes = [f["param2"] for _m, f in rig.link.sent_messages
                         if f.get("command") == mav.MAV_CMD_DO_SET_MODE]
                self.assertNotIn(float(mav.PLANE_MODE_MANUAL), modes)

    def test_heading_accel_is_never_zero(self):
        self.assertGreaterEqual(ArduPlaneBackend.HEADING_ACCEL_M_S2, 0.5)
        rig = Rig(mode=mav.PLANE_MODE_GUIDED)
        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        try:
            heading = [f for _m, f in rig.link.sent_messages
                       if f.get("command") == mav.MAV_CMD_GUIDED_CHANGE_HEADING][0]
            self.assertGreaterEqual(heading["param3"], 0.5)
        finally:
            rig.close()

    def test_altitude_of_zero_is_refused_before_sending(self):
        # frame() has the altimeter set correctly, so a 0 ft target maps to
        # exactly 0 m true - the value ArduPlane answers DENIED to.
        rig = Rig(mode=mav.PLANE_MODE_GUIDED)
        feed(rig.client, rig.backend, **frame())
        with self.assertRaisesRegex(ValueError, "not accepted"):
            rig.backend.select(120.0, 0.0)
        self.assertEqual([f for _m, f in rig.link.sent_messages
                          if f.get("command") == mav.MAV_CMD_GUIDED_CHANGE_ALTITUDE], [])
        self.assertFalse(rig.backend.flying)

    def test_preflight_reports_armed_bit(self):
        rig = Rig(mode=mav.PLANE_MODE_MANUAL)
        feed(rig.client, rig.backend, **frame())
        self.assertTrue(rig.backend.preflight()["armed"])
        rig.link.inject_heartbeat(mav.PLANE_MODE_MANUAL,
                                  base_mode=mav.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED)
        self.assertFalse(rig.backend.preflight()["armed"])


class SecureOnAttachTests(unittest.TestCase):
    """AI-23: SITL can attach in a navigating mode with a default Home on the
    other side of the planet. Nothing may command the aircraft until it is
    parked."""

    def test_sets_home_here_then_loiter(self):
        rig = Rig(mode=mav.PLANE_MODE_RTL)
        feed(rig.client, rig.backend, **frame())
        self.assertEqual(rig.backend.secure_on_attach(), mav.PLANE_MODE_LOITER)
        self.assertEqual(rig.commands(), [mav.MAV_CMD_DO_SET_HOME, mav.MAV_CMD_DO_SET_MODE])
        home = rig.link.sent_messages[0][1]
        self.assertEqual(home["param1"], 1.0, "param1=1 means 'use current location'")
        self.assertEqual(rig.link.sent_messages[1][1]["param2"], float(mav.PLANE_MODE_LOITER))

    def test_skips_the_mode_change_when_already_loitering(self):
        rig = Rig(mode=mav.PLANE_MODE_LOITER)
        feed(rig.client, rig.backend, **frame())
        rig.backend.secure_on_attach()
        self.assertEqual(rig.commands(), [mav.MAV_CMD_DO_SET_HOME])

    def test_raises_when_loiter_is_refused(self):
        rig = Rig(mode=mav.PLANE_MODE_RTL, real_clock=True)
        rig.link.honour_mode_changes = False
        feed(rig.client, rig.backend, **frame())
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "would not enter LOITER"):
            rig.backend.secure_on_attach(timeout=1.0)
        self.assertLess(time.monotonic() - started, 2.5)

    def test_select_still_works_after_securing(self):
        rig = Rig(mode=mav.PLANE_MODE_RTL)
        feed(rig.client, rig.backend, **frame())
        rig.backend.secure_on_attach()
        rig.backend.select(120.0, 4500.0)
        try:
            self.assertIn(mav.MAV_CMD_GUIDED_CHANGE_HEADING, rig.commands())
            self.assertTrue(rig.backend.flying)
        finally:
            rig.close()


if __name__ == "__main__":
    unittest.main()
