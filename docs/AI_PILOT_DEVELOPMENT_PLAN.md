# AI Pilot and Test Pilot Development Plan

Date: 2026-10-10. Owner: Ron. Repository baseline: `57663ec`.
Status: agreed direction; the milestones below require implementation and measured simulator acceptance.

Implementation on `feat/ai-pilot-first-cycle` has passed a fresh frozen
stock-C172 campaign after the activation timing fix: ten consecutive baseline
flights and ten disturbed entries, with independent trace replay and confirmed
terminal pause in every flight. See the [requalification report](evidence/AI_PILOT_REQUALIFICATION_20261010.md),
the [earlier campaign](evidence/AI_PILOT_SOL_CAMPAIGN_20261010.md), and the
[Sol handoff](AI_PILOT_SOL_HANDOFF.md). The earlier startup failures and one
intermediate campaign's in-flight frame expiry are preserved as evidence.
The next phase produced attended [KMYF 28R landing engineering trials](evidence/AI_PILOT_KMYF_LANDING_20261010.md):
normal 65 KIAS approaches, a low/slow recovery, two 12 kt left-crosswind
landings and a calm regression all reached a scored full stop. Repeated
landing qualification, short-field 61 KIAS landings, taxi and takeoff remain
future milestones.
The active stock-C172 route is now the
[KSEE 27R–Mission Bay Two–BAKEL–KMYF ILS 28R trial](C172_KSEE_KMYF_IFR_TRIAL.md).
Its taxi and takeoff controllers are offline candidates pending surveyed
airport geometry, a bounded live bridge mode, and trace-backed simulator tests.
The [first increment](AI_PILOT_FIRST_INCREMENT.md) records the earlier
observation-only stage. Broader aircraft and mission qualification remains
outstanding.

Build an X-Plane pilot that can taxi, take off, cruise, approach, land, and
return to parking, plus a test pilot that can establish reference conditions,
execute handling and performance tests, deliberately enter stalls, and recover.
The AI interprets intent and manages tasks; a local flight controller continuously
flies the aircraft. Progress is measured by repeated simulator trials and their
recorded outcomes.

The first deliverable is an **establish–maneuver–recover–report** cycle on the
stock C172. Starting from a controlled airborne condition, it must stabilize,
execute a turn or climb, recover, and produce an independently scored report.
An initial attended qualification leads to repeatable unattended execution
inside the demonstrated operating envelope.

## Existing evidence and reuse

The repository contains useful components, but their qualification differs.

| Component | Evidence and disposition |
| --- | --- |
| `services/ai_pilot/direct_backend.py` | Starting controller candidate. The detailed H0 record describes a sixth simulator run on 2026-09-17 with nine of ten points entered on condition. This is limited controller evidence, not general aircraft or controller qualification. |
| `flight_executive.py`, `test_pilot_script.py`, `mission_script.py` | Reuse typed tasks, measured completion, test provenance, and explicit outcomes where they fit. Their offline workflows do not establish complete-flight capability. |
| `xplane/PI_capvsar_flight_control.py` and bridge core | Starting point for exclusive control ownership. The current plugin and live routes remain unqualified; protocol and SDK behavior need simulator trials. |
| `taxi.py` | Reuse route and clearance policy. Steering, throttle, brakes, and observed route progress still need implementation. |
| Capture and reduction scripts | Reuse trace channels and analysis after checking timestamps, units, and provenance. |
| ArduPlane integration | Candidate for a bounded normal-flight comparison. The recorded GUIDED trial did not establish heading or altitude capture. |
| Custom C182 | Target aircraft after controller qualification on a stable reference aircraft. Its unresolved aerodynamic calibration must remain distinguishable from controller defects. |

Historical evidence is in [H0 findings](C182T_H0_CONTROL_LAW_FINDINGS.md),
[flight modes status](FLIGHT_MODES_IMPLEMENTATION_STATUS.md), and
[C182 calibration](C182T_FLIGHT_MODEL_CALIBRATION.md). The September status
documents contain historical commit and test-count statements; they are not
current inventories. This plan sets the next development sequence while retaining
their flight evidence and unresolved findings.

## Architecture

