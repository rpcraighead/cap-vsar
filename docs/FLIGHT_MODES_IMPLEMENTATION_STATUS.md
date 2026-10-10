# Flight modes implementation status — 2026-09-18

HEAD remains `212352c`. This is an **uncommitted offline implementation**, not
a flown or qualified AI pilot. No live X-Plane/SITL command, plugin install,
simulator setting, or simulator port was used. `LIVE_CONTROL_QUALIFIED` and
the plugin's `LIVE_PLUGIN_QUALIFIED` both remain `False`; production ArduPlane adapter readiness and virtual-pilot power default
to closed. The earlier September 17 ArduPlane GUIDED flight was real but did
not capture; its final observation faults the gate on offline replay.

## Sequential milestone record

| Milestone | Implemented and verified offline | Still open |
| --- | --- | --- |
| A — truthful results/lifecycle | Gate events carry IDs, sequence, task ID, wall/monotonic times and distinct terminal outcomes. Stable transfer entry rejects the recorded dive. Launchers report achievement only after measured capture; timeout/refusal/fault use nonzero exits. Managed SITL mapping validates before startup; all three legacy launchers wrap acquired resources in final cleanup; detach separates human, Garmin, fault pause and ground stop, with stop/readback reporting. H0 no longer permits forced test points off an unstabilized reference. Injected direct/H0 and ArduPlane start, MAVLink readiness/link, backend, gate and subscription failures release owned resources. An unconfirmed SITL stop prevents override clearing and Garmin engagement. | No teardown behavior was live-verified. |
| B — executive/output boundary | Typed authority/phase/controller/test/transfer states, leases and task sequence; shared process lock across four entrypoints; session/generation arbiter, bounded candidate freshness/skew, watchdog, human takeover, dynamic fresh-session Garmin return, private ArduPlane mapping and separate inert plugin. Stateful fake tests cover AP toggles, overrides, stale candidates, old sessions, and dynamic namespace registration. A second closed guard keeps historical raw launcher/chat paths disabled even if the general bridge gate changes. | Legacy launcher/chat/H0 routes are blocked live rather than fully migrated to the executive. Independent DREFs lack a source sequence, so delayed same-session packets remain a live qualification issue. Plugin SDK behavior is unverified. |
| C — controller adapters | Offline ArduPlane mission, Garmin, direct test, and virtual-pilot adapters with prepare/readiness/activation and observed completion. Garmin requires selected and active mode readbacks. Direct output seeds measured surfaces and slews actual writes. Diagnostics include attitude, servo output, version and effective parameter requests. Virtual-pilot throttle/flap actions are typed and bridge-fenced. | Actual pinned version, runtime parameters, sensor frames, SDK DREF writability, power/configuration response and controller tracking need attended verification. Production ArduPlane and virtual-pilot readiness remain closed. |
| D — mission/Test Pilot workflows | Real MAVLink count/request/item/ACK transaction with retries, AUTO observation, typed home/runway/route geometry and MSL versus relative altitude. Script gates observed ground readiness, takeoff, route, approach, touchdown, rollout and explicit ground-stop confirmation; timeout uses go-around/fault branches. An optional Garmin cruise segment requires achieved waypoint, measured transfer floor and Garmin capture, fresh candidate session and link, mission reupload, acknowledged/observed current waypoint and observed AUTO before rejoin. Managed return stages a private mapping, rotates the bridge session, and runs the blocking SITL restart/protocol work in a worker while normal executive ticks maintain the heartbeat; failures abort to human and report unconfirmed teardown. Observed rollout releases bridge authority. Test Pilot gates stable reference, bounded baseline-relative input and measured recovery, records category/provenance/samples, and separates software result from aircraft acceptance. Sourced runway corridors are required by default; cruise limits are unchanged. | No aircraft-sourced operational runway envelope has been supplied. Managed return is only fake-process/protocol tested; production adapter readiness remains closed, and no live restart, ground controls, flight dynamics or runway-to-runway operation is qualified. |
| E — proof/handoff | Acceptance plan, status, README correction and dated changelog added. Whole service suite, including isolated loopback HTTP tests, passes with permitted local sockets. | Attended stages in the acceptance plan have not run. |

## Exact verification

