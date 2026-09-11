"""
AI Agent Bridge (Hermes & BigBrain LLM Interface)
-------------------------------------------------
Bridges the autonomous FlightController and POH Checklists with an AI model
such as NousResearch Hermes Agent or BigBrain local Ollama (192.0.2.55:11434).

Supports standard tool-use schemas (JSON Schema), direct tool execution,
and an autonomous Captain agent loop.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .c182t_checklists import (
    ChecklistPhase,
    get_checklist_by_name,
)
from .flight_controller import (
    FlightController,
    FlightPhase,
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
    {
        "type": "function",
        "function": {
            "name": "execute_checklist",
            "description": "Execute an authentic Cessna 182T NAV III POH checklist by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "checklist_name": {
                        "type": "string",
                        "enum": [
                            "BEFORE_ENGINE_START",
                            "ENGINE_START",
                            "BEFORE_TAKEOFF",
                            "TAKEOFF_AND_CLIMB",
                            "CRUISE",
                            "DESCENT",
                            "BEFORE_LANDING",
                            "AFTER_LANDING",
                            "SHUTDOWN_AND_SECURING",
                        ],
                        "description": "Name of the POH checklist to execute.",
                    }
                },
                "required": ["checklist_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "command_flight_phase",
            "description": "Command the flight controller state machine to transition to a target phase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phase": {
                        "type": "string",
                        "enum": [
                            "TAKEOFF_ROLL",
                            "ROTATE_AND_CLIMB",
                            "ENROUTE_CLIMB",
                            "CRUISE",
                            "DESCENT",
                            "APPROACH_INTERCEPT",
                            "FINAL_APPROACH",
                            "FLARE_AND_TOUCHDOWN",
                            "ROLLOUT_AND_STOP",
                            "ENGINE_SHUTDOWN",
                        ],
                        "description": "Target flight phase to engage.",
                    }
                },
                "required": ["phase"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_autopilot",
            "description": "Set autopilot targets for heading, altitude, and vertical speed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "heading_mag": {"type": "number", "description": "Target magnetic heading in degrees (0-360)."},
                    "altitude_ft": {"type": "number", "description": "Target altitude in feet MSL."},
                    "vs_fpm": {"type": "number", "description": "Vertical speed in feet per minute (optional)."},
                },
                "required": ["heading_mag", "altitude_ft"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_on_runway",
            "description": "Relocate aircraft to Gillespie Field (KSEE) Runway 27R threshold and set cold-and-dark baseline.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


class AgentBridge:
    """Bridge providing tool dispatch and LLM interaction for the AI Pilot."""

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

        elif name == "execute_checklist":
            checklist_name = args.get("checklist_name", "")
            cl = get_checklist_by_name(checklist_name)
            if not cl:
                return {"success": False, "error": f"Checklist '{checklist_name}' not found."}
            results = cl.run(fc.client, delay_between_items=0.05)
            all_passed = all(r["passed"] for r in results)
            return {
                "success": True,
                "checklist": cl.title,
                "all_passed": all_passed,
                "items_completed": len(results),
                "results": results,
            }

        elif name == "command_flight_phase":
            target_phase_str = args.get("phase", "")
            try:
                target_phase = FlightPhase(target_phase_str)
                fc.set_phase(target_phase)
                return {"success": True, "new_phase": fc.phase.value}
            except ValueError:
                return {"success": False, "error": f"Invalid flight phase: {target_phase_str}"}

        elif name == "set_autopilot":
            hdg = float(args["heading_mag"])
            alt = float(args["altitude_ft"])
            vs = float(args["vs_fpm"]) if "vs_fpm" in args else None
            fc._engage_autopilot(hdg_mag=hdg, alt_ft=alt, vs_fpm=vs)
            return {"success": True, "heading_mag": hdg, "altitude_ft": alt, "vs_fpm": vs}

        elif name == "spawn_on_runway":
            fc.spawn_on_ksee_27r()
            return {"success": True, "location": "KSEE Runway 27R", "phase": fc.phase.value}

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
description: Autonomous flight control and POH checklist copilot for the Civil Air Patrol Cessna 182T NAV III in X-Plane 12.
---

# X-Plane Cessna 182T NAV III Flight & Checklist Skill

This skill allows Hermes Agent to act as Captain or Copilot of the Civil Air Patrol
Cessna 182T NAV III (CAP 487) flying between Gillespie Field (KSEE) and Ramona Airport (KRNM).

## Available Tools
1. `get_flight_telemetry()`: Reads all cockpit gauges, GPS position, airspeed, altitude, and distance to destination.
2. `execute_checklist(checklist_name)`: Executes authentic POH Section 4 normal procedures:
   - `BEFORE_ENGINE_START`
   - `ENGINE_START`
   - `BEFORE_TAKEOFF`
   - `TAKEOFF_AND_CLIMB`
   - `CRUISE`
   - `DESCENT`
   - `BEFORE_LANDING`
   - `AFTER_LANDING`
   - `SHUTDOWN_AND_SECURING`
3. `command_flight_phase(phase)`: Directs the autopilot/guidance system through mission phases.
4. `set_autopilot(heading_mag, altitude_ft, vs_fpm)`: Engages GFC 700 / G1000 modes.
5. `spawn_on_runway()`: Relocates aircraft to KSEE 27R threshold in cold-and-dark state.

## Mission Profile (KSEE 27R -> KRNM 27)
- Runway 27R departure heading: 274° M.
- Initial climb to 1,500 ft MSL before right turn to 015° M.
- Enroute cruise altitude: 4,500 ft MSL (clearing Iron Mountain ridge).
- Descent to 2,400 ft MSL commencing 6 NM out from Ramona.
- Intercept Ramona Runway 27 extended final (heading 273° M).
- Flare, touch down, roll out, and full stop on Runway 27.
- Complete shutdown and securing checklist.
"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(skill_doc)
        logger.info("Exported Hermes skill definition to %s", filepath)
