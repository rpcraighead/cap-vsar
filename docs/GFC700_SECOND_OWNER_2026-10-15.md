# GFC 700 as a second owner of the bridge, and the terrain guard in the executive (2026-10-15)

Status: **flown six times in X-Plane on the CAP 487 on 2026-10-15** (open water; ESCON with the terrain
guard climbing over the Ramona ridge): the final mid-climb hand-back run passes, earlier runs found and fixed
two real defects. Offline tests on a fake SDK before that.
Branch `feat/c182-prop-control`. Simulator engineering only; not operating guidance for any
real aircraft.

Decision context: CONOPS gate G was closed on 2026-10-15 (ArduPlane not adopted,
`docs/ARDUPLANE_TRIAL.md`). The layered stack is **AI -> executive -> {AI pilot's own
controllers | GFC 700}**. This is the executive half: the GFC 700 becomes a second
owner of the same bridge the controllers use, and the terrain guard that flew as a
demo script moves under whoever owns the airplane.

## What exists now

| Piece | Where | What it does |
|---|---|---|
| Terrain scan | `xplane/capvsar_terrain.py` | Probes real terrain along the ground track (centre line and +/-12 deg, 12 nm, 0.5 nm steps) once a second; result rides in every telemetry snapshot as `snapshot["terrain"]` |
| Autopilot readback | `xplane/capvsar_telemetry.py` | `ap_state`, heading/altitude/VS bugs and ground track added to `values` |
| Guard logic | `services/ai_pilot/terrain_guard.py` | Pure. Snapshot in, `Advice` out: altitude floor (indicated), climb rate, full power, turn back. The demo's numbers, ported; same advice whoever flies |
| Bridge, GFC owner | `ControlBridge.gfc_select`, plugin actions `transfer_gfc`, `heartbeat`, `gfc_select`, `set_virtual_aux`, `lab_handback` | Mission session only, and only if staged with `gfc_owner` |
| Bridge fence | `MissionLab` | Same airborne envelope while the autopilot flies, plus: ownership only above 1,000 ft AGL, 60-140 KIAS, bank <= 30, inside the region. Optional last-ditch terrain fence |
| Executive side | `services/ai_pilot/gfc_owner.py` | `GfcOwner`: engage, select, step (heartbeat + guard + verify), hand back |
| Trial | `scripts/ai_pilot_owner_trial.py`, `services/ai_pilot/owner_trial.py` | AI pilot holds, GFC 700 turns and holds, AI pilot takes it back; both hand-overs scored |
| Pattern runner | `scripts/ai_pilot_pattern.py` | Now runs the guard on the DIRECT owner (`--no-terrain-guard` to disable) |

## The hand-over protocol

* **DIRECT -> GFC 700:** `transfer_gfc` releases the actuator overrides and presses the
  autopilot in one simulator callback (overlapped, ARDUPLANE_TRIAL F1). Bridge state goes
  `WAIT_GFC` -> `GFC700`; the session and its frames are retired. `gfc_select` then sets the
  heading bug and altitude and engages HDG and ALT-hold or VS, each toggle only if its
  `autopilot_state` bit is clear. The executive must heartbeat at least every 0.4 s or the
  bridge pauses the simulator.
* **GFC 700 -> DIRECT:** `lab_handback` renews the session, submits the first two frames,
  prepares DIRECT and releases the autopilot, all in one callback. The caller then keeps
  submitting fresh frames until the bridge reads the servos off and goes `ACTIVE`
  (`GfcOwner.hand_back`). The runner must build a fresh controller afterwards.
* **Power** while the autopilot flies: `set_virtual_aux` moves the cockpit throttle lever
  (the GFC 700 has no autothrottle); the guard orders full power below its floor.
* **Faults:** an envelope or telemetry fault in `WAIT_GFC`/`GFC700` pauses the simulator
  like any other (the capture loop previously only did so in `ACTIVE`; fixed here).

## Terrain: advisory, and a fence

