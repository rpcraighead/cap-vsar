# Card H0 — control-law findings from five attempts

**Simulator engineering validation only. These are proposed engineering test
cards, not approved instructions for flight in a real aircraft.** Everything
below was flown in X-Plane 12 on the CAP 487 C182T package through the existing
authorized `ManeuverGate`. No second controller and no second X-Plane instance
was created, the gate was never bypassed, and `services/ai_pilot/maneuvers.py`
was not modified.

Date: 2026-09-11. Aircraft: CAP 487 (`Cessna 182T NAV III`), clean, over water
off San Nicolas Island (33.76 N, 119.08 W). Controller:
`services/ai_pilot/direct_backend.py`. Card: H0, control and trim confidence,
100 KIAS clean.

---

## Headline

**Card H0 was flown on 2026-09-17, on the sixth attempt.** Nine of its ten
points are attributable to a stabilized 100 KIAS reference condition. Run 6 is
recorded in §8.

The five preceding attempts produced no valid data point: none of them reached
a first control input from a stabilized reference. That was not a failure of
the card. Each terminated on a different, real defect in the controller, all
five are fixed and locked by offline tests, and the card found every one of
them — none was caught by the 53 offline tests that existed before the first
run. Those five are documented in §1 and are kept here deliberately, because
the defects are the reason run 6 worked.

**No handling point is recorded as a pass or a fail against a published
criterion, because H0 has no such criterion — it is a control and trim
confidence card. Nothing here validates the aircraft, and nothing here closes
A-1.**

---

## 1. The five defects

### Run 1 — instantaneous inputs, no coordination

*Invalidated on the pilot's call.* Test inputs were applied as steps: the
commanded surface went from zero to the test magnitude in a single 100 ms
control tick. No real control input looks like that, and an airframe's response
to a step is dominated by the step. There was also no rudder coordination, so a
roll input was flown with a sideslip that changes the lift distribution and
biases the measurement — left and right then respond differently for reasons
that are not the airframe.

**Fix.** `TestInput.shaped(elapsed_s)` produces a trapezoidal ramp: a linear
rise over `ramp_s`, a plateau, and a symmetric decay. If the duration cannot
accommodate a full plateau the shape degrades to a triangle rather than back to
a step. Coordination closed on sideslip (`BETA_TO_RUDDER`, `BETA_TO_RUDDER_I`)
on top of the existing adverse-yaw feedforward.

### Run 2a — throttle bang-bang

Throttle swung between 0.150 and 1.000 and airspeed between 94.7 and 108.8 KIAS
about a 100 KIAS target.

**Cause.** The speed loop was a *pure integrator* at 0.010 per tick at 10 Hz —
0.1 of throttle per second per knot of error. An integrator has no way to stop:
by the time the speed reaches target the throttle is already against a limit,
and the error must *reverse* before it begins to unwind.

**Fix.** PI. `SPEED_TO_THROTTLE_P` gives the immediate response;
`SPEED_TO_THROTTLE_I` only trims out what is left.

### Run 2b — a standing sideslip in the climb

*From the pilot: "more right rudder is needed in the climb."*

The controller held a steady +1.6 degrees of right bank all the way up. That was
not trim. It was a **standing sideslip that the heading loop was masking** by
holding a wing down — the heading was correct, so nothing in the outer loop
complained, and the aircraft climbed out of balance the whole way.

A clockwise-turning propeller yaws the aircraft left under power — P-factor,
torque, and the slipstream striking the fin — and the effect grows with power
and with angle of attack, so it is worst slow and at full throttle: the climb.
Proportional feedback alone always lags it.

**Fix.** `RIGHT_RUDDER_FF`, a feedforward scaling with throttle and inversely
with dynamic pressure, plus the bounded sideslip integral.

### Run 3 — "bank is abrupt like pitch inputs were"

*From the pilot, mid-run.*

**The ramp was working.** Verified on the trace, on the command path, for the
roll +0.10 input:

| t (s) | shaped | aileron cmd | aileron (deg) | bank (deg) | roll rate |
|---|---|---|---|---|---|
| 0.10 | 0.0077 | 0.0077 | 0.147 | 1.98 | −0.683 |
| 0.50 | 0.0478 | 0.0478 | 0.682 | 2.00 | +0.898 |
| 1.00 | 0.0979 | 0.0979 | 1.427 | 2.85 | +3.288 |
| 1.10 | 0.1000 | 0.1000 | 1.576 | 3.20 | +3.793 |

The shaped value climbs smoothly over exactly one second and the commanded
aileron tracks it to four decimals.

**The step was at the other end of the input.** On the recovery from the roll
−0.10 point:

