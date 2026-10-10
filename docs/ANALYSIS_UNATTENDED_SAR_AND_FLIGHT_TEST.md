# CAP-VSAR System Analysis: Unattended SAR Missions & Scripted Flight Test Profiles

**Date:** 2026-09-17  
**Scope:** Evaluation of the `cap-vsar` codebase for:
1. **Use Case 1:** Flying an unattended Civil Air Patrol (CAP) Search and Rescue (SAR) mission.
2. **Use Case 2:** Scripting flight test pilot tasks and executing automated flight test profiles.

---

## Executive Summary

The `cap-vsar` platform contains mature algorithms for search pattern generation, detailed aerodynamic and handling test cards, high-rate flight telemetry capture, and several flight-control backends. However, **neither use case can currently be flown fully autonomously end-to-end**.

* **For Unattended SAR Missions:** Search pattern geometry (expanding square, creeping line, parallel track) and `.FMS` export are fully implemented. An airborne heading-bug follower (`scripts/fly_search_grid.py`) can steer search legs. However, the system lacks:
  1. An integrated flight executive to sequence phases from engine start to shutdown.
  2. Automated power/throttle and configuration management when flying via the G1000/GFC 700.
  3. Stable ArduPlane SITL navigation (blocked by defect AI-24).
  4. Phase-aware safety envelopes (the current airborne gate forbids ground roll, takeoff, and landing).

* **For Scripted Flight Testing:** The direct surface backend (`services/ai_pilot/direct_backend.py`) has been equipped with bounded test inputs (trapezoidal pulses), bank holding, and speed-on-pitch. Card **H0** (control and trim confidence) was successfully flown live on 2026-09-17 (`scripts/fly_card_h0.py`). However:
  1. Automated testing at speeds below 90 KIAS (slow flight, stall speeds, cards H1/H5–H7) is strictly blocked by the global safety gate.
  2. The stall state machine (`services/ai_pilot/flight_test.py`) is implemented offline but has never been flown in the simulator.
  3. Active autopilot loops contaminate open-loop airframe identification.
  4. Scripted execution exists only for Card H0; remaining performance and handling cards require manual piloting with passive capture.

---

## 1. Use Case 1: Flying a CAP SAR Mission Unattended

### 1.1 Requirements for an Unattended SAR Mission
An unattended mission requires the system to execute the entire sortie lifecycle without pilot-in-the-loop intervention:
1. **Ground Phase:** Cold & dark setup, authentic POH checklists, engine start, taxi, and runway alignment.
2. **Departure Phase:** Takeoff roll, rotation ($V_r = 60\text{ KIAS}$), initial climb ($V_y = 80\text{ KIAS}$), and noise/obstacle clearance.
3. **Transit Phase:** Enroute climb to cruise altitude, navigation to search area datum, terrain clearance monitoring.
4. **Search Phase:** Execution of assigned CAP search patterns (parallel track / creeping line, expanding square, sector search) with wind-drift compensation, track spacing accuracy, and sensor/DF monitoring.
5. **Retasking & Contingency:** Handling mid-flight retask orders, loiter on beacon detection, fuel reserve tracking, and weather/envelope aborts.
6. **Recovery Phase:** Transit to destination airport, approach briefing, descent profiling, approach intercept (ILS / RNAV / visual), 3° glidepath tracking, flare, touchdown, rollout braking, taxi to ramp, and engine shutdown.

---

### 1.2 Current Capabilities in the Codebase

#### A. Search Pattern Algorithms & Flight Plan Export
* **Implemented in `services/flightplanner/app.py`:**
  * `generate_expanding_square()`: Computes progressive square searches ($1S, 1S, 2S, 2S, 3S, 3S \dots$) with left or right turns around a datum point. Verified in `test_sar.py`.
  * `generate_creeping_line()`: Computes boustrophedon sweep patterns along a specified track vector with configurable leg length and track spacing.
  * `generate_parallel_track()`: Sweeps rectangular search areas with odd leg counts ensuring symmetric datum passage.
  * `generate_xplane_fms_content()`: Generates valid X-Plane 12 `.fms` (FMS version 1100) flight plans for direct loading into the Cessna 182T Garmin G1000.
