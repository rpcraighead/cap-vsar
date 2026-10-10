# AI pilot: Sol handoff after the first flight demonstration

The subsequent frozen campaign is complete. See the
[Sol campaign report](evidence/AI_PILOT_SOL_CAMPAIGN_20261010.md) for the
20-flight outcome and the activation timing finding.

2026-10-10. Recommended next model: **Sol High**.
Worktree: `/home/ron/Projects/cap-vsar-ai-pilot`.
Branch: `feat/ai-pilot-first-cycle`. Remote: Gitea `ron/capvsar`.

The architecture now has a measured end-to-end demonstration on the stock C172:
coherent telemetry → simulation-time controller → atomic bridge → X-Plane
physics → independent establish/turn/recover score. This is the point Ron asked
us to stop Astra and hand implementation and the repeatability campaign to Sol.

## Results and their limits

| Trial | Result | Scored simulation duration | Samples |
| --- | --- | ---: | ---: |
| Baseline, cycle03 | PASS | 61.23 s | 704 |
| Repeat baseline after reset, cycle04 | PASS | 61.19 s | 701 |
| Entry 10° left, 100 ft high, 5 kt slow, cycle05 | PASS | 95.77 s | 1091 |

Each passed establish, a 20° heading change, and recovery to 90° magnetic,
4,500 ft indicated and 100 KIAS. Each phase required ten continuous seconds
within ±3° heading, ±75 ft altitude, ±3 KIAS, ±3° bank and ±150 fpm.
The controller gains and observer criteria were unchanged across these flights.
Every completed trial ended with confirmed simulator pause.

The airborne **loss-of-updates** probe observed the atomic-frame watchdog pause
the simulator, release overrides and retire the session. The airborne
**explicit takeover** probe observed MANUAL ownership, released overrides and
disengaged servos. Both rejected subsequent output from the retired writer.
These are fault-probe passes, not scored maneuver passes. Takeover was an
authenticated command; automatic detection of a physical yoke movement was
not tested or implemented here.

Paused native probes also verified all six channel readbacks and rejected
duplicate, stale, wrong-session and incomplete frames. Raw probe reports are
`20261010-native-probe2.json` and `20261010-native-probe3.json` in the evidence
directory below. Native readback alone does not identify a full aerodynamic
control derivative; the subsequent closed-loop flights supplied flight evidence.

All earlier failed attempts remain recorded. Native probe1 encountered a
blocking high-level placement operation. Cycle01 timed out during setup;
there were no scored samples and its final pause request also timed out.
Subsequent inspection confirmed the simulator was paused with overrides off.
Cycle02 was contained by the envelope monitor before scoring because the
airspeed indication had not initialized immediately after resume.

