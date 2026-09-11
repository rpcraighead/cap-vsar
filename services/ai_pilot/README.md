# AI Pilot Service: Cessna 182T NAV III for X-Plane 12

A supervised airborne maneuver controller for Mission Observer training in the
Civil Air Patrol Cessna 182T Skylane NAV III (G1000 / CAP 487) in X-Plane 12.
Earlier full-flight automation remains as an offline test prototype.

## Airborne maneuver controller (2026-09-10)

The new MO-training entrypoint is an isolated, local airborne deck:

```bash
python3 -m services.ai_pilot.maneuver_server
# Browse http://127.0.0.1:8089
# After positioning CAP 487 airborne manually, use the live adapter:
python3 -m services.ai_pilot.maneuver_server --live --min-altitude 3000 --max-altitude 6000
```

When launching X-Plane from the Snap-packaged VS Code terminal, use the project
launcher so X-Plane does not inherit Snap libraries or desktop paths:

```bash
scripts/launch_xplane12.sh --check
scripts/launch_xplane12.sh
```

The preflight check also refuses to start X-Plane when the loaded and installed
NVIDIA driver versions differ, which requires a host reboot after a driver
update.

Mock mode supplies **static** aircraft observations; it verifies the interface,
not flight dynamics. It deliberately does not move observations toward commanded
values. Live mode never spawns or resets the aircraft. It subscribes to aircraft
observations and waits for explicit **Acquire control** before accepting maneuvers.

The project’s legacy web, chat, model-tool, and scripted-mission entrypoints can
no longer write to live X-Plane. The new process has a duplicate-instance lock
and serialized control lease. An unrelated third-party plugin can still write
X-Plane controls, so disable other autopilot/control plugins for acceptance tests.

Supported text commands:

- `heading 090 magnetic` (heading, not ground track; backend chooses turn direction)
- `maintain 4500 feet indicated`
- `climb to 5000 feet indicated` / `descend to 4000 feet indicated`

The full-match parser rejects negations, compound instructions, bare bearings,
specified left/right turns, and unsupported commands without aircraft writes.
Altitude is **pilot-indicated altitude**: set the aircraft altimeter correctly.
Power remains manually managed. There is no voice or LLM dependency in this path.
Altitude changes greater than 100 ft use the G1000 FLC command with a 110-KIAS
exercise target. The supervising pilot supplies climb/descent power; FLC does
not command a fixed climb rate. Confirm FLC, the speed bug, selected altitude
and subsequent altitude capture on the cockpit displays. This target is an
exercise setting, not a POH performance figure.

`maneuvers.FlightBackend` defines `observe`, `select`, `release`, and `pause`.
`XPlaneAutopilotBackend` implements it using the simulated aircraft autopilot;
ArduPlane can later implement the same contract. It is not installed or integrated
here. Its published X-Plane setup guide covers 10/11, so X-Plane 12 compatibility
and CAP 487 tuning still require a separate measured trial:
https://ardupilot.org/dev/docs/sitl-with-xplane.html

The gate validates a control lease and strictly increasing sequence, finite
values, fresh observations, the configured altitude block, and the prototype
exercise envelope (90–140 KIAS, at least 1000 ft AGL, at most 35 degrees bank).
These are exercise guardrails, not POH limits or regulatory minimums. The altitude
check uses current terrain only; no terrain lookahead or airspace model exists.
Accepted maneuvers are reported as executing, then achieved only after heading
within 3 degrees, altitude within 100 ft, bank within 5 degrees, and vertical speed
within 150 ft/min remain satisfied for 3 seconds. Capture is measured aircraft
behavior, not acknowledgement of a UDP write. Events are bounded to 200 in memory.

**I have control** revokes the lease before requesting autopilot disconnect; old
requests cannot re-engage through that lease. Verify disconnect in the cockpit.
A telemetry/envelope fault revokes control and requests simulation pause, leaving
existing autopilot modes alone. Shutdown while owning control also requests pause.
Pause uses the explicit `sim/operation/pause_on` command: `sim/time/paused` is
a read-only observation, not a writable control.
UDP pause/disconnect delivery is not guaranteed; verify locally. Recovery requires
checking the aircraft, resuming X-Plane manually and acquiring a new lease.