The guard is advisory: it raises a floor on the altitude target (DIRECT: the controller's
`altitude_ft`; GFC 700: the altitude selection) and orders full power. It turns back (stops
the trial) when the floor would exceed its ceiling or the airplane leaves the leash. Its
ceiling must stay below the bridge envelope's 6,500 ft indicated
(`AIRBORNE_MAX_ALTITUDE_FT`), or a floor it raised would pause the simulator; the runners
set it 500 ft under.

The fence is separate and dumb: `terrain_backstop_ft` (default 200 in `stage-mission`,
`--terrain-backstop-ft 0` disables) pauses the simulator if the highest terrain within
1.5 nm is closer than that below the airplane, and only above 1,000 ft AGL, so a normal
approach cannot trip it. It is there for when the guard did not act.

## Verified offline

Fake SDK through the real plugin dispatch, core and sink: engage, modes by toggle,
selection fences (generation, session, bounds, readback mismatch pauses), transfer refused
on the ground or low, actions absent unless staged, envelope and heartbeat watchdogs in
GFC700, hand-back in one callback with a new session, guard raising altitude and power,
leash turn-back, a floor above the ceiling turning back instead of pausing, VS zeroed after
selection being re-sent, stager output, and the trial scorer. 636 AI-pilot tests pass
(20 expected failures); the full suite has the same 169 failures as `main` (console tests,
unrelated).

## Flown 2026-10-15 (`scripts/ai_pilot_owner_trial.py`, CAP 487 ACF `11ff17d1...`)

Simulator launched and flown unattended (`xplane-clean`); the bridge's pause and override release
were the containment. Six flights, three passes, two real findings and one scorer error, all kept.
Summary and trace hashes: `docs/evidence/ai_pilot_owner_trial_20261015.json`.

| Run | What | Result |
|---|---|---|
| 1 | Open water off Point Loma, 2,170 ft | **PASS.** Hand-over to the autopilot: 0.4 ft, 24 fpm. 20 deg left captured within 1 deg, altitude within 1.2 ft. Hand-back: 1.2 ft, 0.4 deg of bank. |
| ESCON attempt | 8.6 nm from the Ramona ridge, 3,540 ft | **FAIL, scorer flaw, not a flight result.** The first phase was held to hand-over limits while the air start was still climbing 1,207 fpm. Fixed. |
| 2 | ESCON, same start | **PASS.** The ridge (3,977 to 4,526 ft against 3,530 ft) tripped the guard: floor about 6,000 ft, 700 fpm climb ordered and flown, full power ordered and flown. Hand-back during the climb. |
| 3 | ESCON, long (past the crest) | **FAIL, real.** Under the GFC 700 the airplane crossed the crest at 5,275 ft over 3,668 ft ground (min 1,586 ft clear), then levelled at 6,000 ft **at full throttle** and ran to 129-130 KIAS, breaking the speed band. The GFC owner restored cruise power only if the caller passed one. Fixed: it now remembers the power the AI pilot was flying and gives it back. |
| 4 | ESCON, hand-back mid-climb | **PASS, but a bad hand-over.** Handed 119.6 KIAS at 700 fpm, the fresh AI-pilot law cut the throttle to 0.13 and speed fell to 90.0 KIAS within 19 s. Inside the 70-130 band, so the scorer passed it. |
| 5 | Same, 2 kt/s ramp and seeded power | **FAIL by a wrong criterion; the flight was better but not fixed.** Min speed 90.0 -> 104.6 over the window the scorer saw. My criterion ("no more than 15 kt below the entry speed") also failed the intended slow deceleration to the 100 KIAS target. Replaced by an undershoot criterion. |
| 6 | Same, 0.4 kt/s ramp, undershoot criterion | **PASS.** Handed 119.5 KIAS mid-climb at 4,270 ft. Speed eased to the 100 KIAS target over about 50 s and held 100 +/- 1 (min 98.5), throttle 0.90 -> 0.76, climb continued at about 680 fpm to the 6,000 ft floor and levelled at 6,060 ft. The AI pilot flew over the ridge crest (33.212 N, 116.866 W, 3,737 ft ground, about 1.1 nm from the demo crash site) at 5,440 ft: 1,703 ft above the ground at the closest. Contained: paused, overrides released. |

