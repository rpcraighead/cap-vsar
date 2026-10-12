# C182T port of the C172 AI pilot controllers (2026-10-11)

Status: **implemented; first live C182T trial flown and passed (an expanding
square on the mission bridge, 2026-10-11, see "Live trial 1" below).** Branch
`feat/c182-ai-pilot-baseline`, stacked on `feat/c172-taxi-takeoff-ifr` and with
`main` merged in. Suite: `services/ai_pilot/tests` 540 passed, 20 xfailed.
`tuning_validated` stays False: one pattern flight does not validate the
taxi, takeoff or landing constants. Simulator engineering only; not operating
guidance for any real aircraft.

## Why this shape

Ron's direction: use the C172 autopilot code as the baseline for the 182, since
the two fly very similarly. The C172 controllers (`takeoff_guidance.py`,
`landing_trial.py`, `ksee_kmyf_mission.py`) carried their speeds as literals.
Copying them for a second aircraft would have forked three controllers that
were tuned in the air. Instead every operational number now comes from an
`AircraftProfile` (`services/ai_pilot/aircraft_profiles.py`) and the three
controllers take a `profile=` argument whose default is the C172 record, so
the flown C172 behaviour is byte-for-byte what it was (the 496 pre-existing
tests pass unchanged).

The development plan asked for exactly this ("Aircraft and observation
profiles": record the source of each operational value and label tuning
separately). The profile does both: `sources` names the handbook line for each
sourced speed, and `tuning_validated` is `False` on the C182T record until a
C182T sortie has been scored.

## What the C182T profile says, and where each number comes from

Handbook: Cessna 182T NAV III GFC 700 AFCS information manual, P/N 182TPHBUS,
SHA-256 `ba64adab5d6ed543f73b330f24301e72fdaba4f729c3661075fa55173fd2705c`
(the document `scripts/c182t_dimension_master.json` pins; re-fetched and
re-hashed for this work from the Illinois Wing copy).

| Profile field | C172 (flown) | C182T | Source for the C182T value |
|---|---|---|---|
| `vr_kias` | 55 | 55 | §4 Normal Takeoff: lift nosewheel at 50–60 KIAS |
| `vx_kias` / `vy_kias` | 62 / 74 | 65 / 80 | §4 Maximum Performance Climb 80 KIAS SL; §5 Vx 65 KIAS SL |
| `climb_enroute_kias` | 85 | 90 | §4 Enroute Climb 85–95 KIAS, 23 in.hg / 2400 RPM |
| `cruise_kias` | 100 | 110 | exercise value (README FLC target), inside §4 Cruise 55–80 % power |
| `approach_initial/intermediate_kias` | 100 / 95 | 100 / 95 | unchanged exercise values, inside the 90–140 envelope |
| `approach_clean_kias` | 80 | 85 | §4 Normal Landing 70–80 KIAS flaps up, held 5 kt high outside 3 NM |
| `ils_final_kias` (flaps 10) | 73 | 80 | §4 Normal Landing flaps-up band; Vfe 10° 140 |
| `final_approach_kias` (flaps FULL) | 65 (+5 far out) | 68 (+5) | §4 Normal Landing 60–70 KIAS flaps FULL |
| `missed_kias` / `missed_flap_ratio` | 74 / 10° | 70 / 20° | §4 Balked Landing: flaps 20°, 55 KIAS obstacle speed, retract above 70; 70 is the §4 flaps-20 climb speed |
| `vfe_kias` | 110 (10°), 85 (full) | 140 / 120 / 100 | §2 Figure 2-1 |
| `va_kias` | 105 | 110 | §2 Figure 2-1 at 3100 lb |
| `takeoff_flap_ratio` | 0 | 1/3 (10°) | §4 Normal Takeoff: flaps UP–20°, 10° preferred |
| `flap_retract_kias` / `_agl_ft` | — | 70 / 300 | §4 Short Field Takeoff item 9 (above 70 KIAS); 300 ft is a controller choice |
| `search_kias` | 90 | 100 | CAP training value, not a handbook figure |
| **tuning** `threshold_kias` | 62–68 | 64–72 | C172 observer window moved up with the final speed |
| **tuning** `landing_flap_gates` | 10° >85 kt, 20° >75 kt | 10° >95, 20° >85 | C172 gates +10 kt; all below Vfe (the profile refuses otherwise) |
| **tuning** `touchdown_pitch_deg` | 5–7 | 5–8 | C172 criterion, widened 1° |
| **tuning** base throttles | .55 / .48 / .28 | same | **not retuned**: the 230 HP engine and constant-speed prop will need different base positions |
| **tuning** `min_roll_rpm` | 1800 | 2000 | governed prop reaches 2400 quickly; gate at 5 s into the roll |

