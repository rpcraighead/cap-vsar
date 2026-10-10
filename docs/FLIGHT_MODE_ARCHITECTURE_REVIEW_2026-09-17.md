# Flight modes, pilot roles, and control transfer — architecture review

Review of the September 17 working tree, including the ArduPlane trace ending at 23:08 local time. Repository HEAD was `82fd3bc`; much of the ArduPlane implementation was uncommitted and under active development. Findings describe this snapshot. This is a proposed architecture, not an implementation or a flight acceptance result.

**Commit recheck: `212352c` (September 17, 23:19 local).** The ArduPlane implementation and its trial findings are now committed. The changelog acknowledges that Leg 3 flew without capture, and `docs/bugs/AI-24_ARDUPLANE_GUIDED_TUNING.md` supplies a continuation brief. The ownership, cleanup, H0 bypass, and misleading terminal-label findings below still apply. The following corrections supersede the earlier status wording and must be carried into implementation:

- **The proposed first tuning suspect is unsupported.** The pinned `ArduPlane/Parameters.h:568` initializes `guidedHeading` with P=5000, I=0, D=0, exactly matching the three values in `cap487.parm`. These are upstream defaults, although their suitability for CAP 487 and the values actually loaded remain unverified. The heading loop consumes radians and emits a bank demand in centidegrees; the size of 5000 is not evidence of a units mistake. Do not begin by replacing it with a guessed smaller gain.
- **A recorded circle does not establish that ArduPlane ignored its targets.** In the pinned `GCS_MAVLink_Plane.cpp`, an accepted HEADING command sets `target_heading_type` and the target. `ModeGuided::update()` then selects that heading branch unless another condition takes precedence or state changes. The adapter's heading enum matches the pinned MAVLink dialect. The demanded versus estimated attitude and actual output path must be observed before assigning the failure to default loiter or PID gains.
- **The new changelog's broad “no fault” / successful safety-chain claim is too strong.** Offline replay of all 34 recorded observations through the unchanged `ManeuverGate` yields zero `achieved` events and an altitude-envelope fault at the final 2,973.95-ft sample, with one pause request and revoked ownership. This is a replay result, not recovered proof that a live pause command was delivered. The trace's `fault: null` only records the backend fault field, not the gate's event. The incoming gate observation was already descending at 3,706.5 FPM, so an earlier stable GFC handoff does not establish stable ArduPlane entry.
- **Cleanup is still incomplete.** The new commit still has early SITL/MAVLink failure returns before full cleanup, and `--no-sitl` can clear overrides without stopping the external writer. Moving gate acquisition into `try/finally` fixed that specific exception path, not every startup path.
- **Port flags need a source-based correction.** In the pinned source, `SIM_XPlane.h` fixes its input/output ports at 49001/49000 and the XPlane class does not override `Aircraft::set_interface_ports()`, whose implementation is empty. Consequently the launcher's `--sim-port-in` does not change these XPlane-model ports at this pin. Do not design the mediation bridge around that flag. The observed successful networking configuration remains Data Output destination 49001 and X-Plane's legacy send-from port 49501.
- **The complete Python suite can use pytest.** `/home/ron/.cache/capvsar/capvsar-planner-venv/bin/python` has pytest 9.1.1. `unittest discover` does not run the pytest function tests in `test_maneuvers.py`; treating its import failure as an acceptable gate is inadequate when changing ownership code. Use the pytest-capable interpreter and report the actual collection/results.

These changes strengthen the recommendation to implement ownership, observation, and phase contracts before further flight tuning. They do not change the target of scripted full flight using both ArduPlane and the GFC 700. An unattended implementation prompt is provided in [FLIGHT_MODES_OVERNIGHT_PROMPT.md](bugs/FLIGHT_MODES_OVERNIGHT_PROMPT.md).

**Recheck test baseline:** running that interpreter with `-m pytest services/ai_pilot/tests -q` produced 253 passed and 39 subtests passed, with one failure and 11 setup errors. All 12 unsuccessful cases failed at socket creation with sandbox `PermissionError: Operation not permitted` while constructing isolated HTTP test servers. This is not a fully passing suite; those HTTP cases still require an environment that permits local test sockets. No live simulator commands were issued.

