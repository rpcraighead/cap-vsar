# GFC 700 as a second owner of the bridge, and the terrain guard in the executive (2026-10-15)

Status: **flown twice in X-Plane on the CAP 487 on 2026-10-15 and passed both times**
(open water; ESCON with the terrain guard climbing). Offline tests on a fake SDK before that.
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
were the containment. Summary and trace hashes: `docs/evidence/ai_pilot_owner_trial_20261015.json`.

| Run | Start | Result |
|---|---|---|
| 1 | Open water off Point Loma, 2,170 ft, heading 352 deg | **PASS.** Hand-over to the autopilot: 0.4 ft altitude change, 24 fpm. Heading change of 20 deg left captured within 1.1 deg, altitude held within 1.2 ft. Hand-back: 1.2 ft, 0.4 deg of bank. |
| ESCON attempt 1 | 8.6 nm from the Ramona ridge, 3,540 ft | **FAIL, scorer flaw, not a flight result.** The air start was still climbing at 1,207 fpm when adopted and tripped a hand-over limit. The first phase has no hand-over; it is now recorded, not limited. |
| ESCON run 2 | Same start, same airplane, re-adopted | **PASS.** The GFC 700 held heading and altitude at 3,533 ft (within 11 ft, bank under 6 deg). The ridge ahead (3,977 to 4,526 ft against 3,530 ft) tripped the guard: floor 5,997 ft, minimum clearance -813 ft, 700 fpm climb ordered and flown to within a few fpm, full power ordered and flown. Hand-back happened during the climb. Contained, paused, overrides released. |

What this answers from the offline list:

1. `g1000n1_ap` with no modes, then `gfc_select`: no visible attitude gap. Hand-over transients were
   under 1 ft and 25 fpm in run 1. (Mode state after selection: HDG + ALT hold, `autopilot_state` 16386;
   HDG + VS, 50, during the climb.)
2. VS engagement and the selected rate: the 700 fpm selection held for the whole climb, so the
   rate was not zeroed after the write. `GfcOwner.verify`'s re-send path was not needed live.
3. ALT hold holds the current altitude: held 3,531 +/- 3 ft over 90 s. The hold path works as built.
4. Scan cost: recorded `capture_duration_s` maximum 0.7 ms (every 5th snapshot only).
5. First frame after hand-back (neutral yoke, measured throttle/trim): no excursion.
6. The 0.4 s heartbeat held at this machine's frame rate for the whole of both runs.

New findings:

* **Power after a hand-back mid-climb.** The fresh `CruiseLaw` targets 100 KIAS. Handed the airplane
  at 119 KIAS at full power, it cut throttle to 0.12 for about 8 s and speed fell to 90 KIAS before it
  recovered and climbed at 650 to 690 fpm. Inside the scorer's 70-130 KIAS band, but the DIRECT owner
  should start from the airspeed it is given. Not fixed.
* **The DIRECT owner ignores the guard's `full_power`.** It climbs on its own speed-and-altitude loop,
  which reached full throttle in about 10 s. Only the GFC 700 owner applies `full_power`.
* **The guard's events were swallowed** by a second `guard.update` per frame in the runner, so the trace
  shows `terrain_guard.events` as 0 though the floor rose. Fixed (pass the advice in); not re-flown.
* The airplane ended the ESCON run at 4,590 ft climbing, 1.5 nm short of the ridge line at 4,526 ft and
  heading for a 6,000 ft floor; the trial stops at its time limit, so clearance over the ridge itself was
  not demonstrated. A run long enough to cross it is the next ESCON test.

## Still not verified

1. The GFC 700 is flown on heading and altitude only. GPSS, the G1000 flight plan and NAV/APR coupling
   (what the squadron demo uses) are not driven from here yet.
2. The terrain fence (`terrain_backstop_ft`, 200 ft) never fired; no trial approached it.
3. A turn-back (floor above the ceiling, or the leash) has not been flown.
4. Low frame rates and request latency under load.

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
