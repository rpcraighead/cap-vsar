# Overnight implementation prompt: unified flight modes

Paste the prompt below into the implementation agent. Run it from `/home/ron/Projects/cap-vsar`. This is an unattended **offline implementation** assignment. It does not authorize an unattended live simulator flight.

---

Implement the CAP V-SAR flight-mode architecture in this repository. Work through the milestones sequentially, implement code, and run the relevant tests. Do not stop after a plan, a design document, or an empty framework.

The product goal is a scripted AI Mission Pilot that can take off, fly a sortie, and land, using ArduPlane and the simulated GFC 700 as appropriate. It also needs an AI Test Pilot that executes repeatable test cards under the same control-ownership system. Preserve this full-flight goal. The old airborne-only CONOPS is an incremental delivery scope, not the final requirement.

Your overnight deliverable is a working, tested offline implementation of the executive, control boundary, adapters, and task workflows, with explicit capability status and an attended qualification plan. An offline test does not qualify an aircraft or establish that autonomous takeoff/landing works in X-Plane. Keep unqualified live capabilities disabled. Do not substitute simulated success messages for actual observations.

## 1. Read these and establish the baseline

Read, in order:

1. Applicable `AGENTS.md`, `git status --short`, recent `git log`, and the top of `CHANGELOG.md`.
2. `docs/FLIGHT_MODE_ARCHITECTURE_REVIEW_2026-09-17.md`, including the **commit recheck**.
3. `docs/bugs/AI-24_ARDUPLANE_GUIDED_TUNING.md` and `docs/ARDUPLANE_TRIAL.md` as historical evidence. Their conclusions are not automatically correct.
4. `services/ai_pilot/maneuvers.py`, `maneuver_server.py`, `direct_backend.py`, `arduplane_backend.py`, `sitl_lifecycle.py`, `mavlink_min.py`, `xplane_udp.py`, and their tests.
5. `scripts/fly_arduplane_backend.py`, `scripts/fly_direct_backend.py`, `scripts/fly_card_h0.py`, `xplane/ardupilot/`, and `services/ai_pilot/flight_controller.py` / `c182t_checklists.py`.

This prompt was checked against commit **`212352c`**, “ArduPlane backend: built, tested offline, and flown. No capture yet.” If HEAD has advanced, inspect the relevant changes and adapt. Do not undo a newer correct fix or restart completed work.

Review baseline: the pytest-capable interpreter below ran `services/ai_pilot/tests` with 253 passed and 39 subtests passed. One failure and 11 setup errors were all sandbox socket-creation denials in isolated HTTP tests. Record these separately from application failures; do not claim they passed or modify production code to conceal an environment restriction. Run those tests if your environment permits isolated local sockets.

Confirmed corrections you must preserve:

- `GUIDED_P=5000`, `GUIDED_I=0`, `GUIDED_D=0` match upstream defaults at `~/.cache/capvsar/ardupilot/ArduPlane/Parameters.h:568`, pin `dbe7921` / Plane-4.7.1. Do not invent replacement gains to cure the observed circle. Their loaded values and aircraft suitability still require verification.
- The pinned heading handler sets the heading target/type when it accepts the command. The enum sent by this adapter is correct. Neither an ACK nor a circular flight path proves which internal controller branch actually flew.
- Offline replay of `arduplane_backend_20260917-230653.jsonl` through `ManeuverGate` produces an altitude-envelope fault at 2,973.95 ft, no achieved event, and a pause request. Its final `flight complete` label is a launcher defect. `backend.last_fault == None` is not evidence that the gate did not fault. The entry VVI was already −3,706.5 FPM.
- SITL starts writing before gate acquisition. Startup is not a read-only preparation step with the stock mapping.
- `detach()` always engages the GFC 700. That is wrong for human takeover, fault pause, and ground phases. It also incorrectly treats `sitl=None` as proof that no external process is writing.
- `fly_card_h0.py` bypasses `ManeuverGate` and the shared controller lock. `fly_direct_backend.py` uses a gate but omits the shared lock.
- `sim/cockpit2/autopilot/servos_on` is read-only in the installed DataRefs file. Commands need observed completion. The AP button toggles; never blindly repeat it.
- The pinned XPlane model hardcodes 49001 input / 49000 output and does not override the base class's empty `set_interface_ports()`. The launcher's `--sim-port-in` does not reconfigure this model. Successful existing rig setup is Data Output destination 49001, X-Plane legacy send-from port 49501. Do not alter the rig.
- Defaults files do not reliably override parameters already persisted in `eeprom.bin`. A source file's values are not a runtime parameter readback.