* **Airborne Search Runner (`scripts/fly_search_grid.py`):**
  * Calculates great-circle waypoints and initial bearings for a parallel-track grid.
  * Connects over UDP to X-Plane, monitors latitude/longitude, and commands the autopilot heading bug (`sim/cockpit2/autopilot/heading_dial_deg_mag_pilot`) with magnetic variation compensation ($11.5^\circ\text{E}$).
  * Captures waypoints within a 0.35 NM tolerance radius.
  * Reads scenario DF beacon telemetry (`cap/df/bearing_true`, `cap/df/signal`) during execution.

#### B. Flight Procedures and Checklists
* **POH Normal Procedures Checklists (`services/ai_pilot/c182t_checklists.py`):**
  * Complete 1:1 models of Cessna 182T NAV III POH Section 4 normal checklists: *Before Engine Start*, *Engine Start*, *Before Takeoff Runup*, *Takeoff & Climb*, *Cruise*, *Descent*, *Before Landing*, *After Landing*, *Shutdown & Securing*.
  * Commands exact simulator datarefs for avionics, electrical busses, fuel selectors, beacon/strobe lights, cowl flaps, mixture, and propeller governor.

#### C. Control Backends
* **GFC 700 Autopilot Adapter (`XPlaneAutopilotBackend` in `services/ai_pilot/maneuvers.py`):** Interfaces with X-Plane's native Garmin autopilot via heading bug, altitude preselect, and FLC mode commands.
* **ArduPlane SITL Backend (`ArduPlaneBackend` in `services/ai_pilot/arduplane_backend.py`):** Bridges ArduPilot SITL Plane-4.7.1 to X-Plane via MAVLink (`TCP:5760`) and X-Plane DRef socket (`UDP:49001/49000`). Designed to support full runway-to-runway autonomy once tuned.
* **Direct Surface Backend (`XPlaneDirectBackend` in `services/ai_pilot/direct_backend.py`):** Autonomous inner/outer loop flight controller operating primary flight controls (aileron, elevator, rudder, throttle, elevator autotrim).

---

### 1.3 Critical Gaps & Blockers for Unattended SAR Flight

* **Primary Blocker 1: AI-24 ArduPlane GUIDED Mode Tuning.** During the Leg 3 flight trial on 2026-09-17 (`CHANGELOG.md`), ArduPlane commanded CAP 487 for the first time through the gate. While safety interlocks worked (SITL detached cleanly on completion), **the aircraft failed to capture heading or altitude**, flying continuous left circles ($261^\circ \to 178^\circ$) and descending from 4,616 ft to 2,974 ft. MAVLink commands were accepted, but ArduPlane remained in default loiter. Runway takeoff/landing via ArduPlane cannot be implemented until basic GUIDED mode capture is resolved.
* **Primary Blocker 2: Power and Configuration Gap on GFC 700.** The C182T NAV III GFC 700 autopilot controls elevator and aileron servos, but **has no autothrottle**. In `XPlaneAutopilotBackend`, speed-by-pitch (FLC mode) relies on the human pilot to manually add climb power or reduce descent power. Running an unattended GFC 700 mission will stall the aircraft in climbs or overspeed it in descents unless a deterministic virtual-pilot autothrottle service is deployed.
* **Primary Blocker 3: The Rigid ManeuverGate Airborne Envelope.** The active supervisory gate (`ManeuverGate` in `services/ai_pilot/maneuvers.py`) enforces an envelope designed exclusively for airborne MO training (3,000–6,000 ft MSL, 90–140 KIAS, $\ge 1,000$ ft AGL, $\le 35^\circ$ bank). Any takeoff roll ($0\text{ KIAS}, 0\text{ AGL}$) or landing flare ($<60\text{ KIAS}, <50\text{ AGL}$) triggers an immediate fault and pauses the simulation. A multi-phase envelope model (Ground, Takeoff, Climb, Search, Approach, Landing) is required.