The reset now uses a bounded local-coordinate/velocity/quaternion update while
paused and released, following the [Laminar positioning conventions](https://developer.x-plane.com/article/movingtheplane/).
Setup operations have a separate response timeout; actuator leases still expire
within 200 ms. A maximum two-second startup phase accommodates the instrument
filter only while true airspeed, attitude and clearance remain bounded. It is
recorded as setup and cannot satisfy the observer's maneuver criteria.

Machine-readable trial results and hashes are in
[the evidence summary](evidence/ai_pilot_first_cycles_20261010.json).
Raw JSONL and probe JSON files are under
`/home/ron/.cache/capvsar/ai-pilot/`. Each flight manifest records source,
controller, runner, installed bridge, aircraft and scenery hashes. These were
development runs from a dirty worktree; their hashes identify the tested
versions. The final pre-flight identity guard received a subsequent offline
regression test. Run the formal campaign against the final committed build.

**This is not full flight qualification.** The ten-baseline/ten-disturbed-entry
campaign has not been run. Taxi, takeoff, landing, stalls, recovery from an
actual stall, and the custom C182 remain outside this demonstration. Production
and legacy live-control switches remain false.

## What changed

- `SnapshotController` drives the existing direct control laws synchronously,
  without its worker thread or native UDP writer. It adopts measured controls
  initially and emits complete candidate frames. Pause, stale/invalid data,
  duplicate frames and time discontinuities latch a fault; a fresh controller
  instance is required after reset. Integrals and slew limits use simulation
  time. Legacy nominal-tick behavior remains gated separately.
- The temporary qualification plugin mode pins the stock C172 ACF by path and
  SHA-256, expires automatically, bounds actuator authority and monitors the
  flight envelope locally. It checks aircraft identity before applying active
  outputs. It only permits DIRECT ownership. It does not assert production
  qualification or enable old raw-control launchers.
- Reset is limited to loaded Southern California scenery. It sets a reference
  offshore location, attitude and velocity, starts the engine, sets clear/static
  weather, 170 kg payload and 100 kg fuel, and rotates the output session.
  Measured initial total mass was approximately 1,050.63 kg. Readiness checks
  local position, pause, ownership, payload, fuel and local wind; the flight
  runner additionally requires engine-running readback.
- `ai_pilot_cycle.py` records setup, inputs, outputs, observer evidence,
  interventions and final containment. `--fault-probe loss` and
  `--fault-probe takeover` provide reproducible fault trials. State setup inside
  a scored trace invalidates that trace.

The reset is not an exhaustive failure-system reset or arbitrary third-party
plugin isolation facility. The successful environment used stock scenery and
the existing DF/G1000 SAR plugins. The installed North Island scenery still has
an unrelated missing OpenSceneryX dependency; it was temporarily disabled for
testing. Do not fold scenery repairs into this controller task.

## Next assignment for Sol

1. Review this handoff and the recorded manifests; continue this worktree and
   branch. Do not use the old `cap-vsar` working directory as the source baseline.
2. Add a small campaign runner around the existing cycle command. Use
   [`qualification_entries.json`](../services/ai_pilot/qualification_entries.json)
   for ten baseline repetitions and the ten predeclared disturbed entries.
   Run one controller process at a time and use unique trace paths. Capture
   startup/lock failures as campaign outcomes too.
3. Freeze the committed code, criteria, gains and environment for a fresh
   campaign. Do not count these development demonstrations toward the ten
   consecutive baseline successes. Retain failed attempts. If a fix or tuning
   change is necessary, start a new named campaign and preserve the earlier one.
4. Independently replay every scored trace. Produce a compact report with
   per-phase capture times, tracking errors, maximum telemetry gap, actuator
   saturation, interventions and terminal ownership/pause readbacks.
5. Re-run the loss and takeover probes on the frozen build, restore the
   simulator installation, commit/push the campaign runner and evidence report.

Stop after reporting the campaign. Do not open the global live-control gates,
move to the C182, or expand to takeoff/landing/stalls in this assignment.
Return to Astra if evidence calls for changing the control architecture or
shows unexplained instability; routine runner, reporting and bounded fixes are
appropriate Sol work.

## Running the laboratory session

The test session and cleanup are complete. After the separate desktop-launched
X-Plane instance exited, all backed-up simulator preferences, stock C172
preferences and the original scenery configuration were restored and verified
byte-for-byte against the backups. X-Plane is stopped. All six temporary bridge
and configuration files were removed from the active plugin directory and
archived in `tested-flight-plugin` under the backup directory; the private
configuration retains mode 0600. Original scenery and preferences remain under:
`~/X-Plane 12/Output/capvsar-backups/ai-pilot-flight-20261010/`.
Start a fresh expiring session rather than reusing its old private config.

```sh
cd /home/ron/Projects/cap-vsar-ai-pilot
python3 scripts/ai_pilot_experiment.py stage-qualification /tmp/capvsar-lab-new \
  --aircraft "$HOME/X-Plane 12/Aircraft/Laminar Research/Cessna 172 SP/Cessna_172SP_G1000.acf"
```

With X-Plane stopped, back up its preferences, stock C172 preferences, scenery
configuration, and any existing bridge files. Install the six staged files in
`Resources/plugins/PythonPlugins/`, preserving the config's `0600` permissions.
Temporarily use stock scenery while preserving the original scenery file.
The staged lease lasts one hour. Launch with:

```sh
bash scripts/launch_xplane12.sh --no_sound \
  '--load_acf=Aircraft/Laminar Research/Cessna 172 SP/Cessna_172SP_G1000.acf' \
  --load_apt=KNZY
```

Wait for loading and fresh telemetry before starting a trial. For example:

```sh
python3 scripts/ai_pilot_bridge_probe.py \
  --config "$HOME/X-Plane 12/Resources/plugins/PythonPlugins/capvsar_flight_control_config.json" \
  --output "$HOME/.cache/capvsar/ai-pilot/new-native-probe.json"

python3 scripts/ai_pilot_cycle.py \
  --config "$HOME/X-Plane 12/Resources/plugins/PythonPlugins/capvsar_flight_control_config.json" \
  --output "$HOME/.cache/capvsar/ai-pilot/new-cycle.jsonl"

python3 scripts/ai_pilot_experiment.py score \
  "$HOME/.cache/capvsar/ai-pilot/new-cycle.jsonl"
```

Disturbed runs add `--heading-offset`, `--altitude-offset` and `--speed-offset`.
Fault probes use the cycle command with `--fault-probe loss` or
`--fault-probe takeover`. Their traces intentionally are not scored flights.
Never copy or commit the socket secret into Git. After testing, exit X-Plane,
restore the backed-up settings, and remove the temporary plugin/config.

Offline validation uses
`/home/ron/Projects/cap-vsar-integration/.venv/bin/python -m pytest`.
The final full run produced **955 passed, 22 expected failures, one skip and the
same two known console-route failures**, plus 97 passed subtests. The focused
controller/bridge/qualification/observer run passed all 65 tests. The existing
fake-UDP-thread warning is a separate baseline issue; record it without
expanding this flight task.