## 2. Scope and working rules

You are assigned `services/ai_pilot/`, its tests, the three flight launchers above, `scripts/setup_ardupilot_sitl.sh`, `xplane/ardupilot/`, and new flight-control bridge files named `xplane/PI_capvsar_flight_control.py` and helper modules with the `capvsar_flight_control` prefix. You may update the AI pilot README, review/implementation/acceptance notes, and add one accurate changelog entry. For this architecture assignment, earlier AI-24 file-lane exclusions are superseded for these expressly named paths; this is not permission to widen mission limits indiscriminately.

Preserve other agents' work. Re-read a file's diff before editing it. Do not reset, clean, stash, force-checkout, commit all changes, or overwrite unrelated work. Leave your changes uncommitted for review and list exactly which files you changed. Do not modify the aircraft package, calibration experiment, donor assets, DF engine (`PI_capvsar_df.py`), radios, instruments, exercise service, planner, deployment, or shared board/tracker in this task.

Do not start, stop, reset, reposition, pause, unpause, or send commands to the user's X-Plane/SITL session. Do not install the new plugin or change simulator preferences. Test against injected clients and isolated fake endpoints. Do not bind the actual simulator/SITL ports for tests. No unrestricted `--model xplane` process: it can seize the live aircraft before your code acquires authority. If a live-only question cannot be answered offline, mark it `UNVERIFIED_LIVE` and continue independent implementation work.

Use one sequential implementation stream. No UI redesign, new cloud services, or LLM dependency in the control loop. Prefer existing stdlib conventions; use existing pytest for tests. A missing optional package is not permission to skip the gate tests.

Create `docs/FLIGHT_MODES_IMPLEMENTATION_STATUS.md` immediately, with the baseline, milestone checklist, decisions, verification commands, and outstanding live checks. Update it after each milestone so another session can resume. Track implemented behavior separately from live qualification.

## 3. Required design

Build one deterministic `FlightExecutive` above the controllers and an actual output-authority boundary below them.

Keep these dimensions explicit:

- Authority: HUMAN, AI_MISSION, AI_TEST, plus fault/recovery state.
- Task/phase: GROUND, TAKEOFF, CLIMB, TRANSIT, SEARCH, APPROACH, LAND, ROLLOUT, TEST, PAUSED_FAULT.
- Controller: HUMAN, GFC700, DIRECT, ARDUPLANE.
- Test substates: ESTABLISH, STABILIZE, EXCITE, MEASURE, RECOVER, ACCEPT/REJECT.
- Transfer states: REQUESTED, PREPARING, READY, COMMITTING, VERIFYING, ACTIVE, FAILED/CANCELED.

These dimensions need typed representations and a documented table of valid combinations, not one giant list of every combination. Inactive controllers may observe/prepare but cannot command native controls. Each actuator domain has exactly one owner: primary controls, trim, throttle, configuration, and ground controls. Validate each domain allocation; never let a script compete with ArduPlane's throttle/flap outputs.

Expose separate operations equivalent to:

```text
request_mode(role, phase, controller, profile)
submit_task(lease, sequence, typed_task)
transfer_control(destination, expected_generation)
cancel_task(lease, sequence)
human_takeover(reason)
fault_pause(reason)
status()
```

