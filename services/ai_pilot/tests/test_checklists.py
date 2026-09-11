"""Unit tests for authentic Cessna 182T NAV III POH checklists."""

import unittest

from services.ai_pilot.c182t_checklists import (
    ALL_CHECKLISTS,
    ChecklistPhase,
    get_after_landing_checklist,
    get_before_engine_start_checklist,
    get_before_landing_checklist,
    get_before_takeoff_checklist,
    get_checklist_by_name,
    get_cruise_checklist,
    get_descent_checklist,
    get_engine_start_checklist,
    get_shutdown_and_securing_checklist,
    get_takeoff_and_climb_checklist,
)
from services.ai_pilot.xplane_udp import XPlaneUDPClient


class TestC182TChecklists(unittest.TestCase):
    def setUp(self):
        self.client = XPlaneUDPClient(mock=True)

    def tearDown(self):
        self.client.stop()

    def test_all_checklists_registered(self):
        self.assertEqual(len(ALL_CHECKLISTS), 9)
        for phase in ChecklistPhase:
            self.assertIn(phase, ALL_CHECKLISTS)
            cl = ALL_CHECKLISTS[phase]()
            self.assertGreater(len(cl.items), 0)
            self.assertEqual(cl.phase, phase)

    def test_before_engine_start_execution(self):
        cl = get_before_engine_start_checklist()
        results = cl.run(self.client, delay_between_items=0.0)
        self.assertEqual(len(results), len(cl.items))
        self.assertTrue(all(r["passed"] for r in results))

        # Check that parking brake is set to 1.0 and avionics master is 0.0
        self.assertEqual(self.client.get_dref("sim/cockpit2/controls/parking_brake_ratio"), 1.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/switches/avionics_power_on"), 0.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/fuel/fuel_tank_selector"), 4.0)

    def test_engine_start_execution(self):
        # Seed oil pressure to green arc for verification
        self.client.set_mock_dref("sim/cockpit2/engine/indicators/oil_pressure_psi[0]", 35.0)

        cl = get_engine_start_checklist()
        results = cl.run(self.client, delay_between_items=0.0)
        self.assertTrue(all(r["passed"] for r in results))

        # Battery ON, Alt ON, Avionics ON, Ignition BOTH (3.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/electrical/battery_on[0]"), 1.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/electrical/generator_on[0]"), 1.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/switches/avionics_power_on"), 1.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/engine/actuators/ignition_key[0]"), 3.0)

    def test_before_takeoff_execution(self):
        self.client.set_mock_dref("sim/cockpit2/engine/indicators/oil_pressure_psi[0]", 50.0)
        cl = get_before_takeoff_checklist(runway_heading_mag=274.0, target_altitude_ft=4500.0)
        results = cl.run(self.client, delay_between_items=0.0)
        self.assertTrue(all(r["passed"] for r in results))

        # Heading bug 274, altitude bug 4500, strobe lights ON
        self.assertEqual(self.client.get_dref("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot"), 274.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/autopilot/altitude_dial_ft"), 4500.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/switches/strobe_lights_on"), 1.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/controls/parking_brake_ratio"), 0.0)

    def test_shutdown_execution(self):
        cl = get_shutdown_and_securing_checklist()
        results = cl.run(self.client, delay_between_items=0.0)
        self.assertTrue(all(r["passed"] for r in results))

        # Mixture 0.0, Ignition 0.0, Battery 0.0, Parking Brake 1.0
        self.assertEqual(self.client.get_dref("sim/cockpit2/engine/actuators/mixture_ratio[0]"), 0.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/engine/actuators/ignition_key[0]"), 0.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/electrical/battery_on[0]"), 0.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/controls/parking_brake_ratio"), 1.0)

    def test_get_checklist_by_name(self):
        cl = get_checklist_by_name("ENGINE_START")
        self.assertIsNotNone(cl)
        self.assertEqual(cl.phase, ChecklistPhase.ENGINE_START)

        cl_invalid = get_checklist_by_name("NON_EXISTENT")
        self.assertIsNone(cl_invalid)


if __name__ == "__main__":
    unittest.main()
