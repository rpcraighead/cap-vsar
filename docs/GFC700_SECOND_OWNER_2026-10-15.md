# GFC 700 as a second owner of the bridge, and the terrain guard in the executive (2026-10-15)

Status: **implemented and tested offline (fake SDK); never run in X-Plane.** Branch
`feat/c182-prop-control`. Simulator engineering only; not operating guidance for any
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

## Not verified: everything the simulator has to answer

1. Engaging the autopilot with `sim/GPS/g1000n1_ap` and no modes: does it come up ROL/PIT
   (ARDUPLANE_TRIAL F4) and hold attitude for the frames before `gfc_select` lands? The
   trial's hand-over transient numbers answer this.
2. Whether `XPLMCommandOnce` completes before the next line, i.e. whether engaging VS zeroes
   the rate before or after the sink writes it. `GfcOwner.verify` re-sends, up to 3 times.
3. `sim/autopilot/altitude_hold` holds the *current* altitude, not the bug. The hold path
   therefore holds wherever the airplane is when it engages; the trial scores that.
4. The scan runs about 75 probes once a second inside the telemetry callback. Check
   `capture_duration_s` in the trace.
5. The first frame after hand-back uses a neutral yoke with measured throttle, trim and
   prop. Whether the airplane holds through it is the second transient the trial scores.
6. Request latency: the plugin serves at most 8 requests per simulator frame, one round
   trip each. At low frame rates the 0.4 s heartbeat has less margin.
7. The GFC 700 is flown on **heading and altitude only**. GPSS, the G1000 flight plan and
   NAV/APR coupling (what the squadron demo uses) are not driven from here yet.

## Live trial (needs a person at the workstation)

```bash
python3 scripts/ai_pilot_experiment.py stage-mission ~/.cache/capvsar/stage-<stamp> \
    --aircraft "$HOME/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III/Cessna_182T_G1000.acf"
# install the staged files (now including capvsar_terrain.py) into Resources/plugins/PythonPlugins,
# config mode 0600; air start paused inside the mission region; then:
python3 scripts/ai_pilot_owner_trial.py --config <PythonPlugins>/capvsar_flight_control_config.json \
    --output ~/.cache/capvsar/ai-pilot/owner_trial_c182_1.jsonl --profile C182T
```

Restore the previous bridge afterwards. The squadron demo rig (`~/capvsar-demo`) keeps its
own copy of the guard and is untouched.