Use the existing command validation and lease sequencing where appropriate. Introduce a control generation/session at the final output boundary so revoked or delayed output cannot regain authority. `human_takeover` is latched and does not re-engage any AP. Resuming automation requires explicit fresh authority. Canceling a task must select an explicit hold/abort behavior rather than abandoning the aircraft. A fault pause must not turn into an automatic Garmin engagement during cleanup.

Retain strict heading/altitude text parsing and existing API compatibility where possible. Add structured task types for flight phases; do not expand unrestricted language interpretation overnight. Scripts and checklists submit typed actions through this system and wait for observed completion. The LLM never writes flight controls or supplies hidden beacon truth.

## 4. Milestone A — truthful results and lifecycle ownership

Implement this first, with regression tests:

1. Persist gate events with sequence IDs, task IDs, both simulation and monotonic/wall timestamps where available, and explicit outcomes: achieved, refused, canceled, faulted, timed out. Persist backend and gate faults separately. Empty `active` is not success. A timeout without capture is not achievement. Fix launcher terminal messages and exit status accordingly.
2. Put lifetime cleanup around the complete resource-acquisition sequence. Cover failure before/after process startup, MAVLink connection, telemetry readiness, mode preparation, gate acquisition, and task selection. Cleanup must continue essential teardown even if one teardown action fails, be idempotent, and report what was confirmed versus merely requested.
3. Separate cleanup targets: human, explicitly requested automatic transfer, fault-pause, and ground stop. Do not neutralize surfaces or impose 0.45 throttle as a generic automatic handoff. Do not report SITL stopped when an externally managed process is still alive. Refuse unsupported unmanaged live ownership rather than pretend it is fenced.
4. Treat missing fresh mode/servo/override readback as unknown. Never infer successful takeover from a packet-send return value. A heartbeat outage alone is not proof that SITL has stopped writing.
5. Add a stable-entry check separate from the operating envelope. A finite −3,700 FPM VVI must not pass ordinary controller-transfer readiness. Keep recovery-entry policy separate; expose testable, documented profile thresholds rather than silently changing mission limits.

## 5. Milestone B — shared executive and enforced output path

Integrate `maneuver_server`, the direct launcher, H0 runner, and ArduPlane launcher with the common executive. Route test-specific bank, speed, configuration, and excitation requests through a typed test-task interface. Do not merely acquire a lease once and then write around it. Enforce revocation during the entire card, including recovery. Preserve the existing backend algorithms unless a demonstrated ownership/lifecycle defect requires a change.

Use one shared process-ownership helper across supported entrypoints. The helper is a first barrier, not proof that raw SITL UDP is fenced. Prevent legacy full-flight/chat/web paths from regaining raw live authority. Add preflight rejection when the required control bridge is absent or unqualified.

**Expected bridge approach:** implement a separate XPPython3 flight-control plugin with a small pure-Python arbitration core that can be tested without X-Plane. Inspect the existing DF plugin read-only for the installed `xp` API conventions. Do not add flight control to the DF plugin.

Generate a dedicated ArduPlane mapping that sends its actuator demands to private candidate datarefs, not native X-Plane controls. Remove native override writes from that mapping. The bridge alone applies authorized candidates and native overrides, and commands/verifies the Garmin servo transition. This avoids relying on the ineffective SITL port flag or modifying the pinned ArduPilot source. Validate the entire mapping before starting a managed SITL: no native actuator, override, or command target may escape mediation.

Candidate namespaces/session identity must prevent writes from a retired SITL session being mistaken for a new owner. On revocation discard staged output. On engagement require fresh complete candidate data, correct identity, finite values, bounded skew, and readiness evidence. Stock independent DREF packets are not an atomic, sequenced control frame: explicitly account for that limitation; do not claim a raw packet contains a generation/sequence that it does not. Use a session-specific mapping/namespace and a separate bounded authority protocol. Never re-label queued old output with the latest authority generation.

