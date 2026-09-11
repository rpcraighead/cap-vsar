# AI Pilot Service: Cessna 182T NAV III for X-Plane 12

An autonomous flight and AI-orchestrated piloting system for the Civil Air Patrol Cessna 182T Skylane NAV III (G1000 / CAP 487) in X-Plane 12.

## Features

- **Inner-Loop Guidance Laws & State Machine (`flight_controller.py`)**:
  - High-frequency (20-50 Hz) telemetry reading via native X-Plane UDP (port 49000).
  - Handles ground roll, rotation at $V_r = 55\text{--}60\text{ KIAS}$, climb out at $V_y = 80\text{ KIAS}$, enroute hold at 4,500 ft MSL, descent profiling, final approach glidepath intercept, flare assist, rollout, and braking.
  - Controls X-Plane GFC 700 / G1000 autopilot datarefs with direct surface command fallback.
- **Authentic POH Normal Procedures Checklists (`c182t_checklists.py`)**:
  - 1:1 fidelity with the official Cessna 182T Skylane Information Manual / POH Section 4.
  - Real datarefs for avionics, electrical, magnetos, mixture, cowl flaps, propeller control, lighting, and flaps.
  - Challenge-response verification for interactive AI execution.
- **Hermes Agent & BigBrain LLM Bridge (`agent_bridge.py`)**:
  - Standard JSON schema tool calling definitions (`get_flight_telemetry`, `execute_checklist`, `command_flight_phase`, `set_autopilot`, `spawn_on_runway`).
  - Supports NousResearch Hermes Agent running in the lab or direct Ollama queries (`http://192.0.2.55:11434/api/chat`) using models like `gemma4:12b` or `qwen2.5-coder:14b`.
- **Validation Flight Scenario (`mission_ksee_krnm.py`)**:
  - Gillespie Field (KSEE Runway 27R) to Ramona Airport (KRNM Runway 27).
  - Starts cold & dark, runs all 9 checklists, climbs to 4,500 ft MSL over Santee/Iron Mountain ridgeline, descends to Ramona, lands on Runway 27, and shuts down.

## Quick Start

### 1. Launch the Glassmorphic Web Deck (Recommended)
Starts the lightweight AI copilot agent and web dashboard on port **8088**:
```bash
# Offline simulated mode:
python3 -m services.ai_pilot.web_server --port 8088

# Or live X-Plane 12 connection (UDP 49000):
python3 -m services.ai_pilot.web_server --port 8088 --live
```
Open **http://localhost:8088** in your browser.

The web dashboard features:
- **Primary Flight Display (PFD)**: Real-time airspeed tape, artificial horizon (pitch & roll canvas), altimeter tape, VVI, and heading bug.
- **Engine & System Gauges**: Lycoming IO-540 tach RPM, manifold pressure, flaps indicator, parking brake status.
- **Mission Progress & Route Track**: Interactive route bar from Gillespie Field (KSEE 27R) to Ramona Airport (KRNM 27) with live distance and terrain profiling.
- **Authentic POH Checklists**: All 9 Cessna 182T Section 4 checklists with interactive execution and verification badges.
- **AI Copilot Chat**: Natural language terminal to instruct the copilot (e.g. *"takeoff"*, *"climb to 4500"*, *"turn heading 015"*, *"run before landing checklist"*, *"land at Ramona"*).
- **Quick Command Buttons**: Instant triggers for spawn, start engine, takeoff, climb, descent, approach, flare, rollout, and shutdown.

### 2. Run the Headless Mission CLI
Runs in simulated mock mode without requiring a browser or X-Plane:
```bash
python3 -m services.ai_pilot.mission_ksee_krnm --fast
```

### 3. Run against Live X-Plane 12
1. Launch X-Plane 12 with the `Cessna 182T NAV III (CAP 487)`.
2. Start the mission:
```bash
python3 -m services.ai_pilot.mission_ksee_krnm --live
```

### 4. Run Unit & Integration Tests
```bash
python3 -m unittest discover -s services/ai_pilot/tests -v
```