| t after release (s) | aileron cmd | bank (deg) | roll rate (deg/s) |
|---|---|---|---|
| 0.00 | −0.0035 | −20.71 | −1.72 |
| 0.15 | **0.3500** | −20.46 | 9.02 |
| 0.60 | **0.3500** | −14.87 | 14.19 |
| 1.20 | **0.3500** | −7.25 | 14.26 |
| 1.96 | 0.1892 | +3.11 | 8.95 |
| 3.16 | 0.0321 | +9.17 | 1.49 |

The instant the input expired, the heading loop saw a 20.7 degree bank and
commanded the **aileron limit in a single 100 ms tick**, held it saturated for
1.2 s, reached 14.3 deg/s of roll rate and overshot through wings-level to +9.2
degrees the other way.

No amount of ramping the input can fix a step that is not in the input.

**Two fixes.**

*Rate damping* on both inner loops (`ROLL_RATE_TO_AILERON`,
`PITCH_RATE_TO_ELEVATOR`). Proportional-on-*angle* has no way to know the
aircraft is already moving, so it keeps commanding correction all the way to the
target and overshoots through it. The rate term is what a pilot does
instinctively — lead the roll out.

*A slew-rate limiter* on all three surfaces, applied last before the wire, so
nothing upstream — loop, clamp, or test input — can produce a step at the
controls. A ramped test input passes through untouched (0.10 of travel per
second against a 0.40 limit); what gets limited is the transition at each end of
it. A hand on a yoke cannot move full travel in one control tick; neither should
this. The limiter delays authority, it never withholds it, and that is locked by
a test.

### Run 3 (also) — the reference condition was never established

Obscured by the abruptness, and worse. Run 3 entered **22 knots fast**. The
throttle went to the idle stop and the integral wound to its −0.35 limit and sat
there for ten seconds, where integrating could not change the output because the
throttle could not go lower anyway:

```
  t    kias     alt      vs      thr    thr_i
  1.0  121.5   4100      12    0.150   -0.350
  5.0  111.3   4096     -94    0.150   -0.350
 10.0  101.0   4084    -209    0.180   -0.350     <- on target, trim still at the stop
 14.1   95.0   4067    -270    0.441   -0.208     <- still unwinding, speed still falling
```

When speed reached 100 at t=10 the trim term still had to unwind off the stop,
so the throttle stayed near idle and speed sailed on through to **94.1 KIAS in a
274 fpm descent**. That was the condition the first test input was flown from.
None of run 3's responses are attributable to a 100 KIAS level reference.

**Fix.** Clamping the integral *term* is not anti-windup. Conditional
integration: accumulate only when doing so can actually change the output — when
the output is unsaturated, or when the update moves it away from the stop.

### Run 4 — the gate worked, and found a loop satisfied with the aircraft in the wrong place

A **criteria-based stabilization gate** was added to `scripts/fly_card_h0.py`
before this run. It refuses to take data until the reference condition is met
and *held*, records each point's entry condition, and marks any point entered
off-condition as not attributable. A test point is only a test point if it
starts from a known condition.

It earned its place on the first run. Speed was **nailed at 100.0 KIAS** from
the 22-knot entry offset — the anti-windup fix confirmed in flight — with VS −3
fpm and bank −0.2 degrees. And the aircraft sat **107 ft low for two full
minutes, correcting none of it**:

```
  after 120 s: 100.0 KIAS  3993 ft  bank -0.2  vs -3
  NOT STABILIZED: kias 0.0  alt_ft 107.0 OUT  vs_fpm 2.9  bank_deg 0.2
```

Nothing saturated. Nothing oscillating. Every loop satisfied, and the aircraft
in the wrong place.

**Cause.** The cascade was proportional throughout, and a pure proportional
cascade reaches equilibrium the moment pitch equals its command — which it can
do at a standing altitude error, because the pitch the VS loop asks for at that
error is also the attitude that flies level.

**Fix.** `ALT_TO_PITCH_I`, bounded and conditionally integrated: the term a
pilot supplies with the trim wheel. Without it the card's reference condition is
not reachable and **the card cannot be flown at all**.

### Run 5 — out-trimmed, saturated, climbing away from its own commands

The backend engaged on an aircraft the autopilot had left trimmed to **+0.432
nose-up**:

```
  t    kias     alt       vs   pitch    elev     thr   alt_i
 14.1   95.8    3621     734    5.85  -0.400   0.982    0.32
 17.1   95.2    3648     911    8.04  -0.400   0.995    0.32
 21.1   91.0    3731    1533   11.55  -0.400   1.000    0.32
```

