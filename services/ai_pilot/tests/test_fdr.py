"""
Unit tests for Flight Data Recorder (FDR) and Diagnostic Engine.
"""

import json
import shutil
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from typing import Dict, Any

from services.ai_pilot.diagnostics import (
    DiagnosticFinding,
    DiagnosticReport,
    FlightDiagnosticEngine,
    calc_angle_difference_deg,
    calc_great_circle_bearing_deg,
)
from services.ai_pilot.fdr import FDRFrame, FlightDataRecorder
from services.ai_pilot.flight_controller import FlightController
from services.ai_pilot.lightweight_agent import LightweightAgent
from services.ai_pilot.web_server import AIPilotRequestHandler, ThreadingHTTPServer
from services.ai_pilot.xplane_udp import XPlaneUDPClient


class TestFlightDataRecorder(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.client = XPlaneUDPClient(mock=True)
        self.fdr = FlightDataRecorder(
            client=self.client,
            output_dir=self.temp_dir,
            ring_buffer_size=5,
            rate_hz=20.0,  # fast sampling for unit test
        )

    def tearDown(self):
        self.fdr.stop_recording()
        self.client.stop()
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_sample_current_frame(self):
        self.client.set_mock_dref("sim/flightmodel/position/latitude", 32.82)
        self.client.set_mock_dref("sim/flightmodel/position/longitude", -116.96)
        self.client.set_mock_dref("cap/df/valid", 1.0)
        self.client.set_mock_dref("cap/df/bearing_true", 045.0)

        frame = self.fdr.sample_current_frame(phase="CRUISE")
        self.assertAlmostEqual(frame.lat, 32.82, places=2)
        self.assertAlmostEqual(frame.lon, -116.96, places=2)
        self.assertEqual(frame.df_valid, 1)
        self.assertAlmostEqual(frame.df_bearing_true, 45.0, places=1)
        self.assertEqual(frame.flight_phase, "CRUISE")

    def test_start_stop_recording(self):
        log_file = self.fdr.start_recording(session_name="test_flight")
        self.assertTrue(self.fdr.is_recording)
        self.assertTrue(log_file.name.startswith("fdr_test_flight_"))

        # Let the background sampler collect several frames
        time.sleep(0.25)

        saved_file = self.fdr.stop_recording()
        self.assertFalse(self.fdr.is_recording)
        self.assertEqual(saved_file, log_file)
        self.assertTrue(saved_file.is_file())

        lines = saved_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertGreater(len(lines), 0)
        first_frame = json.loads(lines[0])
        self.assertIn("lat", first_frame)
        self.assertIn("df_bearing_true", first_frame)

    def test_ring_buffer_eviction(self):
        # Ring buffer size is 5
        for i in range(10):
            frame = self.fdr.sample_current_frame()
            frame.frame_index = i
            self.fdr.record_frame(frame)

        ring = self.fdr.get_ring_buffer()
        self.assertEqual(len(ring), 5)
        # Should contain indices 5 through 9
        self.assertEqual(ring[0]["frame_index"], 5)
        self.assertEqual(ring[-1]["frame_index"], 9)

    def test_export_csv(self):
        log_file = self.fdr.start_recording()
        time.sleep(0.15)
        self.fdr.stop_recording()

        csv_file = self.temp_dir / "flight.csv"
        rows = self.fdr.export_csv(log_file, csv_file)
        self.assertGreater(rows, 0)
        self.assertTrue(csv_file.is_file())
        with open(csv_file, "r", encoding="utf-8") as f:
            header = f.readline().strip().split(",")
            self.assertIn("lat", header)
            self.assertIn("df_signal", header)


class TestFlightDiagnosticEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FlightDiagnosticEngine()

    def test_bearing_math_helpers(self):
        # Due north
        b1 = calc_great_circle_bearing_deg(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(b1, 0.0, places=2)

        # Due east
        b2 = calc_great_circle_bearing_deg(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(b2, 90.0, places=2)

        # Angle differences
        self.assertAlmostEqual(calc_angle_difference_deg(10.0, 350.0), 20.0, places=2)
        self.assertAlmostEqual(calc_angle_difference_deg(180.0, 180.0), 0.0, places=2)

    def test_bearing_geometry_rule_pass(self):
        # Aircraft flying north towards a beacon due north
        frames = [
            {
                "lat": 32.80 + i * 0.01,
                "lon": -116.90,
                "beacon_lat": 32.90,
                "beacon_lon": -116.90,
                "df_valid": 1,
                "df_bearing_true": 0.0,  # Exact north
                "sim_time_s": float(i),
                "scenario_active": 1,
                "df_in_cone": 0,
            }
            for i in range(5)
        ]
        report = self.engine.evaluate_frames(frames, session_id="TEST_GEOM_PASS")
        geom_finding = next(f for f in report.findings if f.rule_id == "DF_GEOM_01")
        self.assertEqual(geom_finding.status, "PASS")
        self.assertLess(report.metrics["bearing_rms_error_deg"], 1.0)

    def test_bearing_geometry_rule_fail_on_reversal(self):
        # Aircraft with reversed/misaligned 180 deg error
        frames = [
            {
                "lat": 32.80,
                "lon": -116.90,
                "beacon_lat": 32.90,
                "beacon_lon": -116.90,
                "df_valid": 1,
                "df_bearing_true": 180.0,  # 180 degree reversed error
                "sim_time_s": float(i),
                "scenario_active": 1,
                "df_in_cone": 0,
            }
            for i in range(5)
        ]
        report = self.engine.evaluate_frames(frames, session_id="TEST_GEOM_FAIL")
        geom_finding = next(f for f in report.findings if f.rule_id == "DF_GEOM_01")
        self.assertEqual(geom_finding.status, "FAIL")

    def test_becker_406_leak_detection(self):
        # Becker SAR-DF-517 in Emergency mode hearing an off-channel 406.037 beacon is an anomaly
        frames = [
            {
                "df_head_type": 0,  # Becker
                "df_mode": 0,       # Emergency (406.025 only)
                "df_active_freq_hz": 406025000,
                "beacon_freq_hz": 406037000,  # Channel F
                "df_valid": 1,
                "df_signal": 0.5,
                "df_band_mhz": 406.0,
                "sim_time_s": float(i),
            }
            for i in range(3)
        ]
        report = self.engine.evaluate_frames(frames, session_id="TEST_BECKER_LEAK")
        leak_finding = next(f for f in report.findings if f.rule_id == "DF_COV_406_LEAK")
        self.assertEqual(leak_finding.status, "FAIL")
        self.assertEqual(report.summary_status, "FAIL")

    def test_cone_of_confusion_suppression(self):
        # Inside cone of confusion, bearing must be invalidated
        frames = [
            {
                "df_in_cone": 1,
                "df_valid": 0,  # Properly suppressed
                "sim_time_s": float(i),
            }
            for i in range(10)
        ]
        report = self.engine.evaluate_frames(frames, session_id="TEST_CONE_PASS")
        cone_finding = next(f for f in report.findings if f.rule_id == "DF_CONE_01")
        self.assertEqual(cone_finding.status, "PASS")

    def test_cap_radio_ptt_interlock(self):
        # Keyed PTT without COM3 MIC selected MUST NOT transmit
        frames_pass = [
            {
                "cap_fm_ptt": True,
                "cap_fm_mic_selected": False,
                "cap_fm_transmitting": False,  # Interlock held!
                "sim_time_s": 1.0,
            }
        ]
        rep_pass = self.engine.evaluate_frames(frames_pass)
        rad_finding = next(f for f in rep_pass.findings if f.rule_id == "RAD_INTLK_01")
        self.assertEqual(rad_finding.status, "PASS")

        frames_fail = [
            {
                "cap_fm_ptt": True,
                "cap_fm_mic_selected": False,
                "cap_fm_transmitting": True,  # Interlock broken!
                "sim_time_s": 1.0,
            }
        ]
        rep_fail = self.engine.evaluate_frames(frames_fail)
        rad_finding_fail = next(f for f in rep_fail.findings if f.rule_id == "RAD_INTLK_01")
        self.assertEqual(rad_finding_fail.status, "FAIL")

    def test_tot_warning_on_continuous_transmission(self):
        # 65 seconds continuous transmission triggers TOT warning
        frames = [
            {
                "cap_fm_transmitting": True,
                "sim_time_s": float(i),
            }
            for i in range(65)
        ]
        report = self.engine.evaluate_frames(frames)
        tot_finding = next(f for f in report.findings if f.rule_id == "RAD_TOT_01")
        self.assertEqual(tot_finding.status, "WARNING")


class TestFDRWebServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp())
        cls.client = XPlaneUDPClient(mock=True)
        cls.controller = FlightController(cls.client)
        cls.agent = LightweightAgent(cls.controller)
        cls.fdr = FlightDataRecorder(cls.client, output_dir=cls.temp_dir, rate_hz=20.0)
        cls.diag_engine = FlightDiagnosticEngine()

        AIPilotRequestHandler.client = cls.client
        AIPilotRequestHandler.controller = cls.controller
        AIPilotRequestHandler.agent = cls.agent
        AIPilotRequestHandler.fdr = cls.fdr
        AIPilotRequestHandler.diag_engine = cls.diag_engine

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), AIPilotRequestHandler)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.fdr.stop_recording()
        cls.client.stop()
        cls.server.shutdown()
        cls.server.server_close()
        if cls.temp_dir.exists():
            shutil.rmtree(cls.temp_dir)

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

    def test_fdr_rest_lifecycle(self):
        # 1. Check initial status
        status, content = self._get("/api/fdr/status")
        self.assertEqual(status, 200)
        data = json.loads(content.decode("utf-8"))
        self.assertFalse(data["is_recording"])

        # 2. Start recording
        status, res = self._post_json("/api/fdr/start", {"session_name": "sorties_alpha"})
        self.assertEqual(status, 200)
        self.assertEqual(res["status"], "started")

        # Let it record
        time.sleep(0.2)

        # Check status while active
        status, content = self._get("/api/fdr/status")
        data = json.loads(content.decode("utf-8"))
        self.assertTrue(data["is_recording"])
        self.assertGreater(data["frame_count"], 0)

        # Check ring buffer endpoint
        status, content = self._get("/api/fdr/ring")
        self.assertEqual(status, 200)
        data = json.loads(content.decode("utf-8"))
        self.assertGreater(len(data["frames"]), 0)

        # Check analyze endpoint on ring buffer
        status, res = self._post_json("/api/fdr/analyze", {})
        self.assertEqual(status, 200)
        self.assertIn("report", res)
        self.assertIn("scorecard", res["report"])

        # 3. Stop recording and receive automated post-flight report
        status, stop_res = self._post_json("/api/fdr/stop", {})
        self.assertEqual(status, 200)
        self.assertEqual(stop_res["status"], "stopped")
        self.assertIn("report", stop_res)
        self.assertIn("findings", stop_res["report"])

        # 4. Check reports list endpoint
        status, content = self._get("/api/fdr/reports")
        self.assertEqual(status, 200)
        data = json.loads(content.decode("utf-8"))
        self.assertGreater(len(data["reports"]), 0)


if __name__ == "__main__":
    unittest.main()