- `/home/ron/.cache/capvsar/capvsar-planner-venv/bin/python -m pytest services/ai_pilot/tests -q --tb=line` with isolated loopback socket access — **exit 0: 354 passed, 60 subtests passed**. No live simulator/SITL ports were used. An earlier run in the default socket-restricted sandbox failed only when 12 isolated HTTP cases tried to create local listeners; those cases passed with loopback access.
- Focused tests cover mission rejoin ACK/readback, Garmin transfer and refusal paths, delayed managed restart with normal executive heartbeat, rollout ground-stop confirmation, process/link failure cleanup, and unconfirmed stop reporting. All are included in the 354-pass suite.
- After the ArduPlane launcher cleanup-scope edit, `test_sitl_lifecycle.py test_arduplane_backend.py` — **64 passed, 6 subtests passed**; launcher `--dry-run` — **exit 0**.
- `scripts/fly_arduplane_backend.py --dry-run` — **exit 0**, mock preflight/detach only. `fly_direct_backend.py --heading 090 --altitude 4500` and `fly_card_h0.py` — **exit 7**, live qualification guard, before simulator connection.
- `git diff --check` and `python -m compileall -q` for service, bridge and launchers — **exit 0** after the final code edits.

The fake full-sortie test is **workflow/protocol validation, not flight-dynamics validation**. It supplies independent observations. An ACK, mode display or mission item reached never substitutes for measured aircraft behavior.

## Decisions and remaining qualification

- Cruise `Limits` remain 3,000–6,000 ft indicated, at least 1,000 ft AGL,
  90–140 KIAS and at most 35° bank. Runway exceptions require explicit
  phase, position corridor and a cited source; no operational values were
  invented. Ordinary transfer stability is a separate policy.
- Stock SITL mapping and unmanaged SITL cannot be used for live authority.
  Candidate mapping is validated before managed SITL start. The pinned XPlane
  model ignores the launcher’s `--sim-port-in` value; the rig was not changed.
- The plugin can register a fresh candidate namespace for GFC-to-ArduPlane
  return in fake SDK tests. The old session remains retired. The offline
  managed-return procedure now stages a new candidate mapping and requires
  a new link, armed heartbeat, mission reupload, current-item ACK/readback and
  observed AUTO. A real SITL restart and SDK dataref registration still need
  attended proof.
- The managed-return restart runs in a worker while the executive continues
  its normal heartbeat; injected delay and cancellation are tested. If the
  executive stops ticking, the bridge still fences output. Real restart,
  cancellation latency and aircraft response need attended timing evidence.
  The live gate stays closed.
- Runtime `GUIDED_*` values, the controller branch flown in the 2026-09-17
  circle, AP/servo/override readbacks, native throttle/flap DREF writability,
  and continuous aircraft response are `UNVERIFIED_LIVE`.
- The remaining offline architecture work is to replace the blocked legacy
  launcher/chat routes with executive-backed adapters; they must stay closed
  until that migration is implemented and tested. The managed-return
  procedure then needs connection to a future qualified live runtime.
  The next
  attended step begins with bridge standby/no-authority testing in
  [FLIGHT_MODES_ACCEPTANCE.md](FLIGHT_MODES_ACCEPTANCE.md), not a flight.

## Exact files changed for this assignment

Tracked: `CHANGELOG.md`; `scripts/fly_arduplane_backend.py`,
`scripts/fly_card_h0.py`, `scripts/fly_direct_backend.py`;
`services/ai_pilot/README.md`, `arduplane_backend.py`, `direct_backend.py`,
`flight_controller.py`, `maneuver_server.py`, `maneuvers.py`, `mavlink_min.py`,
`sitl_lifecycle.py`; and service tests `test_arduplane_backend.py`,
`test_direct_backend.py`, `test_maneuvers.py`, `test_mavlink_min.py`,
`test_sitl_lifecycle.py`.

New: `docs/FLIGHT_MODES_IMPLEMENTATION_STATUS.md`,
`docs/FLIGHT_MODES_ACCEPTANCE.md`;
`services/ai_pilot/arduplane_mission.py`, `bridge_client.py`,
`candidate_client.py`, `control_ownership.py`, `flight_adapters.py`,
`flight_executive.py`, `managed_return.py`, `mission_script.py`, `phase_profiles.py`,
`test_pilot_script.py`; service tests `test_arduplane_mission.py`,
`test_candidate_client.py`, `test_control_ownership.py`,
`test_flight_control_bridge.py`, `test_flight_control_plugin.py`,
`test_flight_executive.py`, `test_managed_return.py`, `test_phase_profiles.py`,
`test_test_pilot_script.py`, `test_launcher_cleanup.py`; and `xplane/PI_capvsar_flight_control.py`,
`xplane/capvsar_flight_control_core.py`,
`xplane/capvsar_flight_control_mapping.py`.

Other agents’ pre-existing C182T calibration/test-card, RAGD, analysis,
architecture-review and overnight-prompt files were preserved and are not
part of this change list.