Full nose-**down** elevator, saturated at the −0.400 limit for seven seconds,
while the aircraft pitched **up** to 11.5 degrees and climbed at 1,533 fpm. The
run terminated on the gate's own envelope check as speed decayed through the 90
KIAS floor.

**Nothing in the control law was wrong.** It had no trim authority, it inherited
somebody else's trim, and it had no way to know it was being out-trimmed —
because a saturated surface and a slow one look identical from the response
alone.

`docs/C182T_HANDLING_TEST_MATRIX.md` listed "no trim" as a BLOCKED reason for H0
*before any of this was flown.* Run 5 is what that assessment looks like in the
air, and it is the best evidence in this project that the pre-flight assessment
was worth writing.

**Fix.** An autotrim loop driven off the elevator the loop is actually holding,
with a deadband and a rate limit. It adopts the aircraft's real trim by readback
before moving it, and **will not write trim it has not first measured** — flying
out of trim is recoverable; writing a guessed trim position to an aircraft
somebody else has been flying is not. Frozen during a pitch test input, because
trimming out a deliberate input trims out the measurement.

Trim is deliberately kept **out** of `CONTROL_DREFS`, the set `_neutralize`
zeroes. Handing an aircraft back with the trim slammed to neutral is an upset,
not a release.

---

## 2. The instrumentation lesson, and a correction

`docs/C182T_HANDLING_TEST_MATRIX.md` §1 identified capture rate as the
instrumentation risk. **That was not the risk.**

The real gap was that **a saturated surface and a slow one look identical from
the response alone.** Three of the five defects — the recovery step, the throttle
windup, and the trim saturation — were invisible until the *commanded surface
positions* were recorded next to the response. The aircraft's motion alone was
consistent with several different explanations in every case.

Traces now log, every tick:

* the pre-rate-limit **demand** next to the issued command, per surface, so a
  limiter that is binding is distinguishable from a loop that is merely slow;
* elevator **trim position and trim rate** — a trim still running is an aircraft
  still out of trim, whatever the elevator reads at that instant;
* both integrator states (`throttle_i`, `alt_i_deg`) and the sideslip integral;
* `body_rate_age_s`, which is `inf` when the damping terms were flown as zero
  for want of data. A zero that means "not rolling" and a zero that means "no
  data" must never look alike in flight-test evidence.

A related design rule now enforced: body rates and trim are **auxiliary**
datarefs, deliberately outside the telemetry freshness gate. Letting a damping
channel go stale must degrade the damping, not neutralize the controls on an
airborne aircraft.

---

## 3. Current gain set

Every value is justified in-line in `services/ai_pilot/direct_backend.py`
against the measured flight it came from.

| Loop | Gain | Value | Origin |
|---|---|---|---|
| heading → bank | `HEADING_TO_BANK` | 1.2 | initial |
| | `MAX_BANK_DEG` | 25.0 | inside the gate's own 35 deg limit |
| bank → aileron | `BANK_TO_AILERON` | 0.020 | initial |
| | `ROLL_RATE_TO_AILERON` | 0.022 | **run 3** |
| | `MAX_AILERON` | 0.35 | initial |
| altitude → VS | `ALT_TO_VS` | 3.0 | initial |
| | `MAX_VS_FPM` | 700.0 | initial |
| VS → pitch | `VS_TO_PITCH` | 0.010 | first flight (from 0.004) |
| altitude trim | `ALT_TO_PITCH_I` | 0.0002 | **run 4** |
| | `ALT_PITCH_I_LIMIT` | 4.0 deg | **run 4** |
| pitch → elevator | `PITCH_TO_ELEVATOR` | 0.030 | initial |
| | `PITCH_RATE_TO_ELEVATOR` | 0.030 | **run 3** |
| | `MAX_ELEVATOR` | 0.40 | initial |
| speed → pitch (H1/H3) | `SPEED_TO_PITCH` | −0.55 | negative: pitching up slows down |
| speed → throttle | `SPEED_TO_THROTTLE_P` | 0.020 | **run 2a** |
| | `SPEED_TO_THROTTLE_I` | 0.0015 | **run 2a** |
| | `THROTTLE_I_LIMIT` | 0.35 | **run 2a**, conditional since **run 3** |
| coordination | `AILERON_TO_RUDDER` | 0.25 | adverse-yaw feedforward |
| | `BETA_TO_RUDDER` | 0.045 | **run 1** |
| | `BETA_TO_RUDDER_I` | 0.0020 | **run 1** |
| | `RIGHT_RUDDER_FF` | 0.070 | **run 2b** |
| | `RUDDER_FF_REF_KIAS` | 100.0 | **run 2b** |
| trim | `ELEVATOR_TO_TRIM` | 0.35 /s per unit elevator | **run 5** |
| | `TRIM_DEADBAND` | 0.02 | **run 5** |
| | `MAX_TRIM_RATE_PER_S` | 0.06 | C182 electric trim, roughly full travel in 10 s |
| slew limits | `AILERON_RATE_PER_S` | 0.40 | **run 3** |
| | `ELEVATOR_RATE_PER_S` | 0.40 | **run 3** |
| | `RUDDER_RATE_PER_S` | 0.60 | **run 3** |