The ACF side (what the package actually exposes to X-Plane) agrees with the
handbook on every V-speed the G1000 shows: `scripts/build_c182t_package.py`
patches Vs 51, Vso 41, Vx 65, Vy 80, Vfe 140/100, Vno 140, Vne 175 and flap
detents 10/20/38°. The `test_c182t_port.py` tests pin the profile to those.

## Behaviour that changed for the C182T only

* **Takeoff** holds until the flap handle reads the profile's takeoff setting
  (10° for the 182T, up for the 172), commands that setting through the roll
  and initial climb, and retracts once above 300 ft AGL *and* 70 KIAS; it never
  re-extends. The rejected-takeoff RPM gate is the profile's.
* **Landing** selects flap stages from `profile.landing_flap_gates`, flies the
  profile's final speeds, and the observer insists on `Cessna_182T_G1000.acf`,
  the 64–72 KIAS threshold window and the stage names `10deg/20deg/38deg`.
* **Mission** climb, vector, approach, ILS and missed-approach speeds, and the
  ILS/missed flap stages, come from the profile.

## Search patterns (`services/ai_pilot/search_patterns.py`)

Geometry for expanding square (SS), creeping line (CS) and parallel track (PS)
following decision D2, placed from the datum with one great-circle offset per
point exactly as the g1000-sar library does. The 24-case fixture from
g1000-sar (`tests/data/search_pattern_fixtures.json`, copied verbatim with its
provenance noted) is replayed and every waypoint agrees to better than 6 m.
`scripts/fly_search_grid.py` (heading-bug based, autopilot flown) is untouched.

`SearchPatternController` flies a waypoint list on the primary controls at a
fixed indicated altitude and speed using `CruiseLaw`, which is the altitude,
speed and heading loop of the C172 mission controller lifted unchanged. It
tracks each leg with a cross-track intercept (0.06°/m, ±30°), anticipates
corners with a bank-angle turn radius, and forces each corner in the pattern's
own direction so a lane reversal is never turned the long way round. A
point-mass fly-through in the tests completes all three patterns in order,
passes within 0.35 NM of every waypoint, turns every corner the way the
geometry says, and holds cross-track under 120 m on settled legs.

It is flown by `scripts/ai_pilot_pattern.py` on the mission bridge and scored by
the independent `PatternObserver` (see Live trial 1). It has no envelope
monitoring of its own; the bridge's `MissionLab` envelope does that. `MissionController` still
carries its own copy of the cruise loop; moving it onto `CruiseLaw` is a
refactor to do only with a regression flight behind it.

## Live trial 1: expanding square, CAP 487, 2026-10-11

| Item | Value |
|---|---|
| Aircraft | installed CAP 487 package, ACF SHA-256 `11ff17d1…cd89d8` (Cd 0.120 calibrated build, branch `fix/c182-a2-2026-10-11`) |
| Code | commit `ee990d7`, clean tree; installed bridge byte-identical to `xplane/` |
| Pattern | expanding square, datum 32.70 N 117.30 W, first leg 000°, 1 NM spacing, 6 legs, right turns, 12.0 NM |
| Start | air start 32.68 N 117.31 W, 2,000 ft, 100 kt, ISA calm, full rich, AP off; paused and adopted by `lab_reset` |
| Criteria | every waypoint within 0.35 NM, altitude ±200 ft, 80-140 KIAS, bank ≤ 32° |
| Outcome | **PASS**: DATUM and SS01-SS06 reached in order, 430 s sim time |
| Altitude | 1,980-2,029 ft (max error 20 ft) |
| Speed after the datum | 96.2-105.1 KIAS |
| Bank | max 21.0° |
| Cross-track on settled legs | median 8 m, 95th percentile 81 m, max 113 m |
| Throttle on straight legs | median 0.553 (profile `cruise_base_throttle` 0.55, inherited from the C172) |
| Containment | ended `PAUSED_FAULT`, pause confirmed, overrides released, session retired |