Preparation must leave native controls untouched. When committing, exclude the old external writer, verify native AP state as appropriate, then admit the successor with continuity checks. Do not implement overlapping servo writers. If a verified transfer cannot be completed, enter the defined rollback/fault state and keep the capability unqualified.

The local bridge must independently fence output on executive loss and service an explicit human-takeover command without waiting for a slow MAVLink call or process kill. Validate bounded callbacks and command/state readback through a stateful fake `xp` implementation. Live SDK behavior remains an attended verification item. Keep new plugin deployment and live activation disabled overnight.

## 6. Milestone C — controller adapters and observable readiness

Give adapters explicit prepare, readiness, activate, deactivate, and observed-status behavior. Do not call their current `release()` as an undifferentiated transition primitive.

- **GFC 700:** mode selection uses supported commands/writable selectors, with actual lateral/vertical/servo readback and deadlines. Distinguish selected, armed, and active. FD-only is not AP engaged. Never write the read-only `servos_on` field. Guard toggle commands with fresh state, and verify the effect. Keep attitude/trim ownership separate from virtual-pilot power/configuration ownership.
- **DIRECT:** seed the first admitted output and slew limiter from the measured transfer state; preserve trim and power continuity. Test inputs need explicit baseline-relative versus absolute semantics. The tested axis's control-loop policy must be recorded. Human takeover and output fencing apply during every substate.
- **ARDUPLANE:** prepare while outputs are staged. Verify identity, pinned version, telemetry quality, attitude/rate conventions, effective parameters, and candidate output readiness. Add diagnostics for demanded/estimated attitude, actuator outputs, relevant speed/height state, and parameter readback using the pinned MAVLink definitions. ACKed, mode-observed, and aircraft-achieved are distinct events. Do not “fix” provisional gains without evidence. Use isolated per-run state for future trials; preserve existing `eeprom.bin` and logs.
- **Power/configuration:** implement typed, bounded procedure commands and readbacks. Under Garmin control the virtual pilot supplies the appropriate power/configuration actions. Under ArduPlane automatic throttle, scripts must not write throttle. Reject unqualified automatic-power profiles rather than silently claim full pilot capability.

Unknown SDK/dataref/parameter names must be verified against the installed references or pinned source. Record unresolved facts and keep dependent live capabilities disabled; continue the rest of the work.

## 7. Milestone D — full-flight scripting and Test Pilot

Implement deterministic task runners, not scripted sleeps that assume a phase succeeded.

**Mission sequence:** configuration/startup → runway ready → takeoff → climb → transit/search → approach → landing → rollout/stop. Each transition needs an observation predicate, timeout, and failure/abort branch. Reuse vetted checklist content from the legacy prototype, but not its raw-control route. No self-issued ATC clearance.

Extend the ArduPlane adapter with mission-based takeoff, waypoint flight, and landing, using the pinned MAVLink protocol. Implement and test the real upload/request/ACK transaction, mission progress, retry limits, and go-around/abort semantics. Use explicit frames and typed runway geometry. Home, estimator origin, runway elevation, indicated altitude, and AGL are separate fields. Do not use an airborne `set_home_here()` as an assumed runway elevation. The GUIDED command's rejection of altitude zero must not be copied to NAV_LAND.

Provide the planned ArduPlane-only full-flight path first, then planned stable-altitude Garmin transfers. GFC 700 simulated ILS tracking and ArduPlane runway navigation must be labeled accurately. A landing-controller handoff requires readiness before an explicit transfer floor; otherwise take the preplanned abort path. Do not invent a late-flare transfer to make a demo finish.

Implement phase profiles without weakening the existing cruise profile. Landing/takeoff may use lower speed/AGL only in their explicit phase and permitted runway corridor. Autonomous stall-test and unqualified recovery profiles remain disabled. Numeric aircraft limits must come from existing sourced configuration, not invented overnight.