REST: `POST /api/acquire`, `POST /api/takeover`, `GET /api/status`, and
`POST /api/maneuver` with JSON such as:

```json
{"lease":"<acquire result>","sequence":1,"maneuver":{"heading_mag":90,"altitude_indicated_ft":4500}}
```

Use `text` instead of `maneuver` for the supported grammar. Invalid commands return
JSON 400. The loopback-only deck has no spawn, checklist-write, flight-phase or
scripted-mission endpoints. It does not fetch scenario data or hidden beacon truth.

Validation: automated gate, backend packet-intent and HTTP tests are in
`tests/test_maneuvers.py`. Live X-Plane handling, autopilot indications, maneuver
tracking, pause and disconnect still require simulator acceptance testing. No
ArduPlane, autonomous pattern tracking, speed control, ATC, takeoff or landing is
claimed for this implementation.

## Direct surface-control backend (2026-09-11)

`direct_backend.XPlaneDirectBackend` flies CAP 487 on the **primary flight
controls** — yoke, rudder, throttle and elevator trim — rather than through the
GFC 700 autopilot. It implements the existing `maneuvers.FlightBackend` protocol,
so the control lease, the strictly-increasing sequence, the exercise envelope and
capture detection all apply to it exactly as they do to the autopilot backend.

The point is to let an agent fly an aircraft that has **no autopilot**, and to
make the airframe characterization cards (H0–H7) executable at all. It
disengages the aircraft's autopilot on engaging, because it must own the control
surfaces exclusively — an engaged GFC 700 would be driving the servos toward its
own targets while this loop writes yoke ratios, and the two would fight.

**This is a flight-test instrument, not a pilot.** Do not run it at the same time
as `maneuver_server`, which would put two writers on the same surfaces.

### Commands

| Method | Card | What it does |
|---|---|---|
| `select(heading_mag, altitude_indicated_ft)` | — | the `FlightBackend` protocol command; heading and altitude holding |
| `select_bank(bank_deg, altitude_ft)` | H2 | hold a commanded bank angle directly |
| `select_airspeed(kias, throttle=None)` | H1, H3 | **speed-on-pitch**: pitch holds speed, throttle is the independent variable |
| `set_flaps(ratio)` | H4 | flap actuation |
| `apply_test_input(TestInput(axis, magnitude, duration_s, ramp_s))` | H0 | a bounded, ramped, **self-expiring** single-axis input superimposed on the loop |
| `release()` | — | hand back control; neutralizes only if this backend actually engaged |
| `pause()` | — | fault path |

`TestInput` is frozen and expiry is checked inside the control loop rather than
by a timer, so an input cannot outlive the loop that is applying it. Magnitude
*and* duration are both bounded and both checkable, unlike a raw surface command.

`release()` will not neutralize an aircraft this backend never commanded:
centring the yoke and setting cruise throttle on an aircraft somebody else is
flying disturbs their trim for no reason. Elevator trim is deliberately outside
the neutralize set — handing an aircraft back with the trim slammed to neutral is
an upset, not a release.

### Control structure

```
heading  -> bank     -> aileron   (+ roll-rate damping)
altitude -> VS       -> pitch     -> elevator  (+ pitch-rate damping)
                        + altitude trim integrator
speed    -> throttle  (PI, conditional integration)
elevator -> elevator trim  (autotrim, deadband + rate limit)
coordination: adverse-yaw feedforward + sideslip PI + right-rudder feedforward
```

Every surface command passes a **slew-rate limiter** as the last step before the
wire, so nothing upstream — loop, clamp or test input — can produce a step at the
controls.

### Fail-closed rules

These are not stylistic. Each one is a bug that was found in flight.

* **Trim is never written without a readback.** Flying out of trim is
  recoverable; writing a guessed trim position to an aircraft somebody else has
  been flying is not.
* **Body rates and trim are auxiliary datarefs, outside the freshness gate.**
  Losing a damping channel must degrade the damping, not neutralize the controls
  on an airborne aircraft. Their age is recorded as `body_rate_age_s` (`inf` when
  degraded) so a degraded run is visible in the trace rather than silent.
