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
| `[landing]` | `final_speed_add_kias threshold_kias touchdown_pitch_deg touchdown_max_groundspeed_kt` | tuning and observer windows |
| `[engine]` | `min_roll_rpm` | engine must exceed this RPM 5 s into the takeoff roll |
| `[throttle]` | `taxi_base taxi_speed_gain taxi_max cruise_base ils_base approach_base` | tuning: base throttle positions |
| `[envelope]` | `kias` | the airborne speed band the bridge and observers accept |
| `[prop]` | `constant_speed`, `cruise_ratio` | whether there is a prop lever, and the level-cruise setting (0.5-1.0 of the governing range) |
| `[sources]` | free-form strings; `tuning` required | where the numbers came from |

Numbers are plain TOML floats; `1/3` is written `0.3333333333333333`, which round-trips exactly.

## What does not live here yet

Performance tables (power versus speed and climb rate, climb versus altitude, stall speeds, each tagged with
the aircraft-file hash it was measured against) and further control types are planned, not built. They will
be added as measured, not guessed: the first consumer is a throttle feed-forward to replace the stopgap
speed ramp in `CruiseLaw.adopt_slew_kt_s`. See `docs/GFC700_SECOND_OWNER_2026-10-15.md`, "Findings and fixes".
