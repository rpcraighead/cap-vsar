# Flight-mode attended acceptance plan

**Status: no stage in this plan has been run.** All live control remains disabled by
`LIVE_CONTROL_QUALIFIED = False` in `services/ai_pilot/control_ownership.py`
and `LIVE_PLUGIN_QUALIFIED = False` in the XPPython3 plugin.
The offline tests validate ownership logic, protocol transactions, and scripted
observation gates; they do not validate CAP 487 flight dynamics, XPPython3
behavior on the installed simulator, or a runway-to-runway flight.

The test lead records the aircraft/package hash, weight/CG, weather, simulator
and plugin versions, ArduPilot binary/source pin, effective parameter readback,
mapping/session identity, pilot, date, and trace paths for every attempt. The
human pilot keeps an independent takeover path and can stop any stage.

## 1. Bridge with no authority

Install the isolated flight-control plugin and a new session mapping only in an
attended window. Verify the installed SDK datarefs/commands and their
writability against the actual X-Plane installation before enabling it. With
no authority, run a managed SITL in standby on a **private candidate namespace**.
Record complete candidate timestamps and native actuator/override/AP readbacks.
Pass only if standby produces continuously fresh candidate values while native
actuator and override changes attributable to it remain zero. Inject partial,
stale, nonfinite, wrong-session, skewed, and delayed candidate sets. Each must
be refused or fenced. Establish how to distinguish delayed packets within a
single session; the current DREF protocol cannot carry its own generation.
Exercise bridge watchdog loss and human takeover during preparation, commit,
active control, Garmin verification, and Test Pilot recovery. Record bounded
time from action to override release, AP state, actual pilot control, and any
pause. A second process lock acquisition must fail before any aircraft write.

## 2. Stable ArduPlane flight

Begin from a manually stabilized airborne condition inside the unchanged
cruise envelope. Confirm measured transfer stability, effective ArduPlane
parameters from runtime readback (not merely defaults files), estimator origin,
attitude/rate signs, motor/servo outputs, throttle direction, and actual trim.
Record demanded versus estimated attitude, servo outputs, speed/height state,
mode heartbeat, X-Plane truth, gate events, and both backend and gate faults.
Run bounded straight flight, heading capture, altitude capture, climb/descent,
abort, and pilot takeover. Pass each maneuver only after measured capture and a
stable hold; an accepted MAVLink command or a normal process exit does not
count. Replay the September 17 trace separately: its 2,973.95 ft observation
must remain an envelope fault, and its diving entry condition must be refused
for ordinary transfer. Do not tune `GUIDED_P/I/D` by guesswork.

## 3. ArduPlane runway-to-runway

Approve aircraft-sourced takeoff/landing envelopes and surveyed departure and
arrival corridors before enabling either phase. Record true runway elevation,
verified home/origin, indicated-altimeter setting, MSL mission altitudes, and
measured AGL as separate values. Obtain human runway clearance; the script
must not issue its own ATC clearance. Confirm configuration, engine and ground
readiness, mission count/request/item/ACK, AUTO mode, current/reached items,
takeoff roll, climb, route and approach gates, touchdown, rollout speed, and
confirmed stop. Require an independently observed state at each phase, with a
deadline and explicit go-around or human abort. Run rejected upload/mode,
rejected takeoff, stale progress, unstable approach, go-around, missed touchdown,
and failed stop cases. A mission item reached alone is insufficient for a
landing claim. Expand to different loading/winds only after a reproducible
baseline sortie succeeds.

## 4. Garmin transfers and Test Pilot

First demonstrate ArduPlane-to-GFC 700 at stable altitude. Verify that the old
external writer and overrides are excluded before the Garmin servos engage.
Read lateral and vertical *active* modes as well as selected/armed modes, FD
mode, and servo state; a button send or FD-only display is insufficient.
Qualify virtual-pilot power and configuration ownership with measured response
before claiming AI Mission Pilot under Garmin. For GFC-to-ArduPlane, register a
**fresh** candidate session and managed SITL mapping; the prior plugin session
is retired on Garmin transfer and cannot safely be reused. Dynamic dataref
registration is tested only against a fake SDK and still needs live validation.
Measure bridge heartbeat and cancellation latency throughout the managed
restart, new MAVLink connection, mission reupload, current-item selection,
and AUTO observation. Require the old writer to be confirmed stopped, the
new writer to emit only private candidates, and a failed restart to leave no
native authority. A ground-stop claim requires independent confirmation in
addition to low groundspeed.
Only then consider a preplanned approach transfer with a specified readiness
floor and missed-approach branch. Do not add a late-flare transfer.

Run AI Test Pilot cards through the same authority boundary. Record reference
stability duration, card category, active loops, baseline, commanded and actual
axis deflection, sample times, aircraft/configuration hash, weight/CG evidence,
interventions, and measured recovery. Timeout or authority revocation during
excitation or recovery invalidates that point and stops progression. Report
software execution separately from aircraft performance acceptance.

## Release decision

Each stage needs signed traces and explicit pass/fail against its measured
criteria. Failures keep dependent capabilities disabled. The current code has
**no live release**: legacy launchers still require migration to the executive,
the plugin and candidate protocol need attended qualification, ArduPlane
runtime parameters/flight dynamics are unverified, and Garmin power plus
fresh-session return transfer are unqualified.