Evidence: `docs/evidence/ai_pilot_c182_pattern_20261011.json` (trace path and
SHA-256 `2077c33a…`; the 5.5 MB trace stays in `~/.cache/capvsar/ai-pilot/`).

Two things this run needed. The installed mission bridge at the time was the
C172 KSEE-KMYF trial's uncommitted version, so `main` was merged in and the one
bridge line that trial depends on (a 3 s reply window for `lab_start`) was
committed here as `ee990d7`; the C172 worktree was not touched and its bridge
was restored afterwards from `~/.cache/capvsar/bridge-backup-20261011`. And
`lab_reset` refuses an aircraft whose indicated airspeed is still 0 straight
after an air start, so the sim was run for 3 s before pausing.

## Follow-ups, in order

1. **Runner flag.** Done (`f8098a0`): `--profile` on the KSEE-KMYF, surface,
   observe and pattern runners; manifests record the profile and
   `tuning_validated`.
2. **Bridge identity.** `xplane/capvsar_mission.py` / `capvsar_landing.py`
   envelopes (50–140 KIAS airborne, 40–145 in the landing lab) are wide enough
   for the 182T. Done: the bridge accepts the built package by the SHA-256 the
   stager pins (`aircraft_identity_ok`), proven live in trial 1.
3. **First live C182T trials, safest first:** the pattern trial is done
   (trial 1, PASS; it also confirms `cruise_base_throttle` 0.55 at 100 KIAS).
   Next the H0-style cruise cycle (`experiment.Scenario` at 100 KIAS)
   to retune `cruise_base_throttle`, then taxi-only from East Transient
   Parking 12 (idle thrust of the IO-540 and the constant-speed prop will move
   the taxi throttle constants in `ground_guidance.py`, which are not in the
   profile yet), then takeoff-only with flaps 10, then the full sortie.
4. **Retune and record.** Base throttles, flap gates, threshold window and
   touchdown pitch are C172 criteria shifted by speed. Replace each with a
   measured value, cite the trace, and flip `tuning_validated`.
5. **Taxi constants into the profile** (`ground_guidance.py`,
   `runway_entry.py`: throttle .16 + .08·Δv, corner speeds) once trial 3 has
   numbers.
6. **Pattern integration:** the runner and a waypoint observer exist. Still to
   do: a `pattern` stage in a mission controller (enter from a vector, fly,
   resume), and an observer that scores coverage
   (track spacing held, lane ends reached) the way `LandingObserver` scores a
   landing. The DF datarefs (`cap/df/*`) are available for a beacon-homing
   stage after that.
7. **Flight model.** The C18 ACF defects are fixed and fuselage drag is
   flight-calibrated on `fix/c182-a2-2026-10-11`: cruise is within 1 % of the
   POH, climb at Vy is still about 18 % strong (A-1). Tune against that build
   (ACF `11ff17d1…`); a later geometry fix for the climb will move the
   approach and climb constants again.

## How to run what exists

```bash
PYTHONPATH=. python3 -m pytest services/ai_pilot/tests -q          # 540 passed, 20 xfailed
PYTHONPATH=. python3 - <<'PY'
from services.ai_pilot.aircraft_profiles import C182T
from services.ai_pilot.search_patterns import parallel_track, track_miles
pts = parallel_track(33.10, -117.00, 25., 4., 1., 4, "right")
print([w.name for w in pts], round(track_miles(pts), 1), "nm", C182T.search_kias, "KIAS")
PY
```

Live pattern trial (sim paused and airborne inside the mission region, staged
bridge installed; restore the previous bridge afterwards):

```bash
python3 scripts/ai_pilot_experiment.py stage-mission ~/.cache/capvsar/stage-<stamp> \
    --aircraft "$HOME/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III/Cessna_182T_G1000.acf"
# copy the staged files into Resources/plugins/PythonPlugins, config mode 0600
python3 scripts/ai_pilot_pattern.py --config <PythonPlugins>/capvsar_flight_control_config.json \
    --output ~/.cache/capvsar/ai-pilot/pattern_c182_ss.jsonl --profile C182T \
    --pattern expanding_square --lat 32.70 --lon -117.30 --spacing-nm 1 --legs 6 --altitude-ft 2000
```