**None of these is validated.** They are tuned to make the aircraft hold a
reference condition well enough to take data *from*; they are not a flight-model
result and they say nothing about the airframe.

## 4. Reference condition gate

`scripts/fly_card_h0.py`. The card will not take data until all four criteria
hold continuously for `STEADY_SECONDS`:

| Criterion | Tolerance |
|---|---|
| indicated airspeed | ±2 KIAS |
| indicated altitude | ±60 ft |
| vertical speed | ±120 fpm |
| bank angle | ±2 deg |
| held for | 4 s continuous |
| stabilize timeout | 120 s |
| re-stabilize between points | 45 s |

If the condition is never met the run **aborts with exit 3** and flies nothing.
`--force` will fly it anyway and stamps the run as not a valid test point, in
the console output and in the trace. Each point records its own entry condition
and `entry_on_condition`; points entered off-condition are listed at the end as
not attributable.

## 5. Test coverage

`services/ai_pilot/tests/test_direct_backend.py`: **80 offline tests**, up from
53 before this campaign. Full `services/ai_pilot` suite: 150. All run without
X-Plane, against a `FakeClient`.

New classes, each named for the run that motivated it: `SlewRateTests`,
`RateDampingTests`, `ThrottleAntiWindupTests`, `AltitudeTrimTests`,
`ElevatorTrimTests`, `SpeedIntegralTests`.

Two of these deserve particular note because they encode a *negative*
requirement:

* `test_a_ramped_test_input_passes_through_unlimited` — if the slew limiter were
  biting during a test input it would be distorting the very measurement the
  card exists to take.
* `test_no_trim_is_written_without_a_readback` — fail-closed on the trim channel.

## 6. Recovery and aircraft state

After run 5 the aircraft was left at 77 KIAS at full power, out of trim and
decaying, with the controller disengaged. Recovered with a direct write —
neutral controls, trim 0.05, throttle 0.60 — reaching 81.4 KIAS at 3,908 ft. The
pilot then paused the simulator.

**Procedural finding.** Run 5 engaged during a transient left by the previous
run's release. The entry check tested envelope compliance only, not steadiness.
Engaging on an unsettled aircraft cost a run. The stabilization gate now catches
the consequence, but the aircraft should be settled before the controller is
handed it, and the release path should leave it in a state the next run can
start from.

## 7. Status and what is next

**Card H0: FLOWN, run 6, 2026-09-17.** Results in §8. Five attempts before it
produced no attributable data; the sixth reached a stabilized reference in 12
seconds and flew all ten points.

Open, and unchanged by this work:

* **H1 and H5–H7 remain BLOCKED** on the gate's 90 KIAS floor. That floor is the
  specific guard that stops an autonomous system flying to the stall; removing
  it to enable stall testing inverts its purpose. Not a tooling gap, and not
  recommended for removal. `services/ai_pilot/flight_test.py` carries a
  `StallTestProfile` with stricter guardrails as the vehicle for a documented,
  scoped exception if that is ever wanted.
* **H2 is unblocked between 90 and 110 KIAS**, blocked at 80.
* **H3 and H4 are unblocked** (`select_airspeed`, `set_flaps`) and unflown.
* Stick force and buffet remain **UNMEASURED** and are not inferable. Report
  control displacement, trim demand and simulated cues only.
* The card's caution that an active pitch/altitude loop can hide instability
  still applies to every airframe card. H0 is flown *with* the loop by design
  (it is a controller-confidence card); the airframe cards are not, and that
  needs an explicit hold-off path before they are flown.

---

## 8. Run 6 — the card, flown

**2026-09-17.** CAP 487, clean, **2,718 lb**, over the Pacific about 9 NM west
of KNZY on a 12 NM final line for runway 11, entered by `set_air_start.py` at
4,500 ft so that AGL and indicated altitude coincide. Reference: 100 KIAS
level. Trace `~/.cache/capvsar/flight-tests/H0_run6_20260917-192836.jsonl`,
5,460 samples over 4.6 minutes.