| Layer | Responsibility | Contract |
| --- | --- | --- |
| AI pilot | Interpret requests, plan sorties and cards, explain outcomes, propose changes between trials | Typed tasks and bounded parameters; no dependency on model response time for stabilization or recovery |
| Flight executive | Run checklists and phases; validate entry, completion, deadlines, recovery, and go-around | Explicit state transitions driven by observations |
| Local controller and simulator bridge | Control steering, brakes, yoke, rudder, throttle, trim, and configuration | One owner per actuator; coherent commands applied through the simulator flight loop |
| Independent observer | Record and score aircraft behavior | Evaluate raw observations independently of controller success messages |

Keep one primary airborne controller during initial qualification. Start with
the existing direct controller, measure its response, and replace deficient
loops as needed. Defer routine Garmin/ArduPlane/direct handoffs until a single
controller can fly the baseline reliably. Keep ArduPlane as a comparison option,
not a prerequisite for the first flight demonstration.

Use the existing Python service and XPPython3 integration initially. Keep
callbacks short and bounded; move computation or adopt a compiled component
only when timing measurements justify it. Select the control architecture from
flight evidence rather than committing to a language rewrite first.

### Simulator control boundary

The bridge is the sole project component that writes native aircraft controls.
Control frames carry session identity, ownership generation, increasing sequence,
expiry, and a complete actuator set. Reject stale, duplicate, wrong-session,
incomplete, and nonfinite frames. Independent per-channel UDP updates must not
silently assemble a command from different moments.

Telemetry snapshots carry simulation time, monotonic wall time, frame identity,
channel age, units, coordinate conventions, and aircraft identity. Define true
versus magnetic direction and indicated, MSL, and AGL altitude explicitly.

Use simulation-time intervals in integration, rate limiting, and control laws.
Use wall time for process and communication watchdogs. Define pause, reset,
time-acceleration, and low-frame-rate behavior, including integrator resets or
freezes. Measure actual callback rate and latency instead of promising a fixed
frequency above the simulator's frame rate.

