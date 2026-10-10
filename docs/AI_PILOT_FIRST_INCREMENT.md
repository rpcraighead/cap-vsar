# AI pilot first implementation increment

2026-10-10. Branch: `feat/ai-pilot-first-cycle`, based on `62ed4b9`.

This implements the observation and evidence foundation for the
[development plan](AI_PILOT_DEVELOPMENT_PLAN.md). **It does not yet fly the
establish–maneuver–recover cycle.** Milestone 0 is partially implemented;
milestones 1 and 2 remain unqualified. All production live-control switches
remain false.

## Implemented

- An optional `atomic-v1` bridge protocol accepts all six actuator channels in
  one request. It validates session, generation, increasing sequence, finite
  ranges and a maximum 200 ms monotonic-time expiry before changing candidates.
  Independent dataref packets cannot modify an atomic session. Preparing a
  transfer increments generation and requires a fresh frame before activation.
  Accepted frames still require a separate executive heartbeat and ownership
  readbacks. Legacy candidate mode remains available behind its existing gate.
- Authority requests run before the flight model; coherent telemetry is captured
  after it. Queued requests expire before execution. SDK calls stay in simulator
  callbacks; socket work stays off the simulator thread.
- `mode: observe` permits only status, telemetry and schema queries, even while
  the live-control gate is closed. It registers no candidate datarefs and cannot
  pause, take over, or write native controls.
- Telemetry identifies the aircraft, session, frame, SDK counter, simulation and
  monotonic wall times, capture duration, controls and ownership readbacks.
  The manifest gives channel units and datarefs, including altitude datums and
  magnetic versus true heading.
- Fault handling uses the `sim/operation/pause_on` command. It reports
  `FAULT_PAUSE_PENDING` until `sim/time/paused` confirms the request. The executive
  stops tasks in either fault state. The current flap-handle dataref replaces
  the deprecated `flap_ratio` alias.
- The experiment harness records source, installed plugin, stock aircraft and
  scenery-configuration hashes. It refuses to overwrite a trace or run against
  mismatched installed bridge source. Observation results explicitly state that
  they do not qualify flight control.
- An independent replay observer checks a proposed 20-degree heading change and
  return, with sustained heading, altitude, speed, bank and vertical-speed
  capture. It rejects intervention, reset, gaps, wrong aircraft, malformed data,
  timeout and incomplete evidence. Controller success claims do not affect its
  result. These are provisional engineering criteria, not aircraft POH limits.

## Simulator evidence

The successful trial used X-Plane 12.4.3, the stock C172 G1000 on the ground at
KNZY, and temporarily enabled only stock scenery. SDK versions returned
`[12431, 430, 1]`. The aircraft ACF SHA-256 was
`b9c3c35c956ac5bee8c74fc9cbf933c6ecdfab73db9ad22862022aa3a20ab847`.

| Check | Observation |
| --- | --- |
| Thirty-second read-only recording | 264 distinct snapshots; `OBSERVATION_PASS` |
| Maximum snapshot age when served | 0.01447 s |
| Maximum gap between recorded snapshots | 0.16290 s |
| Control overrides throughout recording | Both off |
| Pause probe using an operator UDP command | Pause read back as 1; simulation time remained 70.15447 s while frame count advanced from 7327 to 7396 |
| Resume probe | Pause read back as 0 |
| Read-only authority denial | `prepare`, `submit_frame`, `activate`, `fault_pause`, and `human_takeover` each rejected |

These checks verify local telemetry transport and pause observability. They do
not demonstrate actuator signs, commanded-control effects, engine response,
failure containment under flight load, controller stability or flight outcomes.

Raw artifacts, outside Git:

- `~/.cache/capvsar/ai-pilot/20261010-observe-attempt3.jsonl`
  (SHA-256 `77ef61a4fb6eb56a0f4110904b554d0fe7cc1413ac8e8aaa12555d4ef9749935`).
- `~/.cache/capvsar/ai-pilot/20261010-pause-readback.json`.
- Simulator logs, original settings, and the tested plugin bundle:
  `~/X-Plane 12/Output/capvsar-backups/ai-pilot-observe-20261010/`.

Earlier attempts are retained in that backup directory. The first encountered
missing OpenSceneryX dependencies in the installed North Island airport. During
retry, checking the process name missed X-Plane after it renamed itself
`Main Thread`, allowing an accidental second launch. Both test processes were
stopped, and a single clean instance was used for the successful trial. The
launcher now checks `/proc` executable identity and was verified to refuse a
second instance. This does not implement a race-free multi-launch lock.

After the successful trial, X-Plane exited normally. The original scenery file
and backed-up main/window preferences were restored. The experimental plugin
and its private config were moved out of the active plugin directory into the
backup bundle. No CAP aircraft or livery files were modified.

## Reproduction

From the worktree, using Python with the service dependencies:

```sh
python scripts/ai_pilot_experiment.py stage-observer /tmp/capvsar-observer-bundle
```

With X-Plane stopped, preserve any existing flight-control plugin/config before
installing the five staged files in `Resources/plugins/PythonPlugins/`. Preserve
the config's `0600` permissions and do not commit its secret. Use a new staged
session for each installation. Launch the stock C172 G1000 with a known scenery
profile and wait for loading to complete, then run:

```sh
python scripts/ai_pilot_experiment.py observe \
  --config "$HOME/X-Plane 12/Resources/plugins/PythonPlugins/capvsar_flight_control_config.json" \
  --output "$HOME/.cache/capvsar/ai-pilot/new-observation.jsonl" --seconds 30
```

The scorer is available for future **scored-cycle** traces:

```sh
python scripts/ai_pilot_experiment.py score /path/to/scored-cycle.jsonl
```

It deliberately rejects observation-only traces as flight evidence. The current
harness has no reset or live-flight runner; synthetic observer tests establish
scoring behavior only.

## Validation and next work

The full repository run produced 929 passed, 22 expected failures, one skip and
the same two previously verified console-route failures in `tests/test_console.py`.
There was also the existing fake UDP socket thread warning. After adding the
executive's pending-pause and malformed-record regressions, the targeted
executive/protocol/observer run passed all 59 tests.

Remaining first-deliverable work:

1. Implement controlled airborne reset, weather/mass/configuration verification
   and readiness checks; define the ten disturbed-entry cases before trials.
2. Adapt the direct controller to coherent snapshots and simulation-time steps.
   Its historical per-tick integrators and raw legacy loop are not migrated by
   this increment. Freeze/reset integration on pause or time discontinuities.
3. Qualify native actuators and fault containment on the stock C172: polarity,
   full-frame application, trim/throttle behavior, delayed/missing process,
   pause, ownership loss, takeover and simulator reset. Read-only qualification
   is insufficient to open the production gates.
4. Connect the deterministic executive, controller, atomic bridge and observer;
   record every tuning trial. Then freeze criteria and tuning for ten baseline
   plus ten predeclared disturbed-entry cycles.

The next code change should implement the snapshot-driven controller adapter
and reset/readiness harness, not enable the existing raw-control launchers.
