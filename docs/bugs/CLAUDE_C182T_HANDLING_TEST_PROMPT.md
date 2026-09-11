# Claude prompt — CAP 487 progressive handling tests

Use this prompt for **X-Plane simulator validation only**. These are proposed
engineering test cards, not approved instructions for flight in a real aircraft.
Continue through the existing authorized flight-control owner and serialized
maneuver gate; do not create a second controller or X-Plane instance.

## Objective and starting evidence

Characterize CAP 487's basic handling across airspeeds before progressing to
slow flight and stalls. Use the discipline of a test pilot: a fixed configuration,
one changed variable per comparison, explicit entry/recovery criteria, repeatable
inputs, and recorded evidence. Do not tune the aircraft between repetitions.

Read current CHANGELOG.md, A-1, docs/C182T_FLIGHT_TEST_CARD.md,
docs/C182T_DIMENSION_MASTER.md and the active flight-test/controller code first.
Preserve other agents' changes. This prompt supplements the existing performance
card; passing these points does not validate the entire aircraft or close A-1.

Before flying, produce a brief test matrix and confirm telemetry/control support.
If the authorized controller cannot perform a maneuver or surrender the necessary
control loops, mark it BLOCKED or have the human pilot fly while you capture.
Do not bypass the controller gate to force a test.

## Reference and configuration gate

Use the project's pinned C182T NAV III/GFC 700 POH, P/N 182TPHBUS-00/-01,
Sections 2, 4, 5 and 6. Record page/figure for each limit and expected result.
Confirm weight-dependent Va, flap speed limits for each setting, normal climb
speeds, stall tables and the IAS/CAS distinction. ACF V-speed labels are not
measurements of the aerodynamic model. Do not substitute a T182T or C172 table.

Resolve the flap-label issue explicitly: record cockpit detent, commanded ratio,
and actual aerodynamic surface deflection. A FULL cockpit setting and a mechanical
travel angle need not have identical numeric labels. Do not assume the recently
patched 38-degree travel has been proved aerodynamically correct.

Use these proposed simulator conditions:

- First sortie: 2,700 lb, CG at the midpoint of the POH-permitted envelope at that
  weight. Later repeat selected points at 3,100 lb, first mid-envelope, then near
  the verified forward and aft limits separately. Record actual weight at each point.
- Do NOT use FS 33 as the forward limit at 3,100 lb. The published envelope is
  weight-dependent; the simulator's single forward limit does not enforce it.
  Verify mass and CG readbacks and their coordinate conversion before testing.
- ISA, daylight, zero wind/turbulence, no icing or failures; fixed fuel loading,
  mixture procedure, cowl-flap setting and propeller RPM appropriate to the card.
- Choose flat terrain with a working block that allows entries at least 6,000 ft
  AGL. Proposed hard recovery floor: 3,000 ft AGL. Record pressure altitude and
  temperature separately; do not compare high-altitude climb to sea-level claims.
- Normal sim rate, recorded frame rate and flight-model settings. Save an initial
  state for reproducing each card. Resets are between points, never in a measured run.

## Instrumentation and repeatability

Capture at least 10 Hz when available (prefer 20 Hz for transients); save actual
sample intervals and flag gaps. Use existing recording facilities first. Log:

- IAS, TAS, altitude MSL/AGL, vertical speed, pitch/bank/heading and body rates;
- angle of attack, sideslip or slip-ball, normal acceleration, stall-warning state;
- throttle, manifold pressure, RPM, fuel flow, flap handle and actual deflections;
- pilot/controller commands, actual elevator/aileron/rudder and trim positions;
- controller mode, saturation/override states, weight, CG, weather and sim rate.

Missing observables are UNMEASURED, never inferred as zero. Ordinary simulator
controls do not establish real stick force or buffet fidelity. Report displacement,
trim demand and simulated cues; do not claim measured force gradients.

Separate **airframe characterization** from **controller tracking**. A pitch/altitude
loop can hide instability and prevent a natural stall. For airframe tests, use
human/manual inputs or supported bounded test inputs through the authorized gate,
with interfering holds off. For controller tests, leave them on and label results.
Use the same aircraft build for both; record its hash and controller version.