* **Integrators are conditional, not merely clamped.** Clamping the integral term
  while the output is against a stop is not anti-windup.
* **Integrators are frozen against a deliberate test input**, and cleared on
  release, so a new engagement never resumes from a stale internal value.

### Flying it

```bash
# supervised target holding through the real gate
python3 scripts/fly_direct_backend.py --heading 120 --altitude 4500

# card H0, control and trim confidence
python3 scripts/fly_card_h0.py --run 6 --kias 100
```

`fly_card_h0.py` **refuses to take data off an unstabilized reference** (exit 3)
and records each point's entry condition. `--force` flies it anyway and stamps
the run as not a valid test point.

Traces are JSONL under `~/.cache/capvsar/flight-tests/`, with the gain set in the
header — a trace you cannot attribute to a tune is not evidence of anything.

### Status

**Not validated.** The gains hold a reference condition well enough to take data
*from*; they are not a flight-model result and say nothing about the airframe.
Card H0 has been attempted five times and remains **unflown** — it has not yet
reached its first input from a stabilized reference. Five control-law defects
were found and fixed in the process; all are recorded with trace evidence in
`docs/C182T_H0_CONTROL_LAW_FINDINGS.md`.

Offline coverage: 80 tests in `tests/test_direct_backend.py`, 150 across the
service, none requiring X-Plane.

## Legacy scripted prototype

The remaining sections describe the earlier experimental controller. Its live
mutation routes are retired: chat and model tools are observation-only, REST
mutation endpoints return HTTP 410, and `mission_ksee_krnm --live` is refused.
The mock mission remains available for regression testing of the prototype.

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
  - Exposes only `get_flight_telemetry`; aircraft mutation tools are retired.
  - Advisory Ollama replies are instructed never to claim aircraft action or ATC clearance.
- **Validation Flight Scenario (`mission_ksee_krnm.py`)**:
  - Gillespie Field (KSEE Runway 27R) to Ramona Airport (KRNM Runway 27).
  - Starts cold & dark, runs all 9 checklists, climbs to 4,500 ft MSL over Santee/Iron Mountain ridgeline, descends to Ramona, lands on Runway 27, and shuts down.

## Quick Start

### 1. Launch the legacy observation deck
Starts the compatibility telemetry and advisory dashboard on port **8088**:
```bash
# Offline simulated mode:
python3 -m services.ai_pilot.web_server --port 8088

# Or read telemetry from live X-Plane 12 (UDP 49000):
python3 -m services.ai_pilot.web_server --port 8088 --live
```
Open **http://localhost:8088** in your browser.

The web dashboard features:
- **Primary Flight Display (PFD)**: Real-time airspeed tape, artificial horizon (pitch & roll canvas), altimeter tape, VVI, and heading bug.
- **Engine & System Gauges**: Lycoming IO-540 tach RPM, manifold pressure, flaps indicator, parking brake status.
- **Mission Progress & Route Track**: Interactive route bar from Gillespie Field (KSEE 27R) to Ramona Airport (KRNM 27) with live distance and terrain profiling.
- **Authentic POH Checklist References**: Displays item state without executing cockpit writes.
- **Advisory Chat**: May describe status; control language returns an explicit no-action response.
- **Retired Controls**: Old mutation requests return HTTP 410 and direct users to the maneuver deck.

### 2. Run the Headless Mission CLI
Runs in simulated mock mode without requiring a browser or X-Plane:
```bash
python3 -m services.ai_pilot.mission_ksee_krnm --fast
```

### 3. Run the supervised controller against Live X-Plane 12
1. Launch X-Plane 12 with `Cessna 182T NAV III (CAP 487)` and position it airborne.
2. Start the maneuver deck:
```bash
python3 -m services.ai_pilot.maneuver_server --live --min-altitude 3000 --max-altitude 6000
```
3. Open **http://127.0.0.1:8089**, check the aircraft and altimeter, then use
   **Acquire control**. `mission_ksee_krnm --live` intentionally exits without
   writing to the simulator.

### 4. Run Unit & Integration Tests
```bash
python3 -m unittest discover -s services/ai_pilot/tests -v
```
