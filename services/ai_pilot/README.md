# AI Pilot Service: Cessna 182T NAV III for X-Plane 12

A supervised airborne maneuver controller for Mission Observer training in the
Civil Air Patrol Cessna 182T Skylane NAV III (G1000 / CAP 487) in X-Plane 12.
Earlier full-flight automation remains as an offline test prototype.

The [AI Pilot and Test Pilot development plan](../../docs/AI_PILOT_DEVELOPMENT_PLAN.md)
sets the next implementation sequence: a measured establish–maneuver–recover
cycle, followed by ground/runway skills, complete sorties, and deliberate
flight-test maneuvers. It includes architecture, acceptance criteria, and the
first implementation assignment.

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

## Full-sortie intent and taxi policy foundation (2026-09-15)

The intended AI Mission Pilot is not limited to the current airborne maneuver
deck. It is expected eventually to taxi out, take off, fly the assigned mission,
land, and taxi back to the position where the session began. Aircraft with an
accepted onboard autopilot may use it for airborne phases; ArduPlane is the
planned navigation and stabilization backend when the aircraft lacks one. The
direct surface-control backend below remains the flight-test instrument for
airframe characterization and deliberate envelope work.

`taxi.TaxiCoordinator` is the first implementation slice. It records the starting
point and will accept a return route only when that route terminates at the same
point. An AI or planner may propose the route, but deterministic policy owns
movement authority: towered movement requires ATC authorization, every runway
crossing is specific and single-use, taxi clearance does not imply departure-
runway entry, route uncertainty produces a stop and progressive-taxi request,
and post-landing taxi cannot begin until the aircraft is reported wholly clear
of the runway.

Those rules follow FAA AIM 4-3-18, 4-3-21 and 2-3-5 plus 14 CFR 91.129(i). They
are simulation policy, not approval for real-aircraft use. The coordinator emits
abstract directives only. It is not connected to X-Plane or MAVLink, and it
cannot move the aircraft. Tracker item AI-8 owns the remaining airport-surface
graph, clearance/ATC state, ArduPlane adapter, steering/throttle/brake actuation,
exclusive handoff, and live acceptance work.

## Aircraft profiles, the C182T port and search patterns (2026-10-11)

`aircraft_profiles.py` holds the operating speeds and acceptance windows the
takeoff, landing and KSEE-KMYF controllers used to carry as literals, one record
per aircraft with the handbook line for each sourced value. `C172SP` is the
flown stock C172 (the default everywhere, so nothing flown has changed);
`C182T` is the CAP 487 package, sourced from the 182T NAV III information manual
the project pins. The C182T record carries `tuning_validated=False`: its base
throttles, flap gates and observer windows are the C172 criteria shifted to the
182T's speeds and have not been flown. See
`docs/C182T_AI_PILOT_PORT_2026-10-11.md` for the mapping and the trial order.

`search_patterns.py` generates CAP expanding square, creeping line and parallel
track waypoints to the D2 convention shared with the planner and g1000-sar
(their fixture is replayed in the tests), and `SearchPatternController` flies
them on the primary controls with the C172 mission controller's cruise loop.
Offline-tested only; no runner, no bridge integration, never flown.

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
Card H0 was flown on its sixth attempt on 2026-09-17, with nine of ten points
entered on condition. The earlier five attempts exposed control-law defects;
their fixes and the sixth run are recorded with trace evidence in
`docs/C182T_H0_CONTROL_LAW_FINDINGS.md`. This limited controller-confidence
result does not qualify the current live bridge or a complete flight.

Offline coverage: 84 tests in `tests/test_direct_backend.py`, 150 across the
service, none requiring X-Plane.

## Flight modes: current implementation status (2026-09-18)

The September 17 ArduPlane GUIDED trial **did fly CAP 487**, but neither
heading nor altitude captured. Offline replay of its final 2,973.95-ft sample
is a gate altitude-envelope fault, so the old “flight complete” label was not
a success result. The pinned `GUIDED_P=5000`, `I=0`, `D=0` match upstream
defaults; their effective loaded values and aircraft suitability are unknown.

The new `flight_executive.py`, `mission_script.py`, `test_pilot_script.py`,
`arduplane_mission.py`, controller adapters, phase profiles, and isolated
flight-control plugin implement an **offline workflow and output boundary**.
The mission runner also accepts an optional planned Garmin cruise segment.
It requires measured entry and task completion, then a caller-supplied managed
SITL restart/fresh candidate session and a mission-progress rejoin check.
`managed_return.py` provides the offline-tested restart sequence with an
isolated mapping, fresh MAVLink link, mission reupload and observed AUTO/current
item. Its worker keeps slow restart work off the executive tick path; the
bridge still times out if executive ticks stop. Its production path remains
blocked pending attended qualification.
All live launchers remain disabled by `control_ownership.py`; the plugin has
not been installed or flown. The legacy launcher paths below are historical
prototype descriptions and still need full migration to the executive. See
`docs/FLIGHT_MODES_IMPLEMENTATION_STATUS.md` and
`docs/FLIGHT_MODES_ACCEPTANCE.md` for gaps and the attended sequence.

The executive keeps role, phase, controller, test substate and transfer state
as separate typed fields. Its valid role/phase/controller combinations are:

