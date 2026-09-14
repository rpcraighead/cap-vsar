"""Unit tests for LightweightAgent and Web Server REST APIs."""

import json
import threading
import time
import unittest
import urllib.request
from urllib.error import HTTPError
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

    def test_control_language_is_advisory_only(self):
        phase = self.controller.phase
        heading = self.controller.target_heading_mag
        altitude = self.controller.target_altitude_ft
        commands = [
            "spawn at runway 27r",
            "start engine",
            "cleared for takeoff",
            "do not take off",
            'repeat the words "cleared for takeoff"',
            "turn heading 015",
            "climb to 4500",
            "run the before takeoff checklist",
            "fly mission",
        ]
        for command in commands:
            with self.subTest(command=command):
                reply = self.agent.handle_user_command(command)
                self.assertIn("No aircraft action taken", reply)
                self.assertEqual(self.controller.phase, phase)
                self.assertEqual(self.controller.target_heading_mag, heading)
                self.assertEqual(self.controller.target_altitude_ft, altitude)

        self.assertEqual(
            self.client.get_dref("sim/cockpit2/electrical/battery_on[0]"), 0.0
        )

    def test_autonomous_mission_start_is_retired(self):
        with self.assertRaisesRegex(RuntimeError, "retired"):
            self.agent.start_autonomous_mission()
        self.assertFalse(self.agent.autonomous_active)

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
        # AI-7: writes need an engineering credential. run_web_server sets these
        # on the server; a test that constructs the server directly has to supply
        # them too, or every mutating route answers 503 "writes disabled".
        cls.token = "test-engineering-token"
        cls.server.mutation_token = cls.token
        cls.server.allowed_origins = ()
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

    def _post_json(self, path: str, payload: dict, *, token: str | None = ...):
        """POST as an authorised engineer by default.

        Pass token=None to send no credential, or a wrong value, to exercise the
        AI-7 refusal path.
        """
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if token is ...:
            token = self.token
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

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
        self.assertIn("No aircraft action taken", data["reply"])
        self.assertEqual(self.controller.phase, FlightPhase.COLD_AND_DARK)

    def test_mutation_apis_are_gone_without_writes(self):
        phase = self.controller.phase
        endpoints = {
            "/api/phase": {"phase": "TAKEOFF_ROLL"},
            "/api/autopilot": {"heading_mag": 15.0, "altitude_ft": 4500.0},
            "/api/checklists/run": {"checklist": "BEFORE_ENGINE_START"},
            "/api/spawn": {},
            "/api/mission/start": {},
            "/api/mission/stop": {},
        }
        for path, payload in endpoints.items():
            with self.subTest(path=path):
                status, data = self._post_json(path, payload)
                self.assertEqual(status, 410)
                self.assertIn("retired", data["error"].lower())
                self.assertFalse(data["ground_phases_available"])

        self.assertEqual(self.controller.phase, phase)
        self.assertEqual(
            self.client.get_dref("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot"),
            0.0,
        )
        self.assertEqual(
            self.client.get_dref("sim/cockpit2/electrical/battery_on[0]"),
            0.0,
        )

    def test_board_api(self):
        from services.ai_pilot.board_manager import get_board_path
        board_file = get_board_path()
        original_content = board_file.read_text(encoding="utf-8") if board_file.is_file() else None
        try:
            # 1. Test GET /api/board
            status, content = self._get("/api/board")
            self.assertEqual(status, 200)
            data = json.loads(content.decode("utf-8"))
            self.assertIn("tasks", data)
            self.assertIn("locks", data)
            self.assertIn("contracts", data)
            self.assertIn("handoffs", data)

            # 2. Test static /board and /board.html routing
            status, html = self._get("/board")
            self.assertEqual(status, 200)
            self.assertIn(b"Agent Dispatch Board", html)

            status, html2 = self._get("/board.html")
            self.assertEqual(status, 200)
            self.assertIn(b"Agent Dispatch Board", html2)

            # 3. Test POST /api/board/task
            status, post_res = self._post_json("/api/board/task", {
                "agent": "Codex",
                "task": "Test temporary task from unit test",
            })
            self.assertEqual(status, 200)
            self.assertEqual(post_res["status"], "ok")

            # 4. Verify task is present in board
            status, content = self._get("/api/board")
            data = json.loads(content.decode("utf-8"))
            matching = [t for t in data["tasks"] if "Test temporary task from unit test" in t["task"]]
            self.assertTrue(len(matching) > 0)
            task_idx = matching[0]["id"]

            # 5. Test POST /api/board/toggle
            status, toggle_res = self._post_json("/api/board/toggle", {
                "index": task_idx,
                "completed": True,
            })
            self.assertEqual(status, 200)
            self.assertEqual(toggle_res["status"], "ok")

            status, content = self._get("/api/board")
            data = json.loads(content.decode("utf-8"))
            self.assertTrue(data["tasks"][task_idx]["completed"])
        finally:
            if original_content is not None:
                board_file.write_text(original_content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()


class WriteCredentialTests(unittest.TestCase):
    """AI-7: the deck's mutating routes must refuse an unauthenticated caller.

    web_server.py bound 0.0.0.0:8088 with no authentication and wildcard CORS,
    so any page in any browser on the network could drive it cross-origin -
    including POST /api/board/raw, which overwrites docs/BOARD.md wholesale.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = XPlaneUDPClient(mock=True)
        cls.controller = FlightController(cls.client)
        cls.agent = LightweightAgent(cls.controller)
        AIPilotRequestHandler.client = cls.client
        AIPilotRequestHandler.controller = cls.controller
        AIPilotRequestHandler.agent = cls.agent
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), AIPilotRequestHandler)
        cls.token = "test-engineering-token"
        cls.server.mutation_token = cls.token
        cls.server.allowed_origins = ()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.client.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def _post(self, path, payload, token=None):
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {token}"} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status
        except HTTPError as e:
            return e.code

    def test_board_raw_overwrite_needs_a_credential(self):
        """The endpoint that can rewrite the agent dispatch queue."""
        from services.ai_pilot.board_manager import get_board_path
        before = get_board_path().read_text(encoding="utf-8")
        self.assertEqual(self._post("/api/board/raw", {"markdown": "# wiped"}), 401)
        self.assertEqual(get_board_path().read_text(encoding="utf-8"), before,
                         "an unauthenticated caller rewrote docs/BOARD.md")

    def test_mutating_routes_reject_missing_and_wrong_credentials(self):
        for path, payload in (("/api/board/task", {"agent": "X", "task": "y"}),
                              ("/api/board/toggle", {"index": 0, "completed": True}),
                              ("/api/chat", {"message": "hello"})):
            for label, token in (("no credential", None), ("wrong credential", "nope")):
                with self.subTest(path=path, credential=label):
                    self.assertEqual(self._post(path, payload, token), 401)

    def test_api_responses_are_not_cacheable(self):
        """The stale-board symptom: no cache headers at all on /api/*."""
        with urllib.request.urlopen(f"{self.base_url}/api/board", timeout=3.0) as r:
            self.assertEqual(r.headers.get("Cache-Control"), "no-store")

    def test_no_wildcard_cors(self):
        with urllib.request.urlopen(f"{self.base_url}/api/board", timeout=3.0) as r:
            self.assertNotEqual(r.headers.get("Access-Control-Allow-Origin"), "*")
