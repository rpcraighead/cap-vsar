# CAP 487 C182T: measured throttle-for-(airspeed, climb rate) table (2026-10-15)

Status: **measured, in the profile, validated on one aircraft in the simulator; for the C172 it is not
measured.** Simulator engineering only; not operating guidance for any real aircraft.

## Why

The AI pilot's cruise law was a speed-on-throttle loop around one fixed power (0.55). Right in level
cruise, wrong in a climb: handed a fast, climbing airplane it cut the throttle to idle and fell 30 knots below
its target (ESCON hand-back runs, `docs/GFC700_SECOND_OWNER_2026-10-15.md`). It had no idea what throttle a
given speed and climb rate need. This table is that knowledge, measured, per aircraft, as data in the
aircraft's profile (`services/ai_pilot/profiles/c182t.toml`, `[performance]`) instead of a guessed constant.

## How it was measured

`scripts/perf_table_sweep.py`: the CAP 487 airborne over open water at 2,185 lb (the loading the AI flights
use), ISA, calm, full rich, prop full forward (2,400 RPM requested), flaps up, cowl flaps at 0.5 (as the air
start leaves them). Throttle is fixed at 0.40-1.00 and the airplane's own GFC 700 holds a vertical speed
(+700, +400, 0, -400, -700 fpm) or the altitude; the airspeed that settles (steady within 1 kt for 10 s) is
recorded. No control surface is written. A point is abandoned, and recorded as such, below 75 KIAS or above
138 KIAS. `scripts/perf_table_to_toml.py` turns the settled points into the profile table. Aircraft file
SHA-256 `11ff17d1...cd89d8`.

Two sweeps: `t1` let altitude drift (2,424-5,203 ft) and the drift correlated with the throttle row, hiding up
to 6.7 kt (indicated airspeed at a given power falls as density does); `t2` recentres to 4,000 ft before each
point (3,376-5,076 ft, mean 4,036) and is the table. Both raw files are kept in `docs/evidence/c182t-2026-10-15/`.

## The table (settled KIAS, run `t2`)

| climb rate \ throttle | 0.40 | 0.50 | 0.60 | 0.70 | 0.80 | 0.90 | 1.00 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| +700 fpm | | | | | 95.7 | 111.2 | 117.1 |
| +400 | | | | 98.9 | 106.8 | 122.5 | 126.4 |
| 0 | | 92.2 | 102.7 | 114.0 | 120.0 | 129.6 | 137.0 |
| -400 | 94.0 | 109.2 | 113.5 | 122.5 | 130.8 | | |
| -700 | 106.8 | 114.4 | 122.5 | 130.5 | | | |

Blank cells could not be flown inside 75-138 KIAS (the climbs ran out of airspeed, the descents exceeded the
ceiling, a few timed out unsettled). Level flight at 100 KIAS needs about 0.59 throttle, close to the old fixed
0.55. `PerformanceTable.throttle_for(kias, vvi)` inverts the map and holds the nearest measured value, saying
so, outside it.

## What the validation flights showed

* **The pattern is unchanged.** The ESCON expanding square (CAP 487, 4,500 ft, same start as 2026-10-14)
  reached the same 9 waypoints with altitude within 30 ft (28 before), 99.3-100.7 KIAS (99.1-100.9), median
  cross-track 11 m (12) and median throttle 0.59 (0.59). Level cruise needs the same power either way.
* **The hand-back is not fixed by the table.** Handed 119.6 KIAS mid-climb:

  | speed command ramp | fixed-base law | with table |
  |---|---|---|
  | 2.0 kt/s | min 90.0 KIAS | min 95.0 KIAS (fails the 5 kt undershoot criterion) |
  | 0.4 kt/s | min 98.5 KIAS, PASS | min 98.9 KIAS, PASS |

  The table helps (a 95, not a 90) but a fast ramp is still unsafe: the speed command cannot fall faster
  than a climbing airplane can slow down, about 0.4-0.5 kt/s, whatever the throttle starts at. The 0.4 kt/s
  ramp (`ADOPT_SLEW_KT_S`) is therefore the operative fix and the table a modest improvement.

## Limits

* One altitude band (mean 4,036 ft), one loading, one cowl setting. The integrator in the cruise law removes
  what the table gets wrong; flights span 2,000-6,000 ft. A second altitude band is the obvious extension.
* The table is only valid for the aircraft file it was measured on. Open item A-1 (exterior geometry; climb at
  Vy about 18% strong) will move it: re-measure with `perf_table_sweep.py` and `perf_table_to_toml.py --write`.
* Level speed jumps 11 kt between 0.60 and 0.70 throttle, because below about 0.65 the engine is held under
  2,400 RPM by the prop's fine stop (`docs/C182T_AI_PILOT_PROP_2026-10-15.md`); the table captures it, it does
  not explain it.
* **Not measured for the C172.** It must be swept, and the frozen C172 campaign flown on the shared code, before
  its profile gets a table; until then C172 controllers use the fixed-base law exactly as flown.
* The MissionController (C172 KSEE-KMYF sortie) still has its own copy of the cruise loop and does not use the
  table.

## Re-measuring

```bash
python3 scripts/perf_table_sweep.py --profile C182T --run t3          # launches the sim, ~35 min
python3 scripts/perf_table_to_toml.py ~/.cache/capvsar/measurements/perf_table_C182T_t3.json \
    --evidence docs/evidence/c182t-<date>/perf_table_C182T_t3.json --write
```
