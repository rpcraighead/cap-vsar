# C182T port of the C172 AI pilot controllers (2026-10-11)

Status: **implemented and tested offline; nothing has been flown on the C182T.**
Branch `feat/c182-ai-pilot-baseline`, stacked on `feat/c172-taxi-takeoff-ifr`
(the attended KSEE–KMYF C172 sortie of 2026-10-11). Suite:
`services/ai_pilot/tests` 537 passed, 20 xfailed (was 496 / 20). No simulator
was started for this work and no qualification claim is made. Simulator
engineering only; not operating guidance for any real aircraft.

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

What it is not: it has no runner script, no bridge integration, no envelope
monitoring of its own (the bridge's `MissionLab` envelope and the experiment
observers do that), and it has never been flown. `MissionController` still
carries its own copy of the cruise loop; moving it onto `CruiseLaw` is a
refactor to do only with a regression flight behind it.

## Follow-ups, in order

1. **Runner flag.** `scripts/ai_pilot_ksee_kmyf.py`, `ai_pilot_surface.py` and
   `experiment.Scenario` still name the C172. Add `--profile C182T`, pass it to
   the controllers and observers, and make the manifest record the profile key
   and `tuning_validated`.
2. **Bridge identity.** `xplane/capvsar_mission.py` / `capvsar_landing.py`
   envelopes (50–140 KIAS airborne, 40–145 in the landing lab) are wide enough
   for the 182T; confirm `verify_identity` accepts the CAP 487 package before
   any live run.
3. **First live C182T trials, safest first:** a `SearchPatternController`
   pattern at 1,500 ft over water (only the cruise loop is exercised; abort by
   pause), then the H0-style cruise cycle (`experiment.Scenario` at 100 KIAS)
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
6. **Pattern integration:** a `pattern` stage in a mission controller (enter
   from a vector, fly, resume), a runner, and an observer that scores coverage
   (track spacing held, lane ends reached) the way `LandingObserver` scores a
   landing. The DF datarefs (`cap/df/*`) are available for a beacon-homing
   stage after that.
7. **Flight model.** The package itself is uncalibrated (A-1; cruise −13 %,
   climb −11 % at 3,100 lb) and `docs/C182T_REVIEW_2026-10-11.md` (branch
   `review-c182-2026-10-11`) lists ACF defects found on 2026-10-11, including
   the propeller disc still being the C172's 76-inch one. Controller tuning
   done before those are fixed will drift when they are.

## How to run what exists

```bash
PYTHONPATH=. python3 -m pytest services/ai_pilot/tests -q          # 537 passed, 20 xfailed
PYTHONPATH=. python3 - <<'PY'
from services.ai_pilot.aircraft_profiles import C182T
from services.ai_pilot.search_patterns import parallel_track, track_miles
pts = parallel_track(33.10, -117.00, 25., 4., 1., 4, "right")
print([w.name for w in pts], round(track_miles(pts), 1), "nm", C182T.search_kias, "KIAS")
PY
```
