# C182T constant-speed prop lever in the AI pilot (2026-10-15)

Status: **channel implemented and unit-tested; no live result yet. The first
sweep says the lever write is not taking effect, cause unknown.** Simulator
engineering only; not operating guidance for any real aircraft.

## What is in the tree

Commit `91951e2` (branch `feat/c182-prop-control`): an optional `prop` channel in
the atomic bridge frame, enabled by `constant_speed_prop` in the staged config so
C172 frames are unchanged; `services/ai_pilot/prop_law.py` (`PropLaw`) applies
`profile.prop_cruise_ratio` only in level, established cruise (above 1,000 ft
AGL, at least 85 KIAS, flaps up, |vvi| under 300 fpm to enter and 500 to leave)
and flies the lever full forward everywhere else; moves are slew-limited at
0.25 per second of simulation time. `prop_cruise_ratio` defaults to 1.0, so the
schedule currently commands full forward at all times. Commit `308d959` added
`scripts/c182t_prop_sweep.py` to measure the lever-to-RPM map.

## First sweep (run p2, 2026-10-15 07:18)

CAP 487 (ACF `Cessna_182T_G1000.acf`), ISA sea level, calm, 2,000 ft, on the
aircraft's own GFC 700 heading and altitude hold. Evidence:
`docs/evidence/c182t-2026-10-15/prop_sweep_p2.json` (SHA-256 `2224afd0cc467f8f…`)
and `.log`. Run p1 launched the simulator but the autopilot never engaged
(modes 0/0/0) and recorded no points; it is not evidence.

| Throttle | Lever commanded | RPM | MP (in.hg) | Power (HP) | KIAS |
|---|---|---|---|---|---|
| 0.55 | 1.00 to 0.50 | 2013-2016 | 15.9 | 76 | 100 |
| 0.80 | 1.00 to 0.50 | 2400 | 21.3 | 142 | 123 rising to 127 |

Across the whole lever range RPM, manifold pressure and power did not change.
In every row the `prop_ratio[0]` readback was 0.0 (commanded 1.0 down to 0.5)
and `ENGN_prop` (commanded prop speed) was a constant 251.3 rad/s (2,400 RPM).

## What this does and does not show

* The write did not land, or something rewrites the lever every frame. A lever
  that reads 0.0 after being set to 1.0 is not a lever with no effect. Both
  `prop_ratio[0]` and `prop_ratio_all` were set at the start of the run.
* It does **not** show the governor model is broken. With the lever reading 0.0
  and the commanded speed pinned at 2,400, the airplane may simply be governing
  at its maximum setting regardless of the lever.
* Candidates, not established: an assigned joystick prop axis rewriting the
  dataref each frame (unassigned axes normally do not); the UDP DREF name with
  an array index not addressing element 0 for writes; the ACF governing range
  (`_RSC_max_pwr_ENGN` and `_RSC_redline_ENGN` are both 2,400 in this build, the
  C172 had 2,500 and 2,700), which would leave the lever little or no room.
  Only a live probe separates them.
* The bridge writes the lever with `setDatavf` inside the plugin, not over UDP,
  and reads it back every frame. That path has passed offline tests only and has
  never run in X-Plane. The sweep does not exercise it.
* Side observation, not yet examined: 76 HP held 100 KIAS at 2,000 ft at 0.55
  throttle. That is a low power for 100 KIAS in a 182 and may bear on the open
  climb and cruise calibration (A-1, A2-4). Check against the POH power grid
  before using it.

## Consequence for the AI pilot

Nothing flies differently today: the schedule commands 1.0 unless
`prop_cruise_ratio` is lowered, and the sweep gives no basis for lowering it.
**Keep `prop_cruise_ratio` at 1.0** until a lever write is shown to move
`ENGN_prop` and the map is measured. The `prop_ratio` channel in the bridge
must be proven in the simulator (frame sent, readback follows) before any C182T
trial depends on it.

## Live probe (needs a person at the workstation)

1. Start X-Plane with the CAP 487 airborne and flying (autopilot on is fine).
2. `python3 scripts/c182t_prop_probe.py`. It writes the lever by two UDP paths,
   at 1.0, 0.5, 0.0, 1.0, and prints lever, commanded speed, RPM and prop pitch
   one second and nine seconds after each write. Output goes to
   `~/.cache/capvsar/measurements/prop_probe.json`.
3. Read the result:
   * readback follows the write, `ENGN_prop` moves: the sweep script had a
     defect; fix it and re-run `c182t_prop_sweep.py`.
   * readback snaps back to 0.0 within a second: something else owns the
     dataref. Check Settings, Joystick for a prop axis, then repeat.
   * readback follows, `ENGN_prop` does not move: the ACF governing range leaves
     no room. That is a builder change (`ACF_PATCHES`), sourced from the POH
     2,200-2,400 RPM cruise band, then re-flown.
4. Only then run the bridge path: stage a mission session with
   `constant_speed_prop` set and confirm the `prop` readback follows the frame.

`scripts/c182t_prop_probe.py` has been syntax-checked only; it has not been run.
