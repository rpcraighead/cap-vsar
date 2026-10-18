# Aircraft profiles

One autopilot, many aircraft: the control laws in `services/ai_pilot/` are shared, and everything that
differs between airplanes is data in this directory, one TOML file per aircraft. `profile_loader.py`
reads and validates them; `aircraft_profiles.py` exposes them as `PROFILES` / `C172SP` / `C182T`
(the `AircraftProfile` the controllers already take).

Nothing here is operating guidance for a real aircraft.

## Adding an aircraft

1. Copy the closest existing file, change `[aircraft].key` and `acf_name`, and set `tuning_validated = false`.
2. State **every** value. The loader refuses a missing key (nothing is inherited, so a new aircraft can
   never silently fly C172 numbers) and refuses an unknown key (a typo cannot fall back to a default).
3. Put the handbook or measurement behind each group of numbers in `[sources]`, and say in `sources.tuning`
   where the controller constants came from and whether they have been flown. `tuning_validated` flips to
   true only after a sortie in that aircraft has been flown and scored with these values.
4. `python3 -m pytest services/ai_pilot/tests/test_profile_files.py`. The profile's own physical checks run
   too: no landing flap gate above Vfe, a sane threshold window, ILS and missed-approach speeds under Vfe.

`load_profiles()` picks the file up by itself; there is no registry to edit.

## Schema

| Table | Keys | Meaning |
|---|---|---|
| `[aircraft]` | `key`, `acf_name`, `display_name`, `tuning_validated` | identity; `acf_name` is the aircraft file the observers insist on |
| `[speeds_kias]` | `vr vx vy climb_enroute cruise approach_initial approach_intermediate approach_clean ils_final final_approach missed va search` | sourced operating speeds |
| `[vfe]` | `stages` | `[[flap handle ratio, Vfe KIAS], ...]`, smallest ratio first |
| `[flaps]` | `takeoff_ratio retract_kias retract_agl_ft missed_ratio ils_ratio stage_names` | flap handling; `stage_names` are the three stage labels the observer expects |
| `[[flaps.landing_gates]]` | `ratio inside_m max_kias` | landing flap stages, first to last; the last must be ratio 1.0 |
| `[landing]` | `toe_brakes final_speed_add_kias threshold_kias touchdown_pitch_deg touchdown_max_groundspeed_kt flare_start_agl_ft` | tuning and observer windows; `toe_brakes` selects cockpit toe-brake ratios under `override_toe_brakes` or the legacy `l_brake_add`/`r_brake_add` path; `flare_start_agl_ft` sets the profile-specific transition to flare |
| `[engine]` | `min_roll_rpm` | engine must exceed this RPM 5 s into the takeoff roll |
| `[throttle]` | `taxi_base taxi_speed_gain taxi_max cruise_base ils_base approach_base` | tuning: base throttle positions |
| `[envelope]` | `kias` | the airborne speed band the bridge and observers accept |
| `[prop]` | `constant_speed`, `cruise_ratio` | whether there is a prop lever, and the level-cruise setting (0.5-1.0 of the governing range) |
| `[performance]` | optional: `acf_sha256 altitude_ft mass_kg conditions evidence points` | a MEASURED table of `[throttle, vertical speed fpm, settled KIAS]` points, tagged with the aircraft-file hash, loading and altitude; the cruise law uses it as throttle feed-forward. Absent means "not measured": the fixed `cruise_base` law is used |
| `[sources]` | free-form strings; `tuning` required | where the numbers came from |

Numbers are plain TOML floats; `1/3` is written `0.3333333333333333`, which round-trips exactly.

## Measured performance

`[performance]` is the first measured (not handbook) data: `scripts/perf_table_sweep.py` flies the points and
`scripts/perf_table_to_toml.py --write` puts them here. It is only valid for the aircraft file it was measured
on, so re-measure when that changes. How the C182T table was made, what it showed and its limits:
`docs/C182T_PERFORMANCE_TABLE_2026-10-15.md`. Both the C172SP and the C182T have one; the climb rate controllers may ask for is derived from it
(`AircraftProfile.sustainable_climb_fpm`). The two airplanes flying the same trials on the same code:
`docs/ONE_AUTOPILOT_TWO_AIRCRAFT_2026-10-15.md`.

## What does not live here yet

Climb performance versus altitude, stall speeds and further control types are planned, not built. They will
be added as measured, not guessed.