Proposed entry gate for steady cards: 20 seconds within ±2 KIAS, ±50 ft, and
±3 degrees heading; wings level within ±2 degrees unless the card calls for a turn.
These are data-quality targets, not Cessna certification tolerances. Capture 30–60
seconds after settling. Repeat each comparison three times and test both turn
directions. If a point will not settle, record that outcome instead of selecting
one favorable instant.

## Profiles — fly in this order

### H0 — control and trim confidence, 100 KIAS clean

Establish level flight and trim. Check small, smooth pitch, roll and yaw inputs
one axis at a time, returning to the reference condition between inputs. Start
with the smallest useful input and record its magnitude/duration. Check control
sign, response delay, trim authority and persistent asymmetry. Do not use full
control reversals. Stop progression for reversed response, divergent motion,
unexpected override or persistent saturation.

### H1 — level-flight speed ladder, clean

Fly **120, 110, 100, 90 and 80 KIAS**, then reverse the order. These are proposed
sample points, subject to verified limits and stall margins, not published C182T
performance promises. Use 120 only as a smooth steady point if permissible; do
not assume it is below Va at every weight. Omit any low-speed point lacking at
least 1.3 times the applicable reference stall speed in consistent calibrated units.

At each point, trim and record power required, pitch, elevator/trim position,
coordination and tracking variation. Plot power and trim against speed. Repeat
90 and 110 KIAS at the end to detect drift with fuel burn or controller state.
Where manual control is supported, briefly hold trim fixed after a small speed
perturbation and observe the initial tendency; recover promptly. Do not label
closed-loop recovery as natural longitudinal stability.

### H2 — bank and coordination ladder

At **110, 90 and 80 KIAS**, fly left/right 90-degree heading changes at **15 and
30 degrees bank**, recovering straight and level between points. Apply the speed
margin to the turning condition, not just the wings-level stall speed. Omit any
combination that fails the margin or verified maneuvering limits.

Measure achieved bank, roll-in/out time, yaw/slip, altitude loss, speed error,
load factor and control demand. Compare left with right. For an approximately
level coordinated turn, use n ≈ 1/cos(bank) and Vs-turn ≈ Vs-level × sqrt(n) as
physics cross-checks, not POH substitute targets; apply speed ratios in CAS/EAS.

Only after these pass, optionally try **45-degree bank at 100 KIAS**, both ways,
with the same gates. Do not extend to 60-degree banks or accelerated stalls here.

### H3 — climb/descent transitions

From 100 KIAS level, establish clean climbs at **90 KIAS** and the **POH Vy for
the test condition**. Stabilize and measure altitude change over a timed interval,
not peak indicated VSI. Compare with the matching weight/altitude/temperature
performance table. Return to the same initial state for repeat comparisons.

Then fly powered descents at **100 and 90 KIAS**, followed by level-offs. Record
pitch/power changes, rudder demand, overshoot and time to settle. Keep controller
tracking results distinct from airframe performance. No ground proximity work.

### H4 — configuration transitions at altitude

At **90 KIAS**, if permitted for each flap setting, change UP → first detent →
20 → FULL one step at a time, then reverse. Hold each for at least 20 seconds.
Record pitch transient, trim change, speed tendency, power needed and actual flap
position. Recover to a stable reference after each step; no abrupt full retraction
at low speed. Abort if a selected setting violates its limit or stall margin.

### H5 — slow flight without sustained stall warning

First clean, then 20 and FULL, use the applicable POH stall reference and verified
configuration. Begin around **1.3 Vs**, then cautiously approach **1.2 Vs** in
consistent CAS/EAS terms, using the POH calibration to establish cockpit IAS.
If calibration at a condition is unavailable, record the uncertainty and use a
conservative higher entry speed; do not invent an exact KIAS target.

Maintain a margin above stall warning; if warning arrives sooner, that is the
boundary, not a reason to keep chasing the planned number. Assess level flight,
small heading changes with no more than **15 degrees bank**, and a modest powered
climb/descent. Record authority, coordination, trim, power and warning onset.
Recover at the first unexpected warning or loss of control margin.

### H6 — approaches to stall, then wings-level power-off stalls

