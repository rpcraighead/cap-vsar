"""Unit tests for LightweightAgent and Web Server REST APIs."""

import json
import threading
import time
import unittest
import urllib.request
from http.server import HTTPServer

from services.ai_pilot.flight_controller import FlightController, FlightPhase
from services.ai_pilot.lightweight_agent import LightweightAgent
from services.ai_pilot.web_server import AIPilotRequestHandler, ThreadingHTTPServer
from services.ai_pilot.xplane_udp import XPlaneUDPClient


class TestLightweightAgent(unittest.TestCase):
    def setUp(self):
        self.client = XPlaneUDPClient(mock=True)
        self.controller = FlightController(self.client)
        self.agent = LightweightAgent(self.controller)

    def tearDown(self):
        self.client.stop()

    def test_handle_spawn_command(self):
        reply = self.agent.handle_user_command("spawn at runway 27r")
        self.assertIn("Gillespie Field", reply)
        self.assertEqual(self.controller.phase, FlightPhase.COLD_AND_DARK)

    def test_handle_engine_start_command(self):
        reply = self.agent.handle_user_command("start engine")
        self.assertIn("Lycoming IO-540", reply)
        self.assertEqual(self.client.get_dref("sim/cockpit2/electrical/battery_on[0]"), 1.0)

    def test_handle_takeoff_command(self):
        reply = self.agent.handle_user_command("cleared for takeoff")
        self.assertIn("takeoff", reply.lower())
        self.assertEqual(self.controller.phase, FlightPhase.TAKEOFF_ROLL)

    def test_handle_heading_command(self):
        reply = self.agent.handle_user_command("turn heading 015")
        self.assertIn("015", reply)
        self.assertEqual(self.controller.target_heading_mag, 15.0)

    def test_handle_altitude_command(self):
        reply = self.agent.handle_user_command("climb to 4500")
        self.assertIn("4500", reply)
        self.assertEqual(self.controller.target_altitude_ft, 4500.0)

    def test_handle_status_query(self):
        self.client.set_mock_dref("sim/flightmodel/position/indicated_airspeed", 120.0)
        reply = self.agent.handle_user_command("what is our status?")
        self.assertIn("Airspeed", reply)
        self.assertIn("120", reply)

    def test_chat_history_logging(self):
        initial_count = len(self.agent.get_chat_history())
        self.agent.handle_user_command("test message")
        self.assertEqual(len(self.agent.get_chat_history()), initial_count + 2)


class TestWebServerAPIs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = XPlaneUDPClient(mock=True)
        cls.controller = FlightController(cls.client)
        cls.agent = LightweightAgent(cls.controller)

        AIPilotRequestHandler.client = cls.client
        AIPilotRequestHandler.controller = cls.controller
        AIPilotRequestHandler.agent = cls.agent

        # Bind to port 0 for ephemeral testing port
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), AIPilotRequestHandler)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.client.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path: str):
        req = urllib.request.Request(f"{self.base_url}{path}")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status, resp.read()

    def _post_json(self, path: str, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_static_files(self):
        status, content = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"AI Pilot Deck", content)

        status, css = self._get("/style.css")
        self.assertEqual(status, 200)
        self.assertIn(b"--accent-cyan", css)

        status, js = self._get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"drawAttitude", js)

    def test_get_telemetry_api(self):
        status, content = self._get("/api/telemetry")
        self.assertEqual(status, 200)
        data = json.loads(content.decode("utf-8"))
        self.assertIn("phase", data)
        self.assertIn("flight_dynamics", data)
        self.assertIn("engine", data)
        self.assertIn("navigation", data)

    def test_get_checklists_api(self):
        status, content = self._get("/api/checklists")
        self.assertEqual(status, 200)
        data = json.loads(content.decode("utf-8"))
        self.assertEqual(len(data["checklists"]), 9)

    def test_post_chat_api(self):
        status, data = self._post_json("/api/chat", {"message": "climb to 4500"})
        self.assertEqual(status, 200)
        self.assertIn("reply", data)
        self.assertIn("4500", data["reply"])

    def test_post_phase_api(self):
        status, data = self._post_json("/api/phase", {"phase": "TAKEOFF_ROLL"})
        self.assertEqual(status, 200)
        self.assertEqual(data["phase"], "TAKEOFF_ROLL")

    def test_post_autopilot_api(self):
        status, data = self._post_json("/api/autopilot", {"heading_mag": 15.0, "altitude_ft": 4500.0})
        self.assertEqual(status, 200)
        self.assertEqual(data["heading_mag"], 15.0)
        self.assertEqual(data["altitude_ft"], 4500.0)

    def test_post_run_checklist_api(self):
        status, data = self._post_json("/api/checklists/run", {"checklist": "BEFORE_ENGINE_START"})
        self.assertEqual(status, 200)
        self.assertTrue(data["all_passed"])
        self.assertGreater(len(data["results"]), 0)


if __name__ == "__main__":
    unittest.main()