What this answers from the offline list:

1. `g1000n1_ap` with no modes, then `gfc_select`: no visible attitude gap; hand-over transients under
   1 ft and 25 fpm (run 1), 12 ft and 36 fpm (ESCON). Modes after selection: HDG + ALT hold
   (`autopilot_state` 16386), HDG + VS during the climb (50).
2. VS engagement and the selected rate: the 700 fpm selection held for the whole climb in every run;
   the rate was not zeroed after the write. `GfcOwner.verify`'s re-send was not needed.
3. ALT hold holds the current altitude: 3,531 +/- 3 ft over 90 s.
4. Scan cost: recorded `capture_duration_s` maximum 0.7 ms (every 5th snapshot only).
5. First frame after hand-back (neutral yoke, measured throttle/trim): no excursion.
6. The 0.4 s heartbeat held at this machine's frame rate in all six runs.

Findings and fixes:

* **A fresh AI-pilot law handed a fast, climbing airplane cuts its power** (run 4). The cruise law is a
  speed-on-throttle loop around a fixed cruise power, with no idea what a climb needs. `CruiseLaw` now
  has an opt-in `adopt_slew_kt_s`: the speed command starts at the measured speed, slews to the target,
  and the throttle integrator is seeded from the measured throttle. At 2 kt/s that was not enough (run 4
  and 5 both dipped); at 0.4 kt/s it is (run 6). **This is a stopgap.** The principled fix is a measured
  power-versus-speed-and-climb-rate table feeding the throttle (the profile-and-performance-table work).
* **The GFC owner must give back the power it raised** (run 3). Fixed and unit-tested; **not re-flown
  through a level-off under the GFC 700**. A full climb-and-level run with a hand-back at level is the
  remaining live check.
* **The AI pilot's own controllers ignore the guard's `full_power`.** They climbed on their own speed and
  altitude loop, which reached about 0.9 throttle on its own. Only the GFC 700 owner applies `full_power`.
* The guard's events were swallowed by a second `guard.update` per frame; fixed (runs 2 onward show
  `events: 2`).
* The first scorer limited the adopted first phase and the hand-back by the wrong measure (runs ESCON
  attempt and 5). Both are fixed; the undershoot criterion is in `owner_trial.py`.
* The geofence's east edge (116.85 W) is short of the 4,526 ft ground, so runs 3-6 used a deliberate,
  recorded widening (`--extra-box 33.0 33.35 -116.85 -116.70`, `extra_airborne_boxes` in the staged
  config, session only). The default fence is unchanged.

## Still not verified

1. A GFC 700 level-off with the throttle restore (run 3's bug) and a hand-back at level.
2. The GFC 700 is flown on heading and altitude only. GPSS, the G1000 flight plan and NAV/APR coupling
   (what the squadron demo uses) are not driven from here yet.
3. The terrain fence (`terrain_backstop_ft`, 200 ft) never fired; the closest any run came was 1,586 ft.
4. A turn-back (floor above the ceiling, or the leash) has not been flown.
5. Low frame rates and request latency under load.

## Running the trial

```bash
python3 scripts/ai_pilot_experiment.py stage-mission ~/.cache/capvsar/stage-<stamp> \
    --aircraft "$HOME/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III/Cessna_182T_G1000.acf"
# install the staged files (now including capvsar_terrain.py) into Resources/plugins/PythonPlugins,
# config mode 0600; air start paused inside the mission region; then:
python3 scripts/ai_pilot_owner_trial.py --config <PythonPlugins>/capvsar_flight_control_config.json \
    --output ~/.cache/capvsar/ai-pilot/owner_trial_c182_1.jsonl --profile C182T
```

The simulator can be launched without anyone at the desk (`xplane-clean --detach --new_flight_json=...`, then pause once airborne). Back up and restore the installed bridge (`~/.cache/capvsar/bridge-backup-*`). The squadron demo rig (`~/capvsar-demo`) keeps its
own copy of the guard and is untouched.