**Reference condition reached in 12 s**, inside every tolerance — 0.4 KIAS,
17.4 ft, 45.6 fpm, 0.7 deg of bank against limits of 2.0 / 60 / 120 / 2.0. The
five previous runs never got here at all.

| Point | on-cond | recovered | peak rate | t-to-peak | peak deviation | recovery |
|---|---|---|---|---|---|---|
| pitch +0.05 | yes | yes | 3.10 deg/s | 1.2 s | +1,031 fpm | 29 s |
| pitch −0.05 | yes | yes | 2.45 deg/s | 1.1 s | −782 fpm | 33 s |
| pitch +0.10 | yes | yes | 5.96 deg/s | 1.2 s | +1,592 fpm | 42 s |
| pitch −0.10 | yes | **NO** | 4.59 deg/s | 1.2 s | −1,459 fpm | >45 s |
| roll +0.05 | **no** | yes | 2.71 deg/s | 3.1 s | +7.8 deg | 15 s |
| roll −0.05 | yes | yes | 2.32 deg/s | 3.1 s | −7.2 deg | 13 s |
| roll +0.10 | yes | yes | 5.23 deg/s | 3.1 s | +15.8 deg | 17 s |
| roll −0.10 | yes | yes | 4.82 deg/s | 3.1 s | −14.1 deg | 16 s |
| yaw +0.05 | yes | yes | 1.40 deg/s | 1.7 s | 0.6 deg beta | 7 s |
| yaw −0.05 | yes | yes | 3.15 deg/s | 0.8 s | 3.1 deg beta | 7 s |

Control response is correctly signed on all three axes. No reversal, no
divergence, no sustained saturation: the elevator touched its limit in exactly
**1 sample out of 5,460**.

### Roll is the clean axis

Linearity is near exact — doubling the input gives **2.05x** right and **1.97x**
left. Time-to-peak is **3.1 s on all four roll points**, identical across both
magnitude and direction, which is what a well-behaved roll axis should do.
Asymmetry is 8-12%, the expected size for the left-turning tendency rather than
anything structural.

### Pitch is the finding

Two things, and they may be the same thing:

* **Non-linear.** Doubling the input yields only **1.54x** nose-up and **1.86x**
  nose-down, where roll gives ~2x. Pitch response compresses at larger inputs.
* **Slow, asymmetric recovery.** 29 / 42 s nose-up against 33 / >45 s nose-down,
  and **pitch −0.10 never recovered inside the 45 s window** — the run's one
  flagged failure.

The small-input asymmetry is **20.9%** at ±0.05 but only **4.5%** at ±0.10. A
power-on pitch coupling would grow with excursion size, not shrink. The
likeliest reading is that the altitude-hold loop still authors part of the
small-input response — precisely the interference the card warns about — so the
±0.05 pitch numbers should be treated as controller-in-the-loop, not airframe.

### Yaw inputs were too small to characterise the axis

Peak deviations of 0.6 and 3.1 degrees of sideslip are near the noise floor, and
the 63.6% "asymmetry" between them is measuring almost nothing. **±0.05 rudder
is not a useful test input on this airframe**; a larger magnitude is needed
before the yaw axis can be said to have been exercised at all.

### One point is not attributable

`roll +0.05` entered at **+124 fpm against a ±120 fpm tolerance** — missed
by 4 fpm. It is excluded rather than argued over; the gate is either the
criterion or it is decoration. The other nine points entered on-condition.

### What the run says about the controller

* The **slew limiter bound on 148 of 16,377 surface commands, 0.90%**. It is a
  safety net at transitions, not a filter distorting normal operation — which is
  what §1's run-3 fix intended.
* **Zero samples were flown with degraded body rates**, so the rate-damping
  terms were live throughout and no result rests on a silently zeroed channel.
* **Autotrim stayed modest**, −0.020 to −0.203, with no runaway — and the
  aircraft it inherited had been hand-flown into a dive moments earlier.

### Limits on all of the above

One run, at **2,718 lb — not the 3,100 lb** the performance card uses, and with
the **altitude and heading loops active by design**. These are
controller-in-the-loop handling numbers. They are not an open-loop airframe
characterisation and must not be quoted as one.

---

## Related

* `CHANGELOG.md` — 2026-09-11 entry for this campaign
* `docs/C182T_HANDLING_TEST_MATRIX.md` — the pre-flight support assessment and
  its §6 revision
* `docs/C182T_FLIGHT_TEST_CARD.md` — POH-sourced performance targets
* `services/ai_pilot/direct_backend.py` — the controller
* `scripts/fly_card_h0.py` — the card driver
* Traces: `~/.cache/capvsar/flight-tests/H0_run*.jsonl`
