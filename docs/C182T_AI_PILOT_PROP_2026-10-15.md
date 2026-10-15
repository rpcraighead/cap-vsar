# C182T constant-speed prop lever in the AI pilot (2026-10-15)

Status: **the bridge channel was wired to the wrong dataref and is fixed; the lever now measured in the
simulator.** The lever-to-RPM map is known (below). The corrected bridge sink is tested offline only; it
has not yet run inside the simulator. Simulator engineering only; not operating guidance for any real
aircraft.

## Result in one paragraph

On the CAP 487 the constant-speed lever is **`sim/cockpit2/engine/actuators/prop_rotation_speed_rad_sec`**,
the requested prop speed in rad/s. `prop_ratio`, which the bridge, the cockpit lever animation and the first
sweep used, drives nothing. Governed RPM follows the lever one-for-one between the aircraft's governing
limits, 2,000 RPM (`acf_RSC_mingov_prp`) and 2,400 RPM (`acf_RSC_redline_prp`), at least above the throttle
where the engine can reach the setting. The bridge's 0-1 `prop` channel is now scaled across that range
(0 = 2,000 RPM, 1 = 2,400 RPM; the lab's authority floor of 0.5 is 2,200 RPM).

## What is in the tree

Commit `91951e2` added an optional `prop` channel to the atomic bridge frame, enabled by
`constant_speed_prop` in the staged config (C172 frames are unchanged), and
`services/ai_pilot/prop_law.py` (`PropLaw`), which applies `profile.prop_cruise_ratio` only in level,
established cruise (above 1,000 ft AGL, at least 85 KIAS, flaps up, |vvi| under 300 fpm to enter and 500 to
leave) and flies the lever full forward everywhere else, slew-limited at 0.25 per second of simulation
time. `prop_cruise_ratio` defaults to 1.0 (2,400 RPM). The correction to the real dataref and range scaling
is in `PI_capvsar_flight_control.py` (`PROP_LEVER`, `PROP_RANGE`, `XPlaneSink._prop_range`).

## How it was found (live, 2026-10-15)

1. **Sweep p2 (07:18):** wrote `prop_ratio[0]` from 1.0 to 0.5; the readback stayed 0.0, commanded prop
   speed stayed 251.33 rad/s, RPM did not move. Evidence: `docs/evidence/c182t-2026-10-15/prop_sweep_p2.*`.
   Run p1 recorded no points and is not evidence.
2. **Probe (10:5x, simulator launched unattended with `xplane-clean`):** `prop_ratio[0]` and
   `prop_ratio_all` again did nothing. The pilot-style commands `sim/engines/prop_down`/`prop_up` did move
   `ENGN_prop`, about 1.7 RPM per step, from 2,400 down to a floor of 2,000 RPM after about 300 steps;
   once the commanded speed fell below the engine's actual RPM the engine followed it and prop pitch
   coarsened (15.1 deg at 2,000).
3. **The right dataref:** X-Plane's `DataRefs.txt` says `prop_rotation_speed_rad_sec` is the "prop handle
   position, in radians per second of requested prop rpm. Use this if your plane has a constant speed
   prop." Writing it at 0.80 throttle, 2,000 ft, GFC 700 altitude hold:

| Lever written (RPM) | Governed RPM | MP (in.hg) | Prop pitch (deg) | Power (HP) | KIAS |
|---:|---:|---:|---:|---:|---:|
| 2400 | 2401 | 21.1 | 15.1 | 141 | 119 |
| 2300 | 2300 | 21.9 | 16.7 | 141 | 123 |
| 2200 | 2200 | 22.5 | 18.3 | 141 | 125 |
| 2100 | 2100 | 23.2 | 19.9 | 140 | 126 |
| 2000 | 2000 | 23.8 | 21.5 | 138 | 126 |

   The corrected probe (`scripts/c182t_prop_probe.py`, evidence `prop_probe_live.json`, SHA-256
   `c630deccc07221a5...`) repeats it: path C (`prop_rotation_speed_rad_sec[0]`) gives 2,400 / 2,200 / 2,000
   RPM for ratios 1.0 / 0.5 / 0.0 with pitch 15.8 / 18.5 / 21.6 deg. `prop_ratio` reads back a small
   derived number (0.05 to 0.40) once the real lever moves; it is an output here, not the lever.

## Consequences

* **The bridge's `prop` channel was inert.** Frames wrote to `prop_ratio` and read back 0.0. Fixed in the
  sink; the unit test now pins the dataref, the scaling and the refusal to guess when the range is
  unreadable. **Not yet exercised inside the simulator** (needs a staged mission session).
* **The cockpit prop lever the builder adds is bound to `prop_ratio[0]`** (`build_c182t_package.py`,
  `add_prop_lever`), so it neither drives the governor nor tracks it. It needs rebinding to the rad/s
  dataref with the 209.4-251.3 key values. Not done here (aircraft-acceptance lane, and AI-4 is open).
* **`prop_cruise_ratio` can now be set from a measured map.** Cruise RPM = 2,000 + 400 x ratio. Power
  barely changes with RPM at fixed throttle (138-141 HP), and airspeed rises about 7 kt from 2,400 to
  2,000 RPM, so the schedule is a noise and fuel-flow choice, not a performance one. It stays at 1.0
  until someone picks a cruise RPM from the POH power table.
* **At low throttle the prop is on its fine stop.** At 0.55 throttle (15.9 in.hg) the engine reaches only
  about 2,010 RPM with the prop at its 14.9 deg minimum pitch, while 2,400 is commanded, so the governor
  has no authority until the commanded speed drops below 2,010. Whether that matches a real B3D36C431 is
  unchecked; it bears on the 182 cruise-power and climb calibration (A2-4, A-1). The earlier "76 HP holds
  100 KIAS" observation is this regime.
* **Corrected sweep:** `scripts/c182t_prop_sweep.py` now writes the rad/s lever scaled across the range.
  A full re-sweep is optional; the map above answers its question.
