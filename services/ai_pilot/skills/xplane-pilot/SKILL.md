---
name: xplane-c182t-pilot
description: Autonomous flight control and POH checklist copilot for the Civil Air Patrol Cessna 182T NAV III in X-Plane 12.
---

# X-Plane Cessna 182T NAV III Flight & Checklist Skill

This skill enables Hermes Agent (or any local model on BigBrain) to act as Pilot-in-Command (PIC) or Copilot for the Civil Air Patrol Cessna 182T NAV III (CAP 487) flying the Gillespie Field (KSEE) to Ramona Airport (KRNM) mission.

## Tools Exposed
- `get_flight_telemetry()`: Reads real-time indicated airspeed, altitude MSL/AGL, magnetic heading, vertical speed, engine RPM, manifold pressure, and distance to destination.
- `execute_checklist(checklist_name)`: Challenges and verifies all authentic Cessna 182T NAV III POH Section 4 procedures:
  - `BEFORE_ENGINE_START`
  - `ENGINE_START`
  - `BEFORE_TAKEOFF`
  - `TAKEOFF_AND_CLIMB`
  - `CRUISE`
  - `DESCENT`
  - `BEFORE_LANDING`
  - `AFTER_LANDING`
  - `SHUTDOWN_AND_SECURING`
- `command_flight_phase(phase)`: Directs the flight controller state machine through takeoff, climb, cruise, descent, approach, flare, rollout, and shutdown.
- `set_autopilot(heading_mag, altitude_ft, vs_fpm)`: Engages and programs GFC 700 / G1000 autopilot datarefs.
- `spawn_on_runway()`: Relocates aircraft to KSEE Runway 27R threshold with cold-and-dark baseline.

## Mission Profile (KSEE 27R -> KRNM 27)
1. **Departure**: Gillespie Field Runway 27R (heading 274° M, elevation 388 ft MSL).
2. **Climb**: Straight climb to 1,500 ft MSL, followed by a right turn to 015° M.
3. **Cruise**: Level off at 4,500 ft MSL to ensure 1,600+ ft ground clearance over the Iron Mountain / Mount Woodson ridgeline. Set 23 in Hg / 2400 RPM, mixture leaned, cowl flaps closed.
4. **Descent**: Commencing 6 NM south of Ramona, descend at 600 fpm to 2,400 ft MSL.
5. **Approach**: Intercept Ramona Runway 27 extended final (heading 273° M), configure flaps 20° then 30°, maintain 65 KIAS on 3° glidepath.
6. **Landing**: Idle throttle at 40 ft AGL, flare to +4.5° pitch, touchdown on Runway 27, rollout with progressive braking, full stop, and engine shutdown.
