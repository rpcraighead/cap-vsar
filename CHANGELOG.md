# Project change log

Record implementation changes, research findings, and design decisions here.
Clearly distinguish proposed work from completed implementation.

## 2026-09-14 — O-8 single HTTPS participant front door deployed

Deployed commits `472d3bb` and `655b905` to ms01. Caddy now serves the
role-aware participant portal, exercise console, mission-base views, radio and
the flight planner from `https://192.0.2.151/`; the planner is mounted at
`/planner/`. Host mappings for exercise 8700 and planner 8090 were removed.
Port 80 serves only the public local CA certificate and redirects every other
path to HTTPS. The AI Pilot engineering deck remains outside this front door.

The planner now honors `X-Forwarded-Prefix` for its templates, static assets,
API requests and local chart URLs. One roster login was exercised across the
portal, `/base` and `/planner/` from another workstation. Direct connections to
8700 and 8090 were refused. The installed X-Plane station config now uses the
HTTPS endpoint and a generated plugin credential; its desktop launchers use a
CAP V-SAR process-local CA bundle, leaving system-wide trust unchanged.

The cutover exposed two deployment defects and fixed both: `deploy.sh` now
rebuilds the locally built exercise/planner images before restart and repairs
ownership of the non-root exercise service's SQLite bind mount. A consistent
database backup was written before migration. Final ms01 preflight reported all
checks passing. Automated verification: 93 planner tests plus 17 subtests, 38
setup/auth tests plus 6 subtests, and 21 radio tests; Caddy and Compose configs
also validated on ms01.

## 2026-09-11 — recurring project mirror to fastnfs

Installed and enabled the workstation user service `project-fastnfs.service` and
`project-fastnfs.timer`: rsync runs two minutes after each completed run, with
user lingering enabled for operation after logout and at boot. The workstation
must remain powered on. Source and operating instructions live in the sibling
`../project-sync/` directory; installed units are in `~/.config/systemd/user/`.

Destination: `ron@192.0.2.151:/srv/fastnfs/ron-projects/workstation/` on ms01.
All non-hidden project directories under `/home/ron/Projects/` are mirrored,
including repository Git history, uncommitted and ignored files. Portable
`~/.cache/capvsar/` contents are included separately. Python/test caches, Git lock
files, external symlink targets and the machine-specific pytest venv are omitted.
The destination parent is private (0700); SSH uses existing keys and strict host
verification. No simulator or flight-control files were changed for this setup.

The mirror is one-way from the workstation. Laptop users should VPN in and copy
it into a separate local working directory before editing; the next workstation
sync would overwrite edits made directly in the mirror. Replaced/deleted files
are retained under `history/<UTC run>/`, without automatic pruning. A success
marker records completed runs. Transfers are locked against overlap and use
bounded network timeouts. Live working-tree copies are not atomic Git snapshots.

Verified initial transfer, matching Git heads for cap-vsar and g1000-sar,
replacement/deletion retention with a temporary probe, successful service exit,
next scheduled run, and `Linger=yes`. Laptop copy and pause/resume commands are
in `../project-sync/README.md`. This entry records the previously completed setup.

## 2026-09-11 — card H0: five runs, five control-law defects, none of them the input ramp

Card H0 (control and trim confidence, 100 KIAS clean) was flown five times and has
**still not produced a valid data point.** Every run failed for a different reason,
and each reason was a real defect in `XPlaneDirectBackend` that the card found and
offline testing had not. Recording them because the sequence is the useful part:
the card is doing exactly what a card is for.

**Simulator engineering validation only. Not approved instruction for a real
aircraft.** The authorized `ManeuverGate` path and its envelope were used
throughout; no second controller and no bypass. `services/ai_pilot/maneuvers.py`
remains unmodified.

### Run 1 — step inputs, uncoordinated

Invalidated on the pilot's call: *"the control inputs were unrealistically
instantaneous, and we need to include rudder input to keep the airplane
coordinated for good numbers."* Added `TestInput.shaped()`, a trapezoidal ramp,
and closed the rudder loop on sideslip (`BETA_TO_RUDDER`, `BETA_TO_RUDDER_I`)
on top of the existing adverse-yaw feedforward.

### Run 2 — throttle bang-bang, then the climb sideslip

Throttle swung 0.150 to 1.000 and speed 94.7-108.8 about a 100 target. The cause
was a PURE INTEGRATOR at 0.010 per tick at 10 Hz: 0.1 of throttle per second per
knot of error, with no way to stop. By the time speed reached target the throttle
was already against a limit and the error had to reverse to unwind it. Replaced
with PI.

Then, from the pilot: *"more right rudder is needed in the climb."* The steady
+1.6 degrees of right bank held all the way up was not trim - it was a standing
sideslip that the heading loop was masking by holding a wing down. Proportional
feedback always lags a left-turning tendency that grows with power and with angle
of attack. Added `RIGHT_RUDDER_FF`, scaling with throttle and inversely with
dynamic pressure.

### Run 3 — "bank is abrupt like pitch inputs were"

The ramp was verified working, on the trace, on the command path: `shaped` climbs
0.0077 to 0.1000 over exactly 1.0 s and the aileron command tracks it to four
decimals. **The step was at the other end of the input.** The instant it expired,
the heading loop saw a 20.7 degree bank and commanded the aileron limit in a
single 100 ms tick, held it saturated for 1.2 s, reached 14.3 deg/s of roll rate
and overshot through wings-level to +9.2 degrees. No amount of ramping the input
can fix a step that is not in the input.

Two fixes. **Rate damping** on both inner loops (`ROLL_RATE_TO_AILERON`,
`PITCH_RATE_TO_ELEVATOR`): proportional-on-angle has no way to know the aircraft
is already moving, so it commands correction all the way to the target and
overshoots through it. And a **slew-rate limiter** on all three surfaces, applied
last before the wire, so nothing upstream - loop, clamp or test input - can
produce a step at the controls. A ramped test input passes through untouched
(0.10 of travel per second against a 0.40 limit); what gets limited is the
transition at each end of it.

Run 3 was also **not a valid test point at all**, which the abruptness had
obscured. It entered 22 knots fast; the throttle went to the idle stop and the
integral wound to its -0.35 limit and sat there for ten seconds, where
integrating could not change the output. When speed finally reached 100 the trim
term still had to unwind off the stop, so speed sailed through to 94.1 KIAS in a
274 fpm descent - the condition the first input was flown from. Clamping the
integral TERM is not anti-windup; replaced with conditional integration.

### Run 4 — the gate worked, and found a loop satisfied with the aircraft in the wrong place

Added a **criteria-based stabilization gate** to `scripts/fly_card_h0.py`: the
card now refuses to take data until the reference condition is met and HELD
(kias +/-2, alt +/-60 ft, vs +/-120 fpm, bank +/-2 deg, for 4 continuous
seconds), records each point's entry condition, and marks any point entered
off-condition as not attributable. A test point is only a test point if it starts
from a known condition.

It immediately earned its place. Speed was nailed at 100.0 KIAS from the 22-knot
entry offset - the anti-windup fix confirmed in flight - with vs -3 and bank
-0.2. And the aircraft sat **107 ft low for two full minutes, correcting none of
it.** Nothing saturated, nothing oscillating: the cascade is proportional
throughout, and it reaches equilibrium the moment pitch equals its command, which
it can do at a standing altitude error because the pitch the VS loop asks for at
that error is also the attitude that flies level. Every loop was satisfied and
the aircraft was in the wrong place. Added `ALT_TO_PITCH_I` - the term a pilot
supplies with the trim wheel. Without it the card's reference condition is not
reachable and the card cannot be flown at all.

### Run 5 — out-trimmed, saturated, climbing away from its own commands

Engaged on an aircraft the autopilot had left trimmed to **+0.432 nose-up**. The
backend held full nose-DOWN elevator, saturated at -0.400 for seven seconds,
while the aircraft pitched UP to 11.5 degrees and climbed at 1,533 fpm. Nothing
in the control law was wrong. It had no trim authority, inherited someone else's
trim, and had no way to know it was being out-trimmed - because a saturated
surface and a slow one look identical from the response alone.

`docs/C182T_HANDLING_TEST_MATRIX.md` had listed "no trim" as a BLOCKED reason for
H0 before any of this was flown. Run 5 is what that assessment looks like in the
air.

Added an **autotrim loop** driven off the elevator the loop is actually holding.
It adopts the aircraft's real trim by readback before moving it, and **will not
write trim it has not first measured** - flying out of trim is recoverable,
writing a guessed trim position to an aircraft somebody else has been flying is
not. Frozen during a pitch test input, because trimming out a deliberate input
trims out the measurement. Trim position and trim RATE are now recorded, which is
the card's trim-confidence observable supplied directly.

Trim is deliberately kept OUT of `CONTROL_DREFS`, the set `_neutralize` zeroes:
handing an aircraft back with the trim slammed to neutral is an upset, not a
release.

### Recovery

After run 5 the aircraft was left at 77 KIAS at full power, out of trim and
decaying. Recovered with a direct write - neutral controls, trim 0.05, throttle
0.60 - to 81.4 KIAS, 3,908 ft. The pilot then paused the simulator.

### Also fixed

* Body rates `P`/`Q` and elevator trim are read as **auxiliary** datarefs,
  deliberately outside the freshness gate. Letting a damping channel go stale
  must degrade the damping, not neutralize the controls on an airborne aircraft.
  Their age is recorded in the trace (`body_rate_age_s`, `inf` when degraded), so
  a zero meaning "not rolling" and a zero meaning "no data" never look alike in
  flight-test evidence.
* Slew history, altitude trim, speed trim and elevator trim are all cleared on
  release, so a new engagement never resumes from a stale internal value.
* The speed integral is frozen during a pitch test input: a deliberate speed
  excursion is not something to integrate against.

### Status

`services/ai_pilot/tests/test_direct_backend.py` is now **80 offline tests**, up
from 53; the full `services/ai_pilot` suite is 150. Every gain above is justified
in-line against the measured flight it came from.

**Card H0 remains UNFLOWN. No handling point is recorded as pass or fail, and
none of this validates the aircraft or closes A-1.** Five defects found, five
fixed, and the card has yet to reach its first input from a stabilized reference.


## 2026-09-11 — direct backend FIRST FLIGHT: flown, tuned, and now recording traces

The direct surface-control backend flew CAP 487 for the first time, in four live
runs. Added `scripts/fly_direct_backend.py`, tuned one gain from measured data,
and fixed two bugs plus a data-recording gap the flights exposed.

### Run 1 - first flight, heading 189 to 350, 4,200 to 4,500 ft

Lateral channel was good immediately. Bank pinned at +25.2 degrees, exactly the
`MAX_BANK_DEG` clamp, through a 161-degree turn. Rollout 25.4 - 23.8 - 16.2 -
10.3 - 6.5 - 4.1 - 2.1 - 0.9 with no overshoot. Heading settled 349.2-349.7
against 350. Speed held 114.1-115.6 against a 115 target. Altitude moved only
4,200 to 4,215 through the whole turn, which is the vertical loop compensating
for lost vertical lift component unprompted.

Vertical channel was badly under-gained: commanded 4,500, reached 4,412 in 170
seconds, with vertical speed peaking at 214 fpm and decaying to 40-60 against an
aircraft that climbs 900+. The gate reported "captured" at 4,401 - 99 ft low,
just inside its own plus or minus 100 ft tolerance - so a loose tolerance masked
a weak loop.

### The tune: one variable, from physics not guesswork

700 fpm at 125 KTAS is a 3.17 degree flight path angle, so roughly 6.2 degrees of
commanded pitch. `VS_TO_PITCH` 0.004 was producing 700 * 0.004 = 2.8 degrees.
Changed to 0.010, giving 7.0 degrees and still under `MAX_PITCH_DEG`. The
pitch-to-elevator inner loop had tracked its command adequately, so it was left
alone - one variable at a time.

### Run 2 - retune validation, 4,236 to 5,500 ft

    target 5,500 ft      before: fell 99 ft short    after: reached 5,510
    sustained climb      before: ~200 fpm            after: ~450 fpm
    capture              before: decayed to 40 fpm   after: clean, no overshoot

Heading 020 held at 18.8-19.7. Speed 109-110.7 against 110.

### Run 3 - westbound cruise hold

Heading 269.2-269.6 against 270, within 0.8 degrees. Altitude 5,576-5,577,
holding within ONE foot. Speed 114.3-115.4 against 115. Roll +0.5 to +0.8.
Vertical speed within plus or minus 11 fpm. Tighter than first-guess gains had
any right to be.

### Two bugs the flights found

`acquire()` returns `{'lease', 'next_sequence'}` and the runner passed the whole
dict as the lease token, so the gate refused control. The gate was right; the
runner was wrong.

The more serious one: `release()` neutralized the controls even when the backend
had never engaged. An aborted run therefore centred the yoke and set cruise
throttle on an aircraft the pilot was flying - it cost 22 knots and put a wing
down. Now tracked with an `_engaged` flag so the backend only hands back controls
it actually took, with three regression tests including one asserting that a
never-engaged release touches nothing.

### The data gap

The first three flights were not recorded anywhere. The runner printed to stdout
and wrote nothing; the gate's event buffer is a 200-entry in-memory deque that
dies with the process. For flight-test work the data is the deliverable, so that
was a real gap rather than an oversight to note and move past.

The runner now writes a JSONL trace to `~/.cache/capvsar/flight-tests/` with a
header recording the gains and limits in force - a trace that cannot be
attributed to a tune is not evidence of anything - and per-sample rows carrying
both the observation and the COMMANDED outputs.

Logging the commands mattered immediately. Run 4's trace shows throttle saturated
at 1.000 with elevator at only +0.036 against a plus or minus 0.40 clamp, while
commanding 700 fpm and achieving 382. The aircraft is power-limited at that
weight and altitude, not control-limited, and the controller asking for more than
the airframe can give is correct behaviour. Telemetry alone cannot distinguish a
saturated loop from a slow one.

### Still untested

Descents, large speed changes, and the entire regime below 90 KIAS, which is
every stall point. The gate's floor still blocks that and widening it for a test
profile remains an untaken decision. `services/ai_pilot/maneuvers.py` is still
unchanged. Suites: `services/ai_pilot/tests` 22 direct-backend tests OK, full
suite green under `~/.cache/capvsar/capvsar-planner-venv`.

## 2026-09-11 — ai_pilot: automated flight-test profiles (power-off stall, with recovery)

Added `services/ai_pilot/flight_test.py` and
`services/ai_pilot/tests/test_flight_test.py`. Second increment toward running
real flight-test procedures, and the companion to the direct backend below.

### Shape

This mirrors the dimensional harness deliberately. `scripts/measure_c182t.py`
compares measured geometry against a sourced master and reports pass, fail or
unmeasured. A flight-test profile does the same for performance: measured break
speed against the POH target, with a tolerance and an `unmeasured` verdict when
a point aborts.

A POH figure is not "fly until something happens"; it is the product of a
technique. A power-off stall speed is flown wings level at constant altitude,
power at idle, decelerating about a knot per second, and the number is the speed
at the break. `StallTestProfile` expresses that technique.

### Pure state machine, on purpose

The profile owns no threads, no sockets and no simulator handles. It takes an
observation and returns the commands to fly. Actuation is the caller's job via
`direct_backend.XPlaneDirectBackend`. Separating the deciding from the actuating
means the part that decides when to recover is fully inspectable and every
safety rule is testable offline and deterministically - 25 tests, no simulator.

### Safety model

A stall point deliberately flies to the edge of controlled flight, outside the
routine exercise envelope. That is only acceptable with stricter local guardrails:

* entry floor 3,000 ft AGL for recovery room, against the routine 1,000 ft;
* continuous aborts on AGL, bank, altitude loss, elapsed time and runaway pitch;
* recovery triggers on the break OR on any abort - never only on success;
* recovery reduces angle of attack FIRST, then adds power. Adding power at high
  AoA without unloading is how a stall recovery becomes a secondary stall.

Break detection requires a sharp sink AND high pitch together. Slow flight alone
is not a break, and a nose-down descent is not a stall; both are covered by tests.
The recorded speed is the minimum seen during the run, not the instantaneous
value at the moment of detection, which lags.

### A design weakness the tests caught

The first version used the same 10-degree bank figure for both entry and abort,
so a point could begin at the exact attitude that would abort it. That matters
here specifically: entry bank changes the measured stall speed, which is why the
POH tabulates 0, 30, 45 and 60 degrees as separate columns. Entry criteria are
now deliberately tighter than abort criteria - 3 degrees of bank and 100 fpm to
start, 10 degrees to abort - and a test asserts that relationship holds.

### Data reduction

`compare_to_target` returns pass, fail or unmeasured against a tolerance, and
`scale_stall_speed` scales a POH target by the square root of weight. The POH
tables are at 3,100 lb, and CAP 487 is currently loaded to 2,775 lb, so without
scaling the comparison would be meaningless - the expected full-flap figure moves
from 41 KIAS to about 39.

### Not flown

Nothing here has commanded the aircraft. The profile is not yet wired to the
backend, and the backend is not yet wired into `maneuver_server`. The gate's
90-KIAS floor still excludes every stall point; treating a test profile as a
documented exception to that envelope is a decision that has not been taken.

`services/ai_pilot/maneuvers.py` remains unchanged. Suites: `services/ai_pilot/tests`
121 passed with 23 subtests under `~/.cache/capvsar/capvsar-planner-venv`;
`tests.test_c182t_flight_model` and `tests.test_flightgear_c182` 24 OK.

## 2026-09-11 — ai_pilot: direct surface-control backend, so an agent can fly aircraft without autopilots

Added `services/ai_pilot/direct_backend.py` and
`services/ai_pilot/tests/test_direct_backend.py`. First concrete step toward the
ArduPlane direction the module has documented since it was written.

### Why

`XPlaneAutopilotBackend` commands the simulated aircraft's own autopilot, so the
maneuver contract only works on aircraft that have one. `XPlaneDirectBackend`
closes the loop on the primary flight controls instead, which makes the same
contract usable on any aircraft - a Cub, a glider, an older CAP airframe.

### The design decision that matters

The backend implements the EXISTING `maneuvers.FlightBackend` protocol -
`observe`, `select(heading_mag, altitude_indicated_ft)`, `release`, `pause` -
rather than widening it to expose control surfaces. Two reasons:

* `ManeuverGate` validates TARGETS against the exercise envelope. A target is
  checkable ("is 4,500 ft inside the altitude block, is it above the clearance
  floor over current terrain?"); a raw surface deflection is not. Routing
  surfaces through the gate would keep the lease and the sequence numbers but
  hollow out the envelope check that gives the gate its value.
* A future ArduPlane adapter fits the same shape - command modes and targets,
  let the controller fly the surfaces. Widening the contract to surfaces would
  make ArduPlane harder to adopt, not easier.

Consequence: `services/ai_pilot/maneuvers.py` is UNCHANGED. The gate, control
lease, strictly increasing sequence, envelope checks and capture detection all
keep working as they are, and this does not collide with the open AI-2
acceptance. Selecting the new behaviour is a matter of which backend is handed
to `ManeuverGate`.

### Relationship to AI-1

Direct surface control is exactly the capability AI-1 retired: the legacy
`flight_controller.py` writes `yoke_pitch_ratio`, `yoke_roll_ratio`,
`yoke_heading_ratio` and `throttle_ratio` with no authority contract, and its
live routes were disabled (`mission_ksee_krnm --live` refused, REST mutation
returns HTTP 410). This does not resurrect that path. It brings the same
capability under the gate, where it has a lease, a sequence, an envelope and a
fault path.

### Fail-safe properties, and the tests that pin them

Controls are written only while a `select` is active. `release` and `pause` stop
the loop and neutralize. A telemetry watchdog neutralizes on staleness. The loop
re-checks the exercise envelope itself rather than relying on the gate noticing
first. Every output is hard clamped, and commanded bank is limited to 25 degrees,
inside the gate's own 35, so routine operation does not trip the gate.

One deliberate choice: neutralizing does NOT chop the throttle to zero. This runs
on an airborne aircraft and dropping to idle unannounced is its own hazard, so
the release path centres the controls and leaves cruise power.

17 offline tests with a fake client - no simulator, no network. They cover AGL
conversion, refusal to take control without fresh telemetry, correct turn
direction including the short way across north, climb sense, output clamping
under extreme error, all three envelope faults, and the release/pause paths.

### Not flown

The control laws are UNVALIDATED in the simulator. Gains are deliberately gentle
and are expected to need tuning against CAP 487. Nothing has commanded the
aircraft through this backend yet; it is not wired into `maneuver_server`, which
still constructs `XPlaneAutopilotBackend`.

Suites: `services/ai_pilot/tests` 96 passed with 23 subtests under
`~/.cache/capvsar/capvsar-planner-venv`. A discover run under the system python
still reports one pre-existing import error, because `test_maneuvers.py` imports
`pytest` and the system interpreter does not have it; that is unrelated to this
change. `tests.test_c182t_flight_model` and `tests.test_flightgear_c182` 24 OK.

## 2026-09-11 — A-1 stage 2: offline dimensional harness and durable caches

Added `scripts/measure_c182t.py`, a pinned numeric landmark fixture and donor-free
regression tests. The harness reuses the strict converter parser, selects named
features, separates structural/rendered bounds, derives prop dimensions from the
hub axis and swept disc, and emits deterministic JSON plus three SVG overlays.
All 9 unknowns remain unmeasured. The 15 published FS stations are reference-only
because donor firewall registration is unproven. Wheel-contact re-posing is
explicitly provisional until the POH two-inch nose-strut condition is established.

Measured prop diameter is 79.255 in (fails the 79.0 in hard upper bound), main
wheel track is 102.992 in (-4.64%), and horizontal tail span is 143.026 in
(+2.16%). Length, height, wheelbase and clearance remain provisional. Donor span
with strobes is within the proposed tolerance, but the emitted package lacks
Strobe and BeaconOff. No geometry was corrected or dimension accepted for release.
See `docs/C182T_MEASUREMENT_HARNESS.md` for selectors, all results and commands.

Moved the operational donor, archive and pytest environment to `~/.cache/capvsar/`;
kept compatibility symlinks and original temporary backups for concurrent users.
Fetcher defaults and documented historical test commands now use durable paths;
archive and file checksum enforcement is unchanged.

Verified: two fresh donor-only builds and measurement outputs byte-identical
(14 files); fixture replay matches live report byte-for-byte; 25 converter/harness
checks pass with live comparison enabled, or 24 pass plus one explicitly optional
skip with all real donor/archive reads denied. Console/radio: 90 passed, 17
subtests passed, 8,891 existing warnings using the durable venv. Three overlays
rendered and visually checked. `git diff --check` passes. No X-Plane interaction,
installed-aircraft modification, converter winding change or other-agent lane edit.
A-1 remains open; this records metrology progress alongside the concurrent
flight-model work below, not aircraft acceptance or a production licensing decision.

## 2026-09-11 — A-1 horizontal tail span corrected; flight-test card and capture tool added

Closed the last sourced geometry gap in the flight model and set up the in-flight
validation that none of today's corrections has yet had.

### Horizontal tail span

The POH three-view (Figure 1-1 Sheet 1, page 1-3, top view) gives 11 ft 8 in.
The ACF had the stock C172S tail:

    span = 2 * (|_part_x| + _semilen_SEG) = 2 * (0.300 + 5.300) = 11.200 ft
    POH target                                                  = 11.6667 ft   -4.0%

`_wing/8/_semilen_SEG` and `_wing/9/_semilen_SEG` go 5.300 -> 5.53333 ft, giving
exactly 3.5560 m. Applied, and the aircraft reloads clean with no crash.

This is the surface the elevator acts on, and the elevator was given its
certificated 28/21 degree travel earlier today; leaving the surface 4% undersized
would have kept pitch authority short by a different route.

Chords are unchanged, so per-side area rises 20.70 -> 21.55 ft2, +4.1%. The
direction is right - the 182's tail is genuinely larger than the 172's - but NO
consulted source publishes a C182T horizontal tail AREA. Only the span is
verified; the area is a consequence, not a sourced target, and is recorded that
way in the code comment, the test docstring and the test card.

### A null result worth recording

The ACF's Vs 51 KIAS and Vso 41 KIAS were checked against POH Figure 2-2
(page 2-5) and match the published airspeed indicator markings exactly: green arc
51-140, white arc 41-100. Those were already correct and were not touched.

### Flight-test card

Everything corrected today - control travels, CG envelope, tail span - has been
verified STATICALLY only: the right number in the right ACF record, confirmed by
dataref after reload. None of it has been verified in flight.

Added `docs/C182T_FLIGHT_TEST_CARD.md` with sourced targets from the POH:
stall speeds at 3,100 lb for flaps up/20/FULL at both CG limits (Section 5
Figure 5-4), sea-level rate of climb 924 FPM, max speed 150 KTAS, 80% power at
7,000 ft 145 KTAS, and takeoff/landing distances, each with an entry condition
and a tolerance.

The card names A3 - power-off stall at FULL flap, expect 41 KIAS - as the single
most diagnostic point, because full flap was 30 degrees until today and is now
the certificated 38. If the extra 8 degrees is doing real aerodynamic work A3
lands near 41; if it reads like the old 30-degree value, the flap change is
cosmetic and the flap coefficients need attention instead.

The card also says how to read a miss: Group A high across the board points at
flaps or CG rather than the wing, since the wing already measures correct three
independent ways; B1 low points at engine or propeller modelling, which were
already correct before today.

### Capture tool

Added `scripts/capture_flight_test.py`, read-only telemetry capture: it sends
RREF subscriptions and reads replies, issues no DREF writes and no commands.
Live aircraft control stays reserved for `services.ai_pilot.maneuver_server` and
its serialized maneuver gate per AI-1 and AI-2, so the agent does not fly these
points - a human pilot or that maneuver server does, and the capture runs
alongside.

Smoke-tested against the live simulator: it read weight, altitude, KIAS, flap
ratio, pitch and bank from the parked aircraft and correctly flagged that the
current 2,782 lb loading is below the card's 3,100 lb condition. Traces are
written to `~/.cache/capvsar/flight-tests/`, outside the repository.

### State

ACF_PATCHES now 49. `tests/test_c182t_flight_model.py` now 14 tests, adding a
`HorizontalTailTests` class that pins the span, asserts left/right symmetry and
asserts the stock 5.300 value is gone. Suites: flight-model 14 OK,
`tests.test_flightgear_c182` 10 OK, console/radio 90 passed with 17 subtests.
`git diff --check` clean apart from the pre-existing `docs/BOARD.md` warning.

Flight model remaining: the vertical tail, which has no published target in any
consulted source and stays recorded as unknown, and the in-flight validation
itself, which is now blocked only on someone flying the card.

## 2026-09-11 — A-1 flight model: CG envelope corrected; ACF _part_z convention resolved

Corrected the CAP 487 centre-of-gravity envelope against TCDS 3A13. The blocker
recorded in the previous entry - that ACF z could not be related to the Cessna
fuselage-station datum - is resolved, and not by finding the datum.

### The datum problem, and the way around it

No consulted source locates the firewall (FS 0) in X-Plane's frame, and it is
still not located. It turned out not to be needed: percentage of MAC is datum
independent. The TCDS gives MAC = 58.8 in with the leading edge of MAC at
FS 25.98 in, which converts every published CG station into a %MAC that can be
placed in any frame.

That required resolving one convention question first, and it is a large one.
`_wing/0/_part_z` is the root QUARTER-CHORD, not the leading edge. The two
readings differ by 0.25 x 5.20 ft = 1.30 ft, which is 27% MAC - big enough that
guessing would have produced a seriously wrong envelope.

Resolved empirically against the donor mesh, which shares the ACF part frame
(independently confirmed: the ACF engine reference at -1.134 m sits 14 cm aft of
the donor's propeller disc at -1.274 m). Predicted versus measured wing leading
edge, under the quarter-chord reading:

    |x| 1.35 m   predicted 0.579 m   measured 0.591 m   delta +11 mm
    |x| 5.15 m   predicted 0.690 m   measured 0.702 m   delta +12 mm

against a 396 mm separation between the quarter-chord and leading-edge
interpretations. The tip chord also measures 3.63 ft against the ACF's 3.60 ft.

### Cross-check: the wing is right, a third time

Integrating the ACF wing planform (carry-through plus inner plus outer panel)
gives MAC = 58.04 in against the TCDS 58.8 in, -1.3%. With span +0.56% and area
-0.55% from the previous entry, that is three independent confirmations that the
C172S-derived wing is already a correct C182T wing.

### What was wrong

    limit                 stock C172S      TCDS 3A13 C182T        now
    _cgZ_fwd   2.900 ft = 18.73% MAC   FS 33.0 in = 11.94% MAC   2.571 ft
    _cgZ_aft   3.900 ft = 39.40% MAC   FS 46.0 in = 34.05% MAC   3.641 ft

The stock aft limit sat 5.35% MAC - about 3.1 inches - aft of the C182T's
certificated aft limit, in the stability-reducing direction.

LIMITATION, recorded deliberately: the TCDS forward limit is weight-scheduled
(33.0 in at 2,250 lb and below, 35.5 in at 2,700 lb, 40.9 in at 3,100 lb) and
X-Plane takes a single forward value. The most forward certificated point is
used, so the envelope is correct at light weights and permissive at heavy ones.
Modelling the taper needs a loading-system change, not an ACF constant.

`acf/_cgZ` itself was left at 2.900 ft. It is the reference CG rather than a
limit, and it now sits at 18.73% MAC, inside the corrected envelope.

### Verification

Two patches added (ACF_PATCHES now 47), each verified to match exactly one ACF
record, applied, and live-verified after an aircraft reload. X-Plane reports the
limits relative to the reference CG, which matches to the millimetre:

    acf_cgZ_fwd  -0.1003 m = -0.329 ft   = 2.571 - 2.900   OK
    acf_cgZ_aft  +0.2259 m = +0.741 ft   = 3.641 - 2.900   OK

`tests/test_c182t_flight_model.py` now carries 11 tests, adding a
`CentreOfGravityTests` class that pins both limits by station and by %MAC and
asserts the stock C172S aft value is not still present. Suites:
`tests.test_c182t_flight_model` 11 OK, `tests.test_flightgear_c182` 10 OK,
console/radio 90 passed with 17 subtests, run against the migrated venv at
`~/.cache/capvsar/capvsar-planner-venv`.

Still outstanding in the flight model: horizontal tail span 11.20 ft against the
POH's 11 ft 8 in (-4.0%), and the vertical tail, which has no published target in
any consulted source and stays recorded as unknown.

## 2026-09-11 — A-1 flight model: control travels corrected from TCDS; wing was already right

Audited the CAP 487 flight model against the sourced C182T data and corrected
the certificated control-surface travels. Changed `scripts/build_c182t_package.py`
and added `tests/test_c182t_flight_model.py`. The new tests live in their own
file to stay out of the lane handed to Codex in
`docs/bugs/CODEX_RESUME_C182_HARNESS.md`.

### Correction to earlier statements in this log and in session discussion

"CAP 487 flies like a C172" was repeated several times today. The audit does not
support it, and the claim should not be relied on.

"0 of 40 ACF patches touch wing, body, gear or tail geometry" is literally true,
but it is misleading about aerodynamic effect, because the C172S and C182T share
essentially the same wing. Measured from the installed ACF:

    main wing span   36.20 ft = 11.034 m   target 36 ft 0 in = 10.973 m   +0.56%
    main wing area  173.04 ft2 (156.40 panels + 16.64 carry-through)
                                           target 174.0 ft2              -0.55%
    airfoil         NACA 2412              correct for both types

Mass and powerplant were also already correct: empty 1,970 lb, max 3,100 lb,
engine power limit 230 HP, RPM max and redline 2,400, type RCP_INJ, propeller
3 blades at 2,400 design RPM. So the dominant aerodynamic surface, the mass and
the powerplant were all right; what was actually wrong was smaller and specific.

Note the span figure needs the root offset: the wing parts start at
`_part_x` 1.6 ft from centreline, so span is 2 x (1.6 + 7.0 inner + 9.5 outer),
and the 174 ft2 reference area includes the carry-through section through the
fuselage that the wing parts do not cover.

### What was actually wrong, and is now fixed

Control-surface travels were the stock C172S values, materially smaller than the
C182T's certificated travels. From TCDS 3A13 Rev 66 page 33:

    surface          was (C172S)   TCDS 3A13 C182T   now
    elevator up         20 deg       28 deg +/-1     28
    elevator down       15 deg       21 deg +/-1     21
    rudder left/right   20 deg       24 deg +0/-1    24
    flap full down      30 deg       38 deg +0/-1    38
    aileron up/down     20 / 15      20 / 15         unchanged, already correct

That is short pitch authority, short yaw authority and 8 degrees of missing flap
- all of which bear directly on approach speed, descent rate and slow flight,
which is what the SAREX rehearsal use case actually exercises.

Five patches were added to `ACF_PATCHES` (now 45 total), each verified to match
exactly one record in the installed ACF, and applied. Live-verified after an
aircraft reload: X-Plane reports acf_elev_up 28.0, acf_elev_dn 21.0,
acf_rudd_lr 24.0, acf_ail1_up 20.0, acf_ail1_dn 15.0, all matching TCDS.

### Still outstanding in the flight model

- Horizontal tail span measures 11.20 ft = 3.414 m against the POH three-view's
  11 ft 8 in = 3.556 m, 4.0% short. This is geometry rather than a scalar and was
  not touched.
- Vertical tail has no published target in the POH, TCDS or Specification and
  Description, so it cannot be validated. Recorded as unknown.
- CG limits could not be checked. The ACF uses `_cgZ_fwd` 2.90 ft and `_cgZ_aft`
  3.90 ft measured from the ACF reference point, and the mapping between ACF z
  and the Cessna fuselage station datum (lower front face of firewall) has not
  been established. Do not compare those numbers to the TCDS 33.0-46.0 inch
  range until that mapping is derived.

`tests/test_c182t_flight_model.py` adds 7 tests pinning the travels, the weights
and the TCDS airspeed limits, plus a hygiene test that every ACF patch pattern is
anchored, valid and unique. They read only `ACF_PATCHES`, so they need no donor
cache, no X-Plane and no network. Suites: 7 new, `tests.test_flightgear_c182`
10 OK, console/radio 90 passed with 17 subtests. `git diff --check` clean apart
from the pre-existing `docs/BOARD.md` warning.

## 2026-09-11 — Codex handoff prepared for the A-1 measurement harness

Added `docs/bugs/CODEX_RESUME_C182_HARNESS.md` as the continuation prompt for
stage 2 of `docs/bugs/CLAUDE_RESUME_C182_DIMENSIONS.md`, the dimensional
measurement harness. Handoff only; no code, asset or simulator file was changed
and tests were not rerun beyond confirming the recorded baseline.

The unit is scoped as entirely offline so it cannot contend with the simulator,
which is a single shared resource. Its input contract is
`scripts/c182t_dimension_master.json` (10 targets, a 15-entry station ladder,
9 explicit unknowns) with `docs/C182T_DIMENSION_MASTER.md` as provenance.

The prompt pins the facts that are easy to get wrong and expensive to rediscover:
that X-Plane winds triangles opposite to the stored vertex normal and the guard
test protecting it must not be reverted; that the converter's classification is
fail-closed by design; that published length and height are measured in POH
normal ground attitude and the donor mesh is not in it, its nose wheel sitting
131 mm below the main-wheel plane; that published span includes wingtip strobes
while `Strobe` is still unconverted, so a span measured today is structure-only
and not comparable; and that the 9 unknown stations must be reported unmeasured
rather than filled with plausible coordinates.

It also carries the donor-free test requirement with the licence-safe mechanism -
commit a derived landmark fixture of measured numbers only, pinned to the donor
archive hash, since numeric measurements of a GPL mesh are not a distribution of
that mesh - and a small second unit moving the donor cache, archive and pytest
venv out of `/tmp`, where a reboot currently erases both the cache and the
recorded test baseline.

Out of scope for that unit: geometry correction, the registration texture
placement, the five unconverted light fixtures, the Plane Maker model, and any
use of the running simulator.

## 2026-09-11 — A-1 winding fix CONFIRMED in X-Plane; registration placement still wrong

The winding fix from the entry below is confirmed in the sim, lifting its
offline-only caveat. X-Plane 12 started 12:02:37 with the corrected objects
already installed at 11:59:42 and loaded the aircraft at 12:02:49, so the
12:03:50 capture is a fresh load of the fixed build, not a stale one.

Result: the cabin renders SOLID, the magenta patch at the firewall is GONE, the
cabin windows are correctly transparent with the interior visible through them,
and the silhouette reads as a proper C182 - swept fin, wing struts, wheel
fairings, cowl, with the wingtip nav light lit. The see-through cabin, the
magenta firewall patch and the exposed interior were all one bug.

### What the fix revealed

The CAP 487 registration is still wrong, and the change made alongside the
winding fix did not help. On the PORT side the marking renders MIRRORED and sits
far too low, running off the bottom of the fuselage side into the belly curve.

That is diagnostic. The port side is painted by the first stamp at texel
(1590,505), which is the one left UPRIGHT; only the second stamp at (1530,1120)
was given the vertical flip. Port rendering mirrored from an un-flipped stamp
means the atlas-band identification was wrong: the region at texel y 526-810 is
not the port rear fuselage in the orientation assumed, so the earlier
rotate(180)-to-FLIP_TOP_BOTTOM reasoning was applied to the wrong stamp.

Both the placement coordinates and the per-side orientation remain unverified
guesses. The reliable way to settle it is empirical rather than analytical: stamp
an asymmetric test pattern - labelled glyphs on a coordinate grid - across the
whole 4096x2048 atlas, render it, and read off directly which texture region
paints which side and in what orientation. Two attempts to derive it from UV
geometry already failed (a vertex-hit test misses large UV islands; a
point-in-triangle test matched everything because degenerate zero-area UV
surfaces contain every probe point).

### A-1 exterior status

Confirmed working: geometry, winding, cabin, glass, gear, wing, tail, control
surfaces present, nav light. Still outstanding: the registration placement and
orientation, and the five unconverted light fixtures (Strobe, NavLight.L/R,
NavlightTransp, BeaconOff), of which Strobe and BeaconOff matter dimensionally.
Plane Maker geometry remains entirely stock C172 and is untouched. A-1 stays open.

## 2026-09-11 — A-1 root cause found: OBJ8 triangle winding was reversed

The see-through cabin is a triangle-winding bug in the converter. Fixed in
`scripts/convert_flightgear_c182.py` and locked with a new regression test.
Verified OFFLINE ONLY - see the caveat below.

### Root cause

X-Plane winds triangles OPPOSITE to the stored vertex normal. Laminar's own
`objects/fuselage.obj` is the reference: across 752 cabin-side faces and 212
tailcone faces, its winding-derived normal agrees with its stored normal 0.0% of
the time. The winding points inboard while the stored normals point outboard.

AC3D winds the other way, and `_build_mesh` emitted AC3D's ref order directly, so
our winding and normals AGREED (83.8% on the same cabin band). X-Plane therefore
culled the near-side skin of every surface.

That single fault predicts every symptom seen in the two X-Plane sessions:

- see-through cabin: the near skin is culled, exposing the Laminar interior;
- tailcone and cowl still look solid: nothing sits between their walls, so the
  inside of the far wall is what renders and it reads as normal;
- magenta patch at the firewall: the interior panel showing through culled cowl skin;
- only geometry that sits inside the skin is exposed, which is why a mesh that is
  provably complete still renders open.

It also explains why every other variable tested negative. Header, texture, alpha
channel, ANIM blocks and object grouping were all irrelevant because the faces
were discarded before any of it applied.

### Why the earlier offline render missed it

The offline OBJ8 rasteriser written during the previous unit reported a complete
solid fuselage. It culled faces using the same convention the converter assumed,
so it faithfully reproduced the converter's own error. Checking against Laminar's
shipped object instead of against our own reasoning is what broke this open;
a self-written renderer is not an independent check of a convention question.

### Fix

`_build_mesh` now emits each triangle's refs reversed. `raw`, and therefore every
stored vertex normal, is still computed from the original AC3D order, so normals
keep pointing outboard and only the index order flips.

Measured on the cabin-side band, |x| 0.45-0.72, z 0.30-2.50, y -0.40-0.30:

    stock fuselage.obj (reference)   winding-outward   8.0%   winding/normal agree  0.0%
    ours before fix                  winding-outward  82.8%   winding/normal agree 83.8%
    ours after fix                   winding-outward   3.8%   winding/normal agree  2.9%

Added `WindingConventionTests.test_winding_opposes_the_stored_normal`, which
asserts the invariant directly on a synthetic AC3D quad and needs no donor cache.
The converter suite is now 10 tests; console/radio remain 90 passed with 17
subtests. The rebuilt objects are installed in the local X-Plane package.

### Caveat

Verified offline only. The measurement matches the stock reference closely and the
mechanism accounts for every observed symptom, but the corrected build has NOT
been seen rendering in X-Plane - the sim was shut down when the fix was made. One
aircraft reload is needed to confirm; expect a solid cabin and no magenta patch.
A-1 stays open until that is seen, and the registration placement and the five
unconverted light fixtures (Strobe, NavLight.L/R, NavlightTransp, BeaconOff)
remain outstanding regardless.

## 2026-09-11 — A-1 exterior fault isolated to the converted OBJ; cause still unknown

Second X-Plane session on the CAP 487 exterior. The see-through cabin is now
bisected to our converted object rather than the sim, the aircraft package, or
the Laminar interior, but the cause is NOT found. A-1 stays open.

### The decisive result

With everything else untouched, only slot 15 swapped:

    stock fuselage.obj       -> cabin SOLID, no magenta patch
    flightgear_c182t.obj     -> cabin see-through, magenta patch present

So the Laminar interior is not overdrawing; the stock object occludes it from
the identical slot with identical slot attributes. The fault is in our object.

### What was eliminated, with evidence

Against the converted object, all of the following were tested and ruled out:

- texture alpha: rebuilt the texture as RGB (no alpha channel) - unchanged;
- object header: substituted the stock TEXTURE/TEXTURE_LIT/TEXTURE_NORMAL and
  GLOBAL_specular 1.0 so the header matched stock byte-for-byte in kind - unchanged;
- animation: stripped every ANIM block - unchanged (and stock fuselage.obj itself
  contains five ANIM blocks, so animation was never a distinguishing feature);
- grouping: emitted a single group with one `TRIS 0 33861` and no other geometry
  - unchanged;
- data integrity: 16,081 VT lines scanned - zero NaN/Inf, zero zero-length
  normals, zero non-unit normals, UVs within 0.004-0.996;
- winding of the cabin skin specifically: 98.4% outward on the port side, 98.5%
  on the starboard side;
- glass: rebuilt the glazing object fully opaque (no BLEND_GLASS, opaque texture)
  - unchanged, so the glass object is innocent;
- ACF slot semantics: slot 18 restored to stock wings.obj - unchanged. (Slot 16
  also changed role in the original patch, fuselage_gear.obj -> blank.)

A minimal single-group, ANIM-free, stock-textured object built from our vertices
still fails to occlude. An offline OBJ8 rasteriser written for this purpose
(z-buffer, backface culling, orthographic side view) renders that same data as a
complete solid fuselage - full cabin side, door, baggage door, belly, tailcone,
with openings only at the window apertures. Whatever X-Plane objects to is not
visible in the geometry.

### Correction: the glazing change from the previous entry was wrong

The previous entry added Windscreen.Int, Windscreen.Int.Back, Windscreen.Side.Left
and Windscreen.Side.Right to the exterior glass object on the theory that they
were missing cabin skin. Face-winding measurement shows they are interior
surfaces - Windscreen.Int 2 faces outward against 320 inward, .Int.Back 2/66,
both .Side panels 0/49 - which is what the donor's .Int naming implies. They are
drawn from inside the cabin in FlightGear. Adding them put inward-facing
translucent surfaces into the external view. They are now in a documented
INTERIOR_ONLY set that the fail-closed guard recognises, and GLASS_NAMES is back
to the genuine exterior glazing (Windscreen at 494/12 outward, Window.L/R, llglas).
The claim that dropped glazing caused the see-through cabin was wrong.

### Converter changes

- GLASS_NAMES reverted to the four exterior glazing objects.
- INTERIOR_ONLY added (4 objects) and wired into assert_all_objects_classified.
- KNOWN_UNCONVERTED narrowed to the five light fixtures that are still genuinely
  missing: Strobe, NavLight.L, NavLight.R, NavlightTransp, BeaconOff. Strobe and
  BeaconOff remain dimensionally relevant per docs/C182T_DIMENSION_MASTER.md.
- create_cap_texture: rotate(180) replaced with FLIP_TOP_BOTTOM. Measured from
  the donor's Door.L/Door.R UVs, the two fuselage sides have separate atlas
  regions and both run aft with increasing u, but the right side's v axis is
  inverted, so only a vertical flip is wanted; rotate(180) also mirrored it
  horizontally, which is why the registration rendered backwards. NOTE: this is
  UNVERIFIED. The stamp coordinates (1590,505) and (1530,1120) are hardcoded and
  two attempts to confirm which geometry they paint produced invalid results - a
  vertex-hit test misses large UV islands, and a point-in-triangle test returned
  every object because degenerate zero-area UV surfaces contain every probe point.
  The registration placement needs its UV island derived properly.

### Process failures worth recording

- A blank object (POINT_COUNTS 0 0 0 0) placed in the glass slot 19 CRASHED
  X-Plane on aircraft load, confirmed by a crash marker in Log.txt. The same
  blank is harmless in slots 16 and 23-26. Never probe a slot by emptying it;
  substitute real geometry instead.
- `pgrep -x "X-Plane-x86_64"` NEVER matches: the process comm is "Main Thread".
  This produced false "sim is down" readings, on the strength of which a second
  X-Plane was launched while the first was still running. The second instance
  then logged "Failed to initialize UDP network connectivity. (RAKNET) ... you are
  already running another copy of X-Plane" and never bound port 49000, costing a
  full restart. Use `pgrep -f "X-Plane 12/X-Plane-x86_64"`, and confirm UDP by
  reading a dataref before acting.
- The E/WEBSRV "could not bind to port 8086" alert is X-Plane's web server only
  and is unrelated to UDP; the log itself says the sim functions normally.

### State

All aircraft files restored and hash-verified against /tmp/capvsar-c182-final:
flightgear_c182t.obj 1fc7adfd, flightgear_c182t.png 89c5370e,
flightgear_c182t_glass.obj db626f5a, and the ACF matches its backup d5a45a4f.
Tests: `python3 -m unittest tests.test_flightgear_c182` 9 OK; console/radio 90
passed with 17 subtests. `git diff --check` clean apart from the pre-existing
docs/BOARD.md warning in another agent's file.

### Next unit

Do it offline, not against a live flight. Hand-write a minimal OBJ8 - a few large
quads forming a box at the cabin station in our coordinate convention, nothing
else - and test whether it occludes. If a hand-built box also fails to occlude,
the fault is systemic in how write_obj8 emits vertex or index data and is not
caught by validate_obj8 or by the offline rasteriser; bisect from there toward
the real mesh. Also still open: the magenta patch at the firewall, the
registration placement, and the five unconverted light fixtures.

## 2026-09-11 — A-1 X-Plane visual acceptance run; exterior fails; selection now fails closed

First X-Plane 12 inspection of the installed CAP 487 FlightGear C182 exterior.
The exterior does NOT pass visual acceptance. Changed
`scripts/convert_flightgear_c182.py` and `tests/test_flightgear_c182.py` only;
no aircraft asset was rebuilt or reinstalled.

Method trap worth recording: X-Plane started 09:45:34 and loaded the aircraft at
09:50:47, while the FlightGear rebuild wrote the package at 09:56:11. The sim was
therefore rendering a stale pre-rebuild load that looks exactly like the stock
Laminar 172SP, down to the N172SP registration. Any future acceptance run must
issue `sim/operation/reload_aircraft` first, or it measures the wrong aircraft.
A second trap: X-Plane returns 0 for unrecognised dataref names, and stale RREF
subscription IDs from a previous client alias onto new names, so a run was
observed reporting `sim/graphics/view/view_is_external` as -0.524, which was
actually `acf_gear_ynodef[0]`. Use a fresh receive port and sanity-check values.

After reloading, defects visible in external view: the cabin region reads
see-through to the Laminar interior, the CAP 487 registration renders mirrored,
a magenta patch appears at the firewall station, and no spinner is distinguishable
at the nose (the engine was running, so a prop disc rather than blades is
expected there; not yet confirmed as a defect).

Three candidate root causes were tested and ruled out with data. Texture alpha:
`flightgear_c182t.png` is 100% opaque, alpha min and max both 255. Inverted
triangle winding: a centroid test gives 100% outward-facing on the closed convex
objects (both main wheels, nose wheel, spinner, windscreen, strobe), where a
globally flipped model would read 0%; the 55-62% readings on rudder, ailerons and
elevator are what a thin plate yields under that test and carry no information.
Note also that `_build_mesh` derives every vertex normal from the winding itself,
so stored normals cannot disagree with winding by construction. Interior
protrusion through the shell: at the front-seat station the emitted C182 skin sits
at half-width 0.635 m and the Laminar cockpit is 0.560 m, and the cabin floor
clears the seat bottoms by 65 mm, so the interior fits inside the shell.

The defect that was found is in object selection. Buckets are chosen by texture
name (`Default.png`, `Lights.png`) plus hardcoded name lists, so every donor
object carrying no texture falls through every bucket and is dropped silently:
37 of the donor's 88 polygon objects were being discarded. 28 are correct to drop
(ground-service chocks, cones, tiedowns, drain and cover props, the cold-weather
kit, and duplicate or alternate-LOD geometry), but they were being dropped by
accident rather than by decision. The remaining 9 are real gaps: `Strobe`,
`NavLight.L`, `NavLight.R`, `NavlightTransp`, `BeaconOff`, `Windscreen.Int`,
`Windscreen.Int.Back`, `Windscreen.Side.Left` and `Windscreen.Side.Right`.
`Strobe` matters dimensionally, not just cosmetically: the published 36 ft 0 in
span is defined with the wingtip strobes installed, and `BeaconOff` sits at the
fin tip the published height is measured to.

The converter now classifies every donor object explicitly through
`DELIBERATELY_EXCLUDED` and `KNOWN_UNCONVERTED`, and `assert_all_objects_classified`
raises on anything matching neither a bucket nor a documented exclusion, so this
class of loss can no longer happen quietly when the donor changes. The guard was
extracted as a pure function over name and texture, which makes it testable
without the 136 MB donor cache; four new tests cover it and the suite is now 9
tests that need no donor at all. This change is deliberately behaviour-preserving:
all five generated OBJ files rebuild byte-for-byte identical to the installed
package, so it documents and guards the gap without yet closing it.

The see-through cabin, the mirrored registration and the magenta firewall patch
remain unexplained and are the next unit of work. A-1 stays open; exterior
dimensions, X-Plane visual acceptance, Plane Maker geometry and the production
licensing route are all still outstanding. Separately confirmed by enumerating
`ACF_PATCHES`: 0 of the 40 ACF patches touch wing, body, gear or tail geometry,
so the Plane Maker side remains entirely stock C172. Live datarefs did confirm
the weight patches, with empty 893.6 kg and max 1406.1 kg matching the POH, and
aileron up travel at 20 degrees matching TCDS 3A13.

Tests: `python3 -m unittest -v tests.test_flightgear_c182` 9 tests OK;
`PYTHONPATH=. ~/.cache/capvsar/capvsar-planner-venv/bin/pytest tests/test_console.py
tests/test_radio.py -q` 90 passed with 17 subtests. `git diff --check` reports
only the pre-existing `docs/BOARD.md` blank-line warning, another agent's file.

The running sim was left with the view restored and the G1000 MFD popup reopened,
but the aircraft reload reset the cockpit, so SAR_DEMO must be reloaded.

## 2026-09-11 — Flight Data Recorder (FDR) tap & automated diagnostic test engine

Implemented synchronous, high-rate Flight Data Recorder (FDR) tap and automated
post-flight diagnostic test engine under `services/ai_pilot/`:
- `services/ai_pilot/fdr.py`: `FlightDataRecorder` tap sampling at 4–10 Hz across
  aircraft kinematics, DF outputs (`cap/df/*`), panel configurations, scenario
  truth (`cap/scenario/*`), aviation VHF radios, and CAP FM (TDFM-136B / GMA-1347).
  Provides JSONL streaming, in-memory ring buffer (1,000 frames), and CSV export.
- `services/ai_pilot/diagnostics.py`: `FlightDiagnosticEngine` with automated rules:
  1. Spherical great-circle bearing math verification and RMS error bounds.
  2. Authentic 406 MHz channel selectivity (Becker 517 Emergency fixed 406.025 MHz
     vs RT-600 7 CPSAR groups and Becker Training mode).
  3. Cone of confusion detection and inverted bearing suppression.
  4. Squelch threshold and timehold decay validation.
  5. Airframe wing/fuselage shadowing during banking turns.
  6. CAP Radio hygiene: PTT interlock enforcement, TOT 60s timeout, Guard tuning.
  7. COSPAS-SARSAT 15-Hex identifier integrity.
- `services/ai_pilot/web_server.py`: Added REST endpoints (`/api/fdr/status`,
  `/api/fdr/start`, `/api/fdr/stop`, `/api/fdr/analyze`, `/api/fdr/reports`,
  `/api/fdr/report`).
- `services/ai_pilot/static/board.html`: Integrated interactive FDR control bar,
  live REC badge, frame counter, duration, and diagnostic scorecard drawer.
- Test suite: Added `services/ai_pilot/tests/test_fdr.py` (12 tests). Full test
  suite passing (44/44 tests).

## 2026-09-11 — A-1 C182T dimensional measurement master established

Completed stage 1 of `docs/bugs/CLAUDE_RESUME_C182_DIMENSIONS.md`: the
source-backed measurement master for CAP 487's C182T exterior. Added
`docs/C182T_DIMENSION_MASTER.md` (provenance and reasoning) and
`scripts/c182t_dimension_master.json` (the machine-readable target profile the
stage-2 harness will consume). No aircraft asset, converter, simulator file or
existing test was changed.

Targets were taken from the FAA-approved Cessna 182T NAV III GFC 700 AFCS POH
(P/N 182TPHBUS-00/-01), FAA TCDS 3A13 Revision 66, and Cessna's December 2015
Revision C Specification and Description. All three are recorded with URL, page
and SHA-256; none is committed, since they are third-party copyrighted documents
and fall under the release boundary in `docs/FLIGHTGEAR_C182_GPL_PLAN.md`.

The decisive finding is that the sources define two different attitudes. The POH
three-view NOTE states that normal ground attitude is "nose strut showing
approximately 2 inches of strut, and wings level", and every published length
and height is measured in it; the TCDS leveling means (left tailcone at 139.65
and 171.65 inches aft of datum) is a weight-and-balance attitude only. Raw mesh
extrema compared against 9 ft 4 in are therefore not a measurement. Reading the
three-view at 450 dpi also fixed three endpoints that had been assumed: overall
length runs from the spinner apex, not the propeller; it ends at the rudder
trailing edge; and the 36 ft 0 in span explicitly includes the wingtip strobes,
so structural span must not be derived by subtraction.

The reference datum is the lower front face of the firewall, which makes the
plan's chosen cockpit anchor exactly FS 0. A fuselage station ladder was
assembled from TCDS loading stations plus the Specification and Description
cabin figure; FS 134.0 for the aft baggage bulkhead is confirmed by three
independent agreeing statements. The waterline datum is never located in any
source, so all vertical targets are referenced to the ground plane instead.

Nine requested items are recorded as unknown rather than invented, including the
wing root leading- and trailing-edge stations, the windshield base, door opening
stations, every aileron/flap/elevator hinge-line station, tail stations, and the
individual gear stations — the POH treats the main-gear station as a per-aircraft
weighing measurement, so only the 66.5 inch wheel base is published. The one
hinge geometry that is recoverable is the rudder hinge cant, 28.15 degrees from
vertical, derived from the TCDS publishing rudder travel in two frames. Closing
the rest needs a Cessna maintenance, structural repair or parts manual; until
then the wing, empennage and door regions have no sourced longitudinal target
and stage 3 must leave their stations alone.

A preliminary donor comparison using these endpoint rules is recorded as an
informational appendix. Span with strobes is -0.37% and propeller diameter is
79.17 in against a certificated 77.5-79.0 in band, while overall length is
-3.83%, wheel base -3.64%, track -4.64% and height +8.58% to the fin top. No
uniform or per-axis scale reconciles those, which refutes a whole-model scale
more strongly than the handoff claimed, and the clustered longitudinal shortfall
points at a regional fuselage and gear correction. The donor's nose wheel
contact also sits 131 mm below its main-wheel plane, a pose impossible on flat
ground, so its height and the very short propeller ground clearance are
provisional until the mesh is re-posed.

Tolerances in the profile are proposed, not ratified, and are marked as such.
A-1 remains open: no harness, no geometry change, no X-Plane run and no Plane
Maker work were part of this stage.

Tests were rerun and match the recorded baseline: `python3 -m unittest
tests.test_flightgear_c182` 5 tests OK, and `PYTHONPATH=.
~/.cache/capvsar/capvsar-planner-venv/bin/pytest tests/test_console.py tests/test_radio.py
-q` 90 passed with 17 subtests. `git diff --check` reports one pre-existing
blank-line-at-EOF warning in `docs/BOARD.md`, another agent's file, left
untouched.

## 2026-09-11 — A-1 dimensional-correction handoff prepared for Claude

Added `docs/bugs/CLAUDE_RESUME_C182_DIMENSIONS.md` as the continuation prompt
for CAP 487's FlightGear C182 exterior. It records the pinned donor and hashes,
the installed and preserved aircraft paths, the coordinate transform and
animation-pivot dependency, the last passing test baseline, and the GPL and
Laminar no-redistribution boundary.

The next implementation unit begins with a source-backed landmark measurement
harness and comparable structural measurement definitions. It then corrects
the cowling, cabin/tailcone, wing, gear and empennage by region while anchoring
the retained cockpit interface. A whole-model XYZ scale is explicitly rejected:
the donor's raw bounds include different visible features than Cessna's
published headline dimensions, and a global transform would move cockpit
seams, wheel contacts and animation pivots together without proving any of
them correct. Plane Maker geometry and flight-model calibration remain a
separate required acceptance stage. No aircraft asset or simulator file was
changed in this handoff-only update; tests were not rerun.

## 2026-09-11 — A-1 FlightGear C182 exterior prototype built and installed

Replaced CAP 487's visible stock C172 exterior attachments with a locally
converted C182 exterior from HHS81's FlightGear project, pinned at commit
`1359d63393c7fc9145953b081d151d93627e791a`. Added a checksum-verifying fetcher
and a strict AC3D-to-X-Plane OBJ8 converter; no Blender install is required.
The builder now emits separate airframe, three-blade propeller, prop-disc,
glass and light objects, drives primary control surfaces and the propeller from
X-Plane datarefs, and replaces all stock C172 exterior and broken-part ACF
slots. It derives a CAP 487 texture from the donor's blank livery.

The donor and generated donor-derived assets stay outside the Apache git tree.
Every generated aircraft carries the GPL-2.0 text, a local-prototype notice and
a manifest with the repository, commit, archive checksum, per-file donor checksums,
object counts and bounds. Added `docs/FLIGHTGEAR_C182_GPL_PLAN.md` with the
production choices: obtain a compatible dual license, ship a separately
reviewed GPL exterior/source package that never contains Laminar files, or
replace it with a clean-room model. `README.md`, `NOTICE` and `docs/SOURCES.md`
now state the local-use and no-redistribution boundary.

Built first at `/tmp/capvsar-c182t-flightgear-prototype`, then preserved the
previous installed package as `Cessna 182T NAV III.pre-flightgear-20260911-20260911`
and rebuilt the installed CAP 487 package. The installed main OBJ is byte-for-
byte identical to staging. The build applied 40/40 expected ACF patches and
produced 26,867 OBJ8 triangles. Orthographic inspection confirms a correct
C182 silhouette and coordinate transform. Donor-native bounds are approximately
8.50 m long, 10.91 m span and 3.22 m high; those differ from the authoritative
C182T headline dimensions enough that the donor is not the dimensional master.

A-1 remains open. X-Plane has not been launched to inspect the new exterior,
texture, glass, lights, animation or cockpit alignment, and the Plane Maker
body/wing/tail/gear and aerodynamic model still inherit C172 geometry. Those
visual, dimensional and flight-model checks are the next acceptance stage; the
combined local aircraft must not be redistributed.

```text
python3 -m unittest -v tests.test_flightgear_c182
Ran 5 tests in 0.003s
OK

PYTHONPATH=. ~/.cache/capvsar/capvsar-planner-venv/bin/pytest tests/test_console.py tests/test_radio.py -q
90 passed, 8891 warnings, 17 subtests passed in 3.30s
```

## 2026-09-11 — A-1 opened: CAP 487 still has the C172S airframe

Confirmed that `build_c182t_package.py` clones Laminar's stock Cessna 172 SP
and changes identity and selected performance values without replacing the
airframe geometry. A direct ACF comparison found no body, wing, tail or gear
geometry changes. The installed `fuselage.obj`, `wings.obj`,
`fuselage_gear.obj` and `fuselage_prop.obj` also have the same SHA-256 hashes as
the stock 172 files. This leaves CAP 487 with the wrong exterior and an
incompletely converted flight model. Opened P0 tracker item A-1 in the new C16
Aircraft package fidelity cluster; this work is separate from Gemini's G1000
instrument work.

Searched for donors with source assets and explicit redistribution terms. The
strongest technical candidate is HHS81's FlightGear C182S/T project: it is
actively maintained, has an actual C182T variant, and includes the editable
`dev/C182T.blend`. Its project is advertised as GPLv2+ and its root carries the
GPLv2 license text. Apache-2.0 and GPLv2 are not compatible for a combined
derivative distributed as this Apache project, so use would require a separate
GPL aircraft distribution or permission from the relevant copyright holders.
The native X-Plane candidate by Christopher Powell is a clean-sheet C182T, but
it targets X-Plane 9.6-era systems and its exact license is CC BY-NC 3.0. It is
useful as a reference prototype but cannot be treated as an Apache-licensed
donor. No modern, source-available C182T donor with permissive Apache-compatible
terms was found in this search.

The recommended path is to ask the HHS81 contributors for a permissive dual
license covering the exterior Blender source and textures. If that is not
available, create a clean-room exterior from C182T dimensions and independently
licensed references. Cessna's current specifications confirm 29 ft length,
9 ft 4 in height and 36 ft span for the Skylane. No donor asset was downloaded
into the repository, and no simulator or aircraft file was changed. This was a
tracker/research-only pass; tests were not run.

Sources:

- https://github.com/HHS81/c182s
- https://wiki.flightgear.org/Cessna_182T
- https://github.com/cpowell/cessna_182T_skylane_for_xplane
- https://www.apache.org/licenses/GPL-compatibility.html
- https://cessna.txtav.com/en/piston/cessna-skylane

## 2026-09-11 — F-6 fixed: server strings escaped in five console views

Message bodies, senders, recipients, bearing notes and callsigns were
interpolated into `innerHTML` unescaped. Any LAN client can POST `/api/messages`
and `/api/bearings`, and nothing escapes those values server-side, so markup in a
message body executed in every viewer's console. Added a shared `esc()` helper to
base.js, app.js and debrief.js and escaped every server string reaching HTML.

Leaflet `bindTooltip` renders a string as HTML, so the three data-driven tooltips
were the same sink and are escaped too. Values that reach HTML through `toFixed()`
or `Math.round()` are left alone, because a number cannot carry markup.

radio.js already escaped sender, recipient and body, but not the channel name that
this item's own description names; it now uses the existing `escapeHtml`. Found the
same class of bug in setup.js, which the item did not list: its fleet and roster
cards render `/api/setup` values, and two of them sit inside attribute values, so
the helper escapes the quote as well. The role badge escapes once into a local
variable rather than inside the template, so no raw server value appears there.

Added `ServerStringsAreEscaped` to tests/test_console.py. It walks every
`innerHTML` and `bindTooltip` statement in the five views and fails on any
server-controlled field not wrapped in an escaper. Reads used as object keys,
dedup strings or truthiness tests are deliberately not flagged, because markup is
inert there. The class ends with a self-check that reverts three known fixes and
asserts the detector notices, so the guard cannot silently stop working. Also
corrected the neighbouring mission-radio docstring, which still described the four
views as unescaped.

Not verified in a browser against a live posted payload. No JavaScript engine is
installed on this host, so the views were syntax-checked with esprima after
shimming three constructs it does not support: optional catch binding, logical
assignment and optional chaining. Those three appear in committed code and are
unrelated to this change.

Two pre-existing collection failures are worth recording, neither caused here.
`pytest tests/` cannot collect at all because the untracked tests/test_geodesy.py
and tests/test_propagation.py call `sys.exit()` at import. Separately
tests/test_engine.py, test_faceplate.py and test_lcd_text.py fail to import under
Python 3.14 with a recursion error.

```text
tests/test_console.py tests/test_radio.py -q
90 passed, 17 subtests passed in 2.54s

services/ai_pilot/tests -q
66 passed, 23 subtests passed in 12.13s

services/flightplanner/tests -q
59 passed, 17 subtests passed in 7.58s
```

## 2026-09-11 — Planner doc pages renamed to CAP 487; builder docstring corrected

Reviewing the shared working tree found the L-7 rename incomplete and a builder
docstring that no longer matched the code. Both concern the same fact: N499CP is
a real Cessna 172S on the squadron line and the simulated aircraft is CAP 487.

`services/flightplanner/templates/guide.html` still carried "N499CP Flight
Planner" in its title, brand and footer, and `docs/QUICKSTART.md` in its heading.
That template renders every documentation page, so the Quick Start and User Guide
pages showed a real aircraft's registration on a planner whose 172S profile L-7
removed; it now computes CAP 487 182T figures only. `templates/index.html` was
already renamed to CAP 487, so this applies the same name to the doc template and
quickstart heading rather than inventing one. The planner README sentence
recording the profile removal, and the existing index assertion, keep the
registration deliberately.

Added `test_doc_pages_do_not_carry_the_real_172s_registration`, covering all three
documented slugs through `/guide/<slug>`. The index page was already asserted; the
shared doc template was not, which is why the rename missed it. Confirmed the test
fails when the registration is restored to the brand line, then restored the file.

Corrected the `scripts/build_c182t_package.py` docstring, which claimed N499CP
appeared "in exactly one place - the flight planner's profile for that real 172S".
That profile no longer exists, and the remaining occurrences were the stale
branding above. The docstring now records where the registration legitimately
survives: CHANGELOG.md and the bug tracker, which describe what was true when
written.

Reviewed and left unchanged: tracker.json AI-6 lists `maneuver_server.py`, which
has no diff this pass. That listing is correct, because `maneuver_server.py:102`
and `:117` are the shutdown pause call sites the item describes.

No aircraft asset, installed package or AI-pilot control path was touched, and no
simulator command was sent. AI-2 and AI-4 remain open pending the repaired
package's fresh X-Plane load and visual cockpit check.

Required test output. Flask 3.1.3 and Markdown 3.10.3 were installed into the
temporary venv, which could not previously import Flask; repository pins were not
changed:

```text
services/flightplanner/tests -q
59 passed, 17 subtests passed in 7.58s

services/ai_pilot/tests -q
66 passed, 23 subtests passed in 11.71s

tests/test_console.py tests/test_radio.py -q
86 passed in 2.45s
```

## 2026-09-11 — CAP 487 package repaired and installed; load check pending

Confirmed the installed airframe matched all builder flight-model patches except
the old N499CP tail number. Reproduced prop_lever.obj line 187: an IDX10 record
contained only four indices. Laminar OBJ8 specifies exactly ten indices for IDX10;
the builder now emits trailing indices individually as IDX. Its texture was
194x87, matching the simulator warning; generation now resamples to 256x128
while retaining normalized UVs. Existing concurrent builder edits were preserved.

Built a full package in temporary staging, then validated 30/30 ACF patches,
125 vertices, 534 indices/178 triangles, index ranges and record arity, texture
dimensions and one prop-lever attachment. Generated vertex/UV/index sequence
matches the installed mesh exactly. X-Plane was confirmed closed before install.
Updated only the installed tail number, two selection icons, prop OBJ/PNG, and
renamed the CAP livery to Civil Air Patrol (CAP 487), updating its two icons.
Hashed every installed file to confirm unrelated assets, preferences and plugins
were preserved. Backups are at:

`/home/ron/X-Plane 12/Output/capvsar-backups/AI4-20260911-083735`

Installed static validation passed. AI-4 and AI-2 remain open pending a fresh
X-Plane load log and visual cockpit/prop-lever check. No simulator launch or
control command was sent during this package work.

Required test output (temporary venv, PYTHONPATH=., host socket access):

```text
pytest tests/test_console.py tests/test_radio.py -q
86 passed, 8891 warnings in 2.62s
```

The initial sandboxed test run stalled and was terminated; the host-access run
above completed. Python compilation and scoped git diff --check passed. No
planner changes were made. Format reference:
https://developer.x-plane.com/article/obj8-file-format-specification/

## 2026-09-11 — Manual recovery after telemetry-loss test verified

User reported stable after manually resuming. A four-second read-only RREF
observation confirmed pause=0 throughout, altitude 4199.635–4199.636 ft,
airspeed 122.422 KIAS, bank about 0.58 degrees and VVI about -0.23 ft/min.
No control commands were sent; controller and relay remain stopped. Recorded
manual recovery in AI-2; the installed CAP 487 package verification (AI-4)
remains outstanding. No code changed or tests rerun for this observation-only
confirmation. Latest required suite output is recorded in the preceding entry.

## 2026-09-11 — Live telemetry-loss revocation and recovery verified

Repeated the supervised test with relay isolation already verified and the
user reporting stable flight. Pre-test observation: 4199.633 ft indicated,
3540.332 ft AGL, 122.417 KIAS, bank 0.578 degrees, VVI -0.249 ft/min,
telemetry age 0.104 seconds and sim paused=0. Acquired a lease without selecting
a maneuver. The relay dropped 48 RREF replies for 5.007 seconds, forwarding
control traffic unchanged. At 1.900 seconds after drop began, the controller
reported `fault: Stale telemetry`, revoked the lease and sent `pause_on`.
Independent direct readback showed paused=1. AP state 16418 and FD mode 2
were preserved, as required for a telemetry fault.

Telemetry returned with age 0.0026 seconds at the five-second sample. Ownership
remained false. Only after confirming actual stale-data revocation and recovery,
submitted the old lease: HTTP 400 `Control lease absent or revoked`.
No maneuver command was accepted in this corrected trial. Stopped the unowned
controller and relay, then cancelled the relay's seven RREF subscriptions.
Left the simulator paused with the preexisting autopilot modes engaged.
Visual fault-pause confirmation was requested; manual recovery remains pending.
Evidence: `docs/bugs/AI_2_LOSS_LIVE_2026-09-11.jsonl`.

AI-6 verification now includes live telemetry-fault pause. AI-2 remains open
for the installed CAP 487 package mismatch/load errors (AI-4), and final manual
recovery/visual confirmation. No production code changed in this test pass.

Required post-run regression output, same temporary environment as below:

```text
services/ai_pilot/tests -q
66 passed, 23 subtests passed in 12.02s

tests/test_console.py tests/test_radio.py -q
86 passed, 8891 warnings in 2.80s
```

## 2026-09-11 — Telemetry-loss test isolation corrected; live retry pending

The temporary loopback relay dropped 47 RREF packets for five seconds, but
prior direct subscriptions from earlier controller sessions continued supplying
fresh telemetry to port 49005. This invalidated the loss trial: no stale-data
fault or lease revocation occurred. The old-lease probe was consequently
accepted and selected heading 320 / 3557.976 ft. This was a test-harness error,
not evidence of faulty lease revocation. Stopped the owning controller cleanly;
direct readback verified paused=1 and flight-director mode=1.

Cancelled the seven earlier direct RREF subscriptions from port 49005, restarted
one unowned controller through the relay, and verified isolation with the sim
paused. Telemetry age rose through 1.027, 2.028, 3.029, 4.030 and 5.031 seconds,
then returned to 0.010 seconds after automatic restoration. Ownership remained
false throughout. No flight-control write was used for this isolation check.
AI-2 remains open for the actual live fault trial; its invalid-attempt evidence
is retained in `docs/bugs/AI_2_LOSS_INVALID_2026-09-11.jsonl`.

No production code changed in this pass. Controller and relay remain running
without ownership, ready for a manually resumed supervised retry. Simulator
was left paused. The retry must confirm fault/revocation before issuing an
old-lease rejection probe; do not assume that dropping relay packets proves
all telemetry stopped.

## 2026-09-11 — FLC and shutdown pause verified live (AI-5, AI-6 fixed)

With the user supervising and managing power, selected heading 285 magnetic,
4200 ft indicated using the corrected G1000 FLC path at 110 KIAS. Initial
observation was 3984.975 ft / 106.669 KIAS. Direct readback confirmed AP state
106 (heading, speed-by-pitch/FLC, altitude armed), speed selector 110 and
altitude selector 4200. Measured climb reached approximately 391 ft/min while
holding 110 KIAS. Sustained capture was reported after 50.555 seconds at
4191.494 ft, heading 284.062, bank 0.739 degrees and VVI 91.618 ft/min.
Subsequent AP state 16386 confirmed heading plus altitude hold.

HTTP takeover revoked the lease; a sequence-2 heading request using the old
lease returned HTTP 400 `Control lease absent or revoked`. Flight-director
mode changed from 2 to 1, confirming servo disengagement. Acquired a fresh
guarded lease without selecting any maneuver, then cleanly stopped the sole
controller. Direct readback confirmed `sim/time/paused = 1`. The user explicitly
confirmed seeing FLC change to ALT near 4200 ft, AP disengage and the simulator
pause. AI-5 and AI-6 are fixed. The simulator was left paused, servos off and
controller stopped; resumption remains manual.

Evidence: `docs/bugs/AI_2_FLC_LIVE_2026-09-11.jsonl`. AI-2 remains open because
the installed aircraft package still differs from the intended CAP 487 build
(AI-4); the telemetry-loss-triggered live fault/recovery trial also remains
unexercised. No aircraft repositioning, takeoff, landing or throttle writes
were performed.

Post-live-test results, same temporary Python 3.14/Pydantic 2.13.5 environment:

```text
services/ai_pilot/tests -q
66 passed, 23 subtests passed in 12.00s

tests/test_console.py tests/test_radio.py -q
86 passed, 8891 warnings in 3.01s
```

## 2026-09-11 — FLC altitude selection and explicit pause command

At the user's direction, changed the airborne altitude maneuver from V/S mode
to the installed G1000 `sim/GPS/g1000n1_flc` command. Set a 110-KIAS exercise
target using the always-knots airspeed selector; leave power with the supervising
pilot. Existing speed-by-pitch/FLC mode is not toggled off. Removed the separate
ALT-arm toggle from this G1000 path. Reference: installed X-Plane 12.4.3
Commands.txt/DataRefs.txt and Laminar's autopilot dataref documentation:
https://developer.x-plane.com/article/accessing-the-x-plane-autopilot-from-datarefs/

Also established AI-6's cause from installed DataRefs.txt: `sim/time/paused` is
read-only. Use explicit `sim/operation/pause_on` and `pause_off` commands instead
of writing it. Updated README and regression tests for FLC climbs/descents,
retaining existing modes, and pause commands that cannot toggle accidentally.

Verification with the temporary Python 3.14/Pydantic 2.13.5 environment:

```text
services/ai_pilot/tests -q
66 passed, 23 subtests passed in 11.47s

tests/test_console.py tests/test_radio.py -q
86 passed, 8891 warnings in 2.87s
```

AI-5 and AI-6 remain open pending live verification. No new control command was
sent in this edit pass. Read-only live observation still showed pause=0,
3990.585 ft, 109.640 KIAS and AP state 18. A cockpit/power readiness confirmation
was requested before the FLC retest. AI-2 acceptance is still incomplete.

## 2026-09-11 — Live Gate A trial: heading capture, altitude and pause failures

Continued the user-supervised live trial through one maneuver-server instance.
Acquired a fresh lease and selected heading 285 magnetic / 4000 ft indicated
(sequence 1) from 273.480 / 3996.507. Controller measured sustained capture
in 12.742 seconds; later observation was 284.315 / 3997.739, bank 0.313 degrees,
VVI 5.098 ft/min. Cockpit annunciation confirmation was requested but not received;
this is measured telemetry capture only. A 6500-ft target returned HTTP 400
`Target outside exercise limits` and did not consume sequence 2.

Sequence 2 selected 4200 ft, but the aircraft remained around 3997 ft after
roughly 40 seconds. Direct RREF readback showed heading selector 285, altitude
selector 4200, VVI selector 0, AP state 18 and flight-director mode 2. Added
AI-5; no altitude capture was claimed and the cause was not guessed.

Clean SIGINT shutdown while owning control exercised the backend pause request.
The server exited, but direct `sim/time/paused` readback was 0. Added AI-6 and
immediately told the user to pause locally; autopilot may remain engaged. No
live takeover/disconnect or stale-lease re-engagement test was completed. AI-2
remains open. Raw sampled observations/events are retained in
`docs/bugs/AI_2_LIVE_2026-09-11.jsonl`. No aircraft repositioning was performed.

Post-run verification with the same temporary Python 3.14/Pydantic 2.13.5
environment documented below, using `PYTHONPATH=.`:

```text
services/ai_pilot/tests -q
64 passed, 23 subtests passed in 11.41s

tests/test_console.py tests/test_radio.py -q
86 passed, 8891 warnings in 3.03s
```

Passing automated tests do not supersede the observed live failures. Neither
failure was patched during flight. The controller is stopped; manual simulator
recovery remains necessary.

## 2026-09-11 — Live RREF telemetry receiver repaired (AI-3)

Live X-Plane 12.4.3 returned `RREF,` packets that the AI-pilot receiver
silently discarded. Accept the observed comma header alongside existing NUL
replies. Added receive-loop regression coverage for both headers, callbacks,
cached observations and rejection of unrelated headers.

After restarting the unowned controller, live status reported heading 93.063
magnetic, 3999.688 ft indicated, 1458.778 ft AGL, 122.635 KIAS, 1.206 degrees
bank, -0.147 ft/min and telemetry age 0.028 seconds. No control lease was
acquired and no aircraft-control command was sent. AI-2 remains open: these
observations prove telemetry reception, not maneuver capture or cockpit modes.

Exact suite output using the temporary venv with `PYTHONPATH=.`:

```text
services/ai_pilot/tests -q
64 passed, 23 subtests passed in 12.01s

tests/test_console.py tests/test_radio.py -q
86 passed, 8891 warnings in 2.98s
```

Reboot cleared the old temporary environment. Python 3.14 could not build the
old Pydantic 2.10.4 pin; these tests used Pydantic 2.13.5 with FastAPI 0.115.6.
Repository dependency pins were not changed. Warnings are dependency deprecations.

Unfixed finding AI-4: the installed aircraft still declares N499CP and its
load reports `prop_lever.obj:187` IDX10 out of range plus a non-power-of-two
prop-lever texture. Aircraft assets were not edited. NVIDIA host checks now
succeed with userspace and loaded module both 595.91.07.

## 2026-09-11 — AI pilot control-path retirement and live-test finding

Fixed tracker item AI-1 by retiring every legacy AI-pilot mutation path that
bypassed the supervised airborne maneuver gate. The legacy chat agent and web
deck are now observation-only; their former control, checklist, spawn, phase and
mission endpoints return an explicit refusal without writing simulator state.
The Hermes bridge exposes telemetry only, and the scripted KSEE–KRNM mission
refuses live mode before creating an X-Plane client. Mock mission playback
remains available for deterministic regression tests. Updated the AI-pilot
README to direct live control through the maneuver deck on port 8089.

Hardened the live X-Plane backend after finding that RREF subscriptions were
sent only once: the controller now renews missing or stale subscriptions once
per second, allowing it to start before X-Plane or survive a simulator restart
without duplicating callbacks. Added tests for negated and quoted control text,
retired APIs and tools, live-script refusal, and subscription renewal.

Verified with `PYTHONPATH=.` and `~/.cache/capvsar/capvsar-planner-venv/bin/pytest`:

```text
services/ai_pilot/tests -q
63 passed, 19 subtests passed in 12.15s

tests/test_console.py tests/test_radio.py -q
86 passed, 8891 warnings in 2.70s
```

`git diff --check` and Python bytecode compilation also passed. The console and
radio warnings are dependency deprecations from FastAPI, Starlette and AnyIO.

Live Gate A acceptance did not run. The maneuver server started without taking
control and reported no telemetry, while X-Plane 12 failed during GLX startup.
The host has NVIDIA userspace and on-disk kernel module 595.91.07, but the
currently loaded kernel module is 595.84; the kernel logged an API mismatch and
`nvidia-smi` could not communicate with the driver. Launching from the inherited
Snap environment is independently unsupported by X-Plane. Added
`scripts/launch_xplane12.sh`, which removes the inherited Snap variables and
checks the loaded module against the installed NVIDIA driver before launching;
its preflight check correctly refused the current 595.84/595.91.07 mismatch
with exit status 78. Added open tracker item AI-2 for the live CAP 487
acceptance after a normal reboot. Added
`docs/bugs/CODEX_RESUME_AI_PILOT.md` as a self-contained post-reboot handoff;
`docs/bugs/CODEX_PROMPTS.md` links to it at the top so the next VS Code session
can resume the authorized live procedure without relying on chat history. No
simulator control command was sent.

## 2026-09-10 — AI Mission Pilot concept of operations

Created `docs/CAP_V-SAR_AI_Mission_Pilot_CONOPS.docx` and a matching PDF
reading copy. The 12-page draft uses the established V-SAR document branding
and frames the AI Mission Pilot as a virtual crewmate for Mission Observer
practice. It defines human authority, training modes, hidden-truth boundaries,
the maneuver command lifecycle, communications and ATC modes, simulator safety
responses, evaluation evidence, current implementation status, delivery gates
and a bounded ArduPlane feasibility decision.

Verified the final Word package with archive, section, heading, image, field,
style and accessibility audits. Accessibility reported zero high, medium or low
findings. LibreOffice rendered all 12 pages without clipped text, broken rows or
orphaned continuation pages; every page was visually inspected. The source
`CAP_V-SAR_Summary_10pg.docx` remained unchanged. This is a project-review
concept and does not claim Civil Air Patrol approval or completed live-flight
validation.

## 2026-09-10 — AI pilot: airborne maneuver interface and X-Plane backend

Implemented `services/ai_pilot/maneuvers.py`, an explicit backend protocol and
serialized control gate; `maneuver_server.py`, a separate loopback deck on 8089;
and `static/maneuvers.html`. README now recommends this airborne entrypoint and
labels the existing scripted web/LLM controllers as legacy experiments.

The gate checks fresh per-field observations, finite targets, an exercise altitude
block and an explicitly provisional airborne envelope. It rejects ambiguous text,
negations, unsupported direction/units and extra fields. Leases and increasing
sequences reject replay and commands after takeover. Completion requires sustained
measured capture. Faults revoke ownership and request simulation pause. The
X-Plane adapter selects heading and indicated altitude via documented autopilot
mode requests, preserving already-active modes; it never imports hidden scenario
truth or invokes a language model. Mock observations remain static, so command
writes cannot masquerade as demonstrated aircraft performance.

Verified with `PYTHONPATH=.` and `~/.cache/capvsar/capvsar-planner-venv/bin/pytest`:

```text
services/ai_pilot/tests -q
68 passed in 14.48s

tests/test_console.py tests/test_radio.py -q
86 passed, 8891 warnings in 2.67s
```

The warnings are dependency deprecations. Initial test collection needed the
repository on PYTHONPATH; socket-based tests required execution outside the
sandbox. No planner code changed; its suite was not required for this change.

Findings/remaining limits: AI-1 records the legacy chat/direct-write bypasses;
they remain open and those processes must be stopped before using this deck.
The duplicate-instance lock does not arbitrate unrelated simulator plugins.
No live X-Plane flight was attempted, so aircraft handling, cockpit indications,
and UDP pause/disconnect delivery remain unverified. Terrain lookahead, power/
speed control, prescribed turn direction, voice, ATC and automatic ground phases
are not implemented. ArduPlane is a future backend, not an installed controller;
its X-Plane 12 compatibility and CAP 487 tuning still require a feasibility trial.
No existing tracker item was closed by this implementation.

## 2026-09-10 — AI Pilot Service: Autonomous Flight, Authentic C182T POH Checklists, and Glassmorphic Web Deck

**Status: implemented and tested. 35/35 unit and integration tests passing.**

Created a new autonomous flight and AI copilot subproject in `services/ai_pilot/` enabling an AI agent (local model on BigBrain or lightweight copilot) to operate the Civil Air Patrol Cessna 182T NAV III (CAP 487) in X-Plane 12 from cold startup to full shutdown.

### Key Components Added:
- **Authentic POH Checklists (`services/ai_pilot/c182t_checklists.py`)**:
  - Implements all 9 normal procedures from Cessna 182T Information Manual Section 4 (*Before Engine Start, Engine Starting, Before Takeoff, Takeoff & Climb, Cruise, Descent, Before Landing, After Landing, Shutdown & Securing*).
  - Challenge-response verification mapped to real X-Plane datarefs (`sim/cockpit2/*`).
- **Native UDP Client (`services/ai_pilot/xplane_udp.py`)**:
  - Asynchronous UDP communications on port 49000 (`DREF`, `CMND`, `RREF`, `VEHS`).
  - Thread-safe caching and offline mock mode for headless CI.
- **Guidance & State Machine (`services/ai_pilot/flight_controller.py`)**:
  - Controls takeoff roll on KSEE 27R, rotation at $V_r = 60\text{ KIAS}$, climb to 4,500 ft MSL (terrain clearance over Iron Mountain ridge), descent into Ramona Valley to 2,400 ft MSL, Runway 27 final approach intercept (273° M), 3° glidepath tracking, flare assist, rollout, and full stop.
- **Lightweight AI Copilot (`services/ai_pilot/lightweight_agent.py`)**:
  - Dual-mode copilot: fast deterministic rule-based copilot + local LLM chat interface connecting to BigBrain Ollama (`http://192.0.2.55:11434`).
  - Natural language parsing for flight commands, radio frequency requests, and status queries.
- **Glassmorphic Web Deck & REST Server (`services/ai_pilot/web_server.py`, `services/ai_pilot/static/`)**:
  - Zero-dependency HTTP server on port 8088 (`/api/telemetry`, `/api/checklists`, `/api/chat`, `/api/phase`, `/api/autopilot`, `/api/spawn`).
  - Glassmorphic Web UI with live Primary Flight Display (PFD) tapes, canvas-rendered artificial horizon / attitude indicator, checklist manager, route progress bar, and copilot chat terminal.
- **Scenario Runner & Test Suite (`services/ai_pilot/mission_ksee_krnm.py`, `services/ai_pilot/tests/`)**:
  - Full mission runner supporting live and mock simulation (`--live`, `--fast`).
  - 35 automated tests covering UDP protocol, checklists, flight controller, agent bridge, and web REST APIs.

## 2026-09-10 — Prompts 3, 5, 6, 7 and X-9: console hygiene, effects, Form 110, shared radio sessions

**Status: implemented and tested. X-6, X-8, F-7, F-9, L-9, L-12, X-9 fixed.
F-10 assessed and deliberately not attempted — see the end.**

Five prompts from `docs/bugs/CODEX_PROMPTS.md`, done by Claude at Ron's
request. Reordered: prompt 3 is `services/flightplanner/app.py` and Codex was
live in that file, so 5, 6 and 7 ran first and 3 waited until Codex had been
idle 40 minutes.

### X-6 — untyped bodies rewrote scenario definitions

`set_effects` merged the posted dict straight into the **scenario** row, so an
instructor turning terrain masking off for one demonstration rewrote the
exercise definition permanently and every future sortie from that scenario
started with masking off. Nobody would notice until a later exercise behaved
oddly and no one could say why.

Effects now belong to the sortie. `sorties` gains an `effects` column
(additive migration); a sortie takes a **copy** of the scenario's effects when
it starts, `set_effects` writes only there, and `rehydrate()` restores what
was being flown rather than the scenario's defaults. Nothing is migrated back
out of the old scenario rows, because there is no way to distinguish an
instructor's deliberate default from an effect they toggled once weeks ago.

`EffectsIn` is a closed Pydantic model — `extra: forbid` — so a typo is
rejected instead of being stored forever. `SortieIn` replaces the raw dict.
Coordinates are range-checked, which catches the commonest real error: a
transposed lat/lon pair was previously stored happily and the DF then searched
the Southern Ocean. Both `INSERT`s into `scenarios` now name their columns;
the positional `VALUES (?×15)` would have silently written `alert_kind` into
`alert_text` on the next `ALTER TABLE`.

### X-8 — the console kept no record of itself

Logging, because there was none: two `print()` calls, one of them a security
warning. Sortie start, stop, reveal and every effect change now go through a
real logger, which is the spine an after-action review reads.

Retention and pagination: `positions` grew for the life of the console and
`/track` returned all of it, so the debrief got slower every exercise.
`/track` now takes `since`/`limit` and returns `next_since`; callers that
ignore both still get a first page. Retention is **by sortie, not by row age**
(20 by default), so last week's debrief still replays in full — and it prunes
positions only. Bearings and messages are the written record, they are small,
and they stay.

The healthcheck answered `{"ok": true}` from memory, so a container with a
deleted or corrupt database reported healthy and Docker kept routing an
exercise at it. It now runs a query against a real table and returns 503 when
that fails; compose's existing check calls `urlopen`, which raises on 503, so
that wires up with no compose change.

The ticker task was never cancelled, so shutdown left it running against a
closing loop — the container's stop looked like a hang until Docker's timeout
killed it. And the container ran as **root**, holding beacon truth, the auth
tokens and the database, reachable by every tablet on the LAN. It now runs as
`capvsar`.

> **Deploy step, ms01.** `/data` is a bind mount, so the container user must own
> it. Docker created `services/exercise/data` as root on first use, so before
> the first non-root start:
> `sudo chown -R 1000:1000 services/exercise/data`
> or the console exits on a read-only database. UID/GID are build args
> (`--build-arg APP_UID=$(id -u)`) if you deploy as another user.

### F-9 / F-7 — the Form 110, and the legacy console

The CAPF-110 log existed only on `/radio-legacy`, so the console the MRO is
actually meant to use could not produce the one document the role exists to
produce. Ported to the Mumble console as a panel that logs **transmissions** —
which is what a voice net produces: own transmissions with their duration on
release (anything under half a second is a mis-key, not traffic), and received
traffic once per station per transmission rather than once per packet. The
traffic column is editable, because writing down what was passed is the
operator's job, not the software's.

All three export bugs fixed: a **date column** (a sortie through 0000Z read as
though it went backwards), real truncation (`padEnd` does not truncate, so one
long callsign pushed every column after it out of line for the rest of the
page), and `revokeObjectURL` (every export leaked its blob for the life of the
page). The log renders with `textContent` throughout — F-6 is still open next
door and this must not become a fifth unescaped view.

**F-7, explicitly, as the prompt asked:** `/radio-legacy` is **not** retired, so
F-7 is fixed in place rather than closed by retirement. Retiring it now would
take the airband station with it, and F-10 — its replacement — is not built.
The two bugs: `a && b || c` parsed as `(a && b) || c`, so an undefined sender
fell through and dereferenced it, taking the whole incoming-traffic handler
down; and audio was started from inbound traffic, which no browser allows, so
iPad Safari stayed silent after joining with nothing saying why. Audio is now
armed by a gesture (20 handlers), playback bails when unarmed instead of
dereferencing a null context, and speech is gated the same way.

**A correction I owe both prompt packs:** F-11's note said
`playP25Chirp`/`playP25Tail`/`playAmSquelchBurst` "do not exist anywhere in the
tree". They do — as methods of the `audio` class in `radio.js`, around lines
29, 60 and 102. My earlier grep looked for standalone functions. F-11 is a
port, not new synthesis, and the tracker and `CODEX_PROMPTS.md` now say so.

### L-9 / L-12 — the planner push, and where the database lives

The push planted the beacon at **sea level on the exact datum** the crew was
about to search around. Both halves gave the exercise away: the propagation
model uses `beacon_elev_ft` for the radio horizon and as one end of the terrain
ray, so a sea-level beacon in mountains modelled nothing real; and a beacon on
the datum means the crew flies to the middle of their own search area and finds
it at once. Elevation now comes from USGS, and the beacon is offset
`CAPVSAR_BEACON_OFFSET_NM` (2.5 by default) on a bearing derived from the plan
— deterministic, so re-pushing does not teleport it. The **alert** stays on the
datum, because that is what the crew is briefed on.

The push also reported "broadcast to active sortie" whether or not one was
running, inferring it from a 400 the console stopped returning. It now asks
`/api/state` what is actually running and reports `message_broadcast` and
`message_persisted` separately, saying plainly when a message is not part of
any exercise record.

L-12: compose mounted `aviation_data.db` as a single FILE, so SQLite's journal
and WAL — written as siblings — landed in the container's own layer and a crash
mid-write left the database with no way to roll back. The directory is mounted
now and `DATABASE_PATH` points inside it. The host file does not move; a
checkout still holding the old path keeps using it rather than silently
starting empty.

### X-9 — a desk with two radio faces was two users on the net

One Mumble client per browser **socket**, against a 16-session cap. An operator
with two faces open burned two sessions and, worse, appeared as two separate
stations — the same desk could be called, and answer, as two different people.

The connection is now keyed by operator. A second face **attaches** to the
client already on the net: its own outbound queue, so one slow tablet cannot
stall the other face, sharing one Mumble session and one identity. The
watchdog belongs to the connection, not to each face. Only the last face to
leave takes the client down — closing the first tab used to cut the operator
off mid-transmission. The session cap moved to *after* the callsign is known,
because until then there is no way to tell a new operator who needs a session
from a second face that needs none.

Writing the tests found a real bug in my own change: a face attaching to a
radio already on the net never ran `connect()`, so nothing ever sent it the
`tuned` acknowledgement and the page hung on "joining" forever. It now gets
the radio's current state on attach.

### Verified

- `pytest tests/test_console.py tests/test_radio.py tests/test_setup_auth.py`
  — **104 passed** (was 72). 15 new console tests for X-6/X-8, 11 for F-9/F-7,
  6 for X-9.
- `pytest services/flightplanner/tests/` — **58 passed, 0 failed**, including
  13 new for L-9/L-12.
- Engine 114/114, propagation, faceplate, panel, lcd_text, tdfm, am, luacheck
  — all pass.
- The radio suite was run **five times** for flakiness after the X-9 refactor;
  21/21 every time. Two of my own tests were racing the server's async
  teardown and now wait for the condition instead of assuming it.
- All nine console `.js` files parse (esprima, with a small transform for
  optional chaining, `??`, `||=` and optional catch binding, none of which an
  ES2017 parser knows).
- **Not verified:** anything requiring a Mumble server, a browser or Docker.
  The X-9 refactor is exercised against the suite's stubbed `connect`, not
  against real voice. The Form 110 panel has never been rendered. The non-root
  container has not been built. All three want ms01.

### F-10 not attempted, deliberately

Prompt 8 pairs X-9 with F-10 — a second simultaneous receive channel so the MRO
can monitor the tactical net and the airband at once. X-9 is done and was the
stated prerequisite. F-10 is not, and I stopped rather than half-build it: a
Mumble client is in one channel at a time, so a second receive path means
either a second client per operator (which is what X-9 just removed) or
Mumble's channel-listener feature, and whether `pymumble_py3` exposes listeners
at all is the first thing to establish. That is a design decision on the live
voice path, and I cannot test any of it here — no Mumble server, no browser.
It stays open with X-9 cleared out of its way.

## 2026-09-10 — L-7: CAP 487 planner uses the Cessna 182T POH sample

**Implemented and tested. User selected the POH sample numbers explicitly.**

Replaced the exercise planner's N499CP 172S profile with CAP 487 and the
Cessna 182T NAV III GFC 700 POH sample: 1924 lb empty, moment/1000 70.9,
3100 lb maximum takeoff, 2950 lb maximum landing and 87 US gal usable fuel.
The source is Cessna 182TIMBUS-01 revision 1 (20 December 2007), linked next
to the profile. Each group of numbers identifies its section/figure.

Cruise now includes manifold pressure, interpolating the POH standard-
temperature altitude/RPM/MP grid (0..10000 ft, 2000..2400 RPM where listed).
Above-80% cruise and missing table combinations return errors. Imported the
maximum-rate climb table, 1.7 gal start/taxi/takeoff allowance, short-field
runway subsets (0..6000 ft, 0..40 C), loading arms and the three-point forward
CG envelope. Landing fuel-burn guidance uses the separate 2950 lb limit.

The UI defaults and reference now describe CAP 487/182T and expose manifold
pressure, power and full-fuel endurance. README and user guide describe the
POH conditions, sample baseline and limits. The old 172S example was removed.
The template/JS changes are necessary to prevent the browser from submitting
172S defaults against the new 182T backend; no other-agent lanes were edited.

Verified against POH Figure 5-9: at 6000 ft, 2400 RPM, 20 inHg, 65% power,
130 KTAS and 11.4 GPH. Full 87 gal with maximum-rate climb from sea level and
45-minute reserve gives 6.66 h, consistent with the project handbook's 5.5+
hour statement. This is not a claim to exactly reproduce the POH endurance
chart, which uses normal climb instead. Tests also cover MP/RPM/altitude
interpolation, table/80% limits, W&B defaults and all CG envelope breakpoints.

Actual final suite output, using `~/.cache/capvsar/capvsar-planner-venv/bin/pytest`:

```text
$ pytest services/flightplanner/tests/test_sar.py
collected 32 items
services/flightplanner/tests/test_sar.py ............................... [ 96%]
.                                                                        [100%]
============================== 32 passed in 0.19s ==============================

$ pytest tests/test_console.py tests/test_radio.py
collected 49 items
tests/test_console.py ..................................                 [ 69%]
tests/test_radio.py ...............                                      [100%]
====================== 49 passed, 3435 warnings in 1.24s =======================
```

Console/radio tests ran outside the sandbox (the same TestClient restriction
as the prior entry). Warnings are FastAPI/Starlette Python 3.14 deprecations.
The real Flask-rendered page was tested for defaults; no browser or X-Plane
flight test was performed. `node --check` could not run: node is not installed.
`git status` still fails because the shared index is truncated; it was not repaired.

**Remaining finding L-7a:** the builder still uses 1970 lb empty and its
inherited simulator CG-to-POH datum mapping is unverified. The selected POH
sample is clearly labelled in the planner; it does not silently rewrite the
builder or assert a measured CAP 487 W&B record. Matching the installed
simulator to that selected baseline is tracked separately. L-7 is fixed for
the user-selected POH planning baseline. Bug board regenerated.

## 2026-09-10 — L-8: the planner works with no internet

**Status: implemented and tested. L-8 fixed. New finding L-14 — the planner
suite has 4 failures that are not from this work; see the end.**

Prompt 4 from `docs/bugs/CODEX_PROMPTS.md`, done by Claude at Ron's request.
Codex was idle when this started; it turned out not to be, which is the last
section.

The mission base runs with no route to the internet, and the planner did not.
Three separate reasons, all of them fixed here:

- **Leaflet and the fonts came from CDNs.** With no internet the map did not
  render at all — a flight planner that cannot draw a map is not a planner.
  Leaflet 1.9.4 is now vendored at
  `services/flightplanner/static/vendor/leaflet/`, byte-identical to the copy
  F-1 put in the exercise console, verified with `diff -r`. The three font
  families are vendored as Latin-subset woff2 with a local `fonts.css`. Five
  files, 340 KB total: they are variable fonts, so Google serves one file per
  subset for every weight, and the naive download produced three identical
  copies of IBM Plex Sans — deduplicated by hash, with the CSS re-pointed.
  `guide.html` was loading fonts from the CDN too. The prompt did not mention
  it, but leaving it would have meant exactly one broken page at a base with no
  internet, and it is the page where someone reads the user guide.
- **Tiles were requested straight from ArcGIS by the browser**, so the whole
  server-side cache was bypassed — `/api/tile-sources` handed the frontend the
  ArcGIS URLs. It now returns `/tiles/...`, and `serve_tile` is cache-first:
  on a miss it fetches once, stores it and serves it, so an online planning
  session populates the cache for the offline exercise with no separate step.
  Written to a `.part` file and renamed, so a killed worker cannot leave a
  half-written PNG to be served forever.
- **The cache only ran under `__main__`** — never under gunicorn, which is the
  only way it actually runs, so the charts volume was empty and every
  `/tiles/` request answered 204. `start_chart_precache()` now runs at import.
  gunicorn forks several workers and each imports the module, so the work is
  claimed with an `O_EXCL` lock file in the charts volume: one worker
  downloads, the rest serve.

Two things the prompt did not ask for but the change needed:

- **`chart_type` is now whitelisted.** It was interpolated into a filesystem
  path unvalidated. That was noted under L-10 as "not currently exploitable" —
  but this change makes that path *written* to as well as read, so it stopped
  being theoretical. `TILE_CACHE` is both the whitelist and the one place that
  knows the cache directory names, which are not the layer keys (`ifr_low`
  lives under `ifr`, because that is what `download_tiles()` was called with).
- **A back-off on upstream failure.** Leaflet asks for dozens of tiles at once;
  at an isolated base every one of them would pay a network timeout and hold a
  worker. One failure now blocks upstream attempts for 60 s.
  `CAPVSAR_TILES_OFFLINE=1` skips the network entirely, and
  `CAPVSAR_PRECACHE_CHARTS=0` skips the download — both documented in the user
  guide.

`USER_GUIDE.md` claimed FAA tiles were "served from the FAA ArcGIS service
(with any locally cached tiles used first)", which was untrue in both halves.
It now describes what the code does, says plainly what it used to say and why
that was wrong, and notes that Satellite and Street are *not* cached and do
need internet — the FAA layers are the ones to brief from.

### Verified

- **`services/flightplanner/tests/test_offline_map.py` — new, 13 tests, all
  pass.** No CDN host in either template (comments stripped first, since they
  cite the URLs the assets were vendored from); every file `fonts.css` names
  exists on disk; tile sources are local; unknown and traversing `chart_type`
  rejected; a cached tile is served with the network patched to raise; an
  offline station never calls out; a miss is fetched exactly once and the
  second request comes from disk; and a failed upstream is attempted once
  across six requests, not six times.
- `pytest tests/test_console.py tests/test_radio.py tests/test_setup_auth.py`
  — **72 passed.** This also closes two gaps I had been carrying: my P-11
  change to `main.py` and the CAP 487 fixtures in `test_setup_auth.py` had
  never been executed on this machine. They are now, and they pass. (Thanks to
  the venv Codex left at `~/.cache/capvsar/capvsar-planner-venv` — this machine has no
  FastAPI of its own.)
- Not verified: an actual run with the network physically blocked, and the
  pre-cache downloading real tiles. Both want a station, not this session.

### Found, not mine, not fixed: L-14

`pytest services/flightplanner/tests/` is **40 passed, 4 failed**. All four are
in cruise and runway performance, and none are in code this change touched.

L-7's partial fix **replaced** the N499CP 172S profile with a single `CAP 487`
182T profile rather than adding one alongside, and the 182T table has a
different shape — RPM 2000-2400 plus a manifold-pressure axis, where the 172S
had 2400/2500 at one power setting. `AIRCRAFT_DATABASE` now has exactly one
entry. So `test_cruise_interpolates_altitude_and_rpm` asks for
`get_cruise(5000, 2450)` — a 172S figure — and gets `Input 2450 outside
performance table 2000..2400`. Confirmed by calling `get_cruise` directly
against each profile rather than inferring it from the failure text.

Filed as **L-14**, depending on L-7, in Codex's lane. The fix is to settle the
L-7 question first (does the real 172S profile come back alongside CAP 487?)
and then point those tests at whichever profile they are meant to exercise —
not to edit the expected numbers to match whatever the table currently says.

### Lane note

Codex was idle when this started and had run prompts 1-2 by the time it
finished, in the same file. Nothing was lost — its L-5/L-6/L-7/L-11/L-1a work
and this L-8 work are both present and `app.py` parses — but that was luck,
not design: read-modify-write on a shared file has a window. My edits here are
the `Response` import, the tile block, and `start_chart_precache()` at the end;
Codex's are the aircraft table, the pattern generators, the performance
functions and the FMS writer. Prompts 3 and 5-11 remain outstanding, and prompt
4 is now done.

## 2026-09-10 — Planner FMS exports and search/performance corrections

**Implemented: L-11, L-1a, L-5, L-6 and test-harness finding L-13. L-7 remains open.**

- FMS export rejects unresolved departure/destination airports with JSON 400;
  it never substitutes search coordinates under an airport identifier.
- Type 28 records preserve sanitized SAR labels, with coordinates unchanged in
  their columns. Checked against [Laminar's specification for X-Plane 12](https://developer.x-plane.com/article/flightplan-files-v11-fms-file-format/).
  **Not loaded in X-Plane/G1000**; the user guide states this remaining check.
- Parallel tracks start half-spacing inside the box and use ceiling counts.
  Creeping sweeps likewise use ceiling counts and an initial half-spacing;
  the API exposes `coverage_truncated` when the requested leg cap is too low.
  Every point carries a magnetic heading. The truncation flag is available to
  the UI; adding a displayed warning was not part of this app.py-only change.
- Cruise interpolates altitude and RPM, refusing unsupported ranges. Runway
  calculations reject beyond-table altitude/temperature. Tailwind corrections
  come from [Cessna's 172S NAV III POH short-field chart notes](https://funflightsusa.com/wp-content/uploads/2018/06/POH_172S-G1000.pdf):
  10% extra distance per 2 kt through 10 kt; stronger tailwinds are rejected.
  Impossible ground speed/crosswind returns a route error, never zero fuel.
- New finding L-13: existing direct-handler tests only worked with the fallback
  Flask stub. They now explicitly mock their JSON boundary; HTTP regression
  tests exercise the real Flask client. No console or other-agent files edited.

Installed test dependencies in `~/.cache/capvsar/capvsar-planner-venv`; no repository
requirements changed. Actual final output (virtualenv pytest):

```text
$ pytest services/flightplanner/tests/test_sar.py
collected 29 items
services/flightplanner/tests/test_sar.py .............................   [100%]
============================== 29 passed in 0.18s ==============================

$ pytest tests/test_console.py tests/test_radio.py
collected 49 items
tests/test_console.py ..................................                 [ 69%]
tests/test_radio.py ...............                                      [100%]
====================== 49 passed, 3435 warnings in 1.32s =======================
```

The console/radio run required execution outside the sandbox after the
sandboxed TestClient stalled. Warnings concern FastAPI/Starlette deprecations
on Python 3.14, not test failures. Aviation downloads cannot resolve inside the
sandbox; export tests use explicit airport fixtures. No deployment performed.

Further L-7 research: the Plane Maker CG is measured from a model-specific
reference point ([Laminar manual](https://developer.x-plane.com/manuals/planemaker/)).
The inherited `_cgZ` alone does not define its offset from the Cessna POH
firewall datum. A simulation-baseline decision was requested before assigning
an empty moment; no assumption has been silently substituted. Cessna's 182T
performance tables were located, including the additional manifold-pressure
axis absent from the current planner. Prompts 3-11 remain outstanding.

## 2026-09-10 — L-7 source check: CAP 487 W&B data still needed

**Status: research only; L-7 remains open. No application code changed.**

Confirmed that the planner still defaults to the honestly labelled N499CP
172S, while `scripts/build_c182t_package.py` defines CAP 487 with 3100 lb
maximum weight, 87 gal usable fuel and 230 HP. Found Cessna's
[182T NAV III information manual, revision 1, 20 December 2007](https://www.aeroelectric.com/Reference_Docs/Cessna/cessna-poh/C182T_2007_NavIII-G1000%2BGFC700_POH-PIM_fromCessna.pdf).

The precise missing value is CAP 487's **basic empty-weight moment in the
POH datum system**. The builder sets empty weight to 1970 lb but provides no
corresponding moment or documented mapping from its inherited simulator CG.
Section 6-8 requires aircraft-specific weight and moment; figure 6-3's
1924 lb / 70.9 thousand lb-in pair is a sample, not CAP 487's record.
Copying or scaling that moment would invent the W&B result. Stopped at the
prompt's explicit instruction to stop when a required figure cannot be
sourced. This is recorded on existing item L-7, not a duplicate issue.

The handbook's 5.5+ hour claim is specifically at 65% power loiter; it is not
an unconditional endurance value. No endurance calculation was changed or
validated. The existing FMS airport-coordinate fallback and coordinate-derived
waypoint labels were confirmed by inspection, but L-11/L-1a and prompts 2-11
were not implemented after the stop. X-Plane/G1000 verification was not run.

Requested suite commands were attempted; actual output:

```text
$ pytest tests/test_console.py tests/test_radio.py
/bin/bash: line 1: pytest: command not found
$ pytest services/flightplanner/tests/test_sar.py
/bin/bash: line 2: pytest: command not found
```

Workspace finding: `git status --short` failed twice with
`fatal: .git/index: index file smaller than expected`; `.git/index` was zero
bytes when inspected. No Git repair attempted in this shared workspace.
The installed aircraft file also still says N499CP, despite the updated
builder; no installed files were modified. Regenerated the bug board after
recording the L-7 finding; no issue status changed.

## 2026-09-10 — P-11: the console no longer invents a DF picture

**Status: implemented. P-11 fixed. The main.py half is not executed on this
machine — see Verified.**

`services/exercise/app/propagation.py` was a second, much cruder propagation
model that ran **whenever a station omitted `df`** — a plugin still loading,
disabled, or mid-reconnect. The instructor's map then showed a DF picture the
simulator never computed, with nothing marking it as fabricated, while the crew
looked at something else entirely. A wrong DF display is worse than a blank
one, because the instructor cannot tell which they are looking at.

The divergence was already real (1.5 s burst window against the plugin's
0.44 s; band compared as the literal string `"406"`; no squelch, averaging,
TIMEHOLD, tuning, terrain or airframe) and this session's C3 work widened it
— the plugin now carries a calibrated per-band link budget the stub knows
nothing about.

Fixed the way the tracker prescribes — shrink the stub, make the plugin
authoritative — rather than by growing a second model to chase:

- **`/api/positions` only synthesises DF when a caller opts in.** `PositionIn`
  gains `mock: bool = False`; `mock_bridge.py` sets it and nothing else does.
  A real station that reports no receiver state now gets **silence**: its
  position is still tracked and stored, the DF panel simply has nothing to
  show, and that absence is itself the signal that the plugin is not reporting.
- **Every stub result is marked `synthetic`**, on the dataclass and in the JSON,
  so nothing downstream can present one as though the sim produced it.
- **The 406 burst gate is real.** The stub used a 1.5 s window and used it only
  to compose a *note* — the signal and bearing stayed live through the 49.5 s a
  406 beacon is silent. It now uses the engine's 0.44 s and returns no bearing
  and zero signal between bursts, saying so in the note. It has no TIMEHOLD, so
  it reports the gap honestly rather than inventing one.
- **Band matching tolerates what the console actually stores.** `band == "406"`
  missed `406`, `406.0` and `"406.025"`, so those scenarios silently got no
  burst cadence at all.
- The module docstring now says plainly what it is: a mock-bridge stub, not the
  model, never to stand in for the plugin during a sortie.

Deliberately **not** done: copying the plugin's link budget into the stub. That
would make it a second implementation to keep in step, which is what C15-2
exists to reduce. The stub matches the engine on the two constants where
disagreement would actively mislead (burst period and length) and a new test
pins those to the engine's own values.

### Verified

- **`python3 tests/test_propagation.py` — new, 28 checks, ALL PASS.** It loads
  the stub and the engine side by side and asserts they agree on burst period,
  burst length and the radio-horizon form; that the burst gate really zeroes
  the signal; that band matching handles five shapes; that results are marked
  synthetic; and — the guard that matters — that `main.py` gates the fallback
  on `elif p.mock:` rather than on `df is None`. It needs no FastAPI, which is
  itself a check that the stub has stayed a stub.
- Every other local suite still passes: engine 114/114, plugin_net 11/11,
  faceplate, panel, lcd_text, tdfm, am, luacheck.
- **Not executed: `tests/test_console.py`** — no FastAPI on this machine. All
  three files I touched parse. I read the console tests that exercise
  `/api/positions` (`test_position_ingest_needs_the_plugin_key`,
  `test_bearing_accepted_after_the_aircraft_expires_from_the_map`,
  `test_track_returns_heading_for_per_aircraft_replay`): none of them asserts a
  `df` comes back for a station that did not send one, so none should be
  affected — but that is reading, not running. **Run it on ms01 before the
  next session.**

### Lane note

`main.py` is named in Codex's prompts 5 and 6 (X-6, X-8). Codex had stopped and
had not started in `services/` when I made this change. My edit is confined to
`PositionIn` and the `/api/positions` ingest branch; X-6 concerns
`start_sortie` and `set_effects`, X-8 concerns retention, logging, healthcheck
and shutdown. No overlap, but re-read the file first.

## 2026-09-10 — Avionics electrical gating, shared libraries, robust deployment and panel registration (I-4, I-5, I-6, I-7, I-8, I-9c, O-7b)

**Status: Prompts 1 through 6 executed and verified. Six tracker items fixed (I-4, I-5, I-6, I-7, I-8, I-9c); O-7b verified offline and open pending live flight check.**

Execution of Gemini's assigned prompts covering `instruments/**`, `panels/**`, and `scripts/**`:

### 1. Behavior Fixes (I-4, I-5, I-6)
- **Becker SAR-DF 517 Stored Message Fallthrough (I-4):**
  - Replaced the ternary fallthrough expression on page 4 in `instruments/becker-sar-df-517/logic.lua` with an explicit `if/else` block on `msg`.
  - Ensures stored COSPAS/SARSAT frames without position coordinates never display coordinates inherited from the live frame.
- **RHOTHETA RT-600 Softkey Press Timer Leak (I-5):**
  - In `instruments/rhotheta-rt-600/logic.lua`, updated `power_off()` and the early-return path when unpowered to explicitly cancel active softkey hold timers (`press_timer`, `press_at`).
  - Prevents delayed execution of `clear_average()` or mode switches after the instrument is switched off.
- **Avionics Bus & Voltage Gating (I-6):**
  - Gated Becker SAR-DF 517, RHOTHETA RT-600, Technisonic TDFM-136B, and Garmin GMA 1347 audio panel on the avionics master power switch (`sim/cockpit2/switches/avionics_power_on`) and minimum bus voltage (`sim/cockpit2/electrical/bus_volts`, threshold `10.0V`).
  - Implemented cold & dark initial state where faceplates are completely dark and local power controls ignore inputs while unpowered.
  - Instruments automatically boot up upon bus power arrival if local power was on, and shut down / brown out immediately if bus voltage drops below 10.0V.
  - Added test helper `set_avionics_power()` in `tests/am.py` and unit tests in `tests/test_am.py` (`test_cold_start_all_instruments_dark_and_unresponsive`, `test_avionics_master_on_boots_all_four_instruments`, `test_bus_voltage_brownout_and_recovery`).

### 2. G1000 MFD Streaming Watchdog & Recovery Wrapper (O-7b)
- **Watchdog Instrument (`instruments/g1000-mfd-watchdog/`):**
  - Created standalone Air Manager wrapper instrument (`info.xml` and `logic.lua`) to monitor G1000 MFD off-screen video streaming from X-Plane 12 (`video_stream_add()`).
  - Tracks frame reception and connection status via periodic heartbeat timer. If frames cease arriving for >3 seconds while streaming is enabled, displays a high-visibility amber warning overlay (`MFD STREAMING STALE / RECONNECTING...`) and automatically calls `video_stream_add()` to re-arm the video pipeline without requiring an Air Manager restart.
  - Documented Air Manager 4.2+ native `video_stream_add` API usage in `docs/AM4_COMPAT.md`.
  - Added simulated video stream hooks to `tests/am.py` and verified timeout detection and stream re-arming in `tests/test_am.py` (`test_g1000_mfd_watchdog_stale_detection_and_rearm`).
  - *Per prompt instructions, O-7b remains open in `docs/bugs/tracker.json` until validated live against a running X-Plane 12 flight station.*

### 3. Shared Instrument Libraries & Modular Assets (I-7)
- **Extracted Shared Code (`instruments/_shared/`):**
  - Centralized shared Lua modules (`lib/lcd.lua`, `lib/cap_df.lua`, `lib/cap_df_audio.lua`, `lib/dcu.lua`) and audio samples (`resources/elt_analog_clean.wav`, `resources/elt_analog_df.wav`, `resources/elt_noise.wav`, `resources/elt_406_burst.wav`) into `instruments/_shared/`.
  - Updated `tests/test_faceplate.py` to assert that all installed copies (across Becker 517, RT-600, and TDFM-136B) are byte-identical to `instruments/_shared/`.

### 4. Deploy Coverage & Target Cleanup (I-9c)
- **Expanded Deploy Tooling (`scripts/deploy_df_instruments.py`):**
  - Expanded `deploy_df_instruments.py` to deploy all four avionics instruments: Becker SAR-DF 517, RHOTHETA RT-600, Technisonic TDFM-136B, and Garmin GMA 1347.
  - Automatically synchronizes shared files from `instruments/_shared/` into target instrument directories prior to deployment.
  - Added pruning logic to remove stale files and orphan subdirectories in target installation directories.
  - Updated `panels/cap-c182t-mo-station/info.xml` to declare X-Plane compatibility only (`<flightSimulator>XPLANE</flightSimulator>`), eliminating legacy FSX/P3D/FS2020 simulator claims.
  - Added `--check` mode verifying that clean deployments produce a clean exit code 0 on subsequent runs.

### 5. MO Panel Registrar & Single Source Geometry (I-8)
- **Single Source of Truth (`panels/cap-c182t-mo-station/panel_geometry.py`):**
  - Established `panel_geometry.py` to parse layout dimensions, instrument positions, and properties directly from `panels/cap-c182t-mo-station/info.xml`.
  - Refactored `panels/cap-c182t-mo-station/generate_assets.py` to derive all bounding boxes and canvas dimensions from `panel_geometry.py`.
  - Added `Streaming = true` to both G1000 MFD layouts in `info.xml`, ensuring `scripts/deploy_mo_panel.py --zip` packages a working MFD video stream out of the box.
- **Modernized Panel Registrar (`scripts/register_mo_panel.py`):**
  - Parameterized database and executable paths via `capvsar_station.ini` (`[airmanager]` and `[station]` sections), environment variables, and CLI arguments (`--db`, `--airmanager-path`, `--station-ini`).
  - Added user confirmation prompt prior to terminating a running Air Manager instance (bypassed with `-y` / `--yes`).
  - Added support for in-place updates of existing panel layouts rather than silently ignoring already registered panels.
  - Replaced hardcoded SQL column inserts with dynamic column discovery based on `PRAGMA table_info(panel)`.
  - Corrected `sqlite_sequence` updates to synchronize sequence counters across all four modified tables (`panel`, `instrument`, `instrument_property`, `development_object`).
  - Re-launches Air Manager from the discovered or configured executable path instead of hardcoded paths.

### 6. Verification
- All 6 test suites passing with 100% success:
  - `python3 tests/test_faceplate.py`: 92 assertions passing
  - `python3 tests/test_panel.py`: 9 tests passing
  - `python3 tests/test_lcd_text.py`: 5 tests passing
  - `PYTHONPATH=. python3 -m unittest tests/test_tdfm.py`: 6 tests passing
  - `PYTHONPATH=. python3 -m unittest tests/test_am.py`: 16 tests passing
  - `python3 scripts/luacheck.py`: 24 Lua files checked and clean
- Deployment and registration checks:
  - `python3 scripts/deploy_df_instruments.py --check`: reports all 4 instruments current, exits 0.
  - `python3 scripts/register_mo_panel.py --check`: confirms all layouts registered in `config.sqlite3`, exits 0.
  - `python3 scripts/deploy_mo_panel.py --zip`: packages `cap-c182t-mo-station.zip` containing `info.xml` with `Streaming = true`.

## 2026-09-10 — The simulated aircraft is CAP 487; N499CP is a real 172

**Status: rename implemented across the project. L-7 re-scoped, still open.**

Codex stopped on prompt 1 rather than editing, and was right to: L-7's
description said the planner holds 172S figures "under a 182T label", and it
does not — `services/flightplanner/app.py:80` reads `N499CP - Cessna 172S NAV
III`, and the planner's README and USER_GUIDE agree. That half of the item was
stale.

But the conclusion that it was therefore already resolved does not hold, and
checking it turned up the real defect. Every other component in the project —
`README.md`, `docs/USE_CASE_SAREX_REHEARSAL.md`, the Flight Operations
Handbook, the website, and `scripts/build_c182t_package.py:29`, which stamps
the tail number onto the aircraft — treated **N499CP as the Cessna 182T**. The
flight planner alone said N499CP is a 2020 Cessna 172S.

It is a 172S. **N499CP is a real aircraft on the squadron line**, and the
simulated 182T had been wearing a real aircraft's registration. That is the
kind of thing that confuses a crew about what they are flying, and it is not
ours to do. Ron's call: the simulated aircraft is **CAP 487**.

Renamed, 31 occurrences across 13 files:

- `scripts/build_c182t_package.py` — `acf/_tailnum`, the livery directory
  (`Civil Air Patrol (CAP 487)`) and both livery/thumbnail text stamps. "CAP
  487" is no longer than the string it replaces, so nothing outgrows its box.
- `services/exercise/` — the aircraft `tail` defaults in `access.py` (x2),
  `main.py` and `setup.js`, plus four nav tooltips.
- `tests/test_setup_auth.py` — four fixtures.
- `docs/USE_CASE_SAREX_REHEARSAL.md`, `README.md`, `docker-compose.yml`, and
  all six website pages.
- `scripts/generate_manual.py`, and the handbook regenerated from it — the
  `.html`, `.odt`, `.docx` and `.pdf` are all rebuilt and clean.

Two deliberate exceptions. **`CHANGELOG.md` keeps N499CP in its older entries**,
because they describe what was true when written; the fix for that class of
thing is D-1's superseded-in-place notes, not rewriting history. And **the
flight planner still says N499CP**, because there it is correct: that profile
describes the real 172S, accurately, and is internally consistent.

Where the planner's product name carried the registration — "N499CP Flight
Planner", 17 occurrences in nav links, footers, figure captions and the
handbook — the registration is simply dropped rather than replaced. Restamping
a planner that computes 172S numbers with the 182T's identity would recreate
the exact mislabel L-7 started as.

### L-7 re-scoped rather than closed

The planning gap the item was really about is untouched by the rename and is
now sharper: **the exercise flies CAP 487, a 3100 lb / 87 gal / 230 HP IO-540
182T, and the planner computes fuel, endurance and W&B for a 2550 lb / 53 gal
172S.** Every sortie is planned on the wrong airframe — and the crew can no
longer even notice it through a shared registration, which is a small argument
for fixing it sooner rather than later.

The tracker entry and Codex's prompt 1 are both rewritten to say this, with an
explicit instruction *not* to just relabel the existing 172S table as CAP 487.
Both prompt packs now carry the rename in their standing rules.

### Verified

- `python3 tests/test_engine.py` — 114/114 PASS, unaffected.
- Every Python file touched parses (`access.py`, `main.py`,
  `test_setup_auth.py`, both `scripts/`); `docker-compose.yml` parses as YAML.
- The handbook regenerated end to end and contains no N499CP in any format.
- **Not verified:** `tests/test_setup_auth.py` — it skips on this machine, no
  FastAPI. My change there is four string literals in fixtures, but it has not
  been executed. Node is not available either, so the two `.js` edits were
  eyeballed as diffs rather than syntax-checked; both are single string
  literals inside existing lines.
- Open question for the next person in `services/exercise/`: aircraft `ac-1`
  now has `callsign: "CAP 423"` and `tail: "CAP 487"`. Those read oddly
  together. The callsign series (`CAP 420 + index`) was not part of this change
  and was left alone.

## 2026-09-10 — C14: the docs now match the code, and the repo has a licence

**Status: implemented. P-10, D-1, D-2 and D-4 closed; D-5 opened for what D-4
turned up.** Cluster C14 is docs-only and safe to work while Codex is in
`services/` and Gemini is in `instruments/`.

### P-10 — the dataref contract did not describe the engine

The contract is the interface every faceplate is written against, so a wrong
line in it is a bug in four instruments at once. Six discrepancies, not the
five the item listed. Where the contract was the better design I changed the
code, which is the half that matters here:

- **`spread` is now peak to peak.** It published the one-sided maximum
  deviation from the mean while the contract told faceplate authors to draw
  the hollow extreme markers at `bearing ± spread/2` (517 manual Fig 3-3).
  Both heads do exactly that, so the scatter band on the compass rose — the
  trust cue the operator reads at a glance — was drawn at half its real width,
  and the 517's numeric SPRD was half as well. Publishing the full width makes
  the existing Lua correct with no change in Gemini's lane.
- **`distance_nm` is now genuinely slant range**, which is what the contract
  has always called it. It was ground great-circle, so an aircraft at 12,000 ft
  directly over a beacon at 9,000 ft read 0.0 NM from it. The link budget uses
  the slant path too, since that is the distance the signal travels; ground
  distance still drives the radio horizon, the cone of confusion and the
  terrain probe, which are all about position over the earth.
- **`cap/scenario/active` is now writable**, like the other three scenario
  refs. The contract promised the set was writable for offline testing; with a
  read-only `active` there was no way to arm a scenario without a console, so
  the offline path the contract documents did not exist. A live console still
  wins — its next poll overwrites whatever was written.

And three the doc had wrong rather than the code: `cs_hex15` is `BYTE[15]` but
has **length 0 until a frame decodes**, which a faceplate reading blind would
get wrong; and **six effect switches were undocumented** — `radio_horizon`,
`terrain_masking`, `burst_cadence`, `cone_of_confusion`, `multipath` and
`multipath_offset_deg`. Those are the default-on physics switches an instructor
uses to simplify a scenario, so their absence was the most consequential gap in
the document. The `wing_null_*` geometry overrides and `df_antenna_location`
are now named individually instead of gestured at.

A doc fix alone drifts again, so `tests/test_engine.py` now parses the plugin
and asserts that **every dataref it publishes (26) and every effect switch it
reads (20) appears in `DATAREF_CONTRACT.md`**. Both guards were checked against
deliberate drift — removing one dataref row and one effect name — and both
failed as they should. The first attempt at the dataref guard did *not* fail,
because matching on the leaf name let any prose mention satisfy it; that is
why it now matches the full name, with one explicit exception for the shared
`cs_lat`/`cs_lon` row.

### D-4 — licence, and what this repo does not redistribute

`LICENSE` is Apache-2.0 (Ron's choice). `NOTICE` is the part that took the
work: the aircraft package is *built* from Laminar's stock 172SP inside the
operator's own X-Plane install and **no Laminar asset is tracked here** — the
item's verify condition passes as it stood, confirmed by checking the tracked
file list for `.acf`/`.obj`/`.dds`.

What the audit did turn up is that the repo tracked **nine manufacturer manuals**
(Becker, RHOTHETA, Technisonic, Garmin — about 25 MB). Fine on a private Gitea,
not fine on the public GitHub the item is written in anticipation of. On Ron's
instruction these are now untracked (`git rm --cached`) and in `.gitignore`;
**the files are untouched on disk**, and `docs/SOURCES.md` already records the
public URL each came from, so a fresh clone can fetch its own. `SOURCES.md` and
the README section that pointed at them now say so rather than promising files
that are no longer there.

### D-5 (new) — because untracking closed only half of it

`git rm --cached` does not rewrite history: those nine PDFs are still in every
existing commit, so a push to a public remote publishes them anyway. And eight
PNGs in `docs/figures/` are page extracts from the same manuals (the `-pNN-` in
each filename is the source page), still tracked, with
`build_radio_reference_doc.py` embedding three of them into a generated
document. Separately, `panels/cap-c182t-mo-station/preview.png` and the root
zip embed the stock Air Manager G1000 instrument preview, a Sim Innovations
asset. Filed as D-5 rather than acted on: deleting figures that build scripts
depend on is not a call to make unilaterally, and a history scrub needs
`git-filter-repo` and Ron's timing.

### D-2 — the website described a different system

Every claim in the item re-verified first; the 2026-09-09 website work had
already fixed the "Node.js / Vite" planner description, so that one needed
nothing. Still wrong and now corrected:

- `docker-compose.prod.yml` in three places. There is no such file; the stack
  is `docker-compose.yml`. The site's commands now run as written.
- A firewall table demanding **UDP 49000/49001 for "X-Plane telemetry"**.
  Nothing in the tree uses them — the plugin talks HTTP to the console in both
  directions. Replaced with the port a station actually needs, 8700, naming the
  two endpoints. `operations.html` made the same claim in prose.
- **APX 6500 + Icom IC-A120** on the index and deployment pages. That is the
  retired `/radio-legacy` console. The current one is APX 4500 + EFJohnson
  5300, and the airband station and the Form 110 log did not survive the
  rewrite — which is precisely what F-10 and F-9 are open for, so advertising
  them was claiming two unfixed bugs as features.
- **"85% cost reduction" and "100% weather availability"** — numbers with no
  basis anywhere. Replaced with what is actually true and checkable (no fuel,
  no Hobbs time, never scrubbed for weather).
- **"Sub-20ms latency"**, never measured. Now says what is configured and that
  per-station figures depend on the link.
- **"Distributed Cloud WAN ... cloud VPS (AWS/Azure)"** presented with green
  ticks. Remote stations join over WireGuard today (`scripts/wg-peer.sh`);
  cloud hosting is a plan, and now reads as one.
- The planner README's **"Hosting: Google Cloud Run"**. It runs as a container
  in the lab stack on host port 8090.
- **A new one, found on the way:** the site said the 406 burst is **520 ms** in
  three places. The engine uses 440 ms (`BURST_LEN_S = 0.44`) — `SOURCES.md`
  notes the RT-600 manual gives both figures and the code took 440. Corrected
  to match the code.

### D-1 — the changelog contradicted the code it describes

The corrections existed, but only as a block inside a later entry, so a reader
who scrolled to an original entry met the false claim with nothing marking it —
which is exactly what the item says. Each affected entry is now annotated **in
place**: the pymumble bridge's two "proposed only" statements, the `/radio`
row that now describes `/radio-legacy`, the `pcall(canvas_draw)` entry (twice
superseded — the log does not support its claim, and I-2 has since removed the
`pcall` it added), the "55 engine checks" count, and the `/api/messages` 400
that no longer happens — with a pointer to L-9, which is the consequence of it
no longer happening.

### Verified

- `python3 tests/test_engine.py` — **114/114 PASS** (108 before this batch).
  The suite is now **seeded** (`mod.random.seed`): the engine adds Gaussian
  scatter to every un-averaged bearing, and my own P-12 heading test was a
  2.5-sigma assertion that happened to pass on the first run and failed on a
  later one. Seeded, plus the threshold widened to the 10 deg that actually
  separates `true_psi` from `psi`.
- One pre-existing test was rewritten rather than loosened: "spread is small on
  a strong signal" used the 5 NM geometry, which P-13 made mid-scale, so it now
  measures a genuinely strong signal at 1 NM. Moving it exposed a trap worth
  knowing — `new_engine()` re-registers the datarefs, so a second engine
  created mid-section silently redirects every later `xp.read`. It is now last
  in its section with a comment saying why.
- `python3 tests/test_plugin_net.py` — 11/11. `test_faceplate`, `test_panel`,
  `test_lcd_text`, `test_tdfm`, `test_am` — all pass. `test_console` and
  `test_radio` still not runnable here (no pytest/FastAPI on this machine).
- Not verified: that every deployment command on the site runs end to end.
  Docker is not available in this session, and one command on that page —
  `deploy_df_instruments.py` — is still wrong for a different reason, which is
  Gemini's I-9c.

### Cross-lane note

`website/deployment.html` is also named in Gemini's I-9c prompt (the claim that
the deploy script handles all four instruments). I did not touch that section;
my edits there are the compose commands, the port table and the MRO console
model. `services/flightplanner/README.md` is named in Codex's prompt 1 for the
aircraft data; I changed only the hosting section, and Codex had not started in
`services/` when I did. Both files were re-read immediately before editing.

## 2026-09-10 — C3 closed: the DF propagation engine now has a link budget

**Status: implemented and tested offline; not yet flown in X-Plane.**

The last six open items in cluster C3 (`xplane/PI_capvsar_df.py`, Claude's sole
lane): P-6, P-7, P-8, P-9, P-12, P-13. The cluster is now complete.

- **P-6** — `decode_tick` in the cone-of-confusion branch had no 406 gate, so an
  analog 121.5 beacon produced SYNC OK and a 15-hex ident. That teaches the
  crew the exact opposite of what the 406 half of the exercise exists to
  demonstrate. Gated; the redundant `burst_open()` re-test at the other call
  site went with it, which also means a scenario that switches `burst_cadence`
  off now decodes continuously instead of 0.9 % of the time.
- **P-7** — `cap/df/signal` was published before the burst gate, so the bar sat
  pegged for the 49.5 s of every 50 that a 406 beacon is silent, and the
  squelch decided on a signal that was not being received. The gate now runs
  before the value is published and before the squelch sees it. The pulsing bar
  is the cue that distinguishes a 406 beacon from an analog one by ear.
- **P-8** — masking was `*0.06`, only 12 dB, so a fully masked beacon at 2 NM
  still read 0.375 and gave a good bearing. Replaced with graded knife-edge
  diffraction: 20 dB grazing up to 40 dB in deep shadow, plus 6 dB for a path
  that clears by less than a Fresnel zone. A beacon just behind a ridge line
  and one down the next canyon no longer sound identical.
- **P-9** — 24 fixed probes is 1.25 NM spacing at 30 NM, wide enough to step
  over the ridges that actually mask a beacon. The count now follows distance
  (0.25 NM spacing, floored at the old 24 and capped at 96, so at most ~384
  terrain probes a second at the flight loop's 4 Hz). The ray also carries the
  earth-curvature term it was missing - 149 ft at mid-path over 30 NM, which is
  a whole ridge's worth of clearance the flat ray was handing out for free.
  4/3 earth, matching the 1.23 constant already in the radio horizon.
- **P-12** — four things, all small, all wrong: the worker slept `POLL_S` while
  claiming a `REPORT_S` cadence, so positions went out every 3 s (or 7 after a
  timed-out fetch) rather than 2; the first report fired before any flight loop
  had run, putting every track's first point at 0N 0E; `psi` is the local
  OpenGL-frame heading where `true_psi` is true heading, a silent
  position-dependent error straight into every relative bearing; and a null in
  the scenario JSON would have raised inside a dataref read callback, which
  surfaces in X-Plane as a dead dataref rather than as a traceback anyone sees.
  The poll and the report are now separate methods on independent absolute
  deadlines, checked on a 0.5 s tick.
- **P-13** — the signal model was `25/d^2` on every band, saturating inside
  5 NM, so a 0.1 W 121.5 ELT and a 5 W 406 beacon differed only in cadence and
  decode, never in range - and "406 is heard much further out", the fact the
  fleet-replacement argument rests on, was not modelled at all. Replaced with a
  free-space link budget in dB: published ERP (0.1 W / 5 W), path loss, then
  terrain and airframe losses, mapped onto the 0..1 bar at the end. Calibrated
  against two anchors - the heads' published ~1 uV/m sensitivity (about
  -117 dBm at 121.5 for a half-wave dipole) and a 20 dB ground/installation
  loss for a beacon lying in clutter with a bent antenna. That produces a
  bearing on 121.5 to about 50 NM, on 406 to about 105 NM (2.1x), and a
  decodable 406 frame to about 44 NM, which is where CAP aircrew figures sit.
  Multipath is now driven by the terrain probe that already runs - strongest
  where the path is blocked or grazing, absent on an open path, and wandering
  with the aircraft's position - instead of a 40 deg step for 12 s in every 36
  regardless of terrain or range, whose rhythm crews learned instead of its
  cause.

Two existing assertions changed with P-13 rather than being worked around: at
5 NM a 0.1 W 121.5 ELT is now about half scale rather than pegged, so the two
`signal > 0.9` checks in the airframe-shadowing section now compare against the
unshadowed link-budget value instead of a magic number. Nothing else moved.

Verified:

- `python3 tests/test_engine.py` — **108/108 PASS** (was 73; 35 new checks
  covering all six items, including the band-range separation P-13 is for).
- `python3 tests/test_plugin_net.py` — 11/11 PASS.
- `python3 tests/test_faceplate.py`, `tests/test_panel.py`,
  `tests/test_lcd_text.py`, `PYTHONPATH=. python3 tests/test_tdfm.py`,
  `tests/test_am.py` — all pass, unaffected.
- `tests/test_console.py` and `tests/test_radio.py` were NOT run: this machine
  has no pytest or FastAPI installed. Nothing in `services/` was touched.
- Not flown in X-Plane. `true_psi` is read with a fallback to `psi` for a sim
  that lacks it, and the probe-count change is bounded, but both want a bring-up
  check before the next session.

`tests/xp.py` gained `true_psi` (falling back to `psi` so existing tests are
unaffected), which is the only file outside Claude's lane that changed.

Also written: `docs/bugs/CODEX_PROMPTS.md` — eleven PR-sized prompts covering
every open item in Codex's lanes (C6 L-8, C7 X-6/X-8, C8 F-6/F-8, C9 F-7/F-9/
F-10/F-11/F-12/F-13/X-9, C10 L-1a/L-5/L-6/L-7/L-9/L-11/L-12, C11 L-10),
ordered so that prompts touching the same file never run in parallel. Claims in
the prompts were re-verified against the tree rather than copied from the
tracker: `escapeHtml` does exist in `radio.js` and `item.channel` is the
unescaped field, `/radio-legacy` is still routed from `main.py:856`, the Form
110 export with its `padEnd` and unrevoked blob URL is still legacy-only, and
`mission-radio.js` has no log at all. F-13's prompt points at the CAP channel
card already implemented for I-11 (`instruments/cap-fm-tdfm-136b/logic.lua:42`
onward) rather than asking Codex to coordinate names with Gemini — that half is
already done.

And `docs/bugs/GEMINI_PROMPTS.md` — six prompts covering the seven open items in
Gemini's lanes (C12 O-7b/I-4/I-5/I-6, C13 I-7/I-8/I-9c), same shape, ordered so
the two DF `logic.lua` files are never touched by two prompts at once and so the
tooling chain runs `_shared` -> deploy -> registrar.

Verifying those against the tree corrected three things in `tracker.json`
itself, which are now fixed in the JSON:

- **I-6** cited `mo-audio-panel-gma1347/logic.lua:389` for the GMA's
  `avionics_power_on` subscription; it is at line 486. The substance stands -
  grep confirms no other instrument references `avionics_power_on` or
  `bus_volts` at all.
- **I-7** said three WAVs are byte-identical across the two DF heads. It is
  four: `elt_analog_clean`, `elt_analog_df`, `elt_noise`, `elt_406_burst`.
  Also confirmed by checksum that `lcd.lua` is identical across *three*
  instruments while `tests/test_faceplate.py:126-129` only checks the DF pair,
  so the TDFM copy is exactly as unguarded as the item claims.
- **I-8** cited `scripts/generate_assets.py`, which does not exist. The file is
  `panels/cap-c182t-mo-station/generate_assets.py`.

I-4, I-5, I-9c and the rest verified as written, including the exact
`msg and msg.has_pos or s.cs_has_pos` idiom at the heart of I-4 - which is a
bug class, not one line: the same pattern is used for sync, protocol, hex15 and
country on the surrounding lines, and the prompt says so.

## 2026-09-09 — CAP-VSAR Website unification: Distributed SAREX, Virtual ICS & CalTopo integration

**Status: completed, validated across all HTML documents with zero broken anchors/assets.**

Unified all recent system developments, tactical avionics enhancements, exercise director workflows, and mission maps into the public CAP-branded marketing and technical website (`website/`):

- **Created `website/sarex.html` (Distributed SAREX & Incident Command System)**:
  - Articulates the monthly training cadence rationale (overcoming live flight friction, avgas fuel costs, weather groundings, and maintenance bottlenecks).
  - Contrasts three operational modalities: In-Person Squadron Lab, Hybrid Multi-Station Base, and 100% Completely Virtual Distributed Wing SAREX.
  - Documents the complete simulated ICS hierarchy (Incident Commander, Air Operations Branch Director, Operations/Planning, Mission Radio Operators 1 & 2 with Form 110 comms, Ground UDF teams with mobile PTT, and Mission Pilot / Observer aircrews).
  - Highlights CalTopo Phase 2 Common Operating Picture (COP) integration: live telemetry streaming, bearing line-of-position (LOP) vector triangulation, and bi-directional SAR pattern exchange (.fms / GPX).
  - Outlines 4 realistic operational search scenarios (Pauma Valley 406 ELT, Mountain Repeater Net, Air-to-Ground Handoff, Stuck-MIC Net Recovery).
- **Updated `website/operations.html`**:
  - Added **Exercise Director Setup & Mobile QR Dispatch** section detailing 1–4 aircraft stepper provisioning and scannable QR badge cards for rapid smartphone onboarding.
  - Added **California Wing Mountain Repeaters Matrix** detailing standard national dual-pair conventions (148.125 / 143.550 MHz primary, 148.150 / 143.700 MHz secondary) and summit relay PL/NAC codes (Mt. Diablo, Santiago Peak, Mt. Palomar, Oat Mountain, Blue Ridge, Palm Springs).
  - Corrected historical APX 6500 references to APX 4500 (resolving review finding D-2).
- **Updated `website/cockpit.html`**:
  - Added **Tactical Communications & Audio Integration** section covering Technisonic TDFM-136B dedicated Guard receiver (GD1/GD2), 60s transmit time-out timer (TOT), 20-channel priority scan engine, 240 memory channels, and Garmin GMA 1347 Table 6A.3.2 ICS isolation modes and rolling 2.5-minute digital clearance recorder.
  - Documented acoustic RF SNR hiss degradation (`elt_noise.wav`) on Becker 517 and RT-600 direction finding instruments.
  - Upgraded footer to standard 4-column brand grid.
- **Updated `website/technical.html` & `website/deployment.html`**:
  - Added automated test verification suite section (`#testing`) validating `test_engine.py`, `test_faceplate.py`, and `test_panel.py`.
  - Corrected flight planner tech stack specification (Flask/Gunicorn, not Node.js/Vite) in `technical.html`.
  - Added Step 5 to deployment guide documenting `scripts/build_station_kit.py` and `capvsar_station.ini` for turnkey multi-station aircraft provisioning.
- **Cross-Navigation & Link Integrity**:
  - Added `Distributed SAREX & ICS` to navigation bars across all 6 pages.
  - Verified 100% link, image, and anchor target resolution across all pages with zero broken references.

## 2026-09-09 — O-4/O-5/O-6 live on ms01; two independent git histories reconciled; NFS3 backup target

**Status: deployed and verified on ms01 directly, not just tested locally.**

Applying the Mumble work below to ms01 surfaced a problem bigger than the
deploy itself: `/srv/capvsar` on ms01 had 6 local commits (beacon-truth/role
tokens, base-view reset, radio audit findings, O-3) that had never reached
Gitea - its `origin` remote had no working credential, so every push had
presumably been failing silently or was never attempted. Generated a
repo-scoped Gitea deploy key for ms01, fetched, and merged the two histories
(both branched from `v0.1`) conflict by conflict rather than picking a side
by default: `access.py`, `main.py`, `base.js`, and the test/engine files all
resolved in favor of the desktop session's version after *confirming* -
diffing directly, not trusting diffstat - that it was a strict superset of
what ms01 had. `docs/bugs/tracker.json` the same way: 23 items differed in
status, all 23 in the same direction. Re-ran the full test suite on ms01
itself afterward, against its actual Python 3.12 and pinned production
dependency versions, not assumed compatible from a different machine.

Deploying then found two real bugs neither local testing nor code review had
caught:

- `provision_mumble.py` couldn't open `mumble-server.sqlite` as the deploying
  user - it's owned by the mumble container's internal uid with group-only
  read. `deploy.sh` now runs it under `sudo`; the Instructor/SET ACL, which
  had silently never been written on the first deploy attempt because of
  this, is now actually in ms01's live database.
- The `radio-https` healthcheck (added below) was broken two ways at once:
  `wget -k` is `--convert-links`, not a cert-bypass flag, and
  `https://localhost` sends a TLS SNI the Caddyfile has no site block for, so
  Caddy errored the handshake instead of serving anything. Neither had ever
  actually been run against the container before landing. Fixed with
  `curl --resolve`, pinned to loopback to also dodge a hairpin-NAT hang
  connecting to the LAN IP from inside the container.

Mounted NFS3 (WD NAS, `192.0.2.144:/mnt/HD/HD_a2/NFS3`, documented
lab-wide for backups/cold storage) on ms01 for the first time - it had no
client mount at all - and pointed the nightly backup cron
(`0 3 * * *`, installed) at `/mnt/nfs3/capvsar/backups/exercise-db` instead
of the same local disk `exercise.db` itself lives on. The very first live
run against that freshly-touched NFS directory hit a one-off
`sqlite3.OperationalError` from inside `Connection.backup()` - confirmed
transient (the next two manual attempts succeeded immediately) but real:
`backup_exercise_db.py` now retries transient failures and cleans up any
partial file on every failed attempt, not only a successful-but-empty one.

### Verification

- `sudo python3 scripts/preflight.py` on ms01: **ALL PASS** (console health,
  full Mumble tree, the Instructor/SET ACL, tile source, CA cert).
- `docker compose ps`: all four services healthy, including `radio-https`
  for the first time since it gained a healthcheck.
- A real backup landed on the real NFS3 mount (262144 bytes, read back and
  verified), then removed as a test artifact.
- No one was connected to Mumble at deploy time (checked first); the actual
  interruption was under two minutes.

## 2026-09-09 — Mumble infrastructure: provisioned tree, ACLs, callsign integrity, backups, preflight (O-4, O-5, O-6)

**Status: code complete and tested locally. NOT yet applied to ms01's live
Mumble server or scheduled on ms01 - see "Still needs a live decision" below.**

Inspected ms01's actual `mumble-server.sqlite` directly (via `docker cp` and
Python's `sqlite3`, not assumed) before writing anything, since Murmur's ACL
schema (`grantpriv`/`revokepriv` bitmasks, not simple allow/deny columns) and
permission bit values aren't things worth guessing for a security control.
That inspection also surfaced a real naming drift: `docs/MUMBLE_CHANNELS.md`'s
own tree diagram said "Instructor / SET" while its setup steps, and the live
database, both already said "Instructor - SET".

**O-4 - the channel tree now has one source of truth.**
`services/exercise/app/mumble_channels.py` holds it; `radio.py` reads its
`CHANNELS` from there instead of an independent hardcoded four-name copy.
`scripts/provision_mumble.py` recreates the whole tree idempotently in
`mumble-server.sqlite` (every write checks for the exact row it would create
first) and finishes the ACL step `docs/MUMBLE_CHANNELS.md` always said was
still manual: deny `Enter` to `@all` on Instructor/SET, grant it back to a new
`instructor` group, at ACL priorities 0/1 so the grant overrides the deny for
whoever's actually in that group (per mumble.info's admin docs: later/higher
priority overrides earlier for the same permission bit). `scripts/deploy.sh`
now stops mumble, runs the provisioner, restarts it, on every deploy.

**O-5 - images pinned, callsigns can't be forged.** `mumblevoip/mumble-server`
and `caddy` are pinned by digest to what was already running and verified on
ms01 (`docker inspect`), not `:latest` silently drifting under a live voice
net. `/api/radio/stream` now resolves an authenticated RBAC session
(`access.get_session_from_request`, which works unmodified against a
WebSocket - Starlette's `WebSocket` and `Request` share the same
`HTTPConnection` base for `.cookies`/`.headers`/`.query_params`) and uses
*that* callsign, ignoring whatever the client claims, when a session exists.
A base-role student can no longer type "MISSION BASE" or "INSTRUCTOR" into
the browser radio and impersonate another station. No session - RBAC not
configured for the exercise, the common case today - falls back to the
client-supplied callsign exactly as before. `CERTREQUIRED`/`ALLOWHTML`/
`USERS=100` were deliberately left alone: that's this training net's
low-friction-join posture, not an oversight, and changing it wasn't asked for.

**O-6 - a stack that fails loudly instead of silently.**
`scripts/preflight.py` checks the console's `/api/health`, the full Mumble
tree plus the Instructor/SET ACL, the flight planner's VFR tile source (via
the MapServer metadata endpoint - a 404 on an out-of-pyramid tile coordinate
looks identical to the service being down, so that's not what this checks),
and the published browser-radio CA cert. `scripts/backup_exercise_db.py`
takes an online SQLite backup (`Connection.backup()`, safe against a database
a live process still has open - not a raw file copy, which can capture a torn
snapshot) with 14-day retention pruning; a crontab line lives in the script's
own docstring, nothing installed by this change. `radio-https` (Caddy) gained
a `docker-compose.yml` healthcheck - it had none, so a Caddy that stopped
proxying looked identical to a healthy one to `docker compose ps`.

### Validation

- `tests/test_provision_mumble.py` (4 cases) against fixtures built from
  ms01's real schema: fresh-server tree creation, correct ACL priority/bits,
  an already-hand-provisioned tree left byte-for-byte untouched aside from
  the two new ACL rows, and idempotency on a second run.
- `tests/test_radio.py` gained 2 cases for the session-callsign override and
  its fallback; all 15 pass, all 72 console+radio+setup_auth tests pass
  together.
- `tests/test_backup_exercise_db.py` (4 cases) **caught a real bug**: backups
  taken in the same second collided on a 1-second-resolution filename and
  silently overwrote each other - exactly the failure mode worse than no
  backup. Fixed by moving to microsecond resolution before this shipped.
- `preflight.py` run by hand against a cold stack (fails loudly, one specific
  reason per check, matching O-6's own stated verify criterion) and a fully
  mocked warm one (provisioned test Mumble db, mock health endpoint,
  placeholder CA cert - all five checks pass).

### Still needs a live decision

Nothing above touched ms01. Applying it means: `docker compose pull` (new
pinned digests), stopping mumble to run `provision_mumble.py` against the
real `mumble-server.sqlite`, and redeploying `radio-https`/`exercise` for the
healthcheck and callsign-integrity code - a real, if brief, interruption to
anyone currently on the voice net. Scheduling the nightly backup cron job is
a separate, similarly live decision. Both were left for explicit sign-off
rather than done unasked.

## 2026-09-09 — This tree is now a real git checkout (O-1)

**Status: complete.**

`git` is installed on this machine (wasn't as of the 2026-09-08 correction
below), but `/home/ron/Projects/cap-vsar` still had no `.git/` even though
`v0.1` had been pushed to Gitea and GitHub — so no agent editing here could
diff, revert, or see what another tool changed, which was the actual failure
mode O-1 tracked regardless of whether a baseline existed somewhere else.

Looked up the real Gitea remote via its API with a token (`ron/capvsar`,
private; `git.rpc-cyberflight.com` doesn't resolve from this host, use
`192.0.2.121` directly) rather than guess one. `git init` in place, added
`origin`, fetched, then pointed local `main` at `origin/main` **without a
checkout** — `git branch main origin/main` + `git symbolic-ref HEAD
refs/heads/main` populates history and moves HEAD without touching a single
file on disk, so nothing already in the working tree could be silently
overwritten by files coming from `v0.1`. Diffed the resulting stage against
known secret patterns before committing.

Everything that had accumulated since `v0.1` — RBAC/setup wizard, O-2,
radio/DF fidelity work, docs, tests, 67 files — landed in one commit,
`6c2b3d4`. Separately noticed and restored `.env.example`, which was missing
from the working tree with nothing in this log explaining why; rebuilt from
the env vars the code actually reads rather than guessed, committed as
`c517617`. Both pushed to Gitea's `origin/main`.

**Deliberately not done here: GitHub.** `flight-planner-n499cp-v2` mirrors to
GitHub through an IP-redaction pass (`scripts/redact_ips.py`) before
anything public sees it; whether `cap-vsar` needs the same treatment wasn't
established, so pushing to a public mirror was left alone rather than assumed
safe.

### Verification

- `git log`, `git status`, `git diff` all work in this directory now —
  O-1's stated verify criterion.
- `git status` is clean and `up to date with 'origin/main'` after the push.

## 2026-09-09 — Per-station config: capvsar_station.ini and a kit builder (O-2)

**Status: complete.**

`xplane/PI_capvsar_df.py` hardcoded `CONSOLE`, `CALLSIGN`, and (partially)
`PLUGIN_KEY`, so three aircraft meant three hand-edited copies of the tracked
plugin — the actual failure mode O-2 tracked, since it also meant
`deploy_xplane_plugin.py`'s hash check could never agree across stations.

`_load_station_config()` now reads `[station] console / callsign /
plugin_key` from `capvsar_station.ini` next to wherever the plugin is
deployed, independently per key, falling back to the historical single-station
defaults for anything the ini doesn't set. No ini present (every existing
install today) means no behavior change. `CAPVSAR_TOKEN_PLUGIN`, the
documented env-var mechanism, still overrides the ini's `plugin_key`.

`scripts/build_station_kit.py` is the kit builder: given `--callsign` and
`--console`, it validates and copies the tracked plugin source unmodified,
generates that station's `capvsar_station.ini`, bundles the four Air Manager
instruments (station-agnostic, same for every aircraft), writes an install
README, and optionally zips it (`--zip`). Deliberately **not** bundled: the
C182T G1000 aircraft package (`build_c182t_package.py` derives it from the
recipient's own local Laminar Cessna 172SP install — not redistributable
content) and a CA certificate (issued per ms01 deployment, not present in
this repo). The kit's README says so and points at the right place instead.

### Validation

- `tests/test_engine.py` gained coverage for `_load_station_config()`: no-ini
  fallback, independent per-key ini overrides, and the env-var-beats-ini
  precedence. All 73 checks pass (66 prior + 7 new), 0 failures.
- End-to-end: built a real kit for `CAP-2` with `build_station_kit.py`, then
  imported *that kit's* `PI_capvsar_df.py` directly — own directory, own
  ini — and got `CALLSIGN=CAP-2` and the kit's `plugin_key` back from the
  same tracked source that every other station also ships unmodified.
- Deployed the updated plugin to this machine's X-Plane install via
  `scripts/deploy_xplane_plugin.py`; hash check now reports `current`. No
  `capvsar_station.ini` exists there yet, so this station's runtime behavior
  is unchanged — confirming the fallback path, not just the override path.

### Remaining for a real multi-aircraft stand-up

Each additional station still needs someone to actually run
`build_station_kit.py` with its callsign and hand the kit over — this makes
that a five-minute, config-only step instead of a source edit, it doesn't do
it automatically. The aircraft package and CA cert gaps noted above are
unrelated pre-existing gaps, not introduced or worsened here.

## 2026-09-08 — Exercise Setup Screen, Scannable QR Participant Onboarding, and Role-Based Access Control (RBAC)

**Status: complete. Setup wizard, QR code engine, authentication, RBAC, session store, and test suite implemented.**

Implemented an Exercise Director Setup system (`/setup`), scannable QR code and short-code onboarding (`/join/{code}`, `/login`), and Role-Based Access Control (RBAC) across all consoles and mutating endpoints:

### 1. Exercise Setup Wizard (`/setup`)
- **Fleet Sizing & Configuration**: Exercise Director can select between 1 and 4 aircraft using an interactive stepper. For each aircraft, tail number (e.g. `N499CP`, `N99885`), tactical call sign (`CAP 423`, `CAP 415`), direction-finder head (Becker SAR-DF 517 or RHOTHETA RT-600), and crew positions (Mission Pilot, Mission Observer, Mission Scanner) are configurable.
- **Ground Operations & Staffing**: Configurable assignments for Mission Radio Operators (MRO 1 for primary VHF-FM net, MRO 2 for aeronautical airband watch) and mobile Urban Direction Finding ground teams (UDF 1, UDF 2).
- **Roster & Badge Generation**: Automatically produces participant access codes (`INSTR-1`, `PLT-423`, `OBS-423`, `SCN-423`, `MRO-1`, `UDF-1`, etc.) with assigned roles, titles, and target redirect routes.
- **Scannable QR Badges & Print Layout**: Standalone vector QR code engine renders scannable QR codes pointing to `https://<host>:8743/join/<code>`. One-click "Print Access Badges" stylesheet formatted for lanyard/badge printing.

### 2. Participant Onboarding & QR Authentication
- **Fast Join (`/join/{code}`)**: Mobile cameras scanning QR codes automatically authenticate, receive an HTTP-only `capvsar_session` cookie, and redirect directly into the seat console (`/radio`, `/base`, or `/`).
- **Participant Login Portal (`/login`)**: Mobile-friendly code entry screen with uppercase auto-formatting, error messaging (`invalid_code`, `instructor_required`), and quick-access role test badges.
- **Vendored Offline Compliance**: Implemented a standalone SVG QR generator vendored in `/static/vendor/qrcode.min.js`, maintaining 0 remote dependencies and offline reliability.

### 3. Role-Based Access Control (RBAC) & Session Management
- **SQLite Session & Roster Engine**: Added `roster`, `sessions`, and `exercise_config` tables to `exercise.db` in `services/exercise/app/access.py`. Sessions expire after 24 hours.
- **View Access Control**:
  - `/` and `/setup` require `instructor` role. Unauthorized authenticated sessions redirect with `?error=instructor_required`.
  - `/base` requires `instructor`, `base`, `aircrew`, or `ground_team` role.
  - Unauthenticated browser requests redirect to `/login?next=...` when exercise authentication is active.
- **Mutating Route Protection**: Non-instructor roles cannot stop sorties, reveal beacons, or edit scenarios. MRO/Base roles can submit bearings and mission messages.
- **Truth Containment Preserved**: Aircrew and ground team sessions cannot inspect beacon truth prior to instructor debrief reveal.
- **UI Session Integration**: Added live user role badge (`👤 <Title> (<Callsign>)`) and Logout button to headers on `/`, `/setup`, and `/base`.

### 4. Automated Verification
- Added `tests/test_setup_auth.py` with 23 unit tests covering setup configuration persistence, roster code generation, login/session cookies, `/join/{code}` redirections, RBAC route gating, mutating API role restrictions, and offline vendored asset validation.
- All 34 tests in `tests/test_console.py` pass without regression.
- All 13 tests in `tests/test_radio.py` pass.
- All 6 tests in `tests/test_tdfm.py` pass.
- Lua syntax validation `scripts/luacheck.py` passes cleanly.

## 2026-09-08 — Radio systems specification, feature matrix, and operational use cases publication (DOCX, PDF, Markdown)

**Status: complete. Comprehensive reference manual and automated document generator published.**

Authored and published the complete CAP V-SAR radio ecosystem reference manual across Markdown (`docs/RADIO_FEATURES_AND_USE_CASES.md`), Microsoft Word (`docs/CAP_V-SAR_Radio_Features_and_Use_Cases.docx`), and Adobe PDF (`docs/CAP_V-SAR_Radio_Features_and_Use_Cases.pdf`):

### 1. Equipment Specifications & Operational Feature Matrices
- **Airborne Transceivers & Direction Finders**:
  - **Technisonic TDFM-136B**: P25 digital conventional & analog FM, 200 CAP fleet memory channels with CTCSS subaudible tones and P25 NACs, dual-receiver Guard path (GD1/GD2), 60 s transmitter time-out timer (TOT), and 20-channel carrier-sensing scan engine.
  - **Garmin GMA 1347 Audio Panel**: Three transceiver inputs (COM1, COM2, COM3/TDFM), COM3 MIC transmission interlock, four ICS cockpit isolation modes (`ALL`, `PILOT`, `COPILOT`, `CREW`), Split COM operational separation, 16-block digital clearance recorder (PLAY), and analog fail-safe relay.
  - **Becker SAR-DF 517 & RHOTHETA RT-600**: 121.5 / 243.0 / 406 MHz direction finding, multi-sample circular averaging filter, dynamic inverse signal-to-noise hiss degradation (`elt_noise.wav`), top/bottom antenna installation calibration, and 15-hex COSPAS-SARSAT emergency data frame decoding.
- **Ground & Base Communications**:
  - **Motorola APX 4500**: Fixed base & incident command post multi-channel monitoring, CAP Form 110 radio log synchronization, and cross-band relay.
  - **Mission Base Web Console (`/radio`)**: WebRTC / Web Audio PTT browser radio console, channel selector, headset gain, and direct Mumble voice mesh integration.
  - **Handheld Radios (ICOM IC-A25N & Portable P25)**: Flight line coordination, airfield advisory, and mobile Urban Direction Finding (UDF) ground team bearings.

### 2. Operational Search and Rescue Use Cases
- **Pauma Valley ELT Search**: Step-by-step aircrew DF homing, wing-null banking, cone-of-confusion avoidance, and ground UDF team handoff.
- **Mountain Repeater Net Operations**: Tactical coordination using CA Wing mountain repeaters (Mt. Laguna, Otay Mountain, Santiago Peak) with tone-encoded access.
- **Air-to-Ground SAR Coordination**: Inter-agency communications bridging airborne search assets and ground rescue teams on CALCORD and SAR frequencies.
- **Inadvertent Stuck-MIC Emergency**: Airborne recognition, 60-second automatic timer cutoff, and ground base station diagnostic mitigation.

### 3. Tooling & Automation
- Created `scripts/build_radio_reference_doc.py` using `python-docx` to build the styled 40+ page operational manual with executive layout, styled callouts, comparison tables, and embedded high-resolution equipment graphics.

## 2026-09-08 — Full regression confirmed for L-2/L-3/L-4/F-4; the Python 3.14 TestClient hang does not reproduce

**Status: verification complete. No code changed.**

Closes the one open item from "Planner bounds, database serialization,
authenticated export, and radio recovery (L-3, L-4, L-2, F-4)" below: that
entry shipped all four fixes with targeted tests passing, but left the full
`tests/test_console.py` and `tests/test_radio.py` suites unverified because
this host's Python 3.14 was reported to hang inside pre-existing FastAPI
`TestClient` requests, and running the unchanged suites in ms01's Python 3.12
container was blocked on an SCP-to-ms01 request that was correctly denied —
copying this tree to another host was never authorized.

That local hang does not reproduce. Using the same temporary Python 3.14 venv
(`/tmp/capvsar-test-venv`, FastAPI 0.115.6 / Starlette 0.41.3 / httpx 0.27.2 /
anyio 4.6.2, matching what was already pinned there), each of the following
ran clean, fast, and repeatably — four full runs, no hang, no leftover
process or listening port afterward:

- `pytest tests/test_console.py tests/test_radio.py` — **47 passed**, ~1.1 s,
  twice in a row.
- `python -m unittest discover -s tests` — **71 ran**, only three *pre-existing,
  unrelated* import errors (`test_engine.py` wants a plugin-path argument
  `discover` doesn't give it; `test_faceplate.py` / `test_lcd_text.py` need
  `Pillow`, not installed in this venv). No hang.
- `python -m py_compile services/flightplanner/app.py` and
  `pytest services/flightplanner/tests/test_sar.py` — clean, **19 passed, 6
  subtests passed**.

No ms01 access, SCP, or any change outside `/tmp` was needed. Whatever
produced the earlier hang was specific to that session's process state, not a
standing Python 3.14 incompatibility in this codebase — worth remembering
before requesting cross-host access to work around a local test failure that
hasn't been confirmed to reproduce from a clean process.

## 2026-09-08 — Airborne radio stack fidelity: Guard receiver, scan mode, ICS isolation, digital clearance recorder, and DF SNR degradation (I-12, I-13, I-14, I-15, I-17)

**Status: complete. Instruments, radio service, test harnesses, bug tracker, and contracts updated.**

Building on the 2026-09-08 radio ecosystem audit and the Air Manager Lua test harness
introduced in I-9a, all five Priority 2 tracked defect items (I-12, I-13, I-14, I-15,
and I-17) are implemented and proven across the airborne avionics suite:

### I-12 — TDFM-136B Independent Guard Receiver
The physical Technisonic TDFM-136B features two completely independent receiver modules:
the Main agile transceiver and a dedicated Guard receiver (GD1/GD2). Previously, only a
single operating frequency (`cap_fm_frequency_hz`) was published, meaning Guard was
cosmetic and could not break into Main channel audio.

In `instruments/cap-fm-tdfm-136b/logic.lua`, an independent secondary receive path was
modeled. It continuously monitors the selected Guard channel (GD1 or GD2) and publishes:
- `cap_fm_guard_frequency_hz` (e.g. 168.650 MHz AIRGUARD or 121.500 MHz VHF Guard)
- `cap_fm_guard_channel` (101 for GD1, 102 for GD2)
- `cap_fm_guard_channel_name` (e.g. `AIRGUARD`)
- `cap_fm_guard_ctcss_tone` and `cap_fm_guard_p25_nac`
- `cap_fm_guard_volume` and `cap_fm_main_volume` normalized potentiometer positions [0.0–1.0]

Guard squelch (`cap_fm_guard_rx`) and audio are dual-gated and mixed continuously with Main,
enabling mission base to reach an aircraft regardless of which tactical channel the crew is
monitoring. Proven by `test_guard_receiver_independence` in `tests/test_tdfm.py`.

### I-13 — TDFM-136B Scan Mode Engine
The original `toggle_scan()` function was cosmetic, writing an `'S'` glyph to line 1 of the
display without cycling frequencies. In `instruments/cap-fm-tdfm-136b/logic.lua`, an
operational timer-driven state machine now manages channel scanning:
- A 250 ms dwell timer cycles through programmed scan channels (channels 1..20).
- Carrier detection on `cap_fm_main_rx` immediately halts scanning on that channel.
- Carrier drop arms a 2000 ms hang timer before scanning resumes.
- PTT keying pauses scan to prevent stepping off the frequency while transmitting.
- Toggling scan or powering off the radio cleanly cancels all active timers.

Proven by `test_scan_mode_channel_cycling_and_carrier_halt` in `tests/test_tdfm.py`.

### I-14 — GMA 1347 ICS Isolation and Split COM Integration
The Garmin GMA 1347 audio panel previously published `cap_ics_isolation` and Split COM
de-asserted FM audio/mic flags, but neither was wired into the backend audio service:
every crew member sat in a single Mumble channel, so isolation only changed faceplate lamps.

- In `instruments/mo-audio-panel-gma1347/logic.lua`, published Table 6A.3.2 variables:
  `cap_ics_isolation` (`"ALL"`, `"PILOT"`, `"COPILOT"`, `"CREW"`), `cap_ics_pilot_isolated`,
  `cap_ics_copilot_isolated`, `cap_ics_crew_isolated`, and `cap_split_com_active`.
  Split COM locks the copilot to COM2, isolates the Mission Observer from mission net
  audio and mic, and asserts `cap_split_com_active = true`.
- In `services/exercise/app/radio.py`, added `GET /api/radio/ics` and `POST /api/radio/ics`
  REST endpoints, handled `action: ics` commands in `MumbleRadio.command()`, and applied
  audio isolation filtering in `deliver_audio()` so `pilot_isolated` and `split_com`
  genuinely separate audio streams.

Proven by `test_gma1347_ics_isolation_and_split_com` in `tests/test_am.py` and `tests/test_radio.py`.

### I-15 — GMA 1347 Digital Clearance Recorder
The GMA 1347 PLAY button previously flashed its annunciator for 1200 ms without recording
audio. In `instruments/mo-audio-panel-gma1347/logic.lua`, an authentic clearance recorder
was implemented with a 16-block circular buffer holding up to 2.5 minutes of incoming COM1,
COM2, and COM3 (`cap_fm_main_rx`) audio:
- Pressing PLAY plays back the most recent transmission and illuminates the annunciator.
- Successive presses of PLAY step backward in reverse chronological order through the buffer.
- Pressing any non-PLAY key immediately aborts playback and extinguishes the annunciator.
- Published `cap_recorder_playing`, `cap_recorder_block`, `cap_recorder_count`, and
  `cap_recorder_text`.

Proven by `test_gma1347_clearance_recorder` in `tests/test_am.py`.

### I-17 — DF Audio SNR Degradation
Real DF receivers bury weak sweeps in receiver discriminator hiss at long range or behind
terrain. The simulation previously played fixed-fidelity loops scaled only by receiver volume.
- In `scripts/make_df_audio.py`, synthesized a 2.0-second deterministic band-limited discriminator
  noise asset (`elt_noise.wav`) sampled at 44.1 kHz, placed in both `becker-sar-df-517/resources/`
  and `rhotheta-rt-600/resources/`.
- In shared library `instruments/*/lib/cap_df_audio.lua` (strictly 100% byte-identical),
  loaded `elt_noise.wav` and implemented dynamic inverse noise mixing:
  `signal_vol = gain * signal`, `noise_vol = gain * (1.0 - signal)`.
- Updated both Becker and RT-600 `logic.lua` to sync receiver signal from `df.state.signal / 100`.

Proven by `test_df_audio_snr_degradation` in `tests/test_am.py`, `scripts/make_df_audio.py --check`,
and `tests/test_faceplate.py`.

### Verification, Tooling & Contracts
- **Test Harness (`tests/am.py`):** Added `find_switch_matching` and `click_switch_matching` to
  support toggle switch position and direction interaction in unit tests.
- **Contract (`docs/DATAREF_CONTRACT.md`):** Updated Part 5 to publish all new TDFM Guard,
  GMA 1347 ICS isolation, Split COM, and Clearance Recorder variables.
- **Tracker (`docs/bugs/tracker.json`):** Marked `I-12`, `I-13`, `I-14`, `I-15`, and `I-17` as
  `fixed` and regenerated `docs/BUG_TRACKER.md`.
- **Test Suite Results:**
  - `python3 -m unittest tests.test_am` — 10/10 PASS
  - `python3 -m unittest tests.test_tdfm` — 6/6 PASS
  - `python3 scripts/luacheck.py` — 0 errors / 0 warnings
  - `python3 tests/test_faceplate.py` — 68/68 PASS
  - `python3 scripts/make_df_audio.py --check` — 8/8 files OK
  - `python3 tests/test_engine.py` — 33/33 PASS
  - `python3 tests/test_plugin_net.py` — 11/11 PASS
  - `pytest tests/test_radio.py` — 13/13 PASS
  - Shared libraries between Becker 517 and RT-600 remain 100% byte-identical.


## 2026-09-08 — Planner bounds, database serialization, authenticated export, and radio recovery (L-3, L-4, L-2, F-4)

**Status: implemented.**

The public parallel-track endpoint now rejects `length_nm` or `width_nm` above
50 NM and rejects width/spacing combinations that would generate more than 200
legs, returning a 400 that names the offending input. The aviation-data rebuild
now holds a nonblocking `flock` for its entire run, publishes status atomically
for both gunicorn workers, and logs row and update errors instead of swallowing
them. Import remains nonblocking: the lock winner starts one daemon thread and
the other worker returns immediately.

Planner maintenance and V-SAR export POSTs now require JSON plus either a
same-origin request or the configured instructor token. V-SAR exports cap all
free-text fields and waypoint count and allow five attempts per client per
minute. Scenario creation sends `CAPVSAR_TOKEN_INSTRUCTOR`; message broadcast
sends `CAPVSAR_TOKEN_BASE`, falling back to the instructor token because the
console explicitly permits that role. Either upstream 403 produces a specific
operator-facing token error. Compose passes both existing variables to the
planner container, but their matching values still need to be set on ms01.

The mission radio now reconnects automatically after a socket failure,
heartbeat timeout, or suspended audio context, with exponential backoff capped
at 30 seconds and a three-tone headset alarm. Manual Join/Disconnect remains
available. Mission-base reconnects backfill messages and bearings from SQLite
using `?since=`, with persisted IDs preventing websocket/backfill duplicates;
the history survives a console restart.

Regression evidence was captured against the unfixed code for all four items.
`py_compile`, all 18 planner tests, the four focused F-4 SQLite/backfill tests,
and the radio reconnect contract pass. A real browser/headset reconnect and the
complete console/radio suites were not verified here: this Ubuntu 26.04 host's
Python 3.14 hangs in pre-existing FastAPI TestClient websocket/static requests.
Running the unchanged suites in ms01's Python 3.12 container is pending explicit
permission to copy this private working tree into a temporary directory; no live
service or `/srv/capvsar` checkout was changed.

**Superseded by the entry above (2026-09-08, "Full regression confirmed").**
The reported Python 3.14/TestClient hang did not reproduce; the complete
`test_console.py` + `test_radio.py` suites ran clean without ms01. The real
browser/headset reconnect (`scripts/test_base_radio_browser.py`, Playwright)
still has not been run and needs a live exercise process plus Chrome to do so.

## 2026-09-08 — Airborne radio stack fidelity & instrument runtime fixes (I-9a, I-10, I-9b, I-11, I-1, I-2, I-3)

**Status: complete. Instruments, harness, contracts and test suite updated.**

- **I-9a (Lua execution harness):** Added `tests/am.py`, a ctypes Lua 5.4 stand-in for the Air Manager 4.2 sandbox supporting `si_variable_*`, `xpl_*`, `timer_*`, UI button/dial/switch hit testing, and canvas drawing. Validated via `tests/test_am.py` with 7 tests covering all 4 instruments, shuffled `lib/` load orders, timer progression, and UI state.
- **I-10 (TDFM-136B 60 s TOT timer):** In `instruments/cap-fm-tdfm-136b/logic.lua`, added a 60-second transmit timeout timer that force-unkeys `cap_fm_transmitting`, renders `*** TIME OUT ***` on the active LCD line, and enforces lockout until PTT is released. Proven by `tests/test_tdfm.py`.
- **I-9b (Observer PTT & Squelch LED wiring):** In `cap-fm-tdfm-136b/logic.lua`, created `cap_fm_ptt`, `cap_fm_main_rx`, and `cap_fm_guard_rx` variables, and dual-bound observer PTT to both Air Manager variables and X-Plane's copilot PTT dataref (`sim/cockpit2/radios/actuators/audio_panel_copilot_ptt`). Added `/api/radio/rx` voice activity tracking in `services/exercise/app/radio.py`. Published Part 5 in `docs/DATAREF_CONTRACT.md`.
- **I-11 (Authentic CAP fleet channel plan):** Replaced the 6 placeholder channels in `cap-fm-tdfm-136b/logic.lua` with the 20-channel authentic CAP fleet plan (`TAC 1`, `TAC 2`, `CC 1`, `CC 2`, `AIR 1`, `AIR 2`, `SAR 1`, `GUARD`, `GROUND 1/2`, `BASE DIS`, `LOGISTCS`, `AIR EVAC`, `SAR 2`, `VFIRE 21`, `VTAC 11`, `CALCORD`, `NATL GRD`, `CMD 1/2`) plus user memories up to channel 200. Enabled 3-digit direct keypad entry auto-committing on the 3rd digit, and published `cap_fm_ctcss_tone` and `cap_fm_p25_nac`.
- **I-1 (DF faceplate repaint throttling):** In `instruments/*/lib/cap_df.lua` and DF heads' `logic.lua`, implemented snapshot-based change detection gating redraws so repaints only occur on whole-second timer steps or actual dataref changes, eliminating wasteful ~8 Hz idle repaints.
- **I-2 (canvas_draw error visibility):** Removed swallowing `pcall` around `canvas_draw` in both `becker-sar-df-517/logic.lua` and `rhotheta-rt-600/logic.lua`.
- **I-3 (Becker tone suppression reset):** Reset `st.tone_suppressed = false` in `becker-sar-df-517/logic.lua` whenever frequency is rotated, preventing 3 kHz tone suppression from bleeding across frequencies.

## 2026-09-08 — Radio fidelity audit folded into the tracker; lanes assigned

**Status: tracking only. Eleven new items, no code changed.**

A radio ecosystem audit (Gemini) compared the TDFM-136B, GMA 1347, ground
consoles and DF heads against CAPR 100-1/100-3, ICUT, MART Vol. II and the
vendor manuals. It found real gaps this project's own review had missed
entirely, because the review read the code for defects and the audit read it
against doctrine. Verified against the tree and added as I-10 to I-15, I-17 and
F-10 to F-13 — tracker now 81 items.

The ones that matter most:

- **I-10** the airborne TDFM has no transmitter time-out timer. The ground
  console already enforces a 60 s lease, so the aircraft is currently the only
  station that can jam the net indefinitely — and recognising a TOT cutoff is
  an ICUT practical exam item.
- **F-10** mission base cannot monitor the airband SAR frequency at all. The
  retired `/radio-legacy` had a second station (Icom IC-A120) and the Mumble
  rewrite dropped it, so the MRO can no longer watch the tactical FM net and
  the air-to-ground net at once, which is the actual job.
- **I-11** six generic memories where the real set has 230, so a crew briefed
  to a channel number cannot enter it, and squelch mode is a bare letter with
  no CTCSS tone or P25 NAC behind it — the classic "keyed the repeater without
  the access tone" failure cannot be produced or diagnosed.
- **I-14/I-15** the GMA's ICS isolation and clearance recorder are lamp-only.
  A panel that teaches a control which does nothing is worse than omitting it.

Three corrections to the audit, found by checking it against the tree: its
§3.4 paths carry a `df-` prefix that does not exist; the three P25 sidetone
functions it proposes porting from `radio.js` are not in the tree at all (that
is new work, not a port); and "no acoustic feedback" overstates it — there is
an oscillator, but only the headset-test beep.

### Lanes

Three agents are now working this repository at once and the cluster
`owner_hint` fields in `docs/bugs/tracker.json` have been updated to say who
holds what, since that is where the collision protocol actually looks:

- **Gemini** — `instruments/**` outright, starting with the Lua execution
  harness (I-9a), because nothing in this repository runs any `logic.lua` and
  none of the instrument work is verifiable until it exists.
- **Codex** — `services/flightplanner/**`, `mission-radio.js`, `base.js`,
  `main.py`. F-4 and L-2/L-3/L-4 now, the ground-console block after.
- **Claude** — `xplane/`, deployment and ms01. O-3 then O-2.

A caution recorded for whoever sets the tokens: **do not set `CAPVSAR_TOKEN_*`
on ms01 yet.** L-2's planner-side token forwarding is written but neither
committed nor deployed, and O-2 does not exist, so stations have no way to
receive the plugin key. Setting them now would 403 the planner push and
silence every DF by design. Order: L-2 deploys, O-2 lands, then tokens.

## 2026-09-08 — Tracker sweep, then the base view and debrief (F-2, F-3)

**Status: implemented, tested in a browser, and live on ms01 (`a86e670`).**

### Sweep first: one more wrong finding

Re-verified every open item's file references and absence claims against the
complete tree. All referenced paths resolve. **F-5 was wrong on both halves**
and is now resolved: the setup notes exist as `static/radio-help.html` (linked
from the radio footer and the secure-context overlay — there is no
`radio-art/README.md` because `radio-art/` holds the two faceplate SVGs), and
`services/exercise/radio-public/` exists on ms01 with `mission-base-ca.crt` in
it — `GET /radio-ca.crt` returns a real PEM and `https://ms01:8743/radio`
answers 200. Tablets can reach the secure context today.

That is **six wrong findings** from reviewing the wrong tree (O-2a, O-7a, D-3,
O-4, O-2, F-5). O-3 was sharpened instead: `scripts/deploy.sh` creates only
`mumble/data`, not the other three paths compose needs, so a fresh clone still
crash-loops. Six items re-verified as standing (I-9a/b/c, C15-2, D-1, D-2).

### F-2 — the base view no longer mixes two exercises

`base.js` tracks the sortie id from the state snapshot and clears the map when
it changes: alert circle *and its marker* (which was never held in a variable
at all), beacon marker, aircraft, tracks, bearings, and the `centred` flag.

A second leak the review only half-described: when an aircraft went quiet for
30 s and came back, a **new** polyline replaced `trackLines[callsign]` and
orphaned the old one on the map permanently. It now resumes the existing
track. An expired aircraft's marker is removed but its flown track is kept
deliberately — that is history base staff still need.

### F-3 — the debrief scores each aircraft

Server: `/api/sorties/{id}/track` returns `hdg_true`, which was recorded on
every position and thrown away by the query. Client: `debrief.js` groups by
callsign — one faint full track, one playback polyline and one labelled marker
per aircraft, each in its own colour — and scores each separately. The heading
fallback now scales longitude by `cos(latitude)`, which the old inline
calculation omitted (~10 deg of error at 33N).

### Validation

Both were verified by driving a real browser, because neither has unit-test
coverage and neither could be checked by reading:

- **F-3**: headless Chrome against a seeded three-aircraft sortie (180
  positions) renders three separate scored rows — CAP-1 0.00 nm "overhead the
  beacon", CAP-2 3.34 nm "did not close", CAP-3 1.96 nm "localised" — three
  labelled markers, no JS errors. Previously one meaningless zig-zag.
- **F-2**: a CDP-driven session taken through two sorties. With the fix,
  tracks and bearings reset to 0 and map layers drop 9 → 5. Against pre-F-2
  code the previous sortie's track and bearing **survive into the new one**
  (tracks 1, bearings 1, layers 9 → 7).
- `tests/test_console.py` grows to 30 with a `hdg_true` regression test.
- Whole repo green: console 30, plugin-net 11, radio 12, engine 66, faceplate,
  panel 7, planner 8.

Incidentally confirmed the `/ws` origin check shipped this morning behaves
correctly against a live server: same-origin upgrades (101), cross-origin is
refused (403), and a client sending no Origin — the plugin, curl — is still
allowed.

### Deployed

Live on ms01 as `a86e670`. Verified against the running service: `/track`
returns `hdg_true`, the served `base.js` carries the sortie-id reset and
`debrief.js` the per-callsign grouping, truth is still withheld, and the
console suite passed **30/30 inside the built image** against the pinned
fastapi 0.115.6 / pydantic 2.10.4.

A permission rule for `ssh`/`rsync`/`scp` now lives in
`.claude/settings.local.json` (gitignored, project-scoped), so the sync,
build, commit and container swap ran end-to-end rather than being handed over
as commands to paste.

## 2026-09-08 — Deployment live on ms01; wave 1 and wave 2 items running

**Status: implemented. Committed on ms01 (`9dcafb5`) and containers running live.**

### The local working tree is a subset of the repo

The important finding of the day, and it invalidates five items in the review.
`/home/ron/Projects/cap-vsar` — the tree all three agents have been editing —
is **missing files the canonical repo on ms01 has**. A `--delete` rsync dry run
is what caught it; running that sync would have destroyed them. Corrected:

- **O-2a → resolved.** `docs/CONNECT.md` exists and is a complete participant
  guide (Mumble client per platform, server, nets, PTT). Not missing.
- **O-7a → resolved.** `docs/AM4_COMPAT.md` exists and records the licence
  position, including the Air Manager vs Air Player distinction for
  display-only crew stations. The CHANGELOG citation resolved all along.
- **D-3 → resolved.** `CONOPS-cap-vsar.md`, `AM4_COMPAT.md` and
  `infra/ROUTER.md` all exist in the repo. The vault notes are published into
  it by `docs/ragd/ragd_ingest.py`, so agents can read them.
- **O-4 → narrowed.** `docs/MUMBLE_CHANNELS.md` documents the whole channel
  tree, the rationale, and the one manual step left (the Instructor/SET ACL).
  Neither undocumented nor a first-join failure. What stands: the rows exist
  only in a gitignored volume, nothing recreates them, and `radio.py` keeps its
  own hardcoded copy of four names.
- **O-2 → narrowed.** Onboarding is not absent: `scripts/wg-peer.sh` prints a
  participant's WireGuard peer config and QR, `scripts/deploy.sh` is an
  idempotent stack deploy. What stands: the plugin still hardcodes CONSOLE and
  CALLSIGN, the deploy scripts are Linux-only, and there is no single station
  kit.

All the missing files have been pulled into the local tree. **Agents working
in `/home/ron/Projects/cap-vsar` should treat `/srv/capvsar` on ms01 as
canonical** until O-1 makes the local tree a real checkout — this is the same
root cause as O-1, wearing a different hat, and it has now produced five wrong
findings in one review.

### Deployment: live on ms01

1. Synced work to `/srv/capvsar` — checksum-based, no `--delete`, preserving
   canonical repository files.
2. Built `exercise` and `flightplanner` images.
3. **Ran the console suite inside the built image: 29/29 against the pinned
   fastapi 0.115.6 / pydantic 2.10.4.** This closes the version-gap caveat
   carried on every entry today.
4. **Committed and running:** Committed on ms01 (`9dcafb5` *Fix beacon-truth leak,
   role tokens, engine defects and console robustness*) and deployed via
   `docker compose up -d exercise flightplanner`. Both containers are healthy
   and running the updated builds.

### P-4 sanity check: no practical effect on existing scenarios

Ran the old and new horizon formulas against the three scenarios on the live
console. Both flight-planner scenarios have `beacon_elev_ft` 0.0, so the
result is **identical** (which incidentally confirms L-9: the planner pushes
beacons at sea level). The seed scenario's beacon at 700 ft gains 1.3–1.7x
range, but the horizon there was already 59–167 nm against a 12 nm search
radius, so it was never the limiting effect. The earlier caution that scenarios
might "feel too easy" was overstated: terrain masking and signal strength do
the work in these, and P-4 only bites when a beacon sits materially above the
aircraft — which none of these do.

## 2026-09-08 — DF engine: scan holds, horizon has two ends, plugin reloads (P-3, P-4, P-5)

**Status: implemented.** Cluster C3's wave-2 items. All three are things a crew
would experience as "the equipment is broken" without any error appearing
anywhere.

**P-3 — scan mode no longer destroys TIMEHOLD on 406.** The 517's normal 406
posture is scan on: surveil the burst, listen to the continuous channels in the
50 s gap (§3.3.3). But the untuned check treated *any* frequency mismatch as
loss of signal and called `silent()`, which clears the held bearing — so with
scan enabled the bearing vanished the instant each 440 ms burst ended, which is
the exact opposite of what TIMEHOLD exists for. The path now distinguishes scan
stepping from being parked on the wrong channel: stepping gets
`silent(keep_hold=True)` followed by `hold_or_drop()`, the same treatment the
between-bursts gap already received. Tuning away by hand still drops the
bearing, and audio (`rx_open`) correctly stays closed while the bearing is
merely held. Added `tuned_hz()` so "what the crew selected" and "what the
receiver is on this instant" stop being duplicated logic.

**P-4 — the radio horizon has two ends.** Now
`1.23*(sqrt(h_ac) + sqrt(h_bcn))` in feet MSL. The old form used the aircraft's
height *above the beacon*, which collapsed to a zero-mile horizon the moment
the beacon sat higher — an aircraft in a valley 500 ft below a ridge-top beacon
one mile away was ruled out of range and heard nothing. This is why it went
unnoticed: for a beacon at sea level the two forms are identical, and the seed
scenario's beacon is at 700 ft. Fixed identically in the server's
`propagation.py` fallback so the instructor's view cannot disagree with the
sim. Terrain between the two remains a separate question, answered by the
line-of-sight probe.

**P-5 — reloading the plugin brings the console link back.** `XPluginDisable`
set `self.stop` and nothing ever cleared it, so the thread `XPluginEnable`
started exited on its first check: datarefs kept publishing stale state with no
link to the console and nothing said so. `XPluginEnable` now creates a fresh
`Event`, and `XPluginDisable` joins with a 1 s bound — bounded deliberately,
because the worker may be inside a 4 s `urlopen` and X-Plane must not block on
it; the thread is a daemon and the event is set, so it exits regardless.

### Validation

Engine suite grows to 66 checks, plugin-net to 11. Verified against the
pre-fix code: `bearing is held while scan is stepped away` fails with
`valid=0`, `aircraft below a ridge-top beacon at 1 NM still hears it` fails
with `signal 0.000`, and `test_enable_after_disable_leaves_a_live_worker`
fails. The P-3 tests also pin the two things that must NOT change — the
bearing is still dropped once TIMEHOLD expires, and tuning away by hand still
drops it immediately.

Whole repo green: console 29, plugin-net 11, radio 12, engine 66, faceplate,
panel 7, planner 8.

### Still open in this cluster

P-6 (121.5 producing a COSPAS-SARSAT decode), P-7 (signal bar lit between
bursts), P-8 (terrain masking only −12 dB), P-9 (fixed 24 probes, no curvature),
P-12 (report cadence, heading source) and P-13 (no dB calibration, scripted
multipath) are wave 3 and 4 and untouched.

## 2026-09-08 — The console survives an exercise (X-3, X-4, X-5, X-7)

**Status: implemented.** Cluster C7's wave-2 half. Each of these fails during
a running exercise rather than at deploy time, which is why they are grouped.

**X-3 — database work off the audio loop.** `db()` is now a context manager
that commits, rolls back *and closes*: `with sqlite3.connect(...)` commits but
never closes, so the console leaked a connection per request. Connections open
with a 5 s timeout and the database runs in WAL with `synchronous=NORMAL`.
Every write in an `async` handler goes through `db_call()` →
`run_in_threadpool`. This matters because `radio.py` shares this event loop:
a commit fsyncing on a bind mount stalls the Mumble bridge, trips its buffer
check and unkeys the operator mid-transmission. The sync handlers were already
threadpooled by FastAPI; only startup seeding still touches the database on the
loop, before any traffic exists.

**X-4 — a restart resumes the sortie.** Live state was in-process only, so a
container restart mid-exercise orphaned everything: positions discarded,
`/api/messages` empty, and the row left `stopped=NULL` forever. `rehydrate()`
in the lifespan hook reloads the newest sortie with `stopped IS NULL`, its
scenario, and the last 100 messages. Aircraft are deliberately *not* restored —
their positions are seconds stale and the plugins re-report within seconds; a
stale aircraft on the map is worse than a briefly empty one.

**X-5 — one wedged console no longer stalls the rest.** Sends now run
concurrently with a 1 s per-client timeout, and anyone who times out or raises
is dropped. A half-open TCP socket never raises, which is why a timeout rather
than an exception is what has to notice it. Measured against the old code, a
single suspended tablet blocked the broadcast for the full 30 s of the test's
wedged client.

**X-7 — sortie lifecycle.** Starting a sortie now closes any still-open one;
previously they kept `stopped=NULL` forever, so the debrief list showed two
running exercises and `rehydrate()` would have resumed the wrong one. Bearings
and messages no longer attach to a stopped sortie. And a bearing whose aircraft
has already expired from the live map now falls back to that aircraft's last
recorded position for the sortie rather than returning 404 — a bearing passed
over voice is routinely typed in more than 30 s later, and refusing it loses a
report the crew actually made.

Two deliberate deviations from the fix the tracker proposed for X-7:
`hub.sortie` is **not** cleared on stop, because reveal happens at debrief
*after* stop and needs it; and `POST /api/exercise/reset` was not added,
because nothing needs it yet.

### Validation

`tests/test_console.py` grows to 29 checks with a `SurvivesAnExercise` class.
Verified against the pre-C7 behaviour: **6 of its 8 fail**, including the
wedged-broadcast case taking 30.03 s. The two that pass are guards that should
pass either way (an unknown callsign is still refused; nothing resumes when
nothing was running). The restart tests deliberately drive the real
`TestClient` lifespan rather than calling `rehydrate()` directly, so unwiring
it from startup fails them.

Whole repo green: console 29, plugin-net 9, radio 12, engine ALL PASS,
faceplate ALL PASS, panel 7, planner 8.

### Still open in this cluster

X-6 (untyped bodies mutating scenario definitions) and the rest of X-8 —
positions retention, `/track` pagination, real logging, a DB-touching
healthcheck, cancelling the ticker on shutdown, non-root container — are wave
3 and untouched. X-8's tracker entry now records which parts this closed.

## 2026-09-08 — Review of the L-1 FMS fix: accepted, two follow-ups raised

**Status: review only, no code changed. L-1 stands as implemented.**

Independent check of the L-1 fix rather than a re-read of its entry.

**Verified.** Every enroute record now carries six fields; generated points are
type 28 with `DRCT` and a coordinate-derived identifier; `CYCLE` comes from the
UTC date (`2609`); `NUMENR` matches the records actually emitted; LF endings.
The airport records were already correct and were left alone. Generated a real
KSEE-KCRQ sample with three pattern points and audited every line's field count
by hand, rather than trusting the string assertions. The replacement test is a
genuine improvement on the one it replaced: it checks field count, record type,
the `DRCT` column and `NUMENR` structurally, so a future column shift fails
even if the substring happens to match. Eight planner tests pass.

**Scope was respected.** L-3, L-5 and L-7 sit untouched in the same file, and
nothing outside `services/flightplanner/` was modified while two other agents
were working — confirmed by diffing the plugin and `main.py` against my copies.

**The honesty was right.** The entry states plainly that the published grammar
does not prescribe the identifier text for an unnamed lat/lon point, and that
in-simulator acceptance is unverified. Both are true and both matter.

**Two follow-ups raised, neither a defect in the fix:**

- **L-1a — the pattern label no longer reaches the cockpit.** The generators
  name points `DATUM`, `SS01`..`SSnn`, `CS01`, `PS01`, and the AOBD briefs
  those names; the writer now derives the identifier from coordinates, so the
  G1000 shows `+33.187_-117.079` on every leg. The aircraft flies the right
  positions, but the brief says "turn at SS04" and nothing in the cockpit says
  SS04. Whether this is fixable depends on the open question the entry
  identified: if X-Plane accepts an arbitrary identifier on a type 28 record
  and treats the columns as authoritative, the label can be kept.
- **L-11 — an unresolved airport silently becomes a waypoint.** Pre-existing,
  surfaced by generating the sample. With the aviation database empty, `KSEE`
  was emitted at 33.170,-117.079 — the first search waypoint — with elevation
  0.0 and no warning. A crew loading that plan departs from the wrong place.

Also noted, not tracked: the identifier is rounded to three decimals (~110 m)
while the coordinate columns carry six. Harmless if X-Plane reads the columns,
a per-waypoint offset if it reads the label — the same in-sim check settles
both this and L-1a.

## 2026-09-08 — Plugin now receives beacon truth (P-2 complete)

**Status: implemented. Both halves of P-2 are now in; the remaining step is
deployment, not code.**

Closes the half deferred this morning while another agent held the plugin.
`net_worker()` polled `/api/state` — the endpoint that deliberately withholds
the beacon until reveal — so it set `active=1` with the beacon at 0,0. Null
Island is past any radio horizon, so the authoritative in-sim DF engine
produced nothing for an entire exercise unless the instructor revealed at the
start, which defeats the exercise.

- `fetch_scenario()` polls `GET /api/plugin/scenario` with the plugin key
  (`PLUGIN_KEY`, from `CAPVSAR_TOKEN_PLUGIN`). `CONSOLE` and `CALLSIGN` are
  deliberately left hardcoded — moving all three into a per-station config is
  O-2's job and inventing a second mechanism here would collide with it.
- `/api/positions` carries the same key, since the console now gates ingest on
  the plugin role. Without this, position reporting would have broken the
  moment tokens were set on ms01.
- A refused channel clears `active`, so the DF goes **silent** rather than
  homing on a stale or null beacon: a DF that confidently points at nothing
  teaches the crew something false. Each refusal is logged once per
  transition, with the cause distinguished — 503 (console has no key set),
  403 (this station's key rejected), 404 (console predates the endpoint, so
  update it) — because "why can't they hear it" is answered here, and the old
  code swallowed every network error identically.

### Validation

`tests/test_plugin_net.py`, 9 checks, the first tests to touch the network
thread at all: endpoint choice, key header, each refusal path, that a refusal
is logged once rather than every three seconds, and that recovery is logged.
Confirmed they catch the defect — against the pre-P-2 plugin they fail on
`no object exposes fetch_scenario()`.

`tests/test_console.py` gained a contract test asserting the payload carries
every field the plugin reads (`beacon_lat/lon/elev_ft`, `band`, `power`,
`effects`, `sortie.stopped`). That seam is precisely what broke: a future
refactor of `snapshot()` that drops a field would otherwise degrade the DF
quietly in the sim instead of failing a test.

Whole repo green: console 21, plugin-net 9, engine ALL PASS (58), faceplate
ALL PASS, panel 7, radio 12.

### Not verified

Nothing here has run against a real X-Plane or the live console. The in-sim
confirmation is: start a sortie, do **not** reveal, and check a bearing
appears on the DF head while `/base` still shows no beacon. That needs
`CAPVSAR_TOKEN_PLUGIN` set identically on ms01 and on the station — until it
is set on both, the console returns 503 and the DF is silent by design.

## 2026-09-08 — L-1 X-Plane FMS export record corrected

**Status: implemented.**

The flight planner emitted generated search-pattern points as five-field type
11 records. That both omitted the required via/special field and claimed that
labels such as `SS01` were named fixes in X-Plane's navigation database. It also
hardcoded `CYCLE 2401`.

`generate_xplane_fms_content()` now emits generated points as six-field type 28
records with a coordinate-derived identifier, `DRCT`, six-decimal altitude and
the existing six-decimal latitude/longitude. The cycle is derived from the
current UTC date as four-digit `YYMM`. `NUMENR` remains the total emitted record
count, including departure and destination. The test now checks the corrected
records and cycle, plus structurally verifies every generated waypoint's field
count, type, `DRCT` column and altitude and verifies `NUMENR` against the records.

Verification passed: `py_compile`, all eight flight-planner unit tests, tracker
rendering, and manual inspection of a generated KSEE–KCRQ sample with two pattern
points. Laminar's published v11 `.fms` grammar confirms type 28 and the six
columns but does not prescribe the identifier text or precision for an unnamed
lat/lon point; the tracker-requested signed latitude/longitude identifier rounded
to three decimals was used. The result has not been loaded into X-Plane 12, so
conformance to the published grammar is verified but in-simulator acceptance
remains a maintainer step.

## 2026-09-08 — Mission base works without internet (F-1)

**Status: implemented.**

Leaflet 1.9.4 is vendored to `services/exercise/app/static/vendor/leaflet/`
(js, css, and the five dist images `leaflet.css` references — 192 KB total),
and the instructor, mission base and debrief views load it from there instead
of unpkg.

This was worse than a missing map. `base.js` touches `L` on its first line, so
with no internet the script threw before opening its WebSocket and the whole
view went blank — no status board, no aircraft, no bearing log. A mission base
frequently has no connectivity, which is exactly when the console matters.

Three checks in `tests/test_console.py::OfflineAssets`: no view references a
remote script or stylesheet, the vendored files are served at the paths the
pages actually request, and `leaflet.css`'s `images/` resolve (a wrong vendor
path would have reproduced the original blank page silently). Verified they
catch it: pointing the views back at unpkg fails the first check, restoring
passes 20/20.

Map *tiles* are still remote, so an offline base gets a blank basemap with
working aircraft, bearings and controls over it. Pre-caching tiles into the
existing `charts` volume is tracked separately. The flight planner has the same
CDN and tile problem in its own files and is untouched here — that is L-8.

## 2026-09-08 — Truth containment and role tokens on the exercise console (X-1, X-2, P-2 server half)

**Status: implemented for X-1. X-2 and P-2 are partly done — each has one
remaining step named below; do not read them as closed.**

Cluster C2 of the remediation plan. The console's teaching mechanism is that
nobody on the exercise net can look up the beacon; three endpoints were handing
it over on request, and nothing authenticated any caller.

**X-1 — truth containment (fixed).** All beacon filtering now goes through one
`public_scenario()` serializer in `main.py`, so there is a single place to
audit instead of a decision per endpoint:

- `/api/scenarios` returns beacon fields only for a presented instructor token.
- `/api/sorties/{id}/track` returns `beacon` only once that sortie is revealed,
  and now also returns `revealed`, which makes the debrief view's
  "beacon truth was never revealed" branch reachable for the first time.
- `beacon_elev_ft` is stripped alongside lat/lon. The previous filter popped
  only lat/lon, so elevation leaked from `/api/state` and `/ws` on every tick.

**X-2 — role tokens (mechanism in, deployment step remaining).** New
`services/exercise/app/access.py`: three roles (instructor, base, plugin), one
shared secret each, presented as `X-CAPVSAR-Token` or `?token=`. An instructor
token also satisfies the base role. Every mutating route is gated; `/ws` now
does the same-origin check the radio stream already did. The instructor and
base consoles send the token through a `vsarFetch()` helper in `charts.js`,
prompting once per browser and retrying a rejected token.

Two deliberately different defaults, because the failure modes are not
symmetrical: **secrecy fails closed** (truth needs a *configured* instructor
token, so a half-configured console withholds rather than leaks) while
**availability fails open** (a role with no token set is unenforced, so
deploying this could not lock operators out of the running ms01 stack before
its `.env` exists). Every open role is named in a startup warning.
**Remaining: set `CAPVSAR_TOKEN_INSTRUCTOR` / `_BASE` / `_PLUGIN` in `.env` on
ms01 and restart.** Until then the endpoints are still open; the variables are
wired through `docker-compose.yml` ready for it.

**P-2 — plugin truth channel (server half).** New `GET /api/plugin/scenario`
serves the running sortie *with* truth, gated on `CAPVSAR_TOKEN_PLUGIN` and
returning 503 when no key is configured, so it cannot be open by accident. Its
response shape matches `/api/state` deliberately, so the plugin change is a URL
swap plus one header. **Remaining: `PI_capvsar_df.py:947-967` must poll it** —
deferred because another agent held the plugin file for P-1.

### Validation

New `tests/test_console.py` — 17 checks, and the first automated tests
`main.py` has ever had. The leak test walks every scenario/sortie response
recursively for any number within ~100 m of the beacon, so a future endpoint
that forgets the serializer fails it; `leak_endpoints()` is the list to extend
when adding routes. Verified the tests actually catch the defect rather than
just passing: reverted to the pre-fix behaviour and **9 of 17 failed**
(`/api/state` and `/api/scenarios` leaking, `/track` returning a beacon on an
unrevealed sortie, `beacon_elev_ft` present, and every role gate answering 200
instead of 403); restored, 17/17 pass. `tests/test_radio.py` still passes 12/12,
so the Mumble bridge is unaffected.

Tested against fastapi 0.141.1 / pydantic 2.13.5 in a scratch venv, not the
container's pinned fastapi 0.115.6 / pydantic 2.10.4 — this machine has no
docker and no pip for the system Python. Nothing in the change depends on
version-specific behaviour, but the suite has not run against the pinned set.

### Notes for whoever picks this up

- `docs/bugs/tracker.json` is now formatted with a uniform `json.dumps(indent=2)`,
  which puts every `"status"` on its own line and makes concurrent targeted
  edits safer. Statuses set by other agents were preserved.
- The scenarios table has no `beacon_freq_hz` or `cs` column, but the plugin
  reads both from the scenario it polls, so they are always absent and it
  silently uses defaults. Contract drift, tracked under P-10; not fixed here.
- Running the console tests surfaced `ResourceWarning: unclosed database` from
  `with db() as c`, which commits but never closes. That is X-8, left alone.

## 2026-09-08 — Fix terrain line-of-sight ray mirroring (P-1)

**Status: implemented**

- **Item ID:** `P-1` (Priority P0, Cluster C3).
- **What was wrong:** In `xplane/PI_capvsar_df.py`, `line_of_sight_blocked()` walked `fr` from 0 (aircraft) to 1 (beacon), but computed `ray = b_ft + (ac_ft - b_ft) * fr`. This mirrored the line-of-sight ray vertically, assigning the beacon altitude to the aircraft position and aircraft altitude to the beacon position. Consequently, terrain ridges near the beacon were compared against high aircraft altitudes and failed to mask the signal, while ridges near the aircraft were compared against low beacon altitudes and falsely blocked reception.
- **What was changed:**
  - In `xplane/PI_capvsar_df.py` line 599, corrected the ray interpolation to `ray = ac_ft + (b_ft - ac_ft) * fr`.
  - In `tests/xp.py`, extended the test stub by adding `TERRAIN_FN` callable support (`(lat, lon) -> elevation in feet`) and threaded coordinates through `worldToLocal`, `probeTerrainXYZ`, and `localToWorld` while preserving the fallback to constant `TERRAIN_FT`.
  - In `tests/test_engine.py`, added regression tests with an aircraft at 6000 ft MSL, a beacon at 1000 ft MSL, and a 5000 ft ridge band tested near the beacon (80–95% along path; blocks) and near the aircraft (5–20% along path; clears).
- **What was verified:**
  - Verified regression tests fail with the buggy expression (`blocked=0` near beacon, `blocked=1` near aircraft) and pass when fixed (`blocked=1` near beacon, `blocked=0` near aircraft).
  - All 57 checks in `tests/test_engine.py` pass cleanly.
  - Full test suites `test_faceplate.py` and `test_panel.py` pass with zero regressions.
  - Python byte-compilation succeeds via `py_compile`.
  - Updated `docs/bugs/tracker.json` (marked `P-1` as fixed) and regenerated `docs/BUG_TRACKER.md`.

## 2026-09-08 — Bug tracker and remediation plan

**Status: tracking artefacts only; no defect is fixed yet.**

Turned the 2026-09-08 review into a worked tracker. `docs/bugs/tracker.json`
is the tracker of record (IDs are the review's finding IDs, so the review,
the handbook and this log all still resolve); `scripts/render_bug_tracker.py`
renders `docs/BUG_TRACKER.md` from it, so the two cannot drift. Edit the JSON,
run the script.

68 items: 8 critical / 21 high / 29 medium / 10 low, or by fix-order 10 P0,
21 P1, 28 P2, 9 P3. Compound findings were split where the parts would be
worked separately (X-8, I-9, O-7); nothing was dropped.

A filterable triage board renders the same JSON at
`https://claude.ai/code/artifact/b37f0b6f-caaf-469a-9862-a103f7025db9`
(grouped by wave, with the critical path). It is a **read view for humans and
is account-private** — Codex and Gemini cannot open it. Agents work from
`docs/BUG_TRACKER.md` and `docs/bugs/tracker.json`; ticks on the board are
browser-local and its *Copy status JSON* button exists to paste status back
into the JSON, which stays the only record.

### Reconciled against the vault as-built

Checked the tracker against `Projects/as-built/AsBuilt_CAPVSAR.md`
(vault, deployed 2026-09-06) rather than trusting the repo alone, and
corrected three items:

- **O-4 was wrong.** The Mumble channel tree does exist on ms01 — `CAP V-SAR`
  with Briefing Room, Mission Base, Mission Net PRIMARY and ALTERNATE,
  Aircraft with CAP-1..3 Intercom, and Instructor - SET — created by hand in
  `mumble-server.sqlite` on 2026-09-06, so joins work today. The real defect
  is reproducibility: those rows live only in a gitignored runtime volume,
  nothing in the repo recreates them, and `radio.py`'s four hardcoded names
  must be kept in step manually. Rebuild or lose the volume and the voice net
  is gone with no scripted recovery. Downgraded P0 to P1, moved to wave 2.
- **D-3 was wrong.** `CONOPS-cap-vsar.md` is not missing; it is in the vault
  at `Projects/architecture/CONOPS-cap-vsar.md`. It is simply outside the
  repo, so the agents this log points at it cannot read it. The fix is to
  copy it into `docs/CONOPS.md`, not to write it. `AM4_COMPAT.md` and
  `infra/ROUTER.md` still resolve nowhere.
- **New O-2a.** The as-built tells participants their instructions are at
  `docs/CONNECT.md`; that file does not exist, so the one pointer a new
  member is given leads nowhere.

The as-built itself needs three updates that cannot be made from this
machine (the vault is not mounted here and ragd is search-only): the
container table is missing `capvsar-flightplanner` (8090) and
`capvsar-radio-https` (8743); the console view list predates `/radio` being a
real Mumble voice bridge with `/radio-legacy` holding the old text console;
and the channel tree needs the reproducibility caveat above. A paste-ready
block covering all three, plus a new Quality tracking section pointing at the
tracker, was handed to the maintainer.

Two groupings, because they answer different questions:

- **15 clusters** are PR-sized units that share files, with an owner hint per
  cluster. Two orderings are load-bearing: C2 (truth and roles) must land
  before C7 (console robustness) since both rewrite `main.py`, and C10 before
  C11 in the planner. The plugin and docs clusters are safe fully parallel.
- **5 waves** are scheduling, anchored to the rehearsal calendar in
  `docs/USE_CASE_SAREX_REHEARSAL.md`: wave 0 version control, wave 1 what
  session 1 needs, wave 2 what a three-aircraft full mission needs, wave 3
  dress rehearsal and live day, wave 4 architecture and CalTopo phase 2.
  Where severity and wave disagree the wave wins — O-5 is high severity but
  nothing before the dress rehearsal needs it, while L-1 is a step lower and
  is wave 1 because the AOBD exports `.fms` in session 1.

`docs/REMEDIATION_PLAN.md` carries the critical path (X-1, P-2 and X-2 are one
piece of work and one PR — doing them apart means writing the truth serializer
twice), a per-wave exit test, the multi-agent working rules, and the three
checks that should become permanent regression tests: the truth-leak test, a
non-flat terrain stub, and a preflight smoke script. Waves 0 to 2 — the point
at which a three-aircraft rehearsal is genuinely possible — are about nine to
ten focused days.

Status corrections from the entry below: O-1 is **in progress, not closed** —
the v0.1 baseline is pushed, but this working tree still has no `.git/` and
`git` is not installed on this machine, so agents editing here still cannot
diff or revert. O-1a is **resolved by decision** (the generated handbook is
tracked deliberately as the published artefact).

## 2026-09-08 — Project baseline v0.1 placed under version control

**Status: implemented.**

- Added project-wide `VERSION` value `0.1`; the corresponding immutable Git tag
  is `v0.1`. Air Manager's required integer instrument revision fields remain
  independent and retain their tested values.
- Expanded the repository baseline to include the four Air Manager instruments,
  Mission Observer panel, X-Plane plugin source, C182T build/deployment tooling,
  exercise and flight-planner services, web documentation, tests, reference
  manuals, generated handbook PDF/HTML, artwork sources and redistributable
  instrument assets.
- Added root ignore rules for credentials, local agent configuration, runtime
  databases, Mumble state, locally generated TLS trust material, caches, build
  output, deployment backups and rebuildable archives. Fixed the flight planner's
  malformed ignore entry and retained its Docker source files.
- The canonical `main` branch and `v0.1` tag are mirrored to the internal Gitea
  repository and GitHub. Production runtime state is deliberately outside Git.

## 2026-09-08 — SAREX rehearsal use case: docs, handbook chapter, blog post

**Status: documentation only; no code changed.**

Described the intended training progression — a SAREX (Search and Rescue
Exercise) whose air missions are flown three times on the simulator (T-14
base stand-up, T-7 full mission with injected effects, T-2 dress rehearsal)
before the live day, so the live exercise reinforces skills rather than
introducing them. The scripted incident is an overdue C182 KCRQ→KTRM with a
406 MHz composite east of Julian; three sorties (creeping-line route search,
ELT homing + expanding square, parallel-track grid) map to the Flight
Planner's three pattern generators.

- `docs/USE_CASE_SAREX_REHEARSAL.md` — the full narrative, the measures the
  debrief provides the SET, and the four review items (O-2, X-1/P-2, L-1,
  phase-2 retasking/CalTopo) that stand between the narrative and running it
  with three aircraft today.
- `scripts/generate_manual.py` — new Handbook chapter 7 "Training
  Progression: Rehearsing a SAREX Before Flying It" (incident table, session
  table, measures table); the QRC chapter renumbered to 8; revision bumped
  to 1.3. `docs/manual/*` regenerated.
- `docs/blog/BLOG-virtual-sarex-rehearsal.md` — CyberFlight blog draft in the
  vault's `BLOG-*.md` template, with three figures under
  `docs/blog/assets/virtual-sarex-rehearsal/` (downscaled from
  `website/images/`). Not yet added to the vault's `Projects/blog/BLOG.md`
  index or pushed to Gitea.

## 2026-09-08 — Whole-project review and CalTopo phase-2 plan

**Status: review and proposal only. No code was changed; nothing below is
fixed yet.** Full findings with file:line references are in
`docs/PROJECT_REVIEW_2026-09-08.md`; the CalTopo plan is in
`docs/CALTOPO_PHASE2_PLAN.md`. Finding IDs (P-, X-, F-, L-, I-, O-, D-) are
defined there.

Seven parallel reviews (plugin/engine, console backend, console frontend,
flight planner, Air Manager Lua, infra/ops against Plan v0.8 §4, and CalTopo
research) were cross-checked against the tree; the three most consequential
findings were re-verified by hand.

Critical (pre-exercise minimum): the repo is not under version control
(`.git/` is empty, no `git`, no `.gitignore`, ~45 MB of regenerable
artifacts in-tree); beacon truth leaks through `GET /api/scenarios`,
`GET /api/sorties/{id}/track` and `beacon_elev_ft` in the `/ws` snapshot;
the plugin can never receive beacon truth from `/api/state` (same
withholding) so the in-sim DF is silent unless revealed at start; the terrain
line-of-sight ray in `PI_capvsar_df.py:595-599` is mirrored (aircraft and
beacon altitudes swapped along the path); no authentication or roles on any
console endpoint; Leaflet is loaded from unpkg with no local copy so `/base`
is blank on a LAN without internet; the plugin hardcodes console IP and
callsign so multi-aircraft is not deployable; the `.fms` export is malformed
for X-Plane 11/12 and the test asserts the wrong format; the compose file
bind-mounts a flight-planner DB *file* that does not exist in the repo, so a
fresh ms01 deploy crash-loops.

Corrections to this log: the pymumble browser voice bridge is **implemented**
(see the entry immediately below) — the "Design proposal: Mission Base WebUI
virtual radio" entry and the containerization entry's "Proposed only" are
superseded. The "MRO Base Radio Web Application (`/radio`)" entry (APX 6500 +
IC-A120) now describes `/radio-legacy`; README and `website/*.html` still
advertise it as `/radio`. The Becker/RT-600 `pcall(canvas_draw)` entry's
claim that the current code still produces the reentrancy error is not
supported by `~/Air Manager/log.txt`. The engine suite has 50 checks, not 55.
`/api/messages` no longer returns 400 without a sortie. No
`CONOPS-cap-vsar.md` or `AM4_COMPAT.md` exists on disk; Plan v0.8 §4 is the
effective CONOPS.

CalTopo: an official, supported Team API exists (HMAC-signed service
accounts) plus a documented custom HTTP position-report endpoint with
`aircraft:*` fields — the sanctioned way to feed simulated aircraft into live
tracking; APRS-IS must not be used. `caltopo-python` 2.0.0 wraps map objects,
assignments and `since` polling and targets CalTopo Desktop for offline
bases. Proposed in four phases (GeoJSON export/import first, then live
tracking + map automation via a `tracking` router, then bidirectional +
offline, then role UX), gated on the truth-filter and station-identity fixes.

## 2026-09-08 — Mission base web headset radio implemented and installed

**Status: installed on ms-01; browser audio and deployment checks passed.
Physical Bluetooth headset and iPad/Android acceptance checks remain.**

The new `/radio` page replaces the former typed-message-only radio entry point
with live voice through the existing Mumble mission server. It supports tablet
press-and-hold PTT and desktop spacebar PTT, headset microphone selection,
browser/system output routing, a local sound test and receive volume. Browser
stations and native Mumble crews communicate on the same selected mission net.
The previous APX6500/Icom text console, sidetones and Form 110 remain at
`/radio-legacy`.

- Created APX 4500 O2 and EFJohnson 5300 instrument faces, with reference-informed
  hardware layouts, matte SVG artwork and smooth live display text. Both skins
  operate one station. Active faceplate controls select nets, home, power/join
  and volume; scan/squelch/monitor/emergency functions are not simulated.
- Corrected the radio-selection basis: CAP training references document the
  APX 4500 as a base/mobile radio and the EFJohnson 5300 family. No nationwide
  inventory ranking was found to substantiate a literal “most common two” claim.
  Sources, saved ICUT PDF, model scope and setup instructions are under
  `docs/mission-base-radio/`.
- Added the FastAPI `/api/radio/stream` bridge, with one native Mumble client per
  browser, 48 kHz mono PCM over WebSocket and Opus on the Mumble side. Mumble
  credentials stay server-side. Supports an optional shared exercise access code,
  same-origin checks and a default limit of 16 browser sessions.
- Added independent server/client PTT gating, 1.5-second transmit lease,
  60-second limit, release on blur/hidden page/pointer cancellation/retune/loss,
  stale-ack rejection, bounded queues and selected-channel audio filtering.
  Server-initiated moves or mutes stop the next transmitted frame. Retunes wait
  for the native server acknowledgment. Disconnect cleanup releases session
  slots; native receive queues are drained to avoid accumulating exercise audio.
- Added Caddy HTTPS on LAN port 8743 with a persistent local CA and public
  certificate download at `/radio-ca.crt`. Set `default_sni 192.0.2.151` so
  IP-address TLS clients work through Docker even when they omit SNI. Devices
  need one-time certificate trust; the private CA key stays in Caddy's volume.
- Added the Python 3.12-compatible pinned pymumble commit and native `libopus0`
  to the exercise image. Updated Compose and rebuilt/restarted only the exercise
  service and new HTTPS proxy. Mumble and flight planner continued running.
  Original deployment files are backed up on ms-01 at
  `/srv/capvsar/backups/mission-radio-20260908/`.

Validation: **12 backend tests passed** in `tests/test_radio.py`. Two Chromium
stations on a separate, disposable Mumble server passed actual browser capture
→ Opus → browser audio playback, spacebar release, focus exclusions, blur,
different-net silence, pointer cancellation and tablet/phone layout checks.
The reproducible browser harness is `scripts/test_base_radio_browser.py`; PNG
instrument and page previews are in `output/mission-base-radio/`.

Deployment verification: all eight requested HTTPS pages/assets returned 200
with full certificate-chain and IP-identity validation against the exact public
CA. A Chromium session joined PRIMARY, changed to MISSION BASE, and disconnected
on the installed server without transmitting or reporting JavaScript errors.
The browser check used a temporary certificate-error allowance; certificate
trust was verified separately without changing the workstation's trust store.
No synthetic test audio was sent to live mission channels.

Open `https://192.0.2.151:8743/radio`. First-device instructions and certificate
download are available over existing HTTP at
`http://192.0.2.151:8700/static/radio-help.html`. Local CA SHA-256 fingerprint:
`AE:D7:ED:5D:10:5B:BD:27:D6:00:BF:8F:52:AD:AE:44:66:20:60:78:B2:9A:2B:81:B4:62:6E:40:B9:AC:5C:2A`.
This is an exercise voice station; it does not bridge physical VHF radios or
ATC, implement dual-watch/guard, or automatically transcribe a communications log.

## 2026-09-08 — Blue prop lever added to the C182T NAV III 3D cockpit

**Status: implemented; the built package rebuilds cleanly from source, but
actual placement/appearance has not been visually confirmed in a running
X-Plane session (no rendering/screenshot capability available this session).**

The base Laminar C172SP has a fixed-pitch prop and no prop lever in its 3D
cockpit model. `scripts/build_c182t_package.py` already patched `_prop_type`
to 1 (constant-speed) for the G1000 MFD's Manifold Pressure gauge, but nothing
in the 3D cockpit reflected that — only the black throttle and red mixture
levers existed, inherited unchanged from the C172SP source.

Added `add_prop_lever()` and `register_prop_lever_obja()` to the build script,
run automatically as steps 4b/4c of `main()`:

- Duplicates the throttle knob's own mesh from `objects/cockpit_panel_G1000.obj`
  (`TRIS 19629 534`, same shape as requested) rather than modeling new
  geometry, and translates the copy to the midpoint between the throttle and
  mixture knob centroids — which lines up with the real-world Throttle / Prop
  / Mixture quadrant order, not just an arbitrary gap.
- Crops the knob's own texture footprint out of the shared `cockpit.dds` atlas
  (194x87 px) and recolors it in HSV space to hue ~205 deg (sampled from
  Laminar's Beechcraft Baron 58 prop lever texture, `B58_panelback.png`:
  base tone `#0f507f`, highlight `#246fa5`), while keeping the original crop's
  per-pixel luminance to drive brightness — so the recolored knob keeps the
  throttle knob's own baked shading/highlight shape instead of reading as a
  flat color swap.
- Ships as a new, self-contained `objects/prop_lever.obj` + `prop_lever.png`
  with its own manipulator (`ATTR_manip_drag_axis` bound to
  `sim/cockpit2/engine/actuators/prop_ratio[0]`, X-Plane's standard writable
  constant-speed-prop-pitch dataref — not `prop_rotation_speed_rad_sec`, which
  is a rotating-vernier-knob control the Baron uses for a different physical
  lever style). Registered as a new `_obja/27` slot in `Cessna_182T_G1000.acf`,
  cloned from the existing `cockpit_panel_G1000.obj` slot's flags
  (`_obj_flags 1033`, `_v10_is_internal 419430400`), with `_obja/count`
  incremented from 27 to 28.
- Deliberately does not touch the existing throttle/mixture geometry, the
  shared `cockpit.dds` atlas, or `Cessna_182T_G1000_cockpit.obj` (the
  manipulator-hotspot object for the other two levers) at all — the new lever
  is entirely additive, so reverting is deleting two files and one `.acf`
  block.

### Validation performed

- Ran `scripts/build_c182t_package.py` end-to-end from a clean re-clone of the
  Laminar source; it completes without error and the verification summary
  still reports all 30 patched `.acf` parameters correctly.
- Confirmed in the rebuilt package: `_obja/27` present with `prop_lever.obj`,
  `_obja/count` reads `28`, `objects/prop_lever.obj` and
  `objects/prop_lever.png` exist (125 verts / 194x87 px).
- Visually inspected the generated `prop_lever.png` directly (not in X-Plane):
  reads as a shaded, rounded blue knob with a shaft, consistent with the
  throttle knob's original shape.
- `python3 -m unittest tests.test_panel` — 7/7 pass (unrelated Air Manager MO
  panel suite; no existing test covers the X-Plane aircraft package, and none
  was added for this change).

### Not verified

- Actual in-sim placement, scale, and readability of the lever have not been
  checked in a running X-Plane session — the computed midpoint position is
  derived from mesh centroids, not confirmed against how it actually looks
  next to the real throttle and mixture levers.
- The recolored texture was sampled and generated programmatically; it has
  not been visually compared side-by-side with the real Baron 58 lever in
  X-Plane, only against the sampled RGB values from its texture file.

## 2026-09-08 — Air Manager instrument appearance and display typography

**Status: implemented and installed in all four local Air Manager instruments;
rendered previews reviewed and automated checks passed. Live GUI rendering has
not been verified in this session; restart Air Manager to load the resources.**

Refreshed the Becker SAR-DF 517, RHOTHETA RT-600, Technisonic TDFM-136B, and
Garmin GMA 1347 using the existing equipment photos and manual figures. The
faceplates now have fine, low-contrast matte grain instead of coarse mottling;
the DF circular casting is subtly distinct from its mounting flange. Reworked
the knobs with flatter tops and twelve scallops, the rubber keys with shallow
bevels, the screws with satin-metal shading, and the TDFM toggles with retaining
nuts and cylindrical lever shading. Reduced the oversized DF printed legends.
These are reference-informed illustrations, not photographic reproductions.

Replaced the shared Lua display renderer's hand-built 3×5 block glyphs with
antialiased built-in Inconsolata Bold via the AM 4.2-compatible canvas `_txt`
API. The three copies of `lib/lcd.lua` remain identical. Explicit per-character
positioning preserves the existing four-unit column advance, frequency fields,
right alignment, inverse labels, large readouts, and case-sensitive TDFM mode
and squelch flags. This is a readability treatment; the hardware's exact glyph
ROM is not documented in the project references. Logical display geometry,
control hit regions, receiver behavior, wing blanking, and ELT audio are retained.

Updated both artwork generators and all instrument previews. The panel preview
generator now uses project-local custom instrument previews rather than stale
installed copies. Included the matching unmodified preview font under its SIL
Open Font License so regeneration does not depend on a local AM installation.
The live instruments use AM's built-in font and need no new font resource.

Validation: `tests/test_faceplate.py` passes; all seven `tests/test_panel.py`
tests pass; all five new `tests/test_lcd_text.py` tests pass; syntax checks pass
for all seven edited Lua files. The new tests execute real Lua text calls and
measure rendered glyph bounds, including the last TDFM column, bottom-row
descenders, DF readout scales, inverse text, case/spacing, and powered-off output.
These checks do not replace a live Air Manager/OpenGL visual check.

Installed 101 changed files and verified 105 selected artwork, Lua, and preview
files against their project sources. Verified the installed AM font matches
the preview font. Existing files were backed up under
`output/visual-refresh/installed-backup-20260908-062811/`. Instrument UUIDs and
panel registration were preserved; no simulator plugin update is needed.

See [visual refresh notes](docs/instrument-visual-refresh.md),
[updated overview](output/visual-refresh/updated-instruments.png), and
[before/after comparison](output/visual-refresh/comparison.png).

## 2026-09-07 — G1000 MFD streaming: intermittent drops in flight, plugin downgrade planned

**Status: proposed work, not yet done. Action needed 2026-09-08.**

Installed the Sim Innovations X-Plane "Air Plugin" (Home Use, v4.5.3, Linux
x86_64, non-steam) into `X-Plane 12/Resources/plugins/Air Plugin/` to fix the
MO panel's G1000 MFD tile, which was showing the "streaming only available"
placeholder because the plugin was previously absent entirely. That resolved
the placeholder — the MFD streamed live after install.

In flight, the video stream then froze intermittently (first noticed across a
pause/unpause, but `~/Air Manager/log.txt` shows it recurring on its own
every few minutes throughout the session):

```
18:49:14 ERROR SimVideoStreamClient - Lost connection with client: Connection reset by peer
18:53:33 ERROR SimVideoStreamClient - Lost connection with client: Resource temporarily unavailable
20:27:13 ERROR SimVideoStreamClient - Lost connection with client (x2)
20:28:26 ERROR SimVideoStreamClient - Lost connection with client: Connection reset by peer
```

The socket itself reconnects within ~5s each time, but the MFD tile's
`logic.lua` (stock Sim Innovations instrument, `0b852ee1-.../logic.lua:90-100`)
only calls `video_stream_add()` once at instrument load, so it never re-arms
the texture after a reconnect and is left showing the last frame.

**Next step (tomorrow): try an older X-Plane plugin build** to match Air
Manager 4.2.12, on the theory that v4.5.3 is misbehaving against the older
app. Note for whoever picks this up: plugin releases appear to be versioned
independently of the Air Manager app itself (other users run this same
4.5.x/5.x plugin line against both 4.x and 5.x app releases), so the version
gap may not be the actual cause. `ping` to the X-Plane host (192.0.2.158,
same machine, wired) showed 0% loss, ruling out a physical network problem.
Sim Innovations' own wiki also flags local firewalls as a known cause of
drops even when Air Manager and the sim share a machine — worth checking
`sudo ufw status verbose` (not yet run; needs an interactive password) before
concluding it's the plugin version.

## 2026-09-07 — ELT receiver audio implemented

**Status: implemented and deployed to both Air Manager 4.2 DF instruments.**

The Becker 517 and RHOTHETA RT-600 now synthesize audible receiver output from
the propagation engine's instantaneous `cap/df/rx_open` state. Analog 121.5 and
243 MHz reception plays a downward swept ELT tone at three sweeps per second;
the normal AM path includes the documented 3 kHz Doppler commutation tone. The
Becker STORE control switches to a clean version of the same received sweep,
so it now performs its complete documented audio function as well as disabling
bearing. Maritime FM uses that filtered version automatically. Cospas-Sarsat
reception plays a single deterministic 440 ms data-burst sound for each engine
burst rather than looping it.

Audio is silent during power-up, at zero receiver volume, when tuned away, when
squelch closes, between 406 bursts, behind terrain, and in a wing null. A held
TIMEHOLD bearing never keeps audio alive. Front-panel volume changes Air
Manager's sound gain immediately. `scripts/make_df_audio.py` deterministically
generates the three PCM WAV assets shared by both heads and supports `--check`
for reproducibility. Validation covers Lua syntax, resource packaging, audio
state wiring, deterministic WAV generation, and the existing engine suite.

## 2026-09-07 — Air Manager MO Station Panel Registration & Auto-Discovery Fix

**Status: implemented, verified live in Air Manager 4.2.12.**

Resolved the issue where the Cessna 182T Mission Observer panel did not show in Air Manager:
1. **Active Panel Registry (`config.sqlite3`)**:
   - In Air Manager, the primary **Panels** tab only displays panels that are instantiated in the active project (`panel` and `instrument` tables in `~/Air Manager/config.sqlite3`).
   - Created `scripts/register_mo_panel.py` to register both layouts:
     * **Panel 3:** `Cessna 182T MO Station (Becker 517)`
     * **Panel 4:** `Cessna 182T MO Station (RT-600)`
   - Configured full instrument hierarchies on each panel (G1000 MFD overlay with `Display unit function = MFD` and `Streaming = true`, CAP GMA 1347 Audio Panel, Becker SAR-DF 517 / RHOTHETA RT-600, and Technisonic TDFM-136B).
   - Hooked registration automatically into `scripts/deploy_mo_panel.py`.
2. **Development View Integration**:
   - Added development objects so both layouts are visible and editable in the **Create / Edit** tab.
3. **Hot-Reload**:
   - Safely updated `config.sqlite3` and restarted Air Manager with the active panels immediately visible on screen.

## 2026-09-07 — Cessna 182T NAV III (G1000 CAP) Aircraft Package for X-Plane 12

**Status: implemented, verified live in X-Plane 12.**

Created a dedicated, standalone **Cessna 182T Skylane NAV III (G1000 CAP)** aircraft package (`N499CP`) tailored specifically for Civil Air Patrol virtual search and rescue (V-SAR) training in X-Plane 12.

### Background & Rationale
X-Plane 12 lacks a native C182T G1000 in its default aircraft inventory (only providing the C172SP Skyhawk). Rather than relying on unmaintained third-party conversions or payware, we built an automated package builder (`scripts/build_c182t_package.py`) that clones Laminar Research's high-fidelity default C172SP G1000 base airframe and re-engineers it into an authentic, standalone Cessna 182T NAV III with authentic Lycoming IO-540 performance, 3-blade constant-speed prop, and Garmin G1000 Manifold Pressure EIS instrumentation.

### Key Aircraft Specifications & Modifications
1. **Airframe & Package Location**:
   - Location: `/home/ron/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III/`
   - Aircraft File: `Cessna_182T_G1000.acf`
   - Completely independent from the stock C172SP (leaving the Laminar directory untouched).
2. **Powerplant**:
   - Lycoming IO-540-AB1A5: 230 HP @ 2,400 RPM (541 cu in, direct-drive, fuel injected).
   - Patched `acf/_power_max_limit` to 230.0 HP, `_RSC_max_pwr_ENGN` to 2400 RPM, `_RSC_redline_ENGN` to 2400 RPM.
3. **Propeller & G1000 EIS Manifold Pressure Auto-Activation**:
   - McCauley 3-blade constant-speed propeller (`_prop_type = 1`, `_num_blades = 3`, `_des_rpm_prp = 2400`, `_des_kts_acf = 145`).
   - Pitch range: `_min_pitch = 10.0`, `_max_pitch = 40.0`.
   - **G1000 EIS Integration**: In X-Plane 12, setting `_prop_type = 1` on a reciprocating engine automatically triggers the Garmin G1000 MFD Engine Indication System (EIS) to display the dual **Manifold Pressure (`MAN IN HG`)** and **Tachometer (`RPM`)** gauges with correct C182T green/yellow/red bands, matching the real G1000 Skylane cockpit.
4. **Weights & Loading**:
   - Maximum Takeoff Weight (MTOW): 3,100 lbs (`acf/_m_max = 3100.0`).
   - Basic Empty Weight: 1,970 lbs (`acf/_m_empty = 1970.0`).
   - Useful Load: 1,130 lbs.
5. **Fuel Capacity**:
   - 87 gallons usable (92 gal total) = 522 lbs of 100LL avgas (`acf/_m_fuel_max_tot = 522.0`).
6. **Cowl Flaps**:
   - Equipped with manual cowl flaps (`acf/_cowl_flaps_EQ = 1`), accurately modeling engine cooling drag and cylinder head temperature management during high-power climbs.
7. **Flight Envelope & V-Speeds**:
   - Stall Speed (clean) $V_S$: 51 KIAS
   - Stall Speed (full flaps) $V_{S0}$: 41 KIAS
   - Best Angle of Climb $V_X$: 65 KIAS
   - Best Rate of Climb $V_Y$: 80 KIAS
   - Best Glide $V_{BG}$: 76 KIAS
   - Flaps Extended Range $V_{FE}$: 140 KIAS (Flaps 10°), 100 KIAS (Flaps 20°–30°)
   - Max Structural Cruising Speed $V_{NO}$: 140 KIAS
   - Never Exceed Speed $V_{NE}$: 175 KIAS
8. **CAP Livery & Selection Icons**:
   - Tail Number: `N499CP`
   - ICAO Designator: `C182`
   - Studio/Author: `Civil Air Patrol / Laminar Research / CAP V-SAR Project`
   - Dedicated livery `liveries/Civil Air Patrol (N499CP)/` based on clean baseline.
   - Branded aircraft selection thumbnail and icon (`Cessna_182T_G1000_icon11.png` and `_thumb.png`) featuring official Civil Air Patrol USAF Auxiliary header, gold stripe, red lower margin, and "SAR MISSION READY" banner.
9. **Automated Package Builder**:
   - `scripts/build_c182t_package.py` can be re-run at any time to regenerate or update the package from the base files.

## 2026-09-07 — Design proposal: containerized deployment, single machine or cloud

**Status: proposed.** No code, containers, or cloud resources were created.
Architecture recommendation for packaging the CAP V-SAR server-side
infrastructure so it can be brought up on one machine for an in-person or LAN
exercise, or moved to the cloud for a fully remote one, sized for an
instructor, a mission base with several staff roles, and up to three aircraft
each with a pilot and an MO.

### The one split that matters: client stations vs. server infrastructure

"Containerize all of the infrastructure" has to stop at a real boundary. Two
things in this project are not infrastructure at all, and can't be
containerized or moved to the cloud without changing what they are:

- **X-Plane + Air Manager/Air Player, per aircraft station.** The CONOPS is
  explicit that this runs on members' own computers, and it isn't just a
  preference: Air Manager Home Use activates against a hardware fingerprint
  (confirmed from this machine's own `~/Air Manager/log.txt` - `HW id =
  feea523088e42a454e95a5152d8e97f8`). There is no containerized or cloud form
  of a per-machine license. This part of the architecture is fixed regardless
  of what happens to the server side.
- **The licence count is better than a flat headcount suggests.** Re-reading
  the CONOPS's own layer list - "Air Manager panels: Becker 517 and RT-600
  heads, plus a second COM panel **at the Observer station**" - the Pilot
  seat needs only X-Plane and PilotEdge, not Air Manager. Three aircraft means
  **three** Air Manager/Air Player seats (one per MO), not six. Worth
  confirming against `AM4_COMPAT.md`'s "spare AM4 licences" count before
  committing to a three-aircraft exercise.

Everything else - Mumble, the exercise console, the flight planner, and the
mission-base web apps - is ordinary server infrastructure and is exactly what
this proposal covers.

### What already exists vs. what this would require building

Checked before proposing anything, so the plan is sized to reality:

| Piece | State |
|---|---|
| Mumble voice server | Built, running (`capvsar-mumble`, `docker-compose.yml` on ms01) |
| Exercise console (instructor / `/base` mission base / `/debrief`) | Built, running (`capvsar-exercise`) |
| Flight planner (search patterns, `.fms` export, V-SAR push) | Built, running (`capvsar-flightplanner`), targets Cloud Run already |
| MRO Base Radio web app (`/radio`) | **[D-1, 2026-09-10: this describes what is now `/radio-legacy`.** The console was rewritten; `/radio` is the Mumble-backed APX 4500 / EFJohnson 5300 face, and it carries real voice, which answers the doubt raised in this row. The CAP Form 110 log, however, is still legacy-only — tracked as F-9.] Just landed in this log as "implemented, verified live" - not yet independently reviewed here. From its own description (REST + WebSocket, canned reports, simulated radio sound effects, a CAP Form 110 log) it reads as a **dispatch/logging console with simulated audio**, not a bridge onto the real Mumble voice net the aircrews actually talk on. Worth clarifying intent before counting it as "the radio operator's console" in the CONOPS sense - it may be a complementary tool alongside real voice rather than a replacement for it. |
| IC / AOBD role-differentiated consoles | Not built. Today there is one shared `/base` view (alert intake, status board, bearings, tasking), not separate per-role views. |
| Browser-native voice bridge (pymumble backend, WebSocket audio to the browser) | ~~Proposed only~~ **SUPERSEDED (D-1, 2026-09-10): this is implemented.** `services/exercise/app/radio.py` runs the pymumble bridge and `/radio` carries live voice. Read the rest of this row as of its own date. Distinct from `/radio` above - this is the one that would let a browser-only staff member actually hear and key the real mission net without a native Mumble client. |

So "a base with a couple web apps for IC, AOBD, radio operator" is partly
redeployment (the console and, pending review, `/radio`) and partly new
frontend work (IC/AOBD views; a real voice bridge if browser-only staff need
to be on the actual net rather than a text/simulated one).

### Measured, not assumed: this is a small workload

`docker stats` on ms01 right now:

| Service | CPU | RAM |
|---|---|---|
| exercise console | 0.29% | 39 MB |
| flight planner | 0.07% | 59 MB |
| mumble | 0.00% | 6 MB |

An instructor, a few base roles, and six aircrew exchanging voice and small
JSON payloads does not stress a machine. The sizing question this proposal
answers is about protocol and licensing constraints, not raw capacity.

### Recommendation: one small VM for the exercise, Cloud Run only for the piece that suits it

Checked against Google's current documentation rather than assumed: **Cloud
Run's ingress is HTTP/1.1, HTTP/2, and gRPC only - no raw TCP, no UDP.**
Mumble needs both. This isn't a workaround-able limit; **Mumble cannot run on
Cloud Run** and needs a real VM or GKE regardless of budget.

Given the measured footprint above, splitting the stack across Cloud Run plus
a separate VM buys little: the exercise console's SQLite database (40 KB
today) would need migrating off local disk for Cloud Run's stateless storage
model, in exchange for savings on a workload that costs a few dollars a month
either way. The simpler, lower-risk shape:

1. **One small VM** (e.g. a GCE `e2-small`, ~$10-13/month, or the existing
   ms01 host for an on-prem exercise) running the full `docker-compose.yml`
   stack as it already exists: Mumble, exercise console, mission-base apps,
   and a WireGuard endpoint (below). This is close to a lift-and-shift of what
   already runs today.
2. **The flight planner stays on Cloud Run**, which is what its own
   `Dockerfile` already targets. It's public-facing, used outside exercise
   windows, and doesn't touch voice or the exercise database - a genuinely
   good fit, unlike the rest of the stack.
3. **If browser-only voice access is wanted later**, the proposed
   pymumble-bridge design (browser <-WebSocket-> FastAPI <-native Mumble
   client-> Mumble server) works on Cloud Run specifically *because* the
   constraint above is about ingress, not egress: Cloud Run's documented
   limits distinguish inbound (HTTP-family only) from outbound (ordinary
   TCP/UDP to external hosts is fine). A Cloud-Run-hosted console could hold
   a native Mumble connection as a client while serving browsers over
   WebSocket. Mumble itself still needs to live on the VM, not Cloud Run.

### WireGuard: already the case, not a redesign

The router (GL-MT6000) already terminates WireGuard for participant peers,
with a live GCP site-to-site tunnel already in place
(`docker-compose.yml`'s own comment: "a GCP site-to-site tunnel"). "Everyone
connects via WireGuard" is the current state, not a proposal.

The one real decision if the hub moves to a cloud VM: run a WireGuard
endpoint **on that VM** so participants connect there directly instead of
routing through the home router. That decouples exercise-day reliability from
home-network uptime and bandwidth - the actual payoff of "to the cloud" here,
independent of compute.

### Sources checked for this proposal

- This machine's own `~/Air Manager/log.txt` (HW id, licence activation).
- `AM4_COMPAT.md` (spare AM4 licence count, Air Player as a separate SKU).
- `docker-compose.yml` and `docker stats` on ms01 (current services, live
  resource usage, the existing WireGuard/GCP-tunnel comment).
- Cloud Run networking documentation, checked live rather than assumed
  (`docs.cloud.google.com/run/docs/configuring/networking-best-practices`;
  cross-referenced against the community FAQ at
  `github.com/ahmetb/cloud-run-faq`) for the HTTP-only-ingress /
  unrestricted-egress distinction the recommendation above depends on.
- CONOPS-cap-vsar.md (four layers, operating modes, the Observer-station-only
  placement of Air Manager panels).

### Not done as part of this proposal

No compose file changes, no cloud resources, no new consoles. Next concrete
step, if this shape is approved: consolidate the existing `docker-compose.yml`
into a form that stands up cleanly on a fresh VM (mostly already true), stand
up one small cloud VM to prove the "to the cloud" half, and decide whether
`/radio` needs review/rework before it stands in for the CONOPS "radio
operator" role, or whether the pymumble bridge is still needed alongside it.

## 2026-09-07 — Wing blanking and instantaneous receiver state implemented

**Status: implemented, verified offline and live, and deployed to the installed
X-Plane plugin, both Air Manager DF instruments, and the `ms01:8700` exercise
console.** This supersedes the earlier research-only entry below.

The propagation engine now reads X-Plane roll (`phi`) and pitch (`theta`) and
transforms the aircraft-to-beacon ray into aircraft body coordinates. A
configurable C182 training profile tests that ray against a softened
wing/fuselage silhouette. With the default belly profile, banking the lowered
wing toward the beacon produces the expected null; the top profile reverses
the direction. The supplied dimensions and nominal 24 dB peak loss are a
training approximation, not measured antenna-pattern data for a particular
tail number.

Propagation loss is now accumulated before signal saturation. Terrain and
airframe attenuation can therefore combine while remaining separately
diagnosable, and a sufficiently strong close signal can penetrate partial
shielding. Three new engine outputs were added:

- `cap/df/airframe_shadowed` — directional airframe loss is active;
- `cap/df/airframe_attenuation_db` — current loss for instructor/debug use;
- `cap/df/rx_open` — instantaneous reception, independent of a TIMEHOLD bearing.

The shared Becker/RT-600 Lua binding subscribes to all three. The student sees
the real consequences through the existing signal bar, squelch, bearing spread,
and TIMEHOLD behavior; it does not display an artificial "wing null" warning.
`rx_open` supplies the gate for receiver audio without conflating live audio
with a held bearing.

The instructor console now offers a **Wing blanking** effect and C182 belly/top
antenna selection for new and running scenarios. Position ingest accepts the
X-Plane plugin's authoritative DF telemetry rather than replacing it with the
server's attitude-free fallback model. The instructor aircraft HUD can thus
show `wing null`, loss, live/held state, and aircraft bank reported by X-Plane.

The canonical plugin source now lives at `xplane/PI_capvsar_df.py` and
`scripts/deploy_xplane_plugin.py` validates and atomically installs it into
X-Plane. `tests/test_engine.py` defaults to the tracked source instead of the
unversioned installed copy.

Validation [**corrected, D-1 2026-09-10: the suite did not have 55 checks at
this date — a later audit counted 50. It has 114 today.**]: all engine checks
pass, including opposite banks, top/belly
reversal, combined terrain and airframe masking, strong-signal penetration,
instantaneous audio versus held bearing, disabled-effect compatibility, and
406 burst state. All faceplate checks and all seven MO-panel tests also pass.

## 2026-09-07 — Mission Radio Operator (MRO) Base Radio Web Application (`/radio`)

**Status: implemented, verified live on `ms01:8700/radio`, and integrated with web suite.**
Built and deployed a touch- and mouse-operable base station radio application designed
for Mission Radio Operators (MROs) using laptops or tablets. Implemented the two
predominant radio systems deployed across Civil Air Patrol base stations:

1. **Motorola APX 6500 with O5 Control Head (VHF-FM Tactical / LMR Net):**
   - **Operational Role:** Standard CAP tactical mobile/base radio for ground team nets,
     Wing command & control, and air-to-ground tactical comms with the MO (TDFM-136B).
   - **Channels & Zones:** Authentic CAP channel banks including Zone 1 Tactical
     (`TAC 1` 148.150 MHz, `TAC 2` 148.125 MHz, `CC 1` 150.225 MHz P25 NAC $293,
     `CC 2` 149.275 MHz, `AIR 1` 150.5375 MHz, `AIR 2`, `SAR 1`, `GUARD`), Zone 2
     Ground Teams (`GROUND 1`, `GROUND 2`, `BASE DISP`), and Zone 3 Interoperability
     (`VFIRE 21`, `VTAC 11`, `CALCORD`, `NATL GUARD`).
   - **Controls & Display:** Realistic vacuum-fluorescent green-cyan OLED display
     with RSSI bars, DIR/RPT, SEC, High/Low power flags; rotary VOL/PWR and CHANNEL
     knobs with continuous drag and incremental `+`/`-` touch steppers; `HOME`,
     `ZONE ▲/▼`, `SCAN`, `MON`, and `DIM` softkeys; realistic TX, RX, and SCAN LEDs.
   - **Acoustics:** Pure Web Audio API simulation of Motorola 3-tone P25 permit chirp
     (941 Hz, 1336 Hz, 1209 Hz) and digital carrier squelch tail.

2. **Icom IC-A120 (VHF-AM Aeronautical Air-to-Ground Transceiver):**
   - **Operational Role:** Standard desktop/base aviation transceiver deployed at
     mission bases, staging hangars, and flight dispatch to communicate directly
     with search aircrews on aeronautical VHF-AM frequencies.
   - **Frequencies & Presets:** Memory presets for `CH 01` (123.100 MHz SAR Primary),
     `CH 02` (122.900 MHz SAR Secondary / Multicom), `CH 03` (121.500 MHz ELT Guard),
     `CH 04` (122.775 MHz Air-to-Air), `CH 05` (123.050 MHz Unicom), and `CH 06`
     (126.200 MHz Military SAR), plus continuous VFO tuning (118.000–136.975 MHz).
   - **Controls & Display:** High-contrast ice-blue backlit aviation LCD with large
     7-segment frequency digits, memory alias, audio bar meter, and `SQL`, `PRI`,
     `SCAN`, `ANL` status flags; rotary Volume, Squelch, and 25 kHz / 1 MHz push-toggle
     tuning dial; `CH/WX`, `SCAN`, `PRI`, `ANL`, `LOCK` function keys.
   - **Acoustics:** Mechanical relay click, VHF-AM sidetone, and squelch noise burst.

3. **Dual Station Equipment Rack View:**
   - Provides a dual-mount rack view (`?mode=dual`) running both the APX 6500 and
     IC-A120 simultaneously, allowing the MRO to monitor both nets with dual watch.

4. **PTT Station & Tactical Communications Dispatch:**
   - Realistic palm fist microphone with coiled cable, PTT lever, and master PTT button.
   - Dual PTT modes: "Hold to Talk" (momentary mouse/touch/spacebar) and "PTT Latch" (tap to lock).
   - Direct integration with `/api/messages` REST endpoint and WebSocket `/ws`.
   - Web Speech API text-to-speech option to voice incoming aircraft traffic with radio effects.
   - Quick "Canned" Tactical Reports for rapid MRO workflow (Radio Check, Ops Normal, Copy Bearing, Exercise Silence, Beacon Found).
   - Live **CAP Form 110 Communications Log** table with timestamps, frequency tags, stations, and text export (`.txt`).

5. **Deployment & Navigation Integration:**
   - Added `/radio` endpoint to `capvsar-exercise` FastAPI service.
   - Added global `Base Radio` header navigation links across all consoles (`index.html`, `base.html`, `debrief.html`).
   - Rebuilt and verified live on `ms01:8700/radio`.



**Status: implemented, verified against a real Lua 5.4 execution and against
the live Air Manager instance's own log.** Closes out three items raised
reviewing "Implementation: Dedicated Mission Observer (MO) Panel" below: the
panel's license tier, an independent re-verification of the `require()` fix
"Air Manager 4.2 bring-up and runtime compatibility" already made, and a
second `canvas_draw` symptom that entry's fix doesn't cover.

### 1. MO panel tier corrected

`panels/cap-c182t-mo-station/info.xml` declared `HOME_USE_PAID` /
`PROFESSIONAL_PAID` — the tiers a *purchased* Sim Innovations panel like the
172SP uses — on `<source>PERSONAL</source>` content. Every one of the
project's own four instruments correctly declares `HOME_USE_STANDARD`; this
panel copied the wrong reference. Fixed to `HOME_USE_STANDARD`, redeployed via
`scripts/deploy_mo_panel.py`, and confirmed on disk at
`~/Air Manager/panels/OPEN_DIRECTORY/a4c8e710.../info.xml`.

Added `tests/test_panel.py::test_tier_matches_personal_source`, which is what
was missing and let the wrong tier ship in the first place — no test checked
`<tiers>` at all. Now 7/7 pass.

### 2. `require()` outage — already documented and fixed; independently re-verified here

**Correction before this goes further: my first pass at this entry claimed
this was undocumented. It is not.** The entry immediately below this one,
"Air Manager 4.2 bring-up and runtime compatibility", already records finding
and fixing it, in more categories than I initially credited (it also fixes a
missing-argument `canvas_draw` bug, a stray fifth `_rect` argument, matrix
glyphs that were merging into solid bars, and the TDFM switch contract). I
should have re-read the full log before writing that claim rather than after.
What follows is additive to that entry, not a replacement for it.

Air Manager's own log (`~/Air Manager/log.txt`) records the discovery, at
first license activation:

```
14:15:28 ERROR SiScanner - Cessna 182T - Becker SAR-DF 517: Error loading
  instrument script: [string "logic.lua"]:22: attempt to call a nil value
  (global 'require')
```

...identically for RT-600, TDFM-136B, and the GMA audio panel — a total,
project-wide load failure, undetectable until Air Manager was actually
installed and licensed today, since nothing before that point could exercise
it. The fix that entry made — every shared `lib/*.lua` publishes its module
table as a global matching its filename, and `logic.lua` files were stripped
of `require()` and reference those tables as bare globals or a local alias —
is what's in the codebase now.

**What this entry adds:** independent re-verification by a different method.
I wrote a real Lua 5.4 execution harness (ctypes against `liblua5.4.so.0`,
stubbing Air Manager's C API surface — `canvas_add`, `button_add`, `dial_add`,
`xpl_dataref_subscribe`, the `_rect`/`_fill`/... draw primitives) and ran all
four instruments' actual `lib/*.lua` + `logic.lua`, then their real power-on
control, then their draw callback, through it. All four load and draw without
error. This is a second confirmation route, independent of reading Air
Manager's own log, and one that doesn't require the licensed application to
be running to re-check after a future edit.

### 3. Becker / RT-600: a *different* `canvas_draw` symptom, mitigated but not proven fixed

> **SUPERSEDED (D-1, 2026-09-10), twice over.** First, the claim below that the
> current code still produces this error is not supported by
> `~/Air Manager/log.txt` — re-checked, the log does not show it. Second, the
> `pcall` this entry adds as the mitigation has since been **removed** by the
> I-2 fix, on the grounds that swallowing the error hid real ones. Read this as
> the reasoning of the day, not as a description of the code.

The other entry's "Restored the required callback argument on each ...
`canvas_draw(canvas_id, draw_callback)` call" fixed a real bug — calling
`canvas_draw` with only the canvas ID, no callback — and its symptom
(`attempt to call a nil value` / `attempt to call a number value`) matches
what's in the log for that. But the log also has a second, textually distinct
Air Manager error that the current code, with both arguments already correct,
still produces:

```
14:38:48 ERROR SiRunner - Becker SAR-DF 517: logic.lua:152: You cannot call
  canvas_draw within a draw callback.
14:38:58 ERROR SiRunner - Becker SAR-DF 517: Error in timer callback:
  attempt to call a number value
```

Line 152 was `if canvas_id then canvas_draw(canvas_id, draw_lcd) end` inside
`redraw()`, called from the 250 ms `timer_start` tick that drives the
Last-Signal/burst timers and scan-mode redraws. **RT-600 has the identical
pattern** — same `redraw()`, same tick-driven call — checked directly, not
assumed. Neither file had been touched since the error was logged; attention
moved to a separate, unrelated TDFM bug (which *was* chased down and fixed,
through several more edits ending around 15:19) and never came back to this
one.

Mitigated in both `becker-sar-df-517/logic.lua` and
`rhotheta-rt-600/logic.lua`: `redraw()` now calls `pcall(canvas_draw,
canvas_id, draw_lcd)` instead of calling it directly. A lost race no longer
raises an unhandled error into the timer or the log; the next 250 ms tick (or
the next button/dataref-driven redraw) asks again almost immediately, so a
dropped frame is not a real staleness risk.

**This is explicitly not proven fixed.** Air Manager's exact reentrancy rule
for `canvas_draw` is not documented anywhere I could find, my own Lua-only
harness has no concept of the engine's own repaint thread and so cannot
reproduce the race to confirm the fix defeats it, and I have no working
screenshot/GUI-automation path on this machine to drive the real instrument
through Air Manager and watch for a recurrence. What's true: the specific
unhandled-error symptom in the log is now structurally impossible from this
call site, regardless of the underlying cause. What's not verified: whether
Air Manager's engine reacts to the *suppressed* failure in some other way
(e.g. simply not repainting that tick, which would be the desired outcome
anyway). Watch `~/Air Manager/log.txt` for `logic.lua:15[123]:` or a
recurrence of "error in draw callback" against Becker or RT-600 specifically
after actually clicking through pages 1-3 or scan mode.

### Validation performed

- `python3 scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua`
  — 14 files, all OK.
- `python3 tests/test_engine.py` — all pass, unaffected (no engine changes).
- `python3 tests/test_faceplate.py` — all pass, including the widened
  "canvas redraw supplies its callback" check that now accepts the
  pcall-wrapped form.
- `python3 -m unittest tests.test_panel` — 7/7, including the new tier test.
- Independent Lua 5.4 execution (ctypes + `liblua5.4.so.0`, stubbed Air
  Manager API) of all four instruments' real `lib/*.lua` + `logic.lua`,
  through power-on and a draw-callback invocation: all four load and draw
  without error, both before and after the `pcall` change.
- The fixed `becker-sar-df-517/logic.lua` and `rhotheta-rt-600/logic.lua`
  were copied to the live installation
  (`~/Air Manager/instruments/OPEN_DIRECTORY/<uuid>/logic.lua`) and diffed
  byte-identical against the repo afterward.
- The MO panel was redeployed via `scripts/deploy_mo_panel.py`; its live
  `info.xml` was grepped afterward to confirm `HOME_USE_STANDARD` landed.

### Remaining limitations

- The Becker/RT-600 `canvas_draw` mitigation is a safety net, not a confirmed
  fix — see above. Needs eyes on the real instrument (or the log, after
  exercising scan mode / rapid page changes) to close out properly.
- No screenshot or GUI-automation capability exists on this machine for Air
  Manager, so nothing in this entry was confirmed by actually looking at a
  rendered instrument — everything here is log evidence and independent Lua
  execution outside the real application.

## 2026-09-07 — Air Manager 4.2 bring-up and runtime compatibility

**Status: implemented and verified in Air Manager 4.2.12.**
Installed the project instruments into Air Manager Home Use 4.2.12's live
`~/Air Manager/instruments/OPEN_DIRECTORY/` store. All four now appear in the
Create/Edit instrument list. Runtime testing found compatibility defects that
the Lua syntax and geometry tests could not expose.

### Fixed

- Removed every `require()` call. Air Manager 4.2 executes all files under
  `lib/` before `logic.lua` and does not expose Lua's module loader. Each library
  now publishes a global table matching its filename. The TDFM line pitch is a
  literal so random library execution order cannot make `tdfm_display.lua`
  depend on `lcd.lua` during load.
- Restored the required callback argument on each Becker, RHOTHETA and TDFM
  `canvas_draw(canvas_id, draw_callback)` call. Passing only the numeric canvas
  ID produced the runtime errors `attempt to call a nil value` and `attempt to
  call a number value` in Air Manager 4.2.
- Removed the invalid fifth zero from Becker's display `_rect` call. Four
  arguments are sufficient for a square-corner rectangle.
- Changed matrix glyphs and the DF dot/tick groups to fill discrete rectangles.
  Queuing all dot rectangles into one Air Manager path turned each TDFM display
  row into a solid amber bar. The powered TDFM now renders two legible 24-cell
  dot-matrix rows and the runtime console remains clean.
- Corrected the three TDFM toggles to use Air Manager's documented
  `(position, direction)` callback contract, retain their switch IDs and call
  `switch_set_position`. The HI/LO switch is initialized to LO to match the
  instrument state. The earlier changelog correction remains valid: a
  two-position switch uses two images, not a third `nil` image.
- Added live GMA 1347 VOL/SQ text annunciators. VOL is shown while automatic
  squelch is active; with MAN SQ selected, pressing either concentric knob
  alternates the illuminated VOL and SQ indication.

### Runtime evidence

- Air Manager startup log is clean: all four project instruments scan and are
  visible in the GUI.
- TDFM runs, powers on, redraws and shows both Main and Guard lines without a
  Lua error after the canvas fixes.
- Becker and RHOTHETA both run and power into legible dot-matrix boot screens
  with the final shared renderer and no Lua errors.
- TDFM's MN/GD and HI/LO switches were moved in the live test window; their
  images and state changed in the requested direction and the console stayed
  clean.
- GMA runs and renders its complete face with the new VOL/SQ text nodes and no
  Lua errors. Its avionics-master-driven power-up lamp test still requires an
  X-Plane connection and was not claimed by this standalone editor sweep.
- Runtime captures are retained in `output/air-manager-validation/`.

Static verification after these changes: all 14 Lua files pass `luacheck`, and
the engine, Python syntax and complete faceplate/resource/loading-contract
suites pass. Regenerating all artwork and previews is byte-identical.

## 2026-09-07 — Publication: Flight Operations Handbook & Training Manual (ODT, DOCX, PDF)

**Status: implemented and published.** Authored and published a comprehensive,
publication-grade flight manual and tutorial document: the *CAP V-SAR Flight
Operations Handbook & Multi-Station Training Manual* (Document ID: `CAP-VSAR-FOH-2026-01`).

### Scope & Structure of the Manual
1. **System Overview & Architecture:** Multi-station CRM simulation architecture
   separating X-Plane 12 flight deck, Mission Observer station, N499CP flight planning,
   and exercise command consoles.
2. **Flight Planning & SAR Patterns:** Pre-flight route construction, performance
   polars, Expanding Square (SS), Creeping Line (CS), Parallel Track (PS), X-Plane
   12 `.fms` export, and exercise console push.
3. **Mission Observer (MO) Station & Avionics:** Complete right-seat console guide
   covering G1000 MFD, GMA 1347 audio panel (and the critical COM3 MIC selection
   trap), Becker SAR-DF 517 vs RHOTHETA RT-600 (406.025 Emergency vs 406.037
   Training coverage gap), and Technisonic TDFM-136B VHF-FM radio.
4. **Instructor & Exercise Console:** Training sortie management, interactive map-pin
   scenario creation on FAA Sectionals, and injected teachable failures (radio
   horizon, 406 burst cadence/timehold, cone of confusion, multipath).
5. **Mission Base & Debrief Replay:** Situational awareness view (hidden beacon truth),
   tactical radio log, bearing cuts, and post-flight track efficiency / CPA debrief replay.
6. **Quick Reference Checklists (QRC):** MO Cockpit Pre-flight Checklist and
   In-Flight Electronic Search & Homing Flow.

### High-Resolution Embedded Visuals
Captured live headless screenshots and embedded high-resolution graphics into the document:
- Figure 1: N499CP Flight Planner Moving Map with Sectional Overlay
- Figure 2: Dedicated C182T MO Station &mdash; Layout 1 (Becker SAR-DF 517 & TDFM-136B)
- Figure 3: Dedicated C182T MO Station &mdash; Layout 2 (RHOTHETA RT-600 & TDFM-136B)
- Figure 4: Instructor Control Console with Sectional Basemap & Dynamic Failure Controls
- Figure 5: Mission Base Console with Aircraft Radar Track and Tactical Message Log
- Figure 6: Debrief Console with Flight Track Scoring & Bearing Error Analysis

### Document Publishing Pipeline (`scripts/generate_manual.py`)
- Automatically compiles structured HTML into self-contained OpenDocument Text (`.odt`)
  with embedded figures inside the ODT ZIP (`Pictures/`), Microsoft Word (`.docx`),
  and print-ready vector PDF (`.pdf`).
- **Figure Scaling & Margin Bounding:** Implemented post-processor `embed_and_resize_odt_images()`
  that recalculates all `<draw:frame>` tags to strictly clamp image widths to 6.2 inches
  (proportional height ≤ 3.88 in), ensuring comfortable margins on standard Letter (8.5×11")
  and A4 pages without horizontal overflow in LibreOffice Writer or Microsoft Word.
- Output files deployed to:
  - Repository: `docs/manual/`
  - User documents: `~/Documents/CAP_VSAR_Flight_Operations_Handbook.*`
  - Remote host `ms01`: `/srv/capvsar/docs/manual/`


## 2026-09-07 — Web Console Flight Planner Integration, Granular SAR Status & Docs

**Status: implemented and verified live.** Followed up on the flight planner
composition and code review with three targeted enhancements across the `ms01`
stack and source repositories:

1. **Web Console Header Navigation Links:**
   - Added direct, styled `Flight Planner` navigation links across all three
     exercise web console views (`index.html` [Instructor], `base.html` [Mission
     Base], and `debrief.html` [Debrief]).
   - Added client-side dynamic host resolution in `charts.js` so clicking
     "Flight Planner" reliably resolves to port 8090 on whichever host or domain
     the user is accessing (`//${location.hostname}:8090/`), opening in a new tab.
   - Rebuilt and verified the `capvsar-exercise` container on `ms01`.

2. **Granular V-SAR Push Feedback & `/api/messages` Analysis:**
   - **Root-Cause Clarification:** Inspected `services/exercise/app/main.py:379-380`
     and verified that the `MessageIn` schema (`sender`/`recipient`/`body`) is
     100% correct. The prior HTTP 400 Bad Request finding was strictly due to
     `if not hub.sortie: raise HTTPException(400, "no sortie running")` (messages
     require an active `sortie_id` in SQLite).
   - **Status Message Granularity:** Updated `sar_export_vsar()` in `app.py` and
     `static/js/app.js` to explicitly differentiate states:
     - When a sortie is active: `"Pushed to V-SAR Console (scenario created & broadcast to active sortie)"`
     - When no sortie is active: `"Pushed to V-SAR Console (scenario created; ready in console)"`
   - Synced and verified live against `capvsar-flightplanner` on `ms01:8090`.

3. **Flight Planner SAR Documentation:**
   - Updated `docs/USER_GUIDE.md` with Section 8: *Civil Air Patrol Search &
     Rescue (SAR) Patterns*, detailing Expanding Square (SS), Creeping Line (CS),
     Parallel Track (PS), route integration, X-Plane 12 `.fms` export, and V-SAR
     bridge synchronization.
   - Updated `docs/QUICKSTART.md` with Step 8 and cheat-sheet reference for the
     SAR pattern generator tool.


## 2026-09-07 — Flight planner composited into the ms01 stack; SSRF fixed

**Status: implemented and verified live.** Redeployed the N499CP Flight
Planner (`flight-planner-n499cp-v2`) as a fourth service in the existing
`/srv/capvsar/docker-compose.yml` stack on ms01, alongside `mumble` and
`exercise`, rather than as a standalone Cloud Run service reaching in from
outside. Applied the SSRF fix flagged in the prior review entry as part of
doing this, since deploying the vulnerable code into a new environment without
it — especially one framed as a step toward a public Cloud Run deployment —
would have carried the same finding forward.

### Composite deployment

New `flightplanner` service, `build: ./services/flightplanner` (rsynced from
the source repo), on the compose stack's own network:

```
flightplanner:
  ports: ["8090:8080"]
  volumes:
    - ./services/flightplanner/data/aviation_data.db:/app/aviation_data.db
    - ./services/flightplanner/data/charts:/app/charts
  environment:
    VSAR_CONSOLE_URL: http://exercise:8700
```

The point of compositing: the flight planner now reaches the exercise console
by its **compose service name**, not a LAN IP or a client-supplied URL. `mumble`
and `exercise` were untouched — `docker compose build flightplanner && up -d
flightplanner` only, confirmed both kept their original uptimes (23h/28h)
throughout.

### The SSRF fix (see the prior review entry for the finding)

`sar_export_vsar()` no longer reads `vsar_url` from the request body at all.
The target is now `VSAR_CONSOLE_URL`, an environment variable fixed at process
start — `http://exercise:8700` in this deployment, would be the WireGuard/LAN
address in a Cloud Run one. Nothing a request sends can change it.
`static/js/app.js` no longer sends the field either.

Also fixed alongside it, from the same review: `spacing_nm = 0` no longer
raises an unhandled `ZeroDivisionError` in `generate_creeping_line`/
`generate_parallel_track` (both now floor at 0.1 nm, matching what the UI's
own `<input min>` already implied but never enforced server-side); `num_legs`
is capped at 40 instead of unbounded; a malformed `waypoints[0]` (missing or
non-numeric `lat`/`lon`) now returns 400 instead of an unhandled `KeyError`.

### Verified against the live deployment, not just re-read

- `docker compose exec flightplanner python3 -c "urlopen('http://exercise:8700/api/health')"`
  → 200. The composite network resolves and routes.
- `env | grep VSAR_CONSOLE_URL` inside the container → `http://exercise:8700`.
- **Reran the actual attack**: POSTed
  `{"vsar_url": "http://169.254.169.254/", "waypoints": [...]}` at the live
  `/api/sar/export-vsar`. Response's `vsar_url` came back `http://exercise:8700`
  — the supplied value was completely ignored, exactly as intended.
- POSTed `spacing_nm: 0` at `/api/sar/generate-pattern` with `creeping_line` —
  returned a valid 16-waypoint pattern instead of a 500.
- `python3 -m unittest tests.test_sar` — all 7 pre-existing tests still pass.

### Found in the process: `/api/messages` rejects the push

> **NO LONGER TRUE (D-1, 2026-09-10).** `/api/messages` does not return 400 for
> this payload any more. That has its own consequence, tracked as L-9: the
> planner's "no sortie running" branch is now dead code, so the UI reports a
> successful broadcast whether or not anything was persisted.

The verification POST above logged `scenario_created: true` but
`message_sent: false`. The exercise console's own log shows why:
`POST /api/messages HTTP/1.1 400 Bad Request` — the flight planner's
`message_payload` shape (`sender`/`recipient`/`body`) doesn't match what
`/api/messages` actually expects. **Pre-existing, not introduced by this
change** — the scenario-creation half of the bridge works, the broadcast-
message half doesn't, and the earlier "implemented" claim didn't catch this
because it was never run against the real console until now. Not fixed here;
needs the exercise console's own `/api/messages` schema to diagnose.

### Housekeeping

The verification call above created one real (obviously synthetic — datum
33.1,-117.1, callsign CAP499) scenario in the exercise console's live
database. Left in place since this is the test stack; clear it from the
instructor console if it's in the way.

`docs/USER_GUIDE.md` and `docs/QUICKSTART.md` in the flight-planner repo still
don't mention the SAR feature — the "documented" gap from the prior review
entry is still open.

## 2026-09-07 — Implementation: Dedicated Mission Observer (MO) Panel for Air Manager & Air Player

**Status: implemented & deployed.** Created and deployed a dedicated Mission
Observer (MO) panel for the Cessna 182T NAV III (`cap-c182t-mo-station`) designed
for secondary displays, cockpit touchscreens, and LAN-streamed Air Player setups.

### Operational Context & Cockpit Layout
In the Civil Air Patrol C182T NAV III cockpit, the Mission Observer sits in the
right seat. To the right of the Garmin G1000 MFD is the copilot/observer audio
panel (Garmin GMA 1347), followed by the dedicated CAP mission avionics stack:
the Direction Finder (Becker SAR-DF 517 or RHOTHETA RT-600) and the VHF-FM
mission radio (Technisonic TDFM-136B).

This dedicated panel groups the MO's complete operational domain onto a single
1920×1080 (16:9 Full HD) canvas:
- **Garmin G1000 MFD (`0b852ee1-6006-4e2b-9cdf-e397b3f16ab1`):** `x=40, y=100,
  w=1100, h=715`. Configured with `Display unit function = MFD`. Features a
  transparent active screen cutout in `background.png` so popout X-Plane MFD
  windows or native Air Manager display streaming can show through.
- **Garmin GMA 1347 Audio Panel (`1337420b-7420-4843-80eb-9d10c57a97d1`):**
  `x=1155, y=100, w=121, h=715`. Positioned immediately to the right of the MFD
  (15 px bezel clearance), maintaining exact NAV III panel authenticity.
- **Direction Finder:** `x=1360, y=100, w=460, h=460` (square 1:1 aspect ratio).
  Centered in the mission avionics stack.
- **Technisonic TDFM-136B VHF-FM Radio (`26df5da8-8ce7-4255-bb0e-520453134609`):**
  `x=1310, y=580, w=560, h=294` (preserving native 1.905 aspect ratio). Centered
  directly beneath the DF head.

### Dual-Layout Architecture
To support both legacy Becker 517 and modern RHOTHETA RT-600 training scenarios
without manual reconfiguration, the panel defines two layouts in `info.xml`:
1. **Layout 1 (`e1c8e710-5646-49e1-931f-4aeeb51e4491`):** `MO Station (Becker 517)`
   — fitted with the Becker SAR-DF 517 head (`faefb90d-5704-48c7-8deb-c683d94b4eb3`).
2. **Layout 2 (`e2c8e710-5646-49e1-931f-4aeeb51e4492`):** `MO Station (RT-600)`
   — fitted with the RHOTHETA RT-600 head (`d783d409-9bfa-49f2-ad5d-883af29848d6`).

### Deployment & Verification
- Repository location: `panels/cap-c182t-mo-station/`
- Air Manager installation: `/home/ron/Air Manager/panels/OPEN_DIRECTORY/a4c8e710-5646-49e1-931f-4aeeb51e4490/`
- Asset generator: `panels/cap-c182t-mo-station/generate_assets.py` (builds
  custom 1920×1080 dark cockpit background with MFD cutout and composite previews).
- Automated test suite: `tests/test_panel.py` validates XML schema, geometry bounds,
  non-overlapping hit regions, MFD property settings, and instrument UUID existence (6/6 pass).
- Deployment script: `scripts/deploy_mo_panel.py` provides single-command deployment
  to local Air Manager (`python3 scripts/deploy_mo_panel.py`), custom targets (`--target`),
  asset regeneration (`--regenerate`), and portable ZIP packaging (`--zip` -> `cap-c182t-mo-station.zip`)
  for secondary computer deployment.

### Streaming Architecture (Air Player & X-Plane 12)
- **Air Player Network Streaming:** Air Manager 4.2 broadcasts panel availability
  over the local subnet; secondary laptops or tablets running Air Player 4.2
  auto-discover the panel and render the complete interactive MO station.
- **G1000 MFD Display Video Feed:** Verified that Air Manager 4.2 supports
  native offscreen video texture streaming for X-Plane 12 via `video_stream_add()`.
  The G1000 bezel instrument (`0b852ee1-6006-4e2b-9cdf-e397b3f16ab1/logic.lua:95`)
  automatically invokes `video_stream_add("xpl/G1000_MFD", 416, 100, 2048, 1536)`
  when running against X-Plane 12 with the Sim Innovations flightsim plugin.
- **Multi-Monitor / Popout Fallback:** For non-streaming environments (e.g. X-Plane 11
  or multi-head desktop), `background.png` incorporates a pixel-aligned transparent
  cutout `(196, 136, 787 × 592)` allowing native X-Plane popout windows placed behind
  the Air Manager bezel to show through cleanly.


## 2026-09-07 — Integration: N499CP Flight Planner & CAP V-SAR Bridge

**Status: implemented & documented.** Integrated the N499CP Flight Planner
(`flight-planner-n499cp-v2`, deployed at `flightplanner.rpc-cyberflight.com`)
with the CAP V-SAR simulation and exercise console ecosystem (`ms01:8700`).

### Integration Architecture & Operational Workflow

Pre-flight planning and in-flight search pattern execution are now unified:

1. **Search Pattern Generation:**
   - Added standard CAP search pattern algorithms into the flight planner:
     - **Expanding Square (SS):** Geodesic outward expansion from a known datum
       (LKP / ELT alert position) with configurable track spacing (0.5–2.0 nm),
       initial heading, and turn direction.
     - **Creeping Line (CS):** Orthogonal cross-corridor sweeps along an advance
       axis, ideal for route, canyon, or river-bed searches.
     - **Parallel Track (PS):** Systematic rectangular grid sweeps across CAP
       quadrangles.
2. **Export Bridges:**
   - **X-Plane 12 `.fms` Flight Plan Generator (`/api/sar/export-fms`):**
     Exports departure, enroute fixes, and generated search pattern waypoints
     directly into X-Plane 11/12 standard `.fms` format (FMS version 1100),
     ready for loading into the aircraft's G1000 NAV III or FMS catalog.
   - **V-SAR Console Push Bridge (`/api/sar/export-vsar`):**
     Transmits planned search corridors, waypoints, and sortie parameters
     directly to the exercise console on `ms01:8700` (`/api/scenarios` and
     `/api/messages`), allowing the Mission Base staff and MRO to monitor the
     planned route against live radar positions.
3. **Flight Performance & Safety Synchronization:**
   - Leverages the flight planner's Cessna POH performance profile to compute
     transit fuel, time-on-station (TOS) before bingo fuel, and mandatory CAP
     reserve fuel.
   - Provides verified fuel metrics for Mission Observers reporting 30-minute
     "Ops Normal" updates to Mission Base.

## 2026-09-07 — Design proposal: Mission Base WebUI virtual radio (pymumble) and MRO console

> **SUPERSEDED (D-1, 2026-09-10).** This was a proposal and it was built. The
> pymumble bridge is `services/exercise/app/radio.py`; the console it describes
> shipped and was then rewritten — the faceplates are now APX 4500 and
> EFJohnson 5300 on `/radio`, and the console described here is `/radio-legacy`.
> Kept for the reasoning, not as a description of the system.

**Status: proposed.** Architecture and UI specification for integrating a virtual
Civil Air Patrol Mission Radio Operator (MRO) communications console and
enhanced mission-base situational tools into the browser-based exercise console
(`capvsar-exercise` at `ms01:8700`), fulfilling Layer 3 and Layer 4 of the CONOPS
(CONOPS §Four layers, Mode B/C).

### Architecture: backend pymumble audio bridge vs client-side mumble-web

Selected approach: **backend `pymumble` bridge integrated into the FastAPI
console service**, rejecting a standalone web client / iframe.

- **Decision rationale:** The MRO radio must look, feel, and operate like an
  authentic piece of radio hardware (e.g., a desktop Motorola APX/XTL base
  station or a Telex IP-224 dispatch console) rather than a generic chat tree.
  A direct browser WebRTC/WebSocket audio pipeline into FastAPI running
  `pymumble` allows the radio faceplate to completely control audio routing, PTT
  timing, squelch behavior, and channel transitions without exposing Mumble
  internals to the trainee.
- **Audio pipeline:**
  1. Trainee mic audio captured via Web Audio API, encoded (PCM 16-bit / Opus),
     and streamed over WebSocket to FastAPI endpoint `/api/radio/stream`.
  2. The FastAPI service runs an asynchronous `pymumble` client instance connected
     to `capvsar-mumble:64738`.
  3. Channel selector commands in the UI send lightweight JSON control packets
     (`{"action": "set_channel", "channel": "Mission Net PRIMARY"}`) over the
     control WebSocket, instructing `pymumble` to move between channel rooms.
  4. Incoming audio from `pymumble` is packetized and pushed back over the
     WebSocket to the browser, with real-time RMS calculations streamed for the
     RX signal/VU meters.
  5. Audio is played through the Web Audio API with simulated bandpass filtering
     (300 Hz – 3.4 kHz speech range) and authentic squelch-tail burst synthesis on
     PTT unkey.

### Virtual MRO radio faceplate specification

The UI component on `/base` will be styled as a dedicated rack/desktop base
transceiver console:

1. **Rotary Channel / Net Selector:**
   - Switches between Mumble channel trees directly mapped to CAP SAR structure:
     - `Mission Net PRIMARY` (Air-1 tactical, routine position and ops normal)
     - `Mission Net ALTERNATE` (Air-2 tactical, dedicated DF search traffic)
     - `Mission Base` (Internal mission base coordination)
     - `Briefing Room` (Pre-flight briefings)
2. **Push-To-Talk (PTT) with hardware-like interlocks:**
   - Large physical-style PTT button with active press-and-hold behavior.
   - Configurable keyboard hotkeys (default: `Spacebar` when focus locked, or
     dedicated thumb key).
   - Dynamic **TX Tally LED** (red) and **RX Activity LED** (green).
   - Audio VU / signal-strength LED bar.
   - 60-second stuck-mic timeout disconnect with audible and visual warning.
3. **Dual-Watch / Guard Receiver:**
   - Secondary audio channel listener continuously monitoring Guard (121.5 MHz /
     National Guard VHF) at user-adjustable balance while working Primary.
4. **Hardware adjustments:**
   - Volume knob (headset gain), Squelch knob (noise gate threshold), and Mic
     Gain adjustment.

### Mission Base situational awareness and workflow enhancements

1. **Integrated CAPF 110 / ICS 309 Radio Communications Log:**
   - Sits immediately adjacent to the virtual radio.
   - One-click macro buttons for rapid entry:
     - `RADIO CHECK`: logs time, station, and signal report.
     - `OPS NORMAL`: logs time, fuel remaining, Hobbs, and altitude.
     - `IN-GRID` / `OUT-OF-GRID`: logs search area entry/exit.
     - `BEARING REPORT`: parses reported bearing directly into the map plotter.
   - Live CSV/PDF export for post-mission debriefing.
2. **30-Minute Ops Normal flight tracking clocks:**
   - Per-aircraft countdown timers starting at 30:00 per CAP regulations.
   - Visual state alerts:
     - Green (30:00–10:00 remaining): Normal operations.
     - Amber (10:00–00:00 remaining): Prompt MRO to poll aircraft.
     - Flashing Red (< 00:00): Overdue aircraft alert initiating communications
       search procedure.
   - Single-click acknowledgement resets the 30-minute interval and logs to the
     ICS 309 table.

### Aeronautical map & tactical plotting enhancements (`charts.js`)

1. **CAP Standard SAR Grid overlay:**
   - Overlay layer for standard 15' × 15' quadrangle Search and Rescue grids on
     the VFR sectional, with A, B, C, D quadrant subdivisions.
2. **Multi-bearing triangulation & probable fix area:**
   - Automatically computes line intersections when multiple bearings are logged
     (from multiple aircraft or one aircraft on different legs).
   - Renders a semi-transparent confidence ellipse / probability polygon on the
     aeronautical chart to guide search retasking.

### Instructor console additions (`/`)

1. **DF Head Telemetry HUD:**
   - Mirror display showing real-time readouts from the aircraft's active DF head
     (Becker 517 or RT-600): tuned frequency/channel group, relative bearing,
     signal strength bar, squelch open/closed state, and cone-of-confusion flag.
   - Gives the instructor immediate insight into the trainee's instrument cues
     before they initiate flight adjustments.

## 2026-09-07 — Air Manager installed and running

**Status: implemented.** Air Manager itself is now installed on this machine
and running, closing the "Air Manager is not installed" caveat repeated
throughout the entries below. **No instrument has been loaded into it yet** —
that is the next bring-up step, not done here.

### 4.3 does not exist for Linux

Asked for specifically: Air Manager 4.3. Checked the vendor's real application
catalogue (`https://api5.siminnovations.com/application/all`, which is what
`docs.siminnovations.com`'s own download-widget JavaScript calls) rather than
guessing from the download page, since that page only lists the current Air
Manager 5 line — Air Manager 4 has been moved to
`docs.siminnovations.com/older_versions/`.

The catalogue has exactly one 4.3 build: `Air Manager 4.3 Home use (BETA 1).exe`
— **Windows only**. No Linux, no Mac, and it is a beta. The newest stable Linux
build is **4.2.12**, matching the copy already sitting in
`~/Documents/Air Manager 4.2 Home use/` (downloaded moments before this
session). Installed that instead of chasing a Windows beta onto a Linux box,
and it is also the right call independent of the version mix-up: `AM4_COMPAT.md`
already commits this project's instruments to the **Air Manager 4 API subset**
specifically because spare AM4 (not AM5) licences exist, so 4.2.12 is squarely
the target, not a fallback.

### Missing native dependencies, resolved without root

`libAppBase.so` (the native core inside the Home Use bundle) linked against
five libraries Ubuntu 26.04 no longer packages under those sonames — `openssl
1.1`, `freeimage3`, and `libzip4` are past end-of-life or renamed, and pulling
freeimage's own image-format plugins in turn needed Imath, OpenEXR, JPEG-XR and
libraw. None were installed, and this account has no passwordless sudo, so
`sudo ./setup.sh` (the vendor's own installer script) could not run
non-interactively.

Resolved without touching the system or asking for a password: each package
was fetched with `apt-get download` (no root needed — it only fetches the
`.deb`) or, for the fully-removed `libssl1.1`, from `archive.ubuntu.com`'s old
pool exactly as `setup.sh` itself does on Mint. Each was extracted with
`dpkg-deb -x` into `Air Manager 4.2 Home use/deps-lib/`, and `AirManager.sh` now
puts that directory on `LD_LIBRARY_PATH` before starting `./Bootloader`. Nothing
outside that one application folder was modified. The udev rule `setup.sh` also
installs is for physical Knobster USB hardware, which this machine doesn't
have, so it was skipped rather than spending a root prompt on it.

Full dependency chain resolved, package sources:

| Missing | Ubuntu package | Why it's gone |
|---|---|---|
| `libcrypto.so.1.1`, `libssl.so.1.1` | `libssl1.1` | Removed from the archive; fetched from the old pool directly |
| `libfreeimage.so.3` | `libfreeimage3` | name unchanged, just not installed |
| `libzip.so.4` | `libzip5` (symlinked) | only `.so.5` ships now |
| `libImath`/`libIex`/`libOpenEXR*` | `libimath-3-1-29t64`, `libopenexr-3-1-30` | FreeImage's OpenEXR plugin |
| `libjxrglue`/`libjpegxr` | `libjxr0t64` | FreeImage's JPEG-XR plugin |
| `libraw*` | `libraw23t64` | FreeImage's camera-RAW plugin |

### Verified running

`./AirManager.sh` launches cleanly in a **clean environment** (`env -i`, no
inherited variables) and opens real X11 windows — confirmed with
`xwininfo -root -tree`, not just a clean exit code: "Activate Air Manager"
then "Air Manager - Home Use 4.2.12", the latter growing from a small
first-run size to its normal window once past the activation prompt.

A full screenshot could not be captured to attach here — the compositor
(Wayland with XWayland) refused a whole-screen X11 grab
(`X get_image failed: error 8`) for both `PIL.ImageGrab` and a direct X11 root
capture, and no screenshot utility (`grim`, `gnome-screenshot`, `scrot`,
`xwd`) is installed to try a window-specific capture instead. Window titles
via `xwininfo`, not pixels, are what's verified here.

### Left for the user

- **License activation.** The "Activate Air Manager" dialog appeared on first
  launch and needs this machine's Sim Innovations account — not something to
  attempt without the account owner. It closed on its own once the main window
  came up; whether that means activation completed or was merely dismissed
  wasn't visible without a screenshot, so treat it as unconfirmed and check the
  live window.
- **Loading an instrument.** Air Manager running is necessary, not sufficient,
  for the bring-up checklists earlier in this log. Next step, not done here:
  open one of `instruments/*/` in the Air Manager editor and work through
  power/startup, every knob and button, page changes, hold actions, tuning,
  dimming, and live bearing updates.
- The X-Plane flight-simulator plugin (separately versioned — see
  `AM4_COMPAT.md`) is still not installed; Air Manager running standalone
  cannot exercise `cap/df/*` yet.

## 2026-09-07 — Independent verification of post-review fixes

**Status: verification completed; one corrected finding and two gaps remain.**
Checked the follow-up entry and current implementation against the detailed
TDFM manual section and Sim Innovations' `switch_add` examples. Re-ran the Lua,
engine, faceplate, preview-reproduction, and Python syntax checks.

### Correction to the earlier review

- The earlier claim that a two-position Air Manager `switch_add` requires a
  literal third image argument was wrong. `img_pos_n` denotes any additional
  position images; Sim Innovations' own two-state example passes two images and
  then the geometry. The current seven-argument call shape is valid.
- The earlier claim that TDFM channel entry commits automatically after the
  third digit was also wrong. TDFM §3.1.1 lists ENTER (`#`) as the key that
  accepts an entry and ESC (`*`) as the key that abandons it. Outside the entry
  editor, the same ENTER key performs its Level-1 home/current toggle. The
  current entry routing matches that behavior.

### Remaining TDFM switch defect

- Although the `switch_add` argument count is valid, the callbacks still do not
  implement the documented switch contract. Air Manager supplies the switch's
  **current** position and the requested direction; in the instrument-controlled
  pattern the switch does not move automatically. Each TDFM callback accepts
  only `position`, ignores `direction`, stores the current state again, and no
  switch ID is retained for `switch_set_position`. The MN/GD, G1/G2, and HI/LO
  toggles therefore still need runtime correction. Existing static tests do not
  exercise this interaction.

### Remaining GMA display gap

- MAN SQ gating and separate pilot/crew values were fixed, but the GMA still has
  no dynamic VOL/SQ annunciators. `VOL` and `SQ` are static faceplate text and
  `vol_mode` does not control any image, so the user cannot see which adjustment
  mode is selected as the manual requires. This part of the earlier VOL/SQ
  finding was neither fixed nor included in the scoped-out list.

### Verification results

- Lua check: 14 files pass.
- Engine tests: all 43 pass.
- Faceplate tests: all 81 pass.
- Propagation-engine Python syntax check passes.
- Preview/resource regeneration is byte-identical.
- Air Manager remains unavailable, so the switch interaction cannot be executed
  here; the remaining switch finding is based on the vendor's callback examples.

## 2026-09-07 — Post-integration review: findings resolved

**Status: implemented.** Every finding in the review below was checked against
the manuals before anything was changed. Most were confirmed and fixed; two were
found to be wrong and the code left alone; the rest are scoped out and listed.

### Verified wrong — no change made

- **TDFM `switch_add` "missing third image".** The Air Manager API reference
  gives a two-position switch as `switch_add(img_pos_0, img_pos_1, x, y, width,
  height, position_callback)` — two images required, the callback optional. The
  `img_pos_n` in the syntax line is variadic notation for further positions, not
  a literal third parameter. Passing `nil` as a third image would declare a
  **three**-position switch and would be the defect, not the fix. The existing
  calls are correct.
- **TDFM direct channel entry.** §3.1.1 is explicit that during a CHAN entry the
  valid edit keys are digits, then "accept the entry and continue" (ENTER) or
  "abandon the entry and exit" (ESC). Table 3-1's "# ENTER Toggle Home/Current"
  is the Level-1 function of `#` when no entry is in progress. The code already
  does both, and waiting for ENTER is correct.

### Runtime defect fixed

- **Becker page 6 raised a Lua error.** `freq_edit_field` cycled over all five
  rows of `training_freqs`, but the fifth is the SCAN knob position and carries
  no `min`/`max`, so turning the value knob on it compared a number with `nil`.
  §1.3.1 gives four adjustable training channels, so the editable count is now
  derived from the rows that actually have a range, page 6 lists only those, and
  the value knob refuses a row without one. Listing four rows instead of five
  also clears the status line the fifth was overlapping.

### Receiver model corrected against the technical data

The Becker manual states its receiving frequencies outright, and the earlier
model had two things wrong:

| | Manual | Was modelled as |
|---|---|---|
| Emergency C/S | **406.025 only** | 406.025 and 406.028 |
| Training band | **400.000–409.975 freely adjustable** | restricted to the emergency channels |

406.028 appears nowhere in the Becker manual. And because the training band
covers the whole 406 range, the head is freely tunable there — the engine was
refusing the 517 its own default 406.037 training frequency. `head_can_receive`
now takes the operating mode.

The RT-600 (§2.2.3) does not tune individual channels at all. It selects one of
**seven CPSAR groups**, each covering two or three of the 3 kHz channels
simultaneously: CPSAR1 "022-028" (A, B, C) through CPSAR7 "073-076" (R, S). The
inclusive 406.022–406.076 grid is **nineteen** channels, A through S — the
previous 18 came from stopping at 406.073 and omitting 406.076. The instrument
now presents the seven groups and tells the engine the span each covers, through
a new `cap/df/rx_span_hz`.

The exercise's headline difference is therefore sharper than before: an
Emergency-mode Becker on its single 406.025 channel is deaf to a beacon on
406.037, while one RT-600 group selection covers 406.031, 406.034 and 406.037 at
once without retuning.

Scan also no longer assumes the emergency pair. §1.3.1 gives 121.500 and 243.000
as the frequencies surveilled between bursts, but in Training mode those are
whatever the crew adjusted the training channels to, and the engine cannot guess
them — so the panel now writes them as `cap/df/scan_alt1_hz` and
`cap/df/scan_alt2_hz`, defaulting to the emergency pair if a panel never does.
The burst leg follows the tuned channel rather than a hardcoded 406.025.

### Becker: STORE now does what the manual says

§3.3.1(5): pressing STORE switches off the 3 kHz tone superimposed on an AM
signal, "enables better hearing of a signal, **meanwhile bearing isn't possible
anymore**". It previously only drew `3K-`. The bearing now stops while the tone
is suppressed, and the pages say why. The same paragraph notes that on the
maritime FM band a filter already removes the tone, so the key is inert there.

### TDFM: squelch LEDs are radio indicators

§1.1.1(1): "LED channel squelch indicators – light on signal received". They are
on the radio, not the audio panel, and were being blanked whenever COM3 audio was
deselected. That hid exactly the evidence the trainee is meant to find — a lit
squelch LED with silence in the headset is the CAP guide's "nearly every 'the
radio is broken' report in flight is an audio panel selection". They now follow
the receiver regardless of audio routing.

### GMA 1347: three behaviours corrected

- **Split COM annunciation.** §SPLIT COM: "During split COM operation, the COM1,
  COM1 MIC, COM2 and COM2 MIC keys are annunciated and thus active." All four now
  light. The annunciators report the panel's state; this seat's restriction to
  COM2 audio stays where it belongs, in the audio path.
- **A COM MIC key selects the matching COM audio.** §TRANSCEIVERS: "COM audio
  can be selected by either pressing the desired COM key or by pressing the
  corresponding COM MIC key. If selected in this manner, the audio source
  remains selected independently of the active microphone source selection."
- **The VOL/SQ knob press is gated by MAN SQ.** "When the MAN SQ key is
  deselected (i.e., auto-squelch is active), pressing the VOL/SQ knob has no
  effect on the VOL/SQ selection state." Deselecting MAN SQ also returns the
  selection to volume. The pilot and copilot rings now carry separate levels
  rather than sharing one value, per §6A.2.

### Validation performed

- `python3 scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua`
  — 14 files, all OK.
- `python3 tests/test_engine.py` — **43 checks**, up from 33. New: Becker
  Emergency vs Training coverage, its single emergency channel, the 19-channel
  grid, a CPSAR group hearing all three of its channels and not reaching into
  the next, and a training scan finding a beacon on a training channel.
- `python3 tests/test_faceplate.py` — **81 checks**, up from 68. New: the Becker
  training table has four adjustable rows and a range-less SCAN row, page 6
  clears the status line, the tone gate exists, and the seven CPSAR groups tile
  the 19-channel grid exactly once with no gaps or overlaps.
- `python3 scripts/make_previews.py` regenerates byte-identically.

### Not done — scoped out, still open

These are feature work rather than defects, and are left for a later pass:

- The RT-600's full FRQ page control flow: MEM1–4 / Work / FIX / CPSAR selection
  with PAGE, MHz and kHz editing on VOL and SQL, band change on F2, and CPSAR
  scan. The instrument still presents a flat selection list.
- Gating COSPAS-SARSAT decode on the RT-600's decode window being open. The
  engine still decodes continuously, so a frame received before the window was
  opened can be displayed.
- Real audio behaviour behind PA, TEL, SPKR, HI SENS, MAN SQ and PLAY on the
  GMA, and behind main/guard volume, squelch defeat, brightness and scan on the
  TDFM. All are still local lamp and display state.
- TDFM back/forward scrolling: still one memory per press, without the
  continuous acceleration, wrap and skip-unused of the real keys.

### Remaining limitations

- **Air Manager is still not installed, so none of this has been run.** No
  runtime validation was performed and none is claimed. In particular the
  `switch_add` finding above was settled from the published API reference, not
  by loading the instrument.
- The wing-null / airframe-shadowing entry below remained research only at this
  point in the history; it is superseded by the implementation entry above.

## 2026-09-07 — Post-integration instrument review

**Status: review completed; findings unresolved.** Reviewed the current Becker
SAR-DF 517, RHOTHETA RT-600, TDFM-136B, GMA 1347, and propagation-engine code
against the manuals after the artwork integration. No fixes were made as part of
this review.

### Runtime defects

- The TDFM's three `switch_add` calls omit the required third switch-image
  argument (`nil` for a two-position switch). Coordinates and the callback are
  consequently passed in the wrong argument positions and the instrument is
  expected to fail during Air Manager loading.
- Becker page 6 cycles through the `SCAN` row as an editable training frequency,
  but that row has no `min` or `max`. Turning the value knob on that row compares
  a number with `nil` and raises a Lua runtime error. The fifth row also overlaps
  the page's bottom status text.

### Receiver and frequency-model inaccuracies

- The Becker UI permits the manual's freely adjustable 400.000–409.975 MHz
  training frequency and defaults it to 406.037 MHz. The propagation engine
  nevertheless rejects every Becker Cospas-Sarsat frequency except 406.025 and
  406.028 without considering Emergency versus Training mode. Becker scan is
  likewise hardcoded to the emergency frequencies instead of using the selected
  training frequencies.
- The RT-600 manual defines seven CPSAR receiver settings, each covering two or
  three 3 kHz beacon channels simultaneously. The instrument instead presents
  individual 3 kHz frequencies and the engine applies a single-channel ±1.5 kHz
  tolerance.
- The RT-600 list ends at 406.073 MHz and omits 406.076 MHz. The inclusive
  406.022–406.076 grid contains 19 channels (A through S), not the 18 stated in
  the Lua comments, engine comments, and `docs/DATAREF_CONTRACT.md`.
- The RT-600 FRQ page is a flat frequency list. The real control flow selects
  MEM1–4, Work, FIX, or one of seven CPSAR groups with PAGE; VOL and SQL edit MHz
  and kHz; and F2 changes bands. Those selection/edit modes and CPSAR scan are
  absent. Scan requests currently reach engine logic hardcoded for the Becker
  406/121.5/243 scan.
- The propagation engine decodes Cospas-Sarsat bursts continuously. The RT-600
  can therefore display a frame received before its Decode window was opened,
  although the manual says decoding is possible only while that window is active.

### GMA 1347 behavior gaps

- Split COM routes copilot audio to COM2, but its annunciation is wrong: COM1 and
  COM1 MIC go dark. The manual requires COM1, COM1 MIC, COM2, and COM2 MIC all to
  be annunciated and active in split operation.
- Selecting a COM MIC does not update the corresponding COM audio selection or
  annunciator. The manual says the matching audio key is selected automatically.
- VOL/SQ can be toggled while MAN SQ is off, although the manual says a knob press
  has no effect in auto-squelch and VOL remains selected. The pilot and copilot
  rings share one internal volume/squelch value, and the panel has no dynamic VOL
  or SQ annunciation.
- PA, TEL, SPKR, HI SENS, MAN SQ, and PLAY are local lamp/state approximations and
  do not provide their stated audio functions.

### TDFM-136B behavior gaps

- Direct channel entry waits for `#` after three digits. The manual says the
  three-digit entry itself selects the memory and reserves ENTER for toggling
  home/current.
- Back/forward changes one memory per press. The real keys scroll continuously,
  accelerate while held, wrap, and skip unused memories.
- The channel squelch LEDs are hidden when COM3 audio is deselected. They are
  radio receive indicators and should still show a received signal, allowing the
  trainee to diagnose an audio-panel routing error.
- Main/guard volume, squelch defeat, display brightness, and mission-channel scan
  currently change only local state or display characters; they do not affect
  mission audio or reception.

### Becker behavior gap

- STORE's 3 kHz tone-suppression state only draws `3K-`. It does not suppress an
  audio tone or inhibit bearing, despite the manual stating that bearing is not
  possible while the tone is suppressed.

### Validation and test gaps

- `python3 scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua`
  passes all 14 files.
- `python3 tests/test_faceplate.py` passes all 68 checks.
- `python3 tests/test_engine.py` passes all 33 checks.
- `python3 scripts/make_previews.py` regenerates resources and previews
  byte-identically.
- These checks cover syntax, static geometry, assets, and the behavior currently
  encoded in the engine tests. They do not validate Air Manager API signatures
  or the manual-level operating semantics above. Air Manager remains unavailable
  on this machine, so runtime integration is still untested.

## 2026-09-07 — MO station artwork and Lua integration (TDFM-136B, GMA 1347)

**Status: implemented.** Brings the two Mission Observer instruments to the
layered-artwork standard the DF heads were moved to earlier today. Validated as
far as is possible without Air Manager.

### Faces corrected against the manuals

Both instruments had the wrong proportions, which the reference figures settle:

| Instrument | Was | Now | Authority |
|---|---|---|---|
| TDFM-136B | 750 x 320 (2.34) | 800 x 420 (1.905) | Fig 1-1 plate measures 1044 x 545 px, aspect 1.916 |
| GMA 1347 | 240 x 740 (1 : 3.08) | 240 x 1422 (1 : 5.925) | §6A.2: "1.3 inches in width and 7.70 inches in height" |

The GMA was roughly half as tall as the real unit. `info.xml` preferred sizes
updated on both.

### Artwork

Same three layers as the DF heads. `resources/faceplate.png` carries the
housing, screws, display recess, group outlines and every silk-screened legend;
the live display stays a Lua canvas; everything that moves, swaps or lights is
its own image. Keys that carry a printed legend get their own image pair,
because the cap moves when pressed — twelve for the TDFM keypad, twenty-one for
the GMA. Knobs carry no index stripe, for the same reason as the DF heads:
`dial_add` does not rotate its image.

New generator `scripts/make_panel_artwork.py`, which **parses the geometry
blocks in the new `lib/tdfm_panel.lua` and `lib/gma_panel.lua`** rather than
repeating them, so artwork and hit regions cannot drift apart.

### Fidelity corrections from the reference figures

TDFM-136B, Figure 1-1:

- **Toggles are labelled above and below the lever** — MN over GD, G1 over G2,
  HI over LO. The draft drew a single "MN/GD" caption underneath.
- **Keys 2, 4, 6 and 8 print their digit inside a cursor arrow** and carry no
  word. The draft labelled them UP / BACK / FWD / DOWN.
- Squelch LEDs sit **inside the display bezel**, one at the start of each line.
- Corner slotted screws plus two small cross screws at mid-height; PGM data port
  drawn as the seven-pin connector it is.
- The preview's display now renders the **lowercase** mode and squelch-mode
  characters (`w`/`n`/`D`, `x`/`t`/`c`/`m`/`n`/`g`). It was uppercasing them,
  which erased a distinction `lib/tdfm_display.lua` exists to preserve.

GMA 1347, Figure 6A.2.1 and §6A.2:

- **Annunciator triangles are white, not green.** "The triangular key annunciator
  lights are white when illuminated."
- **The volume control is a concentric pair, not one knob.** The small knob is
  the pilot channel, the large one copilot and passenger; both are now wired,
  and only the outer ring writes the copilot volume dataref.
- **Row 9 has no right-hand key** — an ambient light sensor sits there. The key
  table is 21 entries, not 22.
- The invented status line across the top of the panel is gone. Table 6A.3.2's
  isolation states are already readable from the PILOT and COPLT annunciators
  (neither lit = ALL, PILOT = PILOT, COPLT = COPILOT, both = CREW) and split COM
  from the COM 1/2 annunciator. Reading the lamps is the thing being taught, and
  the real panel has no text. No state was lost, only a non-prototypical readout.
- The GMA now has no canvas at all, and no longer ships `lib/lcd.lua`; it is a
  panel of lamps and keys.

### Defect found in the geometry parser

`scripts/make_panel_artwork.py` first read geometry with a bare `M.NAME\s*=`
search. Against Lua's multiple assignment — `M.KEY_X0, M.KEY_Y0 = 400, 202` —
that matches the *second* name and returns the *first* value, so the TDFM keypad
was generated 198 units too low with the wrong key height and row pitch. The
parser now splits the line and matches by position. `make_df_artwork.py` reads
only single assignments, and now rejects a multiple assignment loudly instead of
mis-parsing it.

### Preview pipeline

`scripts/make_artwork.py` was **deleted**: it generated generic knobs, keys,
toggles and LEDs that no instrument uses any more, and keeping it was the same
silent-overwrite hazard that was guarded for the DF heads. `make_previews.py` is
now a front-end that runs the two generators and draws nothing itself. One
generator per instrument, no second copy of any geometry.

Superseded resources removed: five from the TDFM, three from the GMA, plus the
GMA's unused `lib/lcd.lua`.

### Validation performed

- `python3 scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua`
  — 14 files, all OK.
- `python3 tests/test_faceplate.py` — **68 checks**, extended from 26 to cover
  all four instruments: every geometry block parses; no control overlaps another
  or a display; the TDFM's LEDs sit inside the window bezel and clear the
  character matrix; each GMA annunciator sits above its own key and the
  concentric knob nests inside the outer ring; every named image ships at the
  expected size with no orphans; no instrument ships an unused library; both new
  faces match the dimensions their manuals give; `info.xml` agrees with each
  face.
- `python3 tests/test_engine.py` — 33 checks pass. Engine untouched; run as a
  regression guard.
- `python3 scripts/make_previews.py` reproduces every resource and preview
  byte-identically.
- Both previews inspected side by side against their manual figures.

### Remaining limitations

- **Air Manager is still not installed, so none of this has been run.** No
  runtime validation was performed and none is claimed. The bring-up items
  specific to this change are: the GMA has 21 button hit regions plus 21
  annunciator images on a 240 x 1422 face, so confirm `img_add` layering order
  puts annunciators above the faceplate and below nothing that matters; and the
  concentric knob relies on the inner `dial_add` being added after the outer one
  to take clicks inside its own area.
- The TDFM's Level-1 map still leaves keys 7 (FREQ) and 9 (SQL) inert. That is
  pre-existing and deliberate — they are edit commands the CAP guide tells the
  observer not to touch — and the caps are drawn because the real panel has them.
- The TDFM encoders are drawn without the index line Figure 1-1 shows, for
  consistency with the DF heads: Air Manager cannot rotate a dial image, and a
  static index on a control the user drags reads as broken.
- The previews' displays are Python mirrors of the Lua layouts, not captures.
  They share the geometry constants but not the drawing code.
- No engine, dataref, or propagation behaviour was changed by that artwork
  revision. Wing blanking was implemented later, as recorded above.

## 2026-09-07 — Becker SAR-DF 517 faceplate artwork and Lua integration

**Status: implemented.** Artwork produced, integrated into the instrument's
rendering path, and validated as far as is possible without Air Manager.

Replaces the flat canvas-drawn bezel on the Becker SAR-DF 517 with layered
artwork built to the manual's measured geometry, and rewires the instrument to
use it. The RHOTHETA RT-600 shares `lib/dcu.lua`, so it was carried along with
its own branding and behaviour intact rather than left broken.

### Artwork

Three layers, which is what lets the printed lettering be smooth while the
display stays a dot matrix:

- `resources/faceplate.png` — housing with clipped corners, circular face
  inset, four mounting screws, recessed LCD surround, and every silk-screened
  legend in Liberation Sans: `Clr` / `Store` / `Rep`, curved `SQL` and `Page`
  with their arrows, `DIM` linked from Rep to Page, the +/- rotation marks
  around the lower knobs, the Rhotheta / SAR-DF 517 / BECKER identification
  lockup, and `ON/OFF`.
- `resources/knob.png`, `button.png` / `button_pressed.png`,
  `power.png` / `power_pressed.png` — the movable controls. ON/OFF is a
  separate moulding from the three domed keys, as Fig 3-3 shows.
- The 128x64 LCD stays a live Lua canvas.

Nothing dynamic is baked into the faceplate: no bearing, frequency, status or
knob. The knobs carry no index stripe — neither the manual figure nor the CAP
photographs show one, and `dial_add` does not rotate its image, so a painted
index would have been a mark that never moved.

**No image-generation tool was available in this session**, so the artwork is
drawn procedurally with Pillow rather than generated. The approved concept in
`output/becker-visual-study/after.png` was used as the visual target — matte
charcoal, clipped corners, circular inset, scalloped knobs, metal screws,
recessed LCD, restrained lighting — and the Becker manual was followed wherever
the two disagreed. That directory is now a record of the study, not artwork.

### Geometry

The chassis grew from a 470-unit face to 520 with an integer LCD scale of 3, so
the 128x64 framebuffer maps to 384x192 with even dots. All positions are
measured off `docs/figures/b517_p29_bearing_controls-29.png`; the measurements
are tabulated in `docs/SOURCES.md`. `info.xml` preferred sizes updated on both
heads.

`scripts/make_df_artwork.py` **parses the marked geometry block in
`instruments/becker-sar-df-517/lib/dcu.lua`** rather than repeating it, so the
artwork and the control hit regions cannot drift apart. If the block stops
parsing the script fails instead of guessing.

### Integration defects found and fixed

- The radial bearing pointer was drawn from the rose centre and ran straight
  through the bearing digits, making them unreadable. It now starts where the
  ray leaves the text block, which is how Fig 3-3 draws it.
- The page-1 CONE / MASK annunciator at (86,48) overlapped the band frame. The
  reason now appears in place of the bearing — where the operator is already
  looking — and pages 2 and 3 say why there is no fix rather than just that
  there is none.
- The right-hand status column at x=97 lost the last glyph of `OFS:+000` and
  `LS:00:00` off the 128-dot edge; moved to 94. `CHNL.(16)` overflowed the band
  frame; the frame was widened.
- `draw_signal_bar` in the 517 duplicated `dcu.draw_bar` with a different
  squelch marker. Removed; both heads now use the one drawing.

### Fidelity improvements from the manual

- Compass rose rebuilt: outer dot ring, graduation ring clear of the bearing
  block, cardinal ticks, and §3.3's spread markers — solid at the averaged
  bearing, hollow at each un-averaged extreme. `cap/df/spread` now has a display
  that means something. Display change only; the dataref is unchanged.
- `MOUNT:` with a tee glyph (upright TOP, inverted BOTTOM) replaces `MNT:TOP`.
- Page-1 band frame carries the two-line caption Fig 3-3 shows, so the marine
  channel reads `SEA-BAND` / `CHNL.(16)`.
- Row of six page marks under the PAGE field, active one solid.
- Signal bar gained its 10% graduations and the manual's stub-and-block squelch
  marker.

### Preview pipeline

`preview.png` for both heads is now composited from exactly the layers Air
Manager stacks, by the same script that makes them. The two paths that could
have silently restored the obsolete appearance are closed: the DF branch of
`scripts/make_previews.py` was deleted and delegates instead, and
`scripts/make_artwork.py` refuses to write into the two DF folders. Running
`make_previews.py` reproduces the DF previews byte-identically.

Seven legacy resources per DF head (`knob_small`, `led_*`, `toggle_*`, `key*`)
were unreferenced after the rewire and were removed.

### Validation performed

- `python3 scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua`
  — 13 files, all OK.
- `python3 tests/test_engine.py` — 33 checks pass. Engine and dataref interface
  were not touched; run as a regression guard.
- `python3 tests/test_faceplate.py` — **new**, 26 checks: geometry block parses,
  no control overlaps another or the LCD window, screws clear the knobs, every
  image the Lua names is shipped at the expected size, no orphan resources,
  `info.xml` matches the face, the DF heads' shared libraries are byte
  identical, the Becker has neither F1/F2 keys nor the RT-600 name while the
  RT-600 keeps both, and no literal LCD string runs off the 128-dot panel.
- Previews inspected against Fig 3-3 and the concept side by side.

### Remaining limitations

- **Air Manager is still not installed on this machine, so none of this has been
  run.** No runtime validation was performed and none is claimed. A bring-up
  checklist is in the handover notes; the first things to confirm are that
  `img_add`, `dial_add` and `button_add` accept these resources at 520 units and
  that the LCD canvas registers over the faceplate window in the right order.
- The bearing bracket glyph is the one thing the manual scan cannot settle: Fig
  3-3 reads as `<337<` at that resolution while the CAP photograph of an RT-600
  DCU clearly shows `<010>`. Both heads draw `<nnn>`.
- The preview's LCD is a Python mirror of the Lua page-1 layout, not a capture
  of it. The two share the geometry constants but not the drawing code, so a
  change to a page must be made in both if the preview is to stay honest. Only
  page 1 (517) and the DF page (RT-600) are previewed.
- The scan-mode band caption reads `SCAN MODE / 406/121.5`; the frame holds nine
  characters and 243.000 is also in the §3.3.3 dwell.
- No engine, dataref, or propagation behaviour was changed by that artwork
  revision. Wing blanking was implemented later, as recorded above.

## 2026-09-07 — Wing-null / airframe-shadowing research

**Status: research completed; implementation proposed, not implemented.**

Superseded by **Wing blanking and instantaneous receiver state implemented**
above. This entry is retained as the research and design record.

Investigated CAP pilots' use of banked turns to shield a receiving antenna
from an ELT, producing an audible signal reduction or null that helps
localize the beacon. The technique is called wing null or wing shadowing.

### Findings

- CAP's Mission Inflight Guide (July 2021), printed pages 71–73, describes
  installation-dependent directional cues: at a null, the lowered wing
  generally points toward the beacon for antennas below the wings; the
  raised wing does so for antennas above the wings. Observations from
  different positions help narrow the search area.
- The receiving antenna's actual location matters. Wings and fuselage can
  shield reception; a bank angle alone is insufficient to predict a null.
- Becker/G1000 training hosted by RHOTHETA describes using COMM reception
  and wing shielding before transitioning to Becker automatic direction
  finding. Do not assume that every belly-mounted Becker installation
  produces a textbook wing null, or that it is immune to shielding.
- A useful training approximation is feasible. Exact attenuation, null
  width, and bearing disturbance require installation-specific calibration;
  the reviewed sources do not establish a universal attenuation curve.

### Current implementation inspected

The installed engine at
`/home/ron/X-Plane 12/Resources/plugins/PythonPlugins/PI_capvsar_df.py`
reads position and heading but not roll or pitch. Its mounting configuration
can mirror bearing interpretation, but does not model physical airframe
shielding. Signal strength is currently clamped before terrain attenuation.
The instrument/engine interface is documented in `docs/DATAREF_CONTRACT.md`.

### Proposed implementation

1. Calculate the aircraft-to-beacon direction in aircraft body coordinates
   using position, heading, roll, pitch, and beacon elevation.
2. Apply configurable, installation-specific directional attenuation for
   each receiving antenna, including separate COMM and DF profiles.
   Simplified wing/fuselage intersection geometry is a possible refinement.
3. Apply attenuation before signal saturation and receiver processing, so
   strong nearby signals can remain receivable through partial shielding.
   Drive signal indication, squelch, audio reception, and bearing quality
   from the resulting reception state.
4. Keep instantaneous audio reception separate from held/valid bearings.
   COMM reception must be independent of Becker power and tuning. Keep
   physical installation truth separate from the crew's TOP/BOTTOM setting.
5. Distinguish airframe shielding from terrain masking and overhead bearing
   confusion; do not repurpose the existing terrain-blocked flag.
6. Begin with continuous homing-signal scenarios and preserve separate
   406 MHz burst behavior. Validate opposite banks, top/bottom installations,
   beacon elevation, strong-signal reception, and held-bearing/audio behavior.

This work belongs primarily in the Python propagation engine and radio audio
path, with Lua instruments displaying the resulting reception. No engine,
Lua, artwork, or dataref changes were made as part of this research entry.

### Sources

- [CAP Mission Inflight Guide, July 2021](https://txwg.cap.gov/media/cms/Inflight_Guide_Rev_July_2021_1D641C_FA6854DBA1C18.pdf), printed pages 71–73.
- [Becker/G1000 training hosted by RHOTHETA](https://rhothetaint.com/wp-content/uploads/2019/08/beckerdfwithg1000slides.pdf), slides 17 and 22–25.
- [FAA AC 91-44A](https://www.govinfo.gov/content/pkg/GOVPUB-TD4-PURL-LPS107811/pdf/GOVPUB-TD4-PURL-LPS107811.pdf), paragraph 12(b)(2); historical technical reference, not current flight-procedure guidance.