#### Additional Gaps
1. **Retired Scripted Full-Flight Sequence:** The end-to-end mission controller in `flight_controller.py` and `mission_ksee_krnm.py` is retired from live simulator use because it performed unrestricted direct control writes without safety leases or process mutual exclusion. It currently runs only against an offline mock physics loop (`MockFlightSimulator`).
2. **Lack of Terrain Lookahead:** The gate evaluates AGL only at the current coordinate. It has no digital elevation model (DEM) lookahead along the projected flight path.
3. **No Automated Communications / Duty Cycle:** Unattended SAR requires automated ops-normal reports every 30 minutes, calling "in grid" and leg turns over virtual radio nets, and responding to base retask directives.

---

## 2. Use Case 2: Scripting Flight Test Tasks & Flying Flight Test Profiles

### 2.1 Requirements for Flight Test Automation
Flight test engineering requires:
1. **Repeatable Reference Conditions:** Stabilizing the aircraft at target weight, CG, altitude, and airspeed before initiating any test point.
2. **Precise Excitation:** Applying deterministic, calibrated inputs (e.g., trapezoidal pulses, steps, frequency sweeps, bank steps, speed ladders) on specific axes while holding or freeing off-axis parameters.
3. **High-Rate, Multi-Channel Instrumentation:** Recording demanded control positions, actual surface deflections, body angular rates ($P, Q, R$), true angles of attack and sideslip ($\alpha, \beta$), normal acceleration ($N_z$), engine state, and trim rates at $\ge 10\text{–}20\text{ Hz}$.
4. **Phase-Gated State Machines:** Automating test point sequences: `ESTABLISH` $\to$ `STABILIZE` $\to$ `EXCITE / MEASURE` $\to$ `RECOVER` $\to$ `DATA REDUCTION`.
5. **Specialized Flight-Test Safety Models:** Accommodating maneuvers outside normal flight envelopes (e.g., slow flight, stalls) with dedicated abort floors, maximum loss-of-altitude triggers, and immediate recovery logic.

---

### 2.2 Current Capabilities in the Codebase

#### A. Comprehensive Instrumentation Harness
* **Verified Sensor Datarefs (`docs/C182T_HANDLING_TEST_MATRIX.md`):** 25+ verified live channels including actual surface deflections (`flightmodel2/wing/elevator1_deg[8]`, `aileron1_deg[2]`, `rudder1_deg[10]`), body rates (`flightmodel/position/P,Q,R`), aerodynamic angles (`alpha`, `beta`), normal acceleration (`g_nrml`), elevator trim (`sim/cockpit2/controls/elevator_trim`), fuel flow, and weight.
* **Logging Infrastructure:** `scripts/fly_card_h0.py` and `scripts/capture_flight_test.py` record time-synchronized 20 Hz JSONL traces storing pre-rate-limit demands, actual commands, surface responses, and controller internal states.

#### B. Dedicated Flight-Test Control Laws (`services/ai_pilot/direct_backend.py`)
To support airframe characterization, the direct controller implements:
* **`apply_test_input(TestInput)`:** Superimposes bounded, trapezoid-shaped single-axis inputs (pitch, roll, or yaw) with configurable duration and ramp-in/ramp-out times. Automatically self-expires within the control loop.
* **`select_bank(bank_deg, altitude)`:** Holds commanded bank angles directly (Card H2) rather than treating bank as an intermediate product of heading error.
* **`select_airspeed(kias, throttle)`:** Implements speed-on-pitch (Cards H1, H3) where pitch controls airspeed and throttle is held constant.
* **`set_flaps(ratio)`:** Discrete flap configuration changes (Card H4).
* **Closed-Loop Autotrim:** Continuously trims elevator to unload yoke forces, directly outputting the trim demand required by handling qualities tests.
* **Surface Slew Rate Limiters:** Clamps actuator rates ($0.40/\text{s}$ aileron/elevator, $0.60/\text{s}$ rudder) to prevent non-physical step transients.

