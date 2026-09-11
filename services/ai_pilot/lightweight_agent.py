"""Legacy advisory chat for the retired experimental AI Pilot deck.

This module deliberately has no control path.  Airborne MO training commands go
through :mod:`services.ai_pilot.maneuver_server`, where validation, ownership,
takeover, and measured capture are enforced.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from typing import Dict, List, Optional

from .flight_controller import (
    FlightController,
    haversine_distance_nm,
)

logger = logging.getLogger("ai_pilot.agent")


class LightweightAgent:
    """Observation-only compatibility chat for the legacy web deck."""

    def __init__(
        self,
        controller: FlightController,
        ollama_url: str = "http://192.0.2.55:11434",
        model: str = "gemma4:12b",
    ):
        self.controller = controller
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

        # Kept for API compatibility. Legacy autonomous control is retired.
        self.autonomous_active = False

        # Chat and conversation history
        self.chat_history: List[Dict[str, str]] = [
            {
                "sender": "copilot",
                "text": (
                    "CAP 487 advisory display online. Legacy control is retired; "
                    "use the airborne maneuver deck for validated MO commands."
                ),
                "timestamp": time.strftime("%H:%M:%S"),
            }
        ]
        self._lock = threading.Lock()

    def add_message(self, sender: str, text: str) -> None:
        """Add message to chat log."""
        with self._lock:
            self.chat_history.append({
                "sender": sender,
                "text": text,
                "timestamp": time.strftime("%H:%M:%S"),
            })
            if len(self.chat_history) > 100:
                self.chat_history.pop(0)
        logger.info("[%s] %s", sender.upper(), text)

    def get_chat_history(self) -> List[Dict[str, str]]:
        with self._lock:
            return list(self.chat_history)

    # --------------------------------------------------------------------------
    # Natural Language Command Processing
    # --------------------------------------------------------------------------

    def handle_user_command(self, user_text: str) -> str:
        """Answer an advisory query without changing aircraft or controller state."""
        self.add_message("pilot", user_text)
        cmd_lower = user_text.lower().strip()

        # Status is the only deterministic operation retained by this legacy path.
        if "status" in cmd_lower or "where are we" in cmd_lower:
            t = self.controller.update_telemetry()
            dist = haversine_distance_nm(t.lat, t.lon, self.controller.KRNM_27_THRESHOLD[0], self.controller.KRNM_27_THRESHOLD[1])
            resp = (
                f"Status: {self.controller.phase.value}. "
                f"Airspeed: {t.kias:.0f} KIAS, Alt: {t.alt_msl_ft:.0f} ft MSL ({t.alt_agl_ft:.0f} ft AGL), "
                f"Heading: {t.heading_mag:03.0f}° M, Distance to KRNM: {dist:.1f} NM."
            )
            self.add_message("copilot", resp)
            return resp

        control_words = (
            "spawn", "reset", "start engine", "engine start", "crank",
            "checklist", "takeoff", "take off", "depart", "heading", "turn",
            "climb", "descend", "altitude", "land", "approach", "final",
            "fly mission", "auto fly", "start mission", "abort",
        )
        if any(word in cmd_lower for word in control_words):
            resp = (
                "No aircraft action taken. This legacy chat is advisory only. "
                "Use the airborne maneuver deck for validated heading or indicated-altitude commands; "
                "automatic ground, takeoff, approach, and landing phases are unavailable."
            )
            self.add_message("copilot", resp)
            return resp

        # Fallback to local LLM on BigBrain if accessible
        llm_reply = self._query_bigbrain_llm(user_text)
        if llm_reply:
            self.add_message("copilot", llm_reply)
            return llm_reply

        # Default copilot response
        resp = f"Roger. Current phase is {self.controller.phase.value}. Standing by for flight directions."
        self.add_message("copilot", resp)
        return resp

    def _query_bigbrain_llm(self, prompt: str) -> Optional[str]:
        """Query Ollama on BigBrain with current cockpit context."""
        t = self.controller.telemetry
        system_prompt = (
            f"You are an observation-only advisory assistant for a Civil Air Patrol Cessna 182T NAV III "
            f"(CAP 487) training simulation. Never claim to move controls, execute a checklist, issue or "
            f"receive an ATC clearance, or change flight phase. "
            f"Current telemetry: Phase={self.controller.phase.value}, Airspeed={t.kias:.0f} KIAS, "
            f"Alt={t.alt_msl_ft:.0f} ft MSL, Heading={t.heading_mag:.0f} M. Answer concisely in aviation standard phraseology."
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("message", {}).get("content")
        except Exception:
            return None

    # --------------------------------------------------------------------------
    # Autonomous Flight Mission Loop
    # --------------------------------------------------------------------------

    def start_autonomous_mission(self) -> None:
        """Refuse the retired autonomous route."""
        raise RuntimeError(
            "Legacy autonomous mission control is retired; use maneuver_server"
        )

    def stop_autonomous_mission(self) -> None:
        """Preserve a harmless compatibility stop for already-retired state."""
        self.autonomous_active = False
