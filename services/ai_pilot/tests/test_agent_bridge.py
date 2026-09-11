"""Unit tests for AgentBridge tool dispatch and schemas."""

import unittest

from services.ai_pilot.agent_bridge import HERMES_TOOLS, AgentBridge
from services.ai_pilot.flight_controller import FlightController, FlightPhase
from services.ai_pilot.xplane_udp import XPlaneUDPClient


class TestAgentBridge(unittest.TestCase):
    def setUp(self):
        self.client = XPlaneUDPClient(mock=True)
        self.controller = FlightController(self.client)
        self.bridge = AgentBridge(self.controller)

    def tearDown(self):
        self.client.stop()

    def test_tool_schemas_valid(self):
        self.assertGreater(len(HERMES_TOOLS), 0)
        tool_names = [t["function"]["name"] for t in HERMES_TOOLS]
        self.assertIn("get_flight_telemetry", tool_names)
        self.assertIn("execute_checklist", tool_names)
        self.assertIn("command_flight_phase", tool_names)
        self.assertIn("set_autopilot", tool_names)
        self.assertIn("spawn_on_runway", tool_names)

    def test_dispatch_get_flight_telemetry(self):
        self.client.set_mock_dref("sim/flightmodel/position/indicated_airspeed", 110.0)
        self.client.set_mock_dref("sim/flightmodel/position/elevation", 4500.0 * 0.3048)
        self.controller.set_phase(FlightPhase.CRUISE)

        res = self.bridge.dispatch_tool("get_flight_telemetry", {})
        self.assertEqual(res["phase"], "CRUISE")
        self.assertAlmostEqual(res["kias"], 110.0, places=1)
        self.assertAlmostEqual(res["alt_msl_ft"], 4500.0, places=0)
        self.assertIn("distance_to_krnm_nm", res)

    def test_dispatch_execute_checklist(self):
        res = self.bridge.dispatch_tool("execute_checklist", {"checklist_name": "BEFORE_ENGINE_START"})
        self.assertTrue(res["success"])
        self.assertEqual(res["checklist"], "Before Starting Engine")
        self.assertTrue(res["all_passed"])

    def test_dispatch_command_flight_phase(self):
        res = self.bridge.dispatch_tool("command_flight_phase", {"phase": "TAKEOFF_ROLL"})
        self.assertTrue(res["success"])
        self.assertEqual(self.controller.phase, FlightPhase.TAKEOFF_ROLL)

        # Invalid phase
        res_invalid = self.bridge.dispatch_tool("command_flight_phase", {"phase": "FLY_TO_MARS"})
        self.assertFalse(res_invalid["success"])

    def test_dispatch_set_autopilot(self):
        res = self.bridge.dispatch_tool("set_autopilot", {"heading_mag": 15.0, "altitude_ft": 4500.0, "vs_fpm": 700.0})
        self.assertTrue(res["success"])
        self.assertEqual(self.client.get_dref("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot"), 15.0)
        self.assertEqual(self.client.get_dref("sim/cockpit2/autopilot/altitude_dial_ft"), 4500.0)


if __name__ == "__main__":
    unittest.main()