#### C. Card H0 (Control & Trim Confidence) Automated Execution
* **Automated Runner (`scripts/fly_card_h0.py`):**
  * Enforces a criterion-based stabilization hold ($\pm 2\text{ KIAS}$, $\pm 60\text{ ft}$, $\pm 120\text{ fpm}$, $\pm 2^\circ\text{ bank}$ for $\ge 4.0\text{ s}$). Refuses to fly if the reference condition is not settled.
  * Sequentially commands 10 single-axis test points: pitch $\pm 0.05, \pm 0.10$; roll $\pm 0.05, \pm 0.10$; yaw $\pm 0.05$.
  * Stabilizes and measures post-pulse recovery time after every point.
* **Live Test Verification:** Flown live on 2026-09-17 (Run 6). Findings documented in `docs/C182T_H0_CONTROL_LAW_FINDINGS.md`. Demonstrated $3\%$ roll linearity, identified pitch small-input asymmetry, and proved autotrim function.

#### D. Stall Test Profile Model (`services/ai_pilot/flight_test.py`)
* Implements `StallTestProfile` as a pure state machine: `STABILIZE` $\to$ `DECELERATE` $\to$ `RECOVER` $\to$ `COMPLETE / ABORTED`.
* Evaluates break criteria ($VVI \le -400\text{ fpm}$ with pitch $\ge 4.0^\circ$).
* Executes aerodynamically sound stall recovery: pushes pitch to $0^\circ$ to unload angle of attack *before* applying full throttle ($1.0$).
* Scales target stall speeds by aircraft weight: $V_{s,\text{target}} = V_{s,\text{ref}} \sqrt{W / W_{\text{ref}}}$.

---

### 2.3 Critical Gaps & Blockers for Scripted Flight Testing

* **Primary Blocker 1: Envelope Conflict for Slow Flight & Stalls (H1, H5, H6, H7, Card A-1).** The 90 KIAS floor enforced by `Limits` in `services/ai_pilot/maneuvers.py` directly prevents autonomous testing of Card H1 (Speed ladder at 80 KIAS), Card H5 (Slow flight at 50–65 KIAS), and Cards H6/H7 & Card A-1 Group A (Power-off and power-on stalls at 40–51 KIAS). While `StallTestProfile` carries its own stricter floor ($3,000\text{ ft AGL entry}, 2,000\text{ ft AGL abort}$), it cannot be flown through the current gate without a dedicated test profile exception.
* **Primary Blocker 2: Active Loop Contamination During Airframe Excitations.** In Card H0 Run 6, the direct backend's altitude and heading hold loops remained active while test inputs were applied. Consequently, pitch response was counteracted by the altitude loop seeking $4,500\text{ ft}$, and roll response was counteracted by the heading loop seeking $100^\circ$. The resulting data represents **controller-in-the-loop dynamics**, not pure bare-airframe stability derivatives. Flight testing requires an open-loop excitation mode with frozen or isolated holds.
* **Primary Blocker 3: Lack of Card Runners for Cards H1–H7 and Groups A–E.** `fly_card_h0.py` is currently the only automated test card script. There are no automated runners for climb performance (Group B1), cruise performance (Group C1/C2), or handling ladders H1–H5. These points currently require a human test pilot to fly the aircraft while tooling passively records data.

#### Additional Gaps
1. **Unflown Stall Profile:** `flight_test.py` has never been connected to live simulator actuators or flown in X-Plane.
2. **Bypass of System Lease in H0:** `fly_card_h0.py` instantiates `XPlaneDirectBackend` directly and bypasses `ManeuverGate` and the process mutual-exclusion lock, creating a potential multi-writer conflict if `maneuver_server` is running concurrently.

---

## 3. Comparison Matrix: Current State vs. Required Capabilities