Apply controls through the appropriate flight-loop phase and collect response
after the flight model runs. No HTTP calls, model inference, blocking socket
reads, or resource initialization belong in that callback. X-Plane provides
pre- and post-flight-model callbacks; their timing and restrictions are described
in the [SDK processing documentation](https://developer.x-plane.com/sdk/XPLMProcessing/).

A takeover must stop project control writes and verify the resulting ownership.
For each flight phase, define the response to lost telemetry, lost executive,
and unavailable recovery. Verify pause by readback when used. Pause and reset
are intervention outcomes, never successful maneuver completion.

### Aircraft and observation profiles

Profiles describe the aircraft's control mappings, units, engine and propeller
controls, trim behavior, flap detents, landing gear, steering, brakes, and
configuration-dependent operating limits. Record the source of each operational
value and separately label controller tuning and engineering acceptance values.

Begin with structured simulator telemetry and pilot-equivalent control inputs.
Keep full simulator truth available to the observer. Record which truth channels
the controller uses, so later cockpit-observation or vision-based trials can
restrict inputs without changing the scoring system. State-setting and resets
are allowed between trials; during a scored flight the pilot operates controls
and X-Plane computes the motion.

## Flying skills

Each skill needs an entry condition, commanded behavior, observed completion,
deadline, recovery or abort path, and a trace-backed acceptance test.

| Skill | Required behavior | Evidence |
| --- | --- | --- |
| Taxi and stop | Follow route geometry, manage speed, negotiate corners, stop at a specified point, hold short, return to the recorded parking position | Cross-track error, speed, stop error, boundary incursions, brake and steering response |
| Takeoff and climb | Run configuration checks, track centerline, rotate, establish climb, transition configuration | Runway position, airspeed, attitude, actual liftoff, climb performance and configuration readback |
| Cruise and navigation | Hold speed and altitude, capture headings and ground tracks, coordinate turns, manage power and configuration | Tracking distributions, capture time, sideslip, overshoot, control saturation |
| Approach and landing | Join a path, establish a stable approach, flare, touch down, maintain direction, brake to a stop | Approach error, touchdown location, vertical and lateral motion, rollout, confirmed stop |
| Go-around | Recognize an unsuitable approach and execute the configured climb and configuration sequence | Decision timing, aircraft response, altitude loss and recovered climb |
| Test maneuver and recovery | Establish the reference, apply the card, observe the response, recover and re-stabilize | Actual versus commanded inputs, active loops, aerodynamic response, intervention and recovery records |

Taxi routes should initially come from the active installed airport scenery,
with explicit validated routes where a usable network is absent. Account for
aircraft dimensions and runway boundaries. Keep traffic and clearance conditions
explicit in the scenario. X-Plane's [airport data specification](https://developer.x-plane.com/article/airport-data-apt-dat-12-00-file-format-specification/)
defines runway and taxi-network records.

## Deliberate stall and airframe test mode

Normal-flight prevention and deliberate test behavior need separate profiles.
A stall card must explicitly permit its intended low-speed excursion while
retaining aircraft/configuration-specific altitude, attitude, load, duration,
and recovery limits. A generic cruise speed floor cannot govern the test phase.

Demonstrate recovery from controlled starting conditions before autonomous
stall entry. Detect the maneuver using a defined combination of aerodynamic
and motion evidence, with channel validity checks; low airspeed alone does not
prove a stall. Score recovery by measured aircraft behavior, altitude loss,
time, and return to a stable condition. Spins are a separate future capability
and are not implied by stall recovery.

For each card, classify the result as controller tracking, aircraft performance,
or aircraft response. Record which control loops, trim actions, and protections
are active. For response tests, explicitly hold or disable the loops that would
mask the measured axis, with bounded exposure and a recovery transition.
Report simulator control displacement and available cues; do not invent stick
force or buffet measurements.

If ArduPlane is used, its stall-prevention behavior must be part of this design:
it can constrain bank and raise speed demands. Changes belong to a scoped test
profile with verified restoration. See [ArduPlane stall prevention](https://en.ardupilot.org/plane/docs/stall-prevention.html).

## Milestones and acceptance

All milestones are pending. The repetition counts below are proposed engineering
gates, not aircraft certification criteria. Freeze scenario-specific numerical
tolerances and disturbances before scoring; retain all attempts and record any
revision to those criteria.

| Milestone | Deliverable | Exit evidence |
| --- | --- | --- |
| 0 — Baseline and harness | Known aircraft/configuration, deterministic scenario setup where supported, reset/readiness checks, trace recorder and independent scorer | Repeated setup produces conditions within declared tolerances; replay gives the same score; incomplete data produces an explicit invalid result |
| 1 — Control boundary | One writer, complete control frames, coherent observations, verified actuator mapping and takeover | Recorded SDK tests and fault injection cover stale frames, duplicate sequences, partial data, process loss, pause, and human takeover |
| 2 — First flight cycle | Stock C172 establishes reference, turns or climbs, recovers, reports | Ten consecutive completed baseline cycles plus ten predeclared disturbed-entry trials within their criteria; no unrecorded reset or intervention |
| 3 — Recovery and go-around | Recovery primitives and bounded missed-approach behavior | A matrix of entry states demonstrates recovery; impossible or invalid entries terminate with truthful outcomes |
| 4 — Ground and runway skills | Taxi/stop and approach/landing exercised separately; takeoff connected after airborne control works | Ten repeated trials per baseline skill, then declared wind/configuration variations; runway and stop criteria measured |
| 5 — Complete sortie | Park, taxi, take off, fly route, approach, land, return to parking | Ten complete baseline sorties without intervention; explicit tests of rejected takeoff, unstable approach and go-around |
| 6 — Flight-test cards | Slow flight, controlled inputs, stalls and recoveries | Repeatable entry conditions, measured maneuver and recovery, declared active loops, complete data reduction |
| 7 — C182 qualification and expansion | C182 profile, engine/prop/configuration handling, additional winds, loading and airports | Repeated qualified scenarios on the C182 with separate controller and aircraft-fidelity findings |

Milestone 3 begins with airborne recovery and develops go-around as approach
control becomes available. Ground taxi work can be developed independently of
airborne maneuvers, but complete sorties require both. Test cards beyond the
first flight cycle may proceed once their specific controller, profile, and
recovery dependencies have passed.

Early simulator tests are attended. Unattended runs become available for the
specific demonstrated profiles, with automatic recording, recovery/stop behavior,
and a usable human takeover path. Broader scenario expansion requires new
evidence; the initial qualification does not imply arbitrary-airport autonomy.

## Experiment and reporting contract

Each run records code and aircraft hashes, simulator/plugin versions, weather,
weight/CG, configuration, controller gains, profile and test-card versions,
initial conditions, and reset method. Record commands and actual responses,
trim, actuator ownership, mode changes, telemetry age, timing, intervention,
faults, and recovery. Store large simulator assets and raw traces outside Git;
commit reproducible scenarios, analysis code, and compact result summaries.

Report completed, failed, invalid-data, aborted, and fault-paused outcomes
separately. An acknowledged command, reached mission item, or successful process
exit is insufficient to establish a flight result. Include all attempts in the
summary and report error distributions as well as pass counts.

Keep tuning trials separate from acceptance trials. Freeze a tune before the
acceptance set and vary declared winds, loading, initial errors, latency, and
frame rates. Fault-injection trials have their own expected outcomes; a correct
fault response does not count as a successfully flown maneuver.

## Controller selection and deferred features

Compare the direct controller with ArduPlane only after the harness can measure
level hold, heading capture, climb/descent, disturbance recovery, and control
release on the same aircraft and conditions. Compare response quality, tuning
effort, observability, and failure behavior. Choose one primary normal-flight
controller from that evidence.

ArduPlane includes automatic takeoff and landing but needs aircraft-specific
tuning. Its official X-Plane integration guide still describes X-Plane 10/11;
the installed X-Plane 12 integration needs direct verification. See
[flight modes](https://ardupilot.ardupilot.org/plane/docs/flight-modes.html) and
[SITL with X-Plane](https://ardupilot.org/dev/docs/sitl-with-xplane.html).

Defer routine multi-controller handoffs, voice/ATC integration, vision-only
piloting, learning-based control, and arbitrary-aircraft support until the
initial closed-loop flight cycle is repeatable. Cold-and-dark startup and
shutdown are later checklist skills; the first airborne cycle uses a known
running aircraft state.

## Development model recommendation

Begin with **GPT-6 Astra, High reasoning**, for the simulator boundary,
control architecture, experiment design, and the first measured flight cycle.
This is a project recommendation: these tasks combine uncertain dynamics,
timing, SDK behavior, and failure analysis.

Once interfaces and acceptance scenarios are stable, use **GPT-6.1 Sol, High**
for bounded implementation and routine debugging. Use **GPT-6 Luna** for focused
supporting work such as trace indexing, documentation maintenance, and small
well-specified changes with objective checks. Revisit the choice using actual
task outcomes and cost.

Official [OpenAI model guidance](https://developers.openai.com/api/docs/guides/model-selection)
positions Astra for ambiguous and demanding work, Sol for complex tasks with
time/cost considerations, and Luna for scoped tasks. The reasoning settings and
division of work above are engineering recommendations, not measured project
benchmarks. This is the choice of development assistant; the runtime AI pilot
model remains a later evaluation decision and is outside the fast control loop.

## First implementation assignment

1. Verify the current Gitea main revision and use an isolated worktree. Inventory
   the installed X-Plane/plugin versions, aircraft hashes, and available traces.
2. Reconcile the historical H0 result and current executable paths. Identify
   reusable code, obsolete entrypoints, and actual gaps without expanding the
   executive into another unflown framework.
3. Implement milestone 0 and the minimum milestone 1 boundary needed for the
   first cycle. Specify the command/telemetry contract and scenario metrics.
4. Replay existing traces and inject faults offline, then perform staged
   simulator qualification with explicit observed results. Migrate the intended
   path through the verified boundary rather than merely disabling existing
   qualification checks.
5. Implement and demonstrate milestone 2. Deliver code, repeatable scenario
   invocation, traces, independent scores, tuning provenance, and a concise
   account of any remaining failure. Stop the first implementation scope here
   before beginning full-sortie or stall automation.

Documenting this plan does not enable live control or establish that any
milestone has passed. Qualification records must be updated from actual trials.