**Target confirmed by Ron during this review:** use scripting, the simulated GFC 700, and ArduPilot together. ArduPilot must ultimately take off, fly, and land the simulated aircraft. The older AI Mission Pilot CONOPS's airborne-only initial release is a delivery milestone, not the final scope.

**Assessment:** retain all three capabilities, but give them one deterministic flight executive and one enforceable control-ownership boundary. Mission Pilot and Test Pilot are roles that request work. GFC 700, ArduPlane, and the direct controller are execution mechanisms. A script sequences the work and checks its completion. Treating these as interchangeable `select(heading, altitude)` implementations hides the most important differences: authority, power management, flight phase, preparation, recovery, and handoff.

**What the evidence establishes**

The changelog records successful heading/altitude captures with the GFC 700 and direct controller, and useful H0 measurements. The pinned ArduPilot source was inspected at `dbe7921` (Plane-4.7.1). Those are useful foundations. They do not establish that the three controllers can yet be transferred between reliably.

The following local traces informed the original review; the commit recheck above records the subsequent changelog update:

| Local trace | Observed result |
| --- | --- |
| `arduplane_backend_20260917-224807.jsonl` | Preflight already had override=1, mode RTL, bank −80.5°, descent −4,370 FPM. Only a header was recorded. |
| `arduplane_backend_20260917-225759.jsonl` | LOITER was reported, but preflight bank was −73.5° and descent −5,033 FPM. Gate acquisition refused; detach recorded override=0. |
| `arduplane_backend_20260917-230653.jsonl` | Entered GUIDED targeting heading 300°/4,500 ft. The first sample was already descending at −3,837 FPM. Over roughly 66 seconds, altitude fell from 4,609 to 2,974 ft; sampled bank remained between −30.0° and −22.5°. No capture was demonstrated. The final sample says `captured / idle`, and the end says `flight complete`. |

Traces are under `~/.cache/capvsar/flight-tests/`. The last run is an unsuccessful live control attempt, not an unflown adapter and not a passed flight. In the launcher, a missing active command is labeled `captured / idle` even when the gate has faulted; a break for lost ownership then falls through to `reason = "flight complete"`. The gate's event stream is not persisted in these samples. These labels can conceal exactly the distinction the CONOPS requires: accepted, achieved, aborted, and faulted.

**The immediate problems are structural**

1. **SITL has authority before approval.** `fly_arduplane_backend.py` starts SITL before constructing the gate. It waits for MAVLink and telemetry, then secures the mode, then acquires the lease. The pinned `SIM_XPlane.cpp` writes the mapped outputs and overrides when it receives simulation data. The supervisor's lease therefore does not control the actuator writer. A longer preparation delay can produce a longer uncontrolled attach interval. Disarming or choosing a different flight mode is not an output disconnect.

2. **Cleanup conflates three different operations.** `detach()` always parks on the GFC 700 after releasing ArduPlane, stopping SITL, and clearing overrides. That is unsuitable for “I have control,” a fault pause, ground operations, and landing rollout. ArduPlane's `_hand_back()` selects FBWA or LOITER; neither means that native X-Plane manual control has been restored. FBWA still uses ArduPlane, and LOITER is still automatic flight. A pilot takeover must not finish by re-engaging another autopilot.

3. **Some ownership claims are stronger than the code.** `fly_card_h0.py` imports `Limits`, constructs the direct backend, and calls `backend.select()` and `apply_test_input()` directly. It does not use `ManeuverGate` or the controller lock, despite the H0 changelog's statement that the run used the gate. `fly_direct_backend.py` uses its own gate but does not take the shared file lock. Separate gates cannot establish global exclusivity. The direct backend also lacks the ArduPlane adapter's physical-yoke takeover detector. These are architectural gaps, not just documentation mistakes.

