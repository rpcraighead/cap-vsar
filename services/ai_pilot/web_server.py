"""
Legacy observation-only Web Deck for AI Pilot
---------------------------------------------
The original mutation endpoints are retired.  This compatibility server may
display telemetry, checklist references, status, and advisory chat, but the
validated airborne maneuver deck is the only supported controller.
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import socketserver
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .c182t_checklists import ALL_CHECKLISTS, ChecklistPhase
from .flight_controller import FlightController, haversine_distance_nm
from .lightweight_agent import LightweightAgent
from .xplane_udp import XPlaneUDPClient

logger = logging.getLogger("ai_pilot.web")

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


class AIPilotRequestHandler(BaseHTTPRequestHandler):
    """Read-only compatibility handler for the legacy AI Pilot deck."""

    server_version = "AIPilot/1.0"

    # Shared references attached at server startup
    client: XPlaneUDPClient
    controller: FlightController
    agent: LightweightAgent

    def log_message(self, format: str, *args: Any) -> None:
        # Quieten normal access logs
        if args and str(args[1]) in ("200", "304") and not logger.isEnabledFor(logging.DEBUG):
            return
        logger.info("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), format % args)

    def _send_json(self, data: Any, status: int = 200) -> None:
        """Send JSON response with CORS headers."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath: Path) -> None:
        """Serve a static file."""
        if not filepath.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        content_type, _ = mimetypes.guess_type(str(filepath))
        content_type = content_type or "application/octet-stream"

        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except OSError as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Error reading file: {e}")

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests."""
        url = urlparse(self.path)
        path = url.path

        # REST APIs
        if path == "/api/telemetry":
            self._handle_get_telemetry()
        elif path == "/api/checklists":
            self._handle_get_checklists()
        elif path == "/api/status":
            self._handle_get_status()
        elif path == "/api/chat":
            self._send_json({"messages": self.agent.get_chat_history()})
        else:
            # Static file serving
            rel_path = path.lstrip("/")
            if not rel_path or rel_path == "index.html":
                target_file = STATIC_DIR / "index.html"
            else:
                target_file = STATIC_DIR / rel_path

            # Prevent directory traversal
            try:
                target_file.resolve().relative_to(STATIC_DIR.resolve())
            except ValueError:
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return

            self._send_file(target_file)

    def do_POST(self) -> None:
        """Handle POST requests."""
        url = urlparse(self.path)
        path = url.path

        # Read JSON body
        length = int(self.headers.get("Content-Length", 0))
        body: Dict[str, Any] = {}
        if length > 0:
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as e:
                self._send_json({"error": f"Invalid JSON payload: {e}"}, status=400)
                return

        if path == "/api/chat":
            user_text = body.get("message", "")
            if not user_text:
                self._send_json({"error": "Empty message"}, status=400)
                return
            reply = self.agent.handle_user_command(user_text)
            self._send_json({"reply": reply, "messages": self.agent.get_chat_history()})

        elif path in {
            "/api/checklists/run",
            "/api/phase",
            "/api/autopilot",
            "/api/spawn",
            "/api/mission/start",
            "/api/mission/stop",
        }:
            self._send_json({
                "error": "Legacy aircraft mutation endpoint retired",
                "control_endpoint": "http://127.0.0.1:8089",
                "ground_phases_available": False,
            }, status=HTTPStatus.GONE)

        else:
            self.send_error(HTTPStatus.NOT_FOUND, "API endpoint not found")

    # --------------------------------------------------------------------------
    # API Handlers
    # --------------------------------------------------------------------------

    def _handle_get_telemetry(self) -> None:
        fc = self.controller
        t = fc.update_telemetry()
        dist_to_krnm = haversine_distance_nm(t.lat, t.lon, fc.KRNM_27_THRESHOLD[0], fc.KRNM_27_THRESHOLD[1])

        data = {
            "phase": fc.phase.value,
            "autonomous_active": self.agent.autonomous_active,
            "control_enabled": False,
            "control_endpoint": "http://127.0.0.1:8089",
            "position": {
                "lat": round(t.lat, 6),
                "lon": round(t.lon, 6),
                "alt_msl_ft": round(t.alt_msl_ft, 1),
                "alt_agl_ft": round(t.alt_agl_ft, 1),
                "heading_mag": round(t.heading_mag, 1),
                "heading_true": round(t.heading_true, 1),
            },
            "flight_dynamics": {
                "kias": round(t.kias, 1),
                "groundspeed_kts": round(t.groundspeed_kts, 1),
                "pitch_deg": round(t.pitch_deg, 1),
                "roll_deg": round(t.roll_deg, 1),
                "vvi_fpm": round(t.vvi_fpm, 1),
            },
            "engine": {
                "rpm": round(t.rpm, 1),
                "mp_inhg": round(t.mp_inhg, 1),
            },
            "controls": {
                "flaps_ratio": round(t.flaps_ratio, 2),
                "brakes_ratio": round(t.brakes_ratio, 2),
                "throttle_ratio": round(self.client.get_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]"), 2),
                "prop_ratio": round(self.client.get_dref("sim/cockpit2/engine/actuators/prop_ratio[0]"), 2),
                "mixture_ratio": round(self.client.get_dref("sim/cockpit2/engine/actuators/mixture_ratio[0]"), 2),
                "cowl_flap_ratio": round(self.client.get_dref("sim/cockpit2/engine/actuators/cowl_flap_ratio[0]"), 2),
            },
            "autopilot": {
                "heading_bug": round(fc.target_heading_mag, 1),
                "altitude_bug": round(fc.target_altitude_ft, 1),
                "servos_on": bool(self.client.get_dref("sim/cockpit2/autopilot/servos_on") > 0.5),
            },
            "navigation": {
                "distance_to_krnm_nm": round(dist_to_krnm, 2),
                "ksee_elev_ft": 388,
                "krnm_elev_ft": 1395,
            },
            "recent_events": fc.mission_log[-15:],
        }
        self._send_json(data)

    def _handle_get_checklists(self) -> None:
        checklists = []
        for phase in ChecklistPhase:
            cl = ALL_CHECKLISTS[phase]()
            items = []
            for it in cl.items:
                items.append({
                    "item": it.item,
                    "challenge": it.challenge,
                    "response": it.response,
                    "note": it.note,
                    "is_verified": it.verify(self.client),
                })
            checklists.append({
                "phase": phase.value,
                "title": cl.title,
                "description": cl.description,
                "items": items,
            })
        self._send_json({"checklists": checklists})

    def _handle_get_status(self) -> None:
        self._send_json({
            "service": "ai_pilot",
            "version": "1.0.0",
            "mock_mode": self.client.mock,
            "phase": self.controller.phase.value,
            "autonomous_active": self.agent.autonomous_active,
            "control_enabled": False,
            "control_endpoint": "http://127.0.0.1:8089",
            "chat_messages_count": len(self.agent.chat_history),
        })


def run_web_server(
    host: str = "0.0.0.0",
    port: int = 8088,
    live: bool = False,
    xp_host: str = "127.0.0.1",
    xp_port: int = 49000,
) -> None:
    """Start AI Pilot web server."""
    client = XPlaneUDPClient(host=xp_host, port=xp_port, mock=not live)
    controller = FlightController(client)
    agent = LightweightAgent(controller)

    AIPilotRequestHandler.client = client
    AIPilotRequestHandler.controller = controller
    AIPilotRequestHandler.agent = agent

    server = ThreadingHTTPServer((host, port), AIPilotRequestHandler)
    logger.info("================================================================================")
    logger.info("  LEGACY AI PILOT OBSERVATION DECK: http://%s:%d", "127.0.0.1" if host == "0.0.0.0" else host, port)
    logger.info("  SIMULATOR LINK: %s", "LIVE READ-ONLY X-Plane 12" if live else "MOCK (Offline Mode)")
    logger.info("  AIRCRAFT CONTROL: RETIRED; use http://127.0.0.1:8089")
    logger.info("================================================================================")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down AI Pilot web server...")
    finally:
        client.stop()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Legacy read-only AI Pilot Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8088, help="HTTP port (default: 8088)")
    parser.add_argument("--live", action="store_true", help="Read telemetry from live X-Plane 12")
    parser.add_argument("--xp-host", default="127.0.0.1", help="X-Plane UDP host")
    parser.add_argument("--xp-port", type=int, default=49000, help="X-Plane UDP port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    run_web_server(host=args.host, port=args.port, live=args.live, xp_host=args.xp_host, xp_port=args.xp_port)


if __name__ == "__main__":
    main()
