"""
Legacy AI Agent Bridge (Hermes & BigBrain LLM Interface)
--------------------------------------------------------
The bridge is observation-only. Aircraft mutation tools were retired in favor
of the validated maneuver server and its explicit control lease.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .flight_controller import (
    FlightController,
    haversine_distance_nm,
)

logger = logging.getLogger("ai_pilot.agent_bridge")


# ------------------------------------------------------------------------------
# Tool Schemas for Hermes / OpenAI Compatible Function Calling
# ------------------------------------------------------------------------------

HERMES_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_flight_telemetry",
            "description": "Get current aircraft telemetry, position, engine state, flight phase, and distance to destination.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

RETIRED_MUTATION_TOOLS = frozenset({
    "execute_checklist",
    "command_flight_phase",
    "set_autopilot",
    "spawn_on_runway",
})


class AgentBridge:
    """Observation-only tool bridge retained for prototype compatibility."""

    def __init__(
        self,
        controller: FlightController,
        ollama_url: str = "http://192.0.2.55:11434",
        model: str = "gemma4:12b",
    ):
        self.controller = controller
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

    def dispatch_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a tool call to the FlightController or Checklist engine."""
        fc = self.controller

        if name == "get_flight_telemetry":
            t = fc.update_telemetry()
            dist_to_krnm = haversine_distance_nm(t.lat, t.lon, fc.KRNM_27_THRESHOLD[0], fc.KRNM_27_THRESHOLD[1])
            return {
                "phase": fc.phase.value,
                "lat": round(t.lat, 6),
                "lon": round(t.lon, 6),
                "alt_msl_ft": round(t.alt_msl_ft, 1),
                "alt_agl_ft": round(t.alt_agl_ft, 1),
                "kias": round(t.kias, 1),
                "groundspeed_kts": round(t.groundspeed_kts, 1),
                "heading_mag": round(t.heading_mag, 1),
                "pitch_deg": round(t.pitch_deg, 1),
                "roll_deg": round(t.roll_deg, 1),
                "vvi_fpm": round(t.vvi_fpm, 1),
                "engine_rpm": round(t.rpm, 1),
                "manifold_pressure_inhg": round(t.mp_inhg, 1),
                "flaps_ratio": round(t.flaps_ratio, 2),
                "distance_to_krnm_nm": round(dist_to_krnm, 2),
            }

        elif name in RETIRED_MUTATION_TOOLS:
            return {
                "success": False,
                "error": "Legacy aircraft mutation tool retired",
                "control_endpoint": "http://127.0.0.1:8089",
                "ground_phases_available": False,
            }

        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    def query_ollama(self, messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Send chat query with tool definitions to Ollama on BigBrain."""
        endpoint = f"{self.ollama_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": HERMES_TOOLS,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("message")
        except urllib.error.URLError as e:
            logger.error("Failed to query Ollama at %s: %s", endpoint, e)
            return None

    def export_hermes_skill(self, filepath: str) -> None:
        """Export Hermes Agent skill documentation markdown."""
        skill_doc = """---
name: xplane-c182t-pilot
description: Observation-only telemetry advisor for the CAP 487 X-Plane 12 training simulation.
---

# CAP 487 Telemetry Advisory Skill

This legacy skill may describe current CAP 487 telemetry. It cannot move controls,
execute checklists, change flight phase, relocate the aircraft, or create an ATC
clearance. Validated airborne commands use the local maneuver deck separately.

## Available Tools
1. `get_flight_telemetry()`: Reads all cockpit gauges, GPS position, airspeed, altitude, and distance to destination.
"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(skill_doc)
        logger.info("Exported Hermes skill definition to %s", filepath)