4. **A refusal does not yet mean zero effects.** Moving `gate.acquire()` into `try/finally` fixed one orphan path. Earlier startup failures still stop SITL without the complete override-cleanup path, and initialization before that `try` can still fail. `--no-sitl` is especially problematic: `detach(..., sitl=None)` treats SITL as stopped and clears overrides while an external SITL may still reassert them. A heartbeat loss likewise does not prove the actuator-writing process has died.

5. **Controller engagement is not a verified transaction.** `park_on_gfc700()` sends commands from a previously sampled state and does not confirm resulting servos or lateral/vertical modes. Its write to `sim/cockpit2/autopilot/servos_on` is ineffective: the installed DataRefs file marks that field read-only. The command can still engage AP, but the preceding write proves nothing. The direct backend begins its first output without initializing the slew limiter from actual control positions, and release imposes neutral surfaces and 0.45 throttle. Those are discontinuities rather than a transfer of the trimmed aircraft state.

6. **The gate is an exercise-envelope check, not an entry-stability check.** It accepts finite VVI without bounding it. The latest trial could acquire while descending thousands of feet per minute because speed, bank, altitude, and AGL were momentarily inside their limits. Add a distinct stable-entry requirement for controller qualification and ordinary transfers. Recovery from an upset is a separate capability with different conditions.

7. **The current instrumentation cannot identify the ArduPlane control failure.** Altitude agreement and an accepted MAVLink command do not validate attitude estimates, body-rate signs, servo directions, trim, effective parameters, or energy control. The trace lacks demanded versus estimated attitude and actual servo outputs. The SITL log reports about 10 Hz input data; the official X-Plane setup guide calls for 50 Hz. That mismatch merits measurement, but does not alone explain the failure.

Two causal explanations in the working notes need restraint. A 60 m circle at 110 knots is physically inappropriate, but the pinned `Plane::calc_nav_roll()` clamps demanded bank to the configured roll limit; GUIDED heading also clamps it. The radius calculation alone therefore does not explain an actual 80° bank with an intended 25° limit. Likewise, the initial Canberra `Home:` log and RTL heartbeat warrant investigation, but are not a complete reconstruction of the estimator/home state at the departure. Read back actual parameters, compare both attitude solutions, and measure output-to-response signs before calling this tuning.

The persistent `eeprom.bin` matters: the pinned parameter loader applies defaults to parameters that are not already configured in storage. Editing `cap487.parm` is not proof that the running values changed. Use a dedicated, versioned parameter state and save an effective-parameter readback for every qualification run.

**One system, several visible flight modes**

Keep authority, flight task, controller, and operating profile separate internally. Present sensible combinations to the user as system modes:

| System mode | What scripting does | Flight-control allocation | Required exit or interruption |
| --- | --- | --- | --- |
| MANUAL | Observe, run requested checklist assistance, record | Human native controls | Explicit automation engagement; human priority remains available |
| PILOT AP | Observe cockpit selections; assist if asked | Human commands GFC 700; human owns power/configuration | AP disconnect returns to human |
| AI GROUND | Engine/checklist/configuration sequence and ground-phase checks | Deterministic ground controller for steering/brakes/throttle, or human until qualified | At runway ready: aircraft configured, aligned, and authorized for takeoff |
| AI TAKEOFF | Verify runway plan, clearance, configuration, and abort branch | ArduPlane takeoff guidance and control; explicit configuration/brake ownership | Measured climb-out established; rejected takeoff or go-around branch where applicable |
| AI TRANSIT | Approved route, altitude/speed schedule, checklists, radio tasks | GFC 700 with virtual-pilot power management, or ArduPlane | Arrival, retask, or transfer at a qualified condition |
| AI SEARCH | MO-directed vectors or an MO-approved search pattern | Qualified GFC 700 or ArduPlane execution | Pattern canceled, amended, or completed; no automatic beacon solution |
| AI APPROACH | Brief/configure approach, select navigation source, monitor stabilization | GFC 700 for actual simulated LOC/GS coupling; ArduPlane for its autonomous runway approach | Planned landing-controller transfer or go-around |
| AI LAND | Select runway landing sequence, manage configuration and abort logic | ArduPlane through final, flare, and touchdown; explicitly allocated ground steering/braking for rollout | On-ground plus controlled rollout and stop/ground-mode transition |
| TEST | Execute a versioned card: establish, excite/measure, recover, repeat | Direct test controller or the particular autopilot being evaluated | Recovery hold, human takeover, or fault pause; never implicit mission resume |
| PAUSED FAULT | Record fault and inhibit new actuation authority | Simulator confirmed paused; ownership recorded and reconciled before resume | Explicit recovery and fresh authority |

