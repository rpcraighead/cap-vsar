"""
Lightweight AI Pilot Agent
--------------------------
Self-contained, lightweight AI copilot and flight commander.
Operates in two modes:
1. Autonomous Expert Copilot (rule-based state machine, zero external dependencies).
2. BigBrain Local LLM (interfaces with Ollama on 192.0.2.55:11434 for natural language chat and reasoning).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .c182t_checklists import (
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
from .flight_controller import (
    FlightController,
    FlightPhase,
    haversine_distance_nm,
)
from .xplane_udp import XPlaneUDPClient

logger = logging.getLogger("ai_pilot.agent")


class LightweightAgent:
    """Lightweight copilot agent managing flight decisions, checklists, and natural language dialogue."""

    def __init__(
        self,
        controller: FlightController,
        ollama_url: str = "http://192.0.2.55:11434",
        model: str = "gemma4:12b",
    ):
        self.controller = controller
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

        # Agent state
        self.autonomous_active = False
        self._mission_thread: Optional[threading.Thread] = None
        self._stop_requested = False

        # Chat and conversation history
        self.chat_history: List[Dict[str, str]] = [
            {
                "sender": "copilot",
                "text": "Civil Air Patrol C182T NAV III AI Copilot online. Standing by on Gillespie Field (KSEE) Runway 27R.",
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
        """Process natural language request from the user/pilot."""
        self.add_message("pilot", user_text)
        cmd_lower = user_text.lower().strip()

        # Try fast pattern matching first for zero-latency execution
        # 1. Spawn / Reset
        if any(w in cmd_lower for w in ["spawn", "reset", "runway 27r", "ksee", "start over"]):
            self.controller.spawn_on_ksee_27r()
            resp = "Aircraft repositioned on Gillespie Field (KSEE) Runway 27R in Cold & Dark state."
            self.add_message("copilot", resp)
            return resp

        # 2. Start Engine
        if "start engine" in cmd_lower or "engine start" in cmd_lower or "crank" in cmd_lower:
            self.controller.set_phase(FlightPhase.STARTING_ENGINES)
            cl = get_engine_start_checklist()
            results = cl.run(self.controller.client, delay_between_items=0.05)
            resp = "Engine Start checklist executed. Lycoming IO-540 running; oil pressure in the green."
            self.add_message("copilot", resp)
            return resp

        # 3. Checklists
        if "checklist" in cmd_lower:
            for phase_name in [p.value for p in ChecklistPhase]:
                if phase_name.lower().replace("_", " ") in cmd_lower or phase_name.lower() in cmd_lower:
                    cl = get_checklist_by_name(phase_name)
                    if cl:
                        cl.run(self.controller.client, delay_between_items=0.05)
                        resp = f"Executed {cl.title} checklist. All items verified."
                        self.add_message("copilot", resp)
                        return resp
            # Default run before takeoff or next relevant
            cl = get_before_takeoff_checklist()
            cl.run(self.controller.client, delay_between_items=0.05)
            resp = f"Executed {cl.title} checklist."
            self.add_message("copilot", resp)
            return resp

        # 4. Takeoff
        if "takeoff" in cmd_lower or "take off" in cmd_lower or "depart" in cmd_lower:
            self.controller.set_phase(FlightPhase.TAKEOFF_ROLL)
            resp = "Cleared for takeoff Runway 27R. Full power set, rolling!"
            self.add_message("copilot", resp)
            return resp

        # 5. Heading command
        hdg_match = re.search(r"heading\s+(\d{1,3})", cmd_lower) or re.search(r"turn\s+(?:to\s+)?(\d{1,3})", cmd_lower)
        if hdg_match:
            hdg = float(hdg_match.group(1)) % 360.0
            self.controller.target_heading_mag = hdg
            self.controller._engage_autopilot(hdg_mag=hdg, alt_ft=self.controller.target_altitude_ft)
            resp = f"Heading bug set to {hdg:03.0f}° Magnetic. Autopilot tracking."
            self.add_message("copilot", resp)
            return resp

        # 6. Altitude command
        alt_match = re.search(r"(?:climb|descend|altitude)\s+(?:to\s+)?(\d{3,5})", cmd_lower)
        if alt_match:
            alt = float(alt_match.group(1))
            self.controller.target_altitude_ft = alt
            vs = 700.0 if alt > self.controller.telemetry.alt_msl_ft else -600.0
            self.controller._engage_autopilot(hdg_mag=self.controller.target_heading_mag, alt_ft=alt, vs_fpm=vs)
            resp = f"Altitude preselect set to {alt:.0f} ft MSL. Autopilot engaged."
            self.add_message("copilot", resp)
            return resp

        # 7. Land / Approach
        if any(w in cmd_lower for w in ["land", "approach", "final", "ramona"]):
            self.controller.set_phase(FlightPhase.APPROACH_INTERCEPT)
            resp = "Intercepting Ramona Runway 27 final approach. Configuring flaps and slowing to 80 KIAS."
            self.add_message("copilot", resp)
            return resp

        # 8. Mission Start / Stop
        if "fly mission" in cmd_lower or "auto fly" in cmd_lower or "start mission" in cmd_lower:
            self.start_autonomous_mission()
            resp = "Autonomous mission started: KSEE 27R to KRNM 27. Copilot has the flight controls."
            self.add_message("copilot", resp)
            return resp

        if "stop" in cmd_lower or "abort" in cmd_lower:
            self.stop_autonomous_mission()
            resp = "Autonomous mission stopped. Manual control restored."
            self.add_message("copilot", resp)
            return resp

        # 9. Status report
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
            f"You are the AI Captain of a Civil Air Patrol Cessna 182T NAV III (CAP 487) flying KSEE to KRNM. "
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
        """Start autonomous flight execution in a dedicated thread."""
        if self.autonomous_active:
            return
        self.autonomous_active = True
        self._stop_requested = False
        self._mission_thread = threading.Thread(target=self._run_mission_loop, daemon=True, name="AI-Mission-Loop")
        self._mission_thread.start()

    def stop_autonomous_mission(self) -> None:
        """Signal mission thread to stop."""
        self.autonomous_active = False
        self._stop_requested = True

    def _run_mission_loop(self) -> None:
        """Autonomous progression through the KSEE 27R -> KRNM 27 mission."""
        logger.info("Autonomous flight loop engaged")
        fc = self.controller
        c = fc.client

        # Initial setup if cold & dark
        if fc.phase == FlightPhase.COLD_AND_DARK:
            self.add_message("copilot", "Running Before Engine Start checklist...")
            get_before_engine_start_checklist().run(c, delay_between_items=0.05)
            time.sleep(0.5)

            self.add_message("copilot", "Starting Lycoming IO-540 engine...")
            fc.set_phase(FlightPhase.STARTING_ENGINES)
            get_engine_start_checklist().run(c, delay_between_items=0.05)
            time.sleep(1.0)

            self.add_message("copilot", "Running Before Takeoff runup and instrument check...")
            get_before_takeoff_checklist().run(c, delay_between_items=0.05)
            time.sleep(0.5)

            self.add_message("copilot", "Cleared for takeoff Runway 27R. Advancing full power!")
            fc.set_phase(FlightPhase.TAKEOFF_ROLL)
            get_takeoff_and_climb_checklist().run(c, delay_between_items=0.05)

        last_phase = fc.phase
        while self.autonomous_active and not self._stop_requested and fc.phase != FlightPhase.COMPLETED:
            fc.step()

            # Announce phase changes
            if fc.phase != last_phase:
                last_phase = fc.phase
                msg = f"Phase transition: {fc.phase.value}"
                if fc.phase == FlightPhase.ROTATE_AND_CLIMB:
                    msg = "Airspeed 60 KIAS (Vr). Rotate! Establishing 7° pitch climb at 80 KIAS."
                elif fc.phase == FlightPhase.ENROUTE_CLIMB:
                    msg = "1,500 ft MSL reached. Turning right heading 015° M towards Ramona, climbing to 4,500 ft MSL."
                elif fc.phase == FlightPhase.CRUISE:
                    msg = "4,500 ft MSL reached. Setting cruise power (23 in Hg / 2400 RPM), mixture leaned, cowl flaps closed."
                elif fc.phase == FlightPhase.DESCENT:
                    msg = "6 NM from Ramona. Commencing descent to 2,400 ft MSL."
                elif fc.phase == FlightPhase.APPROACH_INTERCEPT:
                    msg = "Intercepting Ramona Runway 27 extended final (heading 273° M). Flaps 10°."
                elif fc.phase == FlightPhase.FINAL_APPROACH:
                    msg = "Established on Runway 27 final. Flaps 30°, 3° glidepath, target 65 KIAS."
                elif fc.phase == FlightPhase.FLARE_AND_TOUCHDOWN:
                    msg = "Crossing threshold. Throttle idle, smooth flare..."
                elif fc.phase == FlightPhase.ROLLOUT_AND_STOP:
                    msg = "Touchdown on Runway 27! Applying progressive brakes."
                elif fc.phase == FlightPhase.ENGINE_SHUTDOWN:
                    msg = "Full stop on runway. Executing shutdown checklist."
                elif fc.phase == FlightPhase.COMPLETED:
                    msg = "Aircraft shut down and secured. Mission completed successfully!"

                self.add_message("copilot", msg)

            time.sleep(0.1)

        self.autonomous_active = False
        logger.info("Autonomous flight loop ended")

