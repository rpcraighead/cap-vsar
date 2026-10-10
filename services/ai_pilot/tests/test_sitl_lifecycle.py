"""Offline tests for the SITL lifecycle and the detach order.

No process is started and nothing talks to a simulator: a fake Popen and a
fake X-Plane client record what would have happened, in order. The order is
the requirement - overrides can only be cleared after SITL is gone, and the
GFC 700 can only be engaged after that.
"""

from __future__ import annotations

import unittest
import json
from pathlib import Path

from services.ai_pilot import sitl_lifecycle as sl
from services.ai_pilot.tests.test_direct_backend import FakeClient


class FakeProcess:
    def __init__(self):
        self.signals = []
        self._rc = None

    def poll(self):
        return self._rc

    def terminate(self):
        self.signals.append("TERM")
        self._rc = 0

    def kill(self):
        self.signals.append("KILL")
        self._rc = -9

    def wait(self, timeout=None):
        return self._rc


class StubbornProcess(FakeProcess):
    def terminate(self):
        self.signals.append("TERM")      # ignores it


class Timeline:
    """Interleaves client writes/commands and the SITL stop into one log."""

    def __init__(self, client, sitl):
        self.events = []
        write, command, stop = client.send_dref, client.send_command, sitl.stop

        def send_dref(ref, value):
            self.events.append(("dref", ref, value))
            write(ref, value)

        def send_command(cmd):
            self.events.append(("cmd", cmd))
            command(cmd)

        def stopped(*args, **kwargs):
            self.events.append(("sitl", "stop"))
            return stop(*args, **kwargs)

        client.send_dref, client.send_command, sitl.stop = send_dref, send_command, stopped


class FakeBackend:
    def __init__(self, hand_back_mode="LOITER"):
        self.released = 0
        self.last_commands = {"hand_back_mode": hand_back_mode}

    def release(self):
        self.released += 1


def make_sitl(process):
    clock = [0.0]
    sitl = sl.SitlProcess("/bin/false", "/tmp", "/tmp/x.parm", "/dev/null",
                          popen=lambda *a, **k: process, clock=lambda: clock[0],
                          sleep=lambda s: clock.__setitem__(0, clock[0] + s),
                          candidate_session="a" * 32,
                          mapping_validator=lambda mapping, session: None,
                          mapping_loader=lambda path: {})
    return sitl, clock


class SitlProcessTests(unittest.TestCase):
    def test_stock_native_mapping_is_rejected_before_process_start(self):
        stock = json.loads((Path(__file__).parents[3] /
                            "xplane/ardupilot/xplane_plane_cap487.json").read_text())
        started = []
        sitl = sl.SitlProcess("/bin/false", "/tmp", "/tmp/x.parm", "/dev/null",
                              candidate_session="a" * 32,
                              mapping_loader=lambda path: stock,
                              popen=lambda *args, **kwargs: started.append(args))
        with self.assertRaisesRegex(ValueError, "Incomplete candidate"):
            sitl.start()
        self.assertEqual(started, [])

    def test_stop_terminates_then_kills_a_stubborn_process(self):
        process = StubbornProcess()
        sitl, _ = make_sitl(process)
        sitl.start()
        self.assertTrue(sitl.stop(grace=1.0))
        self.assertEqual(process.signals, ["TERM", "KILL"])
        self.assertFalse(sitl.alive)

    def test_stop_is_gentle_when_term_suffices(self):
        process = FakeProcess()
        sitl, _ = make_sitl(process)
        sitl.start()
        sitl.stop()
        self.assertEqual(process.signals, ["TERM"])

    def test_stop_without_a_process_is_a_noop(self):
        sitl, _ = make_sitl(FakeProcess())
        self.assertTrue(sitl.stop())

    def test_wait_for_mavlink_gives_up_if_the_process_died(self):
        process = FakeProcess()
        process._rc = 1
        sitl, _ = make_sitl(process)
        sitl.start()
        self.assertFalse(sitl.wait_for_mavlink(timeout=5.0, probe=lambda port: False))

    def test_wait_for_mavlink_returns_when_the_port_opens(self):
        sitl, _ = make_sitl(FakeProcess())
        sitl.start()
        calls = []
        opened = sitl.wait_for_mavlink(timeout=5.0,
                                       probe=lambda port: bool(calls.append(port)) or len(calls) >= 3)
        self.assertTrue(opened)
        self.assertEqual(calls, [5760, 5760, 5760])

    def test_wait_for_mavlink_times_out(self):
        sitl, _ = make_sitl(FakeProcess())
        sitl.start()
        self.assertFalse(sitl.wait_for_mavlink(timeout=2.0, probe=lambda port: False))


class DetachOrderTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.process = FakeProcess()
        self.sitl, _ = make_sitl(self.process)
        self.sitl.start()
        self.backend = FakeBackend()
        self.timeline = Timeline(self.client, self.sitl)

    def keys(self):
        return [event[1] if event[0] == "dref" else event[0] for event in self.timeline.events]

    def readback(self, heading, altitude):
        return {"age_seconds": 0.0, "servos_on": 1,
                "flight_director_mode": 2, "ap_state": 2 | 16384,
                "heading_selected_deg": heading % 360,
                "altitude_selected_ft": round(altitude / 100) * 100}

    def test_overrides_are_cleared_only_after_sitl_is_stopped(self):
        sl.detach(self.backend, self.client, self.sitl,
                  {"servos_on": 0, "ap_state": 0}, 270.0, 4500.0)
        keys = self.keys()
        stopped_at = keys.index("sitl")
        self.assertLess(stopped_at, keys.index("sim/operation/override/override_joystick"))
        self.assertLess(stopped_at, keys.index("sim/operation/override/override_throttles"))
        self.assertEqual(self.backend.released, 1)
        self.assertIn(("sim/operation/override/override_joystick", 0), self.client.writes)
        self.assertIn(("sim/operation/override/override_throttles", 0), self.client.writes)

    def test_gfc700_is_engaged_after_the_overrides_are_cleared(self):
        sl.detach(self.backend, self.client, self.sitl,
                  {"servos_on": 1, "ap_state": 2, "flight_director_mode": 2,
                   "age_seconds": 0}, 270.0, 4520.0,
                  target="gfc700", verify_gfc=lambda: self.readback(270, 4520))
        last_override = max(i for i, e in enumerate(self.timeline.events)
                            if e[0] == "dref" and "override" in e[1])
        first_command = min(i for i, e in enumerate(self.timeline.events) if e[0] == "cmd")
        self.assertLess(last_override, first_command)

    def test_live_autopilot_is_not_toggled_off(self):
        result = sl.detach(self.backend, self.client, self.sitl,
                           {"servos_on": 1, "ap_state": 2, "flight_director_mode": 2,
                            "age_seconds": 0}, 270.0, 4520.0,
                           target="gfc700", verify_gfc=lambda: self.readback(270, 4520))
        self.assertEqual(result["gfc700_commands"], ["sim/GPS/g1000n1_alt"])
        self.assertIn(("sim/cockpit2/autopilot/altitude_dial_ft", 4500.0), self.client.writes)
        self.assertIn(("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot", 270.0), self.client.writes)

    def test_ap_is_pressed_only_when_the_servos_are_off(self):
        result = sl.detach(self.backend, self.client, self.sitl,
                           {"servos_on": 0, "ap_state": 0, "flight_director_mode": 0,
                            "age_seconds": 0}, 10.0, 3000.0,
                           target="gfc700", verify_gfc=lambda: self.readback(10, 3000))
        self.assertEqual(result["gfc700_commands"],
                         ["sim/GPS/g1000n1_ap", "sim/GPS/g1000n1_hdg", "sim/GPS/g1000n1_alt"])

    def test_heading_is_wrapped(self):
        sl.detach(self.backend, self.client, self.sitl,
                  {"servos_on": 1, "ap_state": 2, "flight_director_mode": 2,
                   "age_seconds": 0}, 371.0, 4000.0,
                  target="gfc700", verify_gfc=lambda: self.readback(371, 4000))
        self.assertIn(("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot", 11.0), self.client.writes)

    def test_garmin_transfer_requires_actual_servo_mode_and_dial_readback(self):
        result = sl.detach(self.backend, self.client, self.sitl,
                           {"servos_on": 0, "ap_state": 0,
                            "flight_director_mode": 0, "age_seconds": 0},
                           90, 4000, target="gfc700",
                           verify_gfc=lambda: {**self.readback(90, 4000),
                                               "flight_director_mode": 1})
        self.assertFalse(result["gfc700_verified"])
        self.assertTrue(any("did not confirm" in e for e in result["errors"]))
        self.assertNotIn(("sim/cockpit2/autopilot/servos_on", 1), self.client.writes)

    def test_detach_without_sitl_does_not_claim_or_clear_an_unmanaged_writer(self):
        result = sl.detach(self.backend, self.client, None,
                           {"servos_on": 0, "ap_state": 0}, 90.0, 4000.0)
        self.assertIsNone(result["sitl_stopped"])
        self.assertNotIn(("sim/operation/override/override_joystick", 0), self.client.writes)
        self.assertFalse(result["gfc700_commands"])
        self.assertEqual(result["hand_back_mode"], "LOITER")

    def test_unconfirmed_sitl_stop_cannot_clear_overrides_or_engage_garmin(self):
        self.sitl.stop = lambda: False
        result = sl.detach(self.backend, self.client, self.sitl,
                           {"servos_on": 0, "ap_state": 0}, 90, 4000,
                           target="gfc700", verify_gfc=lambda: self.readback(90, 4000))
        self.assertFalse(result["sitl_stopped"])
        self.assertFalse(result["overrides_clear_requested"])
        self.assertFalse(result["gfc700_commands"])
        self.assertFalse(self.client.commands)

    def test_human_and_fault_detach_do_not_auto_engage_garmin(self):
        for target in ("human", "fault_pause", "ground_stop"):
            client = FakeClient()
            sitl, _ = make_sitl(FakeProcess())
            sitl.start()
            result = sl.detach(FakeBackend(), client, sitl,
                               {"servos_on": 0, "ap_state": 0}, 90, 4000,
                               target=target)
            self.assertFalse(result["gfc700_commands"])
            self.assertFalse(client.commands)

    def test_release_failure_still_stops_writer_and_requests_override_clear(self):
        def fail():
            raise RuntimeError("release failed")
        result = sl.detach(self.backend, self.client, self.sitl,
                           {}, 90, 4000, release=fail)
        self.assertTrue(result["sitl_stopped"])
        self.assertTrue(result["overrides_clear_requested"])
        self.assertIn("release failed", result["errors"][0])

    def test_detach_reports_the_backend_hand_back_mode(self):
        backend = FakeBackend(hand_back_mode="FBWA")
        result = sl.detach(backend, self.client, self.sitl,
                           {"servos_on": 0, "ap_state": 0}, 90.0, 4000.0)
        self.assertEqual(result["hand_back_mode"], "FBWA")

    def test_detach_can_skip_a_release_the_gate_already_did(self):
        sl.detach(self.backend, self.client, self.sitl,
                  {"servos_on": 0, "ap_state": 0}, 90.0, 4000.0, release=lambda: None)
        self.assertEqual(self.backend.released, 0)


if __name__ == "__main__":
    unittest.main()