“GFC 700 mode” does not supply every pilot duty. The existing adapter explicitly leaves power to a human. For an AI Mission Pilot, scripts need a deterministic virtual-pilot power/configuration service. Allocate controls explicitly: GFC 700 owns its validated servo/trim channels; the virtual pilot owns power and the remaining assigned channels. With ArduPlane automatic throttle active, that same throttle channel belongs to ArduPlane. Flaps also need one owner; the current SITL mapping writes them continuously.

The language model interprets crew requests and produces proposals. Deterministic scripts implement procedures through the flight executive. They do not create a second route to raw control writes. Salvage checklist content and phase sequencing from the legacy full-flight prototype, but migrate its actions to typed requests rather than re-enabling its direct X-Plane control path.

Coaching/practice/evaluation are assistance settings, independent of flight mode. The AI MP receives trainee-visible briefing and aircraft state, not target truth. ATC clearance is an input from the configured authority, not something a takeoff script invents.

**ArduPlane's place in the full-flight design**

ArduPlane supports automatic runway takeoff and mission-based landing, including final approach, flare, touchdown, and abort behavior. The present adapter exposes GUIDED heading and altitude only. It lacks mission upload/execution tracking, takeoff/landing commands, and the corresponding phase contracts. “ArduPlane cannot do it” is the wrong conclusion; “our adapter does not yet expose or qualify it” is the correct one. See the official [takeoff](https://ardupilot.org/plane/docs/automatic-takeoff.html) and [landing](https://ardupilot.org/plane/docs/automatic-landing.html) documentation.

Prove one ArduPlane-controlled runway-to-runway sortie first, with scripts handling the aircraft-specific checklist and configuration work. Then insert GFC 700 cruise/search segments through qualified transfers. This avoids introducing a new controller transition during every phase of the first successful flight.

For an avionics lesson, let the GFC 700 fly the actual simulated ILS. An ArduPlane GPS runway approach is a different navigation method. For an autonomous landing following a GFC 700 approach, prepare ArduPlane well in advance and transfer at an explicitly qualified stable condition above a defined transfer floor. Do not make a last-second flare handoff the first integration target. If readiness is not established by that point, execute the planned go-around or human transfer. Automatic runway navigation must not be announced as an ILS capture.

Home, estimator origin, runway elevation, indicated altitude, and AGL require explicit separate meanings. `secure_on_attach()` currently sets Home to the airborne aircraft's location. That may assist an airborne experiment but is unsuitable as an unquestioned reference for a runway landing plan. Establish and verify the runway/home altitude convention, use explicit coordinate frames in mission items, and provide a qualified height-above-ground input for flare logic. Do not extrapolate the current zero-altitude rejection for GUIDED commands to landing mission items.

Replace the single cruise envelope with phase profiles: ground, takeoff, climb, search, approach, landing, rollout, and test. Each profile specifies permitted commands, current-state limits, stable-entry conditions, trajectory constraints, and abort response. Lower airspeed and AGL during landing become expected only within a verified landing corridor and landing phase. A change of mode must not be a blanket waiver of protection.

**Make handoff a system transaction**

Introduce a persistent flight executive and a local simulator-side control bridge. All supported external writers pass through this boundary. Native GFC 700 actuation is managed through verified servo state; external candidate output is admitted only for the current owner and authority generation. A process lock remains useful, but it cannot exclude raw SITL UDP writes or another process that ignores the lock.

The bridge needs separate observation and actuation paths. ArduPlane can initialize against current telemetry while its actuator outputs and override requests are blocked. This allows version detection, estimator convergence, parameter checks, and mode preparation without seizing the aircraft. A UDP mediation layer or an X-Plane plugin can implement the boundary, but it must mediate the actual SITL output path; wrapping only MAVLink commands will not do it. Standby readiness must include sensible candidate outputs and controlled integrator state, not merely a heartbeat.

Normal automatic transfer follows:

`REQUESTED → PREPARING → READY → COMMITTING → VERIFYING → ACTIVE`

1. Validate the requested owner, operating phase, and destination capability. Stop accepting incompatible new task requests.
2. Keep the incumbent flying while preparing the successor with fresh attitude/rates, airspeed, altitude references, control/trim/power state, configuration, targets, and route position.
3. Check stable entry, estimator health, effective parameters, and candidate control continuity. A preparation failure leaves the incumbent in command.
4. At the local control boundary, revoke the incumbent's actuator generation and admit the successor. Coordinate native AP disengagement/engagement with this barrier. Reject stale packets from the old generation. Overlap preparation, but never competing output authority.
5. Verify controller state, override state, control continuity, and bounded aircraft response. Announce completion only after readback and behavior agree.
6. If transfer verification fails, use a tested rollback to a still-ready incumbent or enter PAUSED FAULT. Do not blindly start an arbitrary fallback controller on an upset aircraft.

The existing direct SITL connection cannot support this preparation safely because starting it grants control. Until the bridge exists, use setup transitions with the simulator frozen and outputs isolated; the trial has already found that paused X-Plane does not supply the required DATA stream, so “start it while paused” alone is not a complete solution. A later warm-standby implementation must explicitly solve that telemetry/actuation separation.

Separate API operations express intent:

- `transfer_control(destination, target_state)` selects a new automatic owner.
- `human_takeover()` revokes all AI authority, restores the native human input path, and stays latched in MANUAL until an explicit new grant. It does not engage the GFC 700 or require waiting for SITL process termination once outputs can be fenced.
- `abort_task()` ends a mission/test while retaining a specified hold, approach abort, or ground-stop action.
- `fault_pause(reason)` freezes the simulation through an independent local watchdog and records confirmation. Resume requires a selected owner and fresh authorization.

Cancellation of an MO instruction is therefore different from disconnecting the pilot. Likewise, a lost language-model connection can leave the last approved deterministic task running under the configured policy; loss of actuator supervision calls for the fault response. Handoff completion is not the same as reaching the eventual heading or altitude target.

**Test Pilot needs its own task contract**

Use a deterministic card runner with `ESTABLISH → STABILIZE → EXCITE/MEASURE → RECOVER → ACCEPT/REJECT`. The runner uses the same executive and ownership boundary as the Mission Pilot, with a separately authorized test profile. It owns the test sequence, not an unrestricted bypass to the aircraft.

Distinguish three test objectives: airframe performance, airframe response to a known excitation, and controller/avionics tracking. For an airframe response test, preserve the trimmed baseline and specify exactly which axis loops, throttle law, coordination, and trim are held or active. Log demand and actual deflection together. For an autopilot test, leave that autopilot active and evaluate its tracking explicitly.

The current H0 pitch input replaces the elevator demand with an absolute shaped value; it is not simply a delta added to the prior trimmed demand. During that interval, the normal elevator loop output is overwritten, while proportional throttle response and other-axis control remain. Recovery then reintroduces the hold loops. This makes the changelog's attribution of small-input pitch asymmetry to altitude hold a hypothesis, not a demonstrated cause. The response and the recovery cannot be treated as an uncontaminated airframe measurement.

Stall tests cannot fit a mission profile with a 90-knot floor. Eventually, an explicitly approved stall-test profile can define entry conditions, bounded excitation, termination, and recovery while retaining the shared ownership and watchdog protections. Until that capability is qualified, a human can fly the point while the test runner records it. Routine MO commands cannot select the stall-test profile.

**Implementation order and proof of completion**

1. **Establish truthful evidence and ownership.** Persist gate events and actual termination reasons; reconcile the latest failed flights with the changelog. Close the H0/direct-launcher bypasses. Separate takeover, abort, transfer, and fault cleanup. Make exceptions at every startup stage leave a defined simulator state. Stop claiming restored control from commands sent alone.
2. **Build the flight executive and output boundary.** Demonstrate that a standby SITL produces no aircraft writes, a second writer is excluded, old-generation packets cannot act, and human takeover works when the command service or SITL is hung. Exercise failures at every transition stage with a stateful simulator-interface harness, not just a fake client's call list.
3. **Qualify basic ArduPlane control.** Use a reproducible aircraft/configuration and saved effective parameters. Verify sensor frames, control directions, trim, timing, and actual aircraft response. Record estimated/demanded attitude, servo outputs, speed/height energy-control state, and X-Plane truth. Demonstrate stable straight flight, heading capture, climb/descent, and ordinary abort behavior before interpreting landing performance. The minimal MAVLink codec will need additional diagnostics and mission support; using an isolated standard MAVLink toolchain is also a reasonable option.
4. **Prove full flight with ArduPlane.** Add mission upload/acknowledgement, phase readback, runway geometry, ground steering/brake integration, takeoff configuration, landing configuration, go-around, and stop detection. Begin in known conditions and expand to changed loading/winds only after resolving failures. Record touchdown/rollout evidence; a reached waypoint is not a completed landing.
5. **Qualify GFC 700 transfers and virtual-pilot power control.** Validate ArduPlane-to-GFC and GFC-to-ArduPlane at stable altitude before approach transfers. Read actual AP/FD/lateral/vertical armed and active modes. A GFC 700 mode switch inside AI TRANSIT is normally a guidance change, not a transfer of the whole pilot role.
6. **Connect mission and test use cases.** Prove MO retasking, route cancel/resume, approved pattern tracking, loss of dialogue services, and human priority. Qualify each test profile separately. Pin each result to aircraft and controller versions; aircraft calibration changes trigger the relevant controller rechecks, while aircraft-fidelity work remains separately scheduled from SAREX development.

The UI should always show who has authority, which controller is actually engaged, lateral/vertical/power modes, task/phase, and any pending transfer or fault. Example: `AI MISSION | GFC 700 HDG + ALT | POWER: AI PILOT | SEARCH VECTOR | TRANSFER: NONE`. An ArduPlane-controlled aircraft should not imply that the Garmin AP is flying it merely because the PFD remains visible.

**Verification and sources**

This review made no live simulator commands and changed no controller code. The ArduPlane adapter, MAVLink codec, and SITL lifecycle suites were rerun: **77 tests passed**, with a ResourceWarning for an unclosed `/dev/null` handle in the test run. These are offline tests; their passing result does not validate flight or transfer behavior.

Primary project evidence: [changelog](../CHANGELOG.md), [trial record](ARDUPLANE_TRIAL.md), [AI Mission Pilot CONOPS](CAP_V-SAR_AI_Mission_Pilot_CONOPS.pdf), [maneuver gate](../services/ai_pilot/maneuvers.py), [SITL lifecycle](../services/ai_pilot/sitl_lifecycle.py), [ArduPlane launcher](../scripts/fly_arduplane_backend.py), [ArduPlane adapter](../services/ai_pilot/arduplane_backend.py), [direct controller](../services/ai_pilot/direct_backend.py), [H0 runner](../scripts/fly_card_h0.py), and [legacy full-flight sequence](../services/ai_pilot/flight_controller.py).

Additional primary references: [ArduPlane flight-mode responsibilities](https://ardupilot.org/plane/docs/flight-modes.html), [X-Plane SITL setup and control-direction checks](https://ardupilot.org/dev/docs/sitl-with-xplane.html), [Laminar autopilot command/state semantics](https://developer.x-plane.com/article/accessing-the-x-plane-autopilot-from-datarefs/), and [Laminar flight-director versus servo state](https://developer.x-plane.com/article/flight-director-and-autothrottle-datarefs/). Pinned local source inspected: `libraries/SITL/SIM_XPlane.cpp`, `ArduPlane/mode_guided.cpp`, `ArduPlane/Attitude.cpp`, and `libraries/AP_Param/AP_Param.cpp` under `~/.cache/capvsar/ardupilot`. Installed `Resources/plugins/DataRefs.txt` identifies `servos_on` as read-only.
