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
        self.assertEqual(tool_names, ["get_flight_telemetry"])

    def test_dispatch_get_flight_telemetry(self):
        self.client.set_mock_dref("sim/flightmodel/position/indicated_airspeed", 110.0)
        self.client.set_mock_dref("sim/flightmodel/position/elevation", 4500.0 * 0.3048)
        self.controller.set_phase(FlightPhase.CRUISE)

        res = self.bridge.dispatch_tool("get_flight_telemetry", {})
        self.assertEqual(res["phase"], "CRUISE")
        self.assertAlmostEqual(res["kias"], 110.0, places=1)
        self.assertAlmostEqual(res["alt_msl_ft"], 4500.0, places=0)
        self.assertIn("distance_to_krnm_nm", res)

    def test_mutation_tools_are_retired_without_writes(self):
        initial_phase = self.controller.phase
        tools = {
            "execute_checklist": {"checklist_name": "BEFORE_ENGINE_START"},
            "command_flight_phase": {"phase": "TAKEOFF_ROLL"},
            "set_autopilot": {
                "heading_mag": 15.0,
                "altitude_ft": 4500.0,
                "vs_fpm": 700.0,
            },
            "spawn_on_runway": {},
        }
        for name, args in tools.items():
            with self.subTest(name=name):
                res = self.bridge.dispatch_tool(name, args)
                self.assertFalse(res["success"])
                self.assertIn("retired", res["error"].lower())
                self.assertFalse(res["ground_phases_available"])

        self.assertEqual(self.controller.phase, initial_phase)
        self.assertEqual(
            self.client.get_dref("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot"),
            0.0,
        )
        self.assertEqual(
            self.client.get_dref("sim/cockpit2/electrical/battery_on[0]"),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