| Role | Phase | Controller | Current capability |
| --- | --- | --- | --- |
| HUMAN | Any phase | HUMAN | Explicit takeover, latched until a new request |
| AI_MISSION | TAKEOFF, CLIMB, TRANSIT, SEARCH, APPROACH, LAND, ROLLOUT | ARDUPLANE | Offline AUTO mission workflow; runway phases need sourced corridors |
| AI_MISSION | TRANSIT, SEARCH, APPROACH | GFC700 | Explicit observed transfer; requires qualified virtual-pilot power/configuration |
| AI_TEST | TEST | DIRECT | Offline H0 typed input and recovery workflow |
| AI_TEST | TEST | GFC700 or ARDUPLANE | Reserved typed combination; tracking card/aircraft qualification not implemented |

Each nonhuman controller gets exactly one allocation per actuator domain.
ArduPlane owns primary, throttle and configuration while the bridge holds
measured trim; the human retains ground controls. GFC 700 owns primary and
trim, while the virtual pilot owns power and configuration. DIRECT owns
primary, trim, power and configuration during an authorized test. A transfer
changes the bridge generation and revokes the previous lease. Candidate DREF
packets are independent and do not contain a source sequence; this remains a
live qualification limitation.

## ArduPlane backend (historical GUIDED prototype)

`arduplane_backend.ArduPlaneBackend` is the third `maneuvers.FlightBackend`:
it puts an ArduPilot ArduPlane SITL (attached to X-Plane with the DRef-based
`--model xplane` backend) into GUIDED and sends `MAV_CMD_GUIDED_CHANGE_ALTITUDE`
/ `_HEADING`; ArduPilot flies the surfaces. This module never writes a control
surface. The historical GUIDED launcher uses `ManeuverGate`. The newer
executive provides typed mission phases through a separate adapter.

MAVLink is spoken by `mavlink_min.py`, a stdlib codec for the backend,
mission-upload, and diagnostic message subset. No new dependency.

**Historical status:** one bounded GUIDED trial flew without capture; gate G
remains undecided. The new AUTO runway-to-runway workflow is offline-tested
only. No X-Plane 12 compatibility, CAP 487 tuning, or autonomous takeoff and
landing behavior is qualified.

### Yoke authority

SITL's mapping sets `sim/operation/override/override_joystick=1`, so while it
is attached the physical yoke reaches X-Plane only through ArduPilot's RC
passthrough. The rules, each a named test:

* moving the yoke releases: ArduPilot's `RC_CHANNELS` ≥40 µs from where they
  sat at engagement (measured, not assumed to be 1500) for 0.3 s, **or**
  X-Plane's raw `joystick_axis_values` moving >8 % — either detector alone is
  enough, so takeover does not depend on the RC map being right; after a
  takeover `select` is refused until `release()` acknowledges it;
* `release()` clears the heading hold and parks ArduPlane in **LOITER** — the
  only mode of the three that flies itself with no RC — or in **FBWA** when a
  valid, centred RC position was measured at engagement. **MANUAL is never
  used**: it passes the raw stick to the surfaces, and an unmapped joystick
  axis reads as full aileron and full throttle (AI-21). `release()` never
  pauses and never touches X-Plane controls, trim or the override;
* the launcher owns the SITL process. On exit it parks the aircraft, stops
  SITL, clears both X-Plane overrides and engages the GFC 700 in HDG+ALT —
  **in that order**, because SITL re-asserts the overrides every frame while it
  lives and clears nothing when it dies (`services/ai_pilot/sitl_lifecycle.py`);
* a lost ArduPilot heartbeat **pauses** and also writes the joystick/throttle
  overrides back to 0 — a dead SITL must not leave a dead yoke;
* `pause()` never changes ArduPilot's mode;
* the aircraft's own autopilot is disengaged before the first MAVLink write,
  and re-engaging it while ArduPilot is flying releases (one writer, CONOPS §7.2).

### Frames

Heading: the gate is magnetic, ArduPilot's guided heading is true — the
offset is measured live as `psi − mag_psi`. Altitude: the gate measures
indicated, SITL flies true MSL — the offset is measured at engagement and the
target re-issued if the aircraft levels more than 40 ft short. ArduPilot's
true altitude is also checked against X-Plane's (±100 ft) as a "SITL is
attached to this aircraft" test.

### Ports

| Link | Port | Owner |
|---|---|---|
| X-Plane → SITL data | UDP 49001 (`_snd_port`) | ArduPilot SITL |
| SITL → X-Plane DREF/RREF | UDP 49000 (`_rcv_port`) | ArduPilot SITL |
| SITL MAVLink | TCP 127.0.0.1:5760 | `MavlinkLink` |
| This backend's RREF replies | UDP 49260 | `fly_arduplane_backend.py` |

### Running it

```bash
scripts/setup_ardupilot_sitl.sh --check       # then without --check to build
python3 scripts/fly_arduplane_backend.py --dry-run          # starts nothing
python3 scripts/fly_arduplane_backend.py --heading 120 --altitude 4500 --axis-pitch 1 --axis-roll 0
python3 scripts/fly_arduplane_backend.py --no-sitl ...     # attach to a SITL you started
```

The launcher holds the maneuver deck's controller lock for the run and refuses
to start if it is held, prints a pre-flight block (heartbeat, mode, magnetic
and altimeter offsets, SITL-vs-X-Plane altitude, joystick axes), and refuses
if SITL's altitude disagrees with X-Plane's. `--backend arduplane` on
`maneuver_server` is deliberately not added until the trial has flown.

Offline coverage: 41 tests in `tests/test_arduplane_backend.py`, 18 in
`tests/test_mavlink_min.py`, 14 in `tests/test_sitl_lifecycle.py`.

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