First fly approaches to stall, recovering at the first warning, in clean and
landing configurations. Progress to full stalls only after consistent recovery
and verified telemetry/control behavior. Follow the applicable POH recovery.

For full stalls: start clean, then 20, then FULL; power idle, coordinated and
wings level, approximately **1 knot/second deceleration**. Do not chase a nominal
stall speed: identify the event from the observed break, loss of lift/control
response and available cues. Log warning onset separately from stall onset.

Recover by reducing angle of attack promptly, applying appropriate power and
coordinated control, then restoring configuration per the POH. Record warning
speed, stall IAS and any valid calibrated equivalent, pitch/AoA, wing drop, yaw,
minimum altitude, altitude lost from recovery initiation, time to positive climb
and secondary warning. Keep full flap until the recovery procedure calls for
staged retraction. No altitude-hold loop should pull through the stall.

Repeat three times per configuration. Compare only with the matching POH weight,
CG, bank and power condition. Treat the existing ±3 KIAS criterion as a proposed
project tolerance, not a manufacturer-guaranteed tolerance. Never use an idle-stall
table as the target for a powered stall.

### H7 — power-on stall behavior, conditional final card

Only after H6 is satisfactory, use the POH takeoff/departure configuration and
specified setup, coordinated and wings level. Start with recovery at warning.
Proceed to a full power-on stall only if the authorized pilot/control path can
perform the entry and recovery without conflicting holds. Record actual power;
a reduced-power run must be labelled as such, not a full-power validation.

Measure yaw tendency, warning-to-break interval, wing drop and recovery loss.
Do not force a break with extreme pitch or uncoordinated input if the model does
not produce one; record NO BREAK UNDER TESTED CONDITIONS. No spins, cross-controlled
stalls, turning power-on stalls or accelerated stalls in this sequence.

## Stop criteria and progression

For every card, recover immediately for an unexpected configuration, telemetry or
control failure, limit exceedance, unexpected warning outside a stall card, or
loss of the test block. Proposed additional stall-card aborts: unintended bank
beyond 20 degrees, uncontrollable yaw or approach to the 3,000-ft-AGL floor.
Record the abort; do not erase it with a reset. After recovery, diagnose before
repeating. Stop the series for divergent behavior or inconsistent control ownership.

Do not expand weight/CG until the initial series is repeatable. At later weight/CG
points repeat H0, selected H1/H2, then H5/H6 in that order; postpone aft-CG powered
stalls to a separately reviewed expansion. Restore identical conditions between
runs rather than changing mass or CG mid-maneuver.

## Deliverable

Save traces and a compact report keyed by card/run ID:

`build | control mode | weight/CG | atmosphere | configuration | target | actual |
repeat spread | reference | pass/fail/inconclusive/blocked | anomaly | trace path`

Plot speed/pitch/altitude, controls/trim, bank/slip and warning/AoA through the
maneuvers. Summarize separately: airframe findings, controller findings, setup or
instrumentation errors, and untested envelope. A miss is evidence to investigate,
not proof of one coefficient being wrong. Propose one change at a time, then
re-run the failing point plus previously good neighboring points. Preserve raw
baseline traces. Update shared status only after re-reading concurrent edits.

## Basis

The sequence, sample speeds, repeat counts and stop gates above are proposed
simulator engineering choices. FAA guidance provides the distinction between
slow flight, warning recognition and stall recovery—not these numeric acceptance
criteria. Consult [FAA Airplane Flying Handbook, Chapter 5](https://www.faa.gov/sites/faa.gov/files/regulations_policies/handbooks_manuals/aviation/airplane_handbook/06_afh_ch5.pdf).

The governing aircraft reference is the [project-pinned C182T NAV III/GFC 700
POH](https://ilwg.cap.gov/media/cms/182TNavIIIGFC700InfoManual_4C95242EF1943.pdf),
with provenance in the dimension master. Its public URL returned HTTP 403 during
preparation; use the previously verified local copy and verify every numeric
limit before execution. An [earlier Cessna NAV III POH](https://www.dentoncap.org/uploads/182T-POH-Section-1-8.pdf)
was available for cross-checking terminology, but is a different part number and
is not substituted for the governing manual. In particular, its headline stall
speeds are labelled KCAS, illustrating why units must be checked.