| Functional Area | Current State | Required for Unattended SAR | Required for Scripted Flight Testing |
|---|---|---|---|
| **Search Patterns** | Full geometry & `.FMS` export implemented | Automated execution & mid-flight retasking | Not required |
| **Ground / Taxi / Takeoff** | Retired prototype code in mock mode only | Deterministic ground steering & rotation laws | Ground roll distance measurement (Card D1) |
| **Cruise / Altitude Holding** | Working in Direct, GFC 700, and ArduPlane backends | Qualified transfer between GFC 700 and ArduPlane | Stable baseline hold before test points |
| **Power Management** | Direct backend has speed-on-throttle; GFC 700 has none | Deterministic autothrottle service for GFC 700 | Precise throttle settings (idle, 80%, full climb) |
| **Approach & Landing** | Retired prototype code in mock mode only | Autonomous flare, touchdown, and rollout | Landing distance measurement (Card D3/D4) |
| **Safety Gate / Envelopes** | Single airborne envelope (3k–6k ft, 90–140 KIAS) | Multi-phase operational envelopes | Scoped high-altitude test envelope (down to stall) |
| **Control Boundary & Ownership** | Gate lease exists; some scripts bypass it | Unified flight executive & output mediation bridge | Exclusive test pilot authority with clean release |
| **Test Excitation Laws** | Trapezoidal pulses (H0), bank (H2), speed-on-pitch (H3) | Not required | Doublets, frequency sweeps, open-loop off-axis holds |
| **Automated Card Runners** | Only Card H0 automated; others manual capture | Mission sequence script | Automated runners for H1–H7 and Groups A–E |
| **Live ArduPlane Status** | Attached, ACKed, but circling in loiter (AI-24) | Must capture GUIDED mode and execute waypoints | Can evaluate ArduPilot tracking as an autopilot test |

---

## 4. Architectural Roadmap & Recommended Next Steps

### Phase 1: Architecture, Safety, and Ownership Foundation
1. **Deploy Multi-Phase Envelopes:** Replace the single 90–140 KIAS, 3,000–6,000 ft MSL envelope in `ManeuverGate` with phase-specific contracts (`GROUND`, `TAKEOFF_CLIMB`, `SEARCH_CRUISE`, `APPROACH_LAND`, `FLIGHT_TEST`).
2. **Unify Control Ownership:** Route all scripts (`fly_card_h0.py`, `fly_search_grid.py`, and `fly_direct_backend.py`) through a centralized flight executive and shared lease lock, eliminating direct actuator write bypasses.

### Phase 2: Controller Qualification & Tuning
1. **Resolve Defect AI-24 (ArduPlane Guided Tuning):**
   * Inspect ArduPilot Plane-4.7.1 source (`ModeGuided::update()` and `navigate()`) to establish why accepted heading/altitude targets do not override default loiter.
   * Validate parameter scale for `GUIDED_P` in `cap487.parm`.
   * Verify TECS climb/sink parameters and baro-versus-true altitude conversions.
2. **Build Virtual Autothrottle for GFC 700:**
   * Implement a deterministic speed-holding power loop that modulates `sim/cockpit2/engine/actuators/throttle_ratio[0]` during GFC 700 climb, cruise, and descent.
3. **Isolate Test Inputs from Hold Loops:**
   * Modify `apply_test_input()` in `XPlaneDirectBackend` to optionally freeze or disable off-axis attitude and altitude holds during the pulse duration.

### Phase 3: Mission Automation & Test Card Execution
1. **Unattended SAR Sequence:**
   * Link `services/flightplanner` pattern generation directly into `fly_search_grid.py` or ArduPlane MAVLink waypoint missions.
   * Resurrect checklist sequencing from `flight_controller.py` into typed executive commands.
2. **Expand Automated Test Cards:**
   * Build `fly_card_h1_speed_ladder.py`, `fly_card_h2_bank_ladder.py`, and `fly_group_b_climb.py`.
   * Hook `StallTestProfile` from `flight_test.py` into `XPlaneDirectBackend` under the new `FLIGHT_TEST` envelope, executing and recording automated power-off stall breaks.

