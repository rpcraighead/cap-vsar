"""Unit tests for flight controller guidance laws and state machine."""

import unittest

from services.ai_pilot.flight_controller import (
    FlightController,
    FlightPhase,
    haversine_distance_nm,
    initial_bearing_deg,
)
from services.ai_pilot.xplane_udp import XPlaneUDPClient


class TestFlightController(unittest.TestCase):
    def setUp(self):
        self.client = XPlaneUDPClient(mock=True)
        self.controller = FlightController(self.client)

    def tearDown(self):
        self.client.stop()

    def test_haversine_and_bearing(self):
        # KSEE 27R threshold to KRNM 27 threshold
        lat1, lon1, _ = self.controller.KSEE_27R_THRESHOLD
        lat2, lon2, _ = self.controller.KRNM_27_THRESHOLD

        dist_nm = haversine_distance_nm(lat1, lon1, lat2, lon2)
        # Distance should be ~13.1 - 13.5 NM
        self.assertGreater(dist_nm, 12.5)
        self.assertLess(dist_nm, 14.0)

        bearing_true = initial_bearing_deg(lat1, lon1, lat2, lon2)
        # Direct track is North-Northeast (~013° True)
        self.assertGreater(bearing_true, 10.0)
        self.assertLess(bearing_true, 25.0)

    def test_spawn_on_ksee_27r(self):
        self.controller.spawn_on_ksee_27r()
        self.assertEqual(self.controller.phase, FlightPhase.COLD_AND_DARK)

        lat = self.client.get_dref("sim/flightmodel/position/latitude")
        lon = self.client.get_dref("sim/flightmodel/position/longitude")
        self.assertAlmostEqual(lat, self.controller.KSEE_27R_THRESHOLD[0], places=4)
        self.assertAlmostEqual(lon, self.controller.KSEE_27R_THRESHOLD[1], places=4)

    def test_takeoff_roll_and_rotation(self):
        self.controller.set_phase(FlightPhase.TAKEOFF_ROLL)
        # Set telemetry below Vr
        self.client.set_mock_dref("sim/flightmodel/position/indicated_airspeed", 45.0)
        self.client.set_mock_dref("sim/flightmodel/position/mag_psi", 274.0)

        phase = self.controller.step()
        self.assertEqual(phase, FlightPhase.TAKEOFF_ROLL)
        # Full throttle commanded
        self.assertEqual(self.client.get_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]"), 1.0)

        # Now cross Vr = 60 KIAS
        self.client.set_mock_dref("sim/flightmodel/position/indicated_airspeed", 62.0)
        phase = self.controller.step()
        self.assertEqual(phase, FlightPhase.ROTATE_AND_CLIMB)

    def test_climb_and_enroute_transition(self):
        self.controller.set_phase(FlightPhase.ROTATE_AND_CLIMB)
        self.client.set_mock_dref("sim/flightmodel/position/elevation", 1200.0 * 0.3048)  # 1200 ft MSL
        phase = self.controller.step()
        self.assertEqual(phase, FlightPhase.ROTATE_AND_CLIMB)

        # Cross 1,500 ft MSL
        self.client.set_mock_dref("sim/flightmodel/position/elevation", 1550.0 * 0.3048)
        phase = self.controller.step()
        self.assertEqual(phase, FlightPhase.ENROUTE_CLIMB)
        self.assertEqual(self.controller.target_altitude_ft, 4500.0)

    def test_full_mission_mock_progression(self):
        from services.ai_pilot.mission_ksee_krnm import run_mission

        success = run_mission(live=False, fast_sim=True)
        self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()