**Test sequence:** establish → continuously stable reference → bounded excitation/measurement → measured recovery → accept/reject point. Separate airframe-performance, airframe-response, and controller-tracking tests. Record which loops are active, aircraft/configuration hash, weight/CG evidence, control baseline, commanded and actual deflection, sample timing, and interventions. Recovery timeout invalidates/stops according to the card policy; never continue as if recovered. Do not conflate the test's aircraft acceptance with successful software execution.

## 8. Milestone E — integration proof and handoff package

Run the service suite using the existing pytest-capable interpreter:

```bash
/home/ron/.cache/capvsar/capvsar-planner-venv/bin/python -m pytest services/ai_pilot/tests -q
```

Also run any new bridge tests outside that directory explicitly. If this interpreter moved, locate another existing interpreter with pytest or create an isolated test environment within the permitted workspace. Do not waive `test_maneuvers.py`: it contains pytest function tests that unittest discovery does not exercise. Capture the real exit status and counts; do not hide failures by piping output to `tail`.

Minimum behavioral acceptance cases:

1. Standby ArduPlane emits candidates continuously and causes **zero native actuation**.
2. Every supported entrypoint uses the shared ownership system; a second acquisition is refused without aircraft writes.
3. Old leases, old candidate sessions, duplicate sequences, delayed packets, and partial/stale candidate sets cannot regain or extend authority.
4. Human takeover during preparation, commit, active control, and test recovery restores the human path and never auto-engages another controller.
5. Cancellation, timeout, backend fault, gate fault, and achievement are distinguishable in API, traces, and process outcomes.
6. Inject startup and teardown failures at every resource boundary; no owned process or permitted writer survives unnoticed.
7. Garmin toggle/readback races and FD-only state do not result in a false claim of AP engagement.
8. Replay the final 2,974-ft observation from the failed trial: the result is an envelope fault, not capture. Test refusal of its diving entry condition for ordinary transfer.
9. Test a complete full-flight task sequence with an independently supplied observation stream and fake MAVLink endpoint, including mission upload retries, rejected takeoff, go-around, and touchdown/rollout confirmation. Clearly label this **workflow/protocol validation, not flight dynamics validation**.
10. Test H0 recovery timeout, revoked authority during excitation, and active-loop attribution. No direct test write can bypass the bridge.
11. Profile switching cannot turn arbitrary low-altitude or low-speed requests into accepted cruise maneuvers.
12. Loss of speech/model service preserves the configured deterministic task behavior; loss of executive authority triggers the independent bridge policy. Hidden scenario truth remains excluded.

Use a stateful simulator-interface fake with independently modeled AP toggles, mode delays, overrides, and actuator ownership. A list of expected function calls is insufficient to test these bugs. Inject faults before, during, and after transitions. Avoid broad unrelated test or styling work.

Finish with:

- `docs/FLIGHT_MODES_IMPLEMENTATION_STATUS.md`: implemented capabilities, test commands/results, remaining failures and live-only checks, exact changed files, and the next concrete step.
- `docs/FLIGHT_MODES_ACCEPTANCE.md`: bounded attended qualification sequence, beginning with bridge/no-authority checks, then stable ArduPlane flight, then runway-to-runway flight, then Garmin transfers. Include measurable outcomes without claiming any run occurred.
- An accurate dated changelog entry distinguishing new code, offline proof, and unverified live behavior. Correct current status summaries without erasing historical flight evidence.
- A short final report with completed milestones, real test results, unresolved blockers, and explicit live-qualification status.

Keep working through all feasible milestones. If one live-only fact blocks a capability, implement and test the remaining independent behavior and leave that capability explicitly disabled. Do not stop merely because the simulator is unavailable, and do not fill the gap with a successful mock-flight claim. Leave a concrete, reviewable implementation for the next attended session.

---
