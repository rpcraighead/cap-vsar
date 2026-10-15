# One autopilot, two aircraft: the stock C172SP through the shared code (2026-10-15)

Status: **flown in the simulator; both aircraft pass the same pattern and owner-transfer trials on the same code
with only their profiles (data) different.** Simulator engineering only; not operating guidance for any real aircraft.

## What was asked

The C172 was where the AI autopilot succeeded, and the C182 work looked like it had branched off. The direction:
handle the autopilot the same across aircraft, with differences in a config file (performance tables, control
types). The steps so far: profiles became TOML data with a strict loader (`services/ai_pilot/profiles/`), no
controller defaults to an aircraft any more, and a measured performance table is part of a profile
(`docs/C182T_PERFORMANCE_TABLE_2026-10-15.md`). This note is the test: does the C172 fly the same code?

## The C172's measured table

`scripts/perf_table_sweep.py --profile C172SP --run t2 --payload-kg 170 --fuel-kg 100`: the stock ACF
(SHA-256 `b9c3c35c...`, the pinned stock hash), 1,043.8 kg (the frozen campaign loading), ISA, calm, full rich,
flaps up, the autopilot holding the vertical speed. Settled KIAS, mean altitude 3,659 ft:

| climb rate \ throttle | 0.50 | 0.60 | 0.70 | 0.80 | 0.90 | 1.00 |
|---:|---:|---:|---:|---:|---:|---:|
| +400 fpm |  |  |  |  | 81.0 | 101.7 |
| +200 fpm |  |  |  | 91.9 | 94.4 | 109.3 |
| +0 fpm |  | 77.3 | 84.7 | 96.0 | 103.5 | 111.6 |
| -400 fpm | 87.8 | 96.8 | 103.4 | 110.7 | 115.9 | 122.7 |
| -700 fpm | 101.3 | 107.6 | 113.2 | 119.2 | 124.1 | 129.5 |

Run-to-run: level and descent points repeat within about 1 kt between the first and second sweep; the edge climb
points do not (the +400 fpm row: 94.3 / 101.7 vs 91.3 / 81.0), because there speed collapses steeply with small
power changes. That row legitimately has only two points, which is why a row now needs two, with at least one row
of three (`performance.py`).

## The two airplanes, from data

| | C172SP | C182T (CAP 487) |
|---|---|---|
| Throttle for level 100 KIAS | 0.85 | 0.57 |
| Throttle for level 90 KIAS | 0.75 | 0.50 |
| Full-throttle level speed | 111.6 KIAS | 137.0 KIAS |
| Best sustained climb at the enroute climb speed (x0.85) | 340 fpm (at 85 KIAS) | 595 fpm (at 90 KIAS) |
| Fixed `cruise_base` in the old law | 0.55 | 0.55 |

The 172 needs about 0.3 more throttle than the old fixed base to hold the speeds the pattern flies; its speed loop
had been trimming the difference. The table carries it.

## Same trials, both airplanes

| Trial | C172SP | C182T |
|---|---|---|
| ESCON expanding square, 9 waypoints | **PASS**: altitude within 25 ft, 89.4-90.6 KIAS (target 90), cross-track median 6 m, throttle median 0.73 | **PASS**: altitude within 30 ft, 99.3-100.7 KIAS (target 100), cross-track median 11 m, throttle median 0.59 |
| AI pilot -> GFC 700 -> AI pilot, terrain guard at the Ramona ridge, hand-back mid-climb | **PASS**: climbed at the 340 fpm cap, held 97-100 KIAS; handed back at 99.6 KIAS, eased to 90, min 88.7; crest crossed under the AI pilot at 5,470 ft over 3,713 ft ground, 1,757 ft above the ground at the closest | **PASS** (run 8, 6): climbed at 700 fpm; handed back at 119.6 KIAS, eased to 100, min 98.9; crest crossed with 1,630-1,703 ft clearance |

## What flying the 172 found

Aircraft-dependent constants that were still in the shared code, each one invisible while only the 182 flew:

1. **The climb the controllers ask for.** The cruise law asked for up to 650 fpm and the terrain guard ordered 500-700 fpm
   whatever the airplane could hold. A 172 cannot sustain that, and an autopilot holding a vertical speed it cannot
   sustain loses airspeed toward the stall. Now bounded by the aircraft's measured table
   (`PerformanceTable.sustainable_vvi`, `AircraftProfile.sustainable_climb_fpm`): the cruise law caps its command, the
   terrain guard plans and orders with it, the GFC owner never asks the autopilot for more. With no table, as flown.
2. **"Climbing" meant 500 fpm** in the owner-trial runner, so the mid-climb hand-back never fired on the 172
   (first owner run). It is now 60% of the airplane's own sustainable rate.
3. **A fixed cruise throttle of 0.55** (see above).
4. **A table rule written for the 182**: three points in every row. The 172's edge climb row has two. Relaxed to two per
   row with at least one row of three and three rows overall.

And, on the 172's first owner run, **the first live turn-back**: from 5,994 ft the guard looked 12 nm ahead, saw ground
needing an 8,000 ft floor, above the 6,000 ft ceiling that keeps it inside the bridge envelope, and stopped the trial.
That is the designed response; the trial has no route to turn onto, so it ended there. It also confirmed, live, the
throttle restore after a GFC 700 level-off (1.00 back to the entry 0.80), which had been unit-tested only.

## One slip, now designed out

Twice a launch was silently refused because the previous run's own simulator was still running, and the trial then
failed on a missing bridge before anything flew. `xplane-clean --restart` now quits a running X-Plane gracefully and
launches the next one.

## Not done

* The **frozen C172 qualification campaign** (the 20-flight establish/turn/recover cycles) was not re-flown. It flies
  `SnapshotController`'s direct laws, not `CruiseLaw` or the profile table, so nothing in this work touches it; it is
  not evidence about it either way.
* The C172 **KSEE-KMYF sortie** (`MissionController`) still carries its own copy of the cruise loop and does not use the
  table or the climb cap. Merging that loop into `CruiseLaw` is the next structural step, behind a regression flight.
* One altitude band per table (means 4,036 ft and 3,659 ft); the A-1 airframe fix will move the C182T's.
