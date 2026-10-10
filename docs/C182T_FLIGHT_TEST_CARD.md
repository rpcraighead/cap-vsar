# CAP 487 flight-model validation test card (A-1)

The individual C182T ACF corrections have been checked statically and by
dataref after reload. **B1 and C1 have since been flown and both missed their
POH targets.** Those two points diagnose a model gap; they do not validate the
flight model. The remaining card points and repeats after any model change are
needed for acceptance. See `CHANGELOG.md` (2026-09-15) and
`docs/C182T_FLIGHT_MODEL_CALIBRATION.md`.

Source for every target below: Cessna Model 182T NAV III GFC 700 AFCS POH,
P/N 182TPHBUS-00/-01, recorded with SHA-256 in
[`docs/C182T_DIMENSION_MASTER.md`](C182T_DIMENSION_MASTER.md). Section 1
"Performance — Specifications" (pages i–ii), Section 2 Figure 2-2 (page 2-5),
Section 5 Figure 5-4 (page 5-14).

## Who flies it

**Not the agent.** Tracker items AI-1 and AI-2 require that live aircraft control
go only through `services.ai_pilot.maneuver_server` and its serialized maneuver
gate, which is another agent's active lane. The agent's role here is **read-only
telemetry capture** over UDP — the same passive dataref reads used throughout the
exterior work.

Fly the points yourself, or route them through the maneuver server if that lane
is free. Either way, say when a point starts and the capture will bracket it.

## Aircraft configuration for every point

| Item | Setting | Why |
|---|---|---|
| Weight | 3,100 lb (max gross) | Every POH figure below is at max gross |
| CG | note which, fwd or aft | Stall speeds differ by ~1 KIAS between limits |
| Weather | Standard day, no wind | POH figures are ISA sea level unless stated |
| Fuel | Set to reach 3,100 lb total | — |

State the CG used. The corrected envelope is 2.571–3.641 ft in the ACF frame,
which is FS 33.0–46.0 in, 11.94–34.05% MAC.

## Test points

### Group A — stall speeds (highest value)

Power **IDLE**, wings level, decelerate ~1 kt/sec, record KIAS at break.
POH Section 5 Figure 5-4, page 5-14.

| # | Flaps | Expected KIAS (fwd CG) | Expected KIAS (aft CG) | Tolerance |
|---|---|---|---|---|
| A1 | UP | 51 | 50 | ±3 KIAS |
| A2 | 20° | 44 | 43 | ±3 KIAS |
| A3 | FULL (38°) | 41 | 40 | ±3 KIAS |

The POH itself notes "KIAS values are approximate", hence ±3.

**A3 is the single most diagnostic point on this card.** Full flap was 30° until
today and is now the certificated 38°. If the extra 8° of flap is doing real
aerodynamic work, A3 should sit near 41 KIAS; if it reads like the old 30° value
it will sit high, and the flap change is cosmetic.

Cross-check while you are there: the ASI white arc should begin at 41 KIAS and
the green arc at 51 KIAS (POH Figure 2-2). Those two ACF values were already
correct before today and should not have moved.

### Group B — climb

| # | Point | Expected | Tolerance |
|---|---|---|---|
| B1 | Rate of climb at sea level, full power, Vy | 924 FPM | ±10% |

Vy is 80 KIAS in the ACF. Stabilise before recording; use a 30-second average
rather than a peak.

### Group C — cruise

| # | Point | Expected | Tolerance |
|---|---|---|---|
| C1 | Max speed, sea level, full power, level | 150 KTAS | ±5 KTAS |
| C2 | 80% power at 7,000 ft, level, lean | 145 KTAS | ±5 KTAS |

Let speed stabilise for at least 60 seconds.

### Group D — takeoff and landing (lower confidence)

POH Section 1. Short field technique, flaps 20° for takeoff, flaps FULL for
approach at 60 KIAS.

| # | Point | Expected | Tolerance |
|---|---|---|---|
| D1 | Takeoff ground roll | 795 ft | ±15% |
| D2 | Takeoff over 50 ft obstacle | 1,514 ft | ±15% |
| D3 | Landing ground roll | 590 ft | ±15% |
| D4 | Landing over 50 ft obstacle | 1,350 ft | ±15% |

Wider tolerance because these are strongly technique-dependent. Treat a miss here
as weak evidence on its own; a miss in Group A is much more informative.

### Group E — optional, slow

| # | Point | Expected | Tolerance |
|---|---|---|---|
| E1 | Service ceiling | 18,100 ft | ±1,000 ft |

Long climb. Only worth flying if the other groups look right.

## What the capture records

Read-only, via `scripts/capture_flight_test.py`:

* `sim/flightmodel/position/indicated_airspeed` — KIAS
* `sim/flightmodel/position/true_airspeed` — for the cruise points
* `sim/flightmodel/position/vh_ind_fpm` — vertical speed
* `sim/flightmodel/position/elevation` — altitude
* `sim/flightmodel/weight/m_total` — confirms the 3,100 lb condition
* `sim/flightmodel2/controls/flap_handle_deploy_ratio` — confirms the configuration
* `sim/flightmodel/position/theta` and `phi` — pitch and bank, to confirm wings level

Nothing is written to the simulator.

## How to read the results

These corrections landed today, so a result that differs from the POH does not
automatically mean the correction was wrong:

* **Group A high across the board** — suspect the wing, but note the wing already
  measures correct three independent ways (span +0.56%, area −0.55%, MAC −1.3%),
  so look at flap effectiveness and CG first.
* **A3 high, A1 correct** — the 38° flap is not doing aerodynamic work. That
  points at flap chord ratio or the `_flap1_cl`/`_flap1_cd` coefficients, none of
  which were touched today.
* **B1 low** — compare engine power and propeller state with aerodynamic
  geometry and drag. The recorded B1/C1 pair showed that the 7% C1 power
  shortfall alone cannot account for the 13.3% speed shortfall; the ACF body and
  almost all wing parameters are still inherited from the C172SP.
* **All recorded points within tolerance** — record a pass only for the tested
  weight, CG, atmosphere and configuration. A-1 also requires exterior and
  broader flight-model acceptance; one set of max-gross ISA points cannot close
  it alone.

Record the actual numbers in `CHANGELOG.md` whatever the outcome, including
misses. A partial pass with honest numbers is worth more than a selective one.

## Not covered

Weight-scheduled forward CG behaviour (X-Plane takes a single forward limit, so
the envelope is permissive at heavy weights), any non-ISA condition, any weight
other than max gross, spins, and icing. The horizontal tail **area** is also
unverified — only its span is published, so the +4.1% area change made alongside
the span correction is a consequence rather than a sourced target.
