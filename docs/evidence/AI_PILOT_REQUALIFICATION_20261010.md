# AI pilot: activation timing fix and requalification

2026-10-10. Branch `feat/ai-pilot-first-cycle`.

The qualification start now submits the initial complete frame, transfers
DIRECT ownership, and resumes X-Plane within one flight callback. It rejects
stale source snapshots and pauses/releases control if start fails after
activation. The flight runner also sends new measured frames more frequently,
while the bridge's 180 ms frame lease remains unchanged.

The first frozen campaign after the start change (B, commit `9e14409`) passed
19 of 20 entries. `right_high_slow` passed establish but stopped during the
turn when the atomic frame lease expired. The bridge paused, released override,
and retired the writer. Its independent score is FAIL. An isolated diagnostic
repeat of the same entry passed, but it does not count toward campaign B.

A second frozen campaign (C, commit `4cd9580`) included the shorter runner
poll interval and passed **all 20 entries**: ten consecutive baseline flights
followed by all ten predeclared disturbed entries. Every trace independently
replayed as PASS, every trial ended with confirmed pause, and there were no
scored-flight interventions. Across 26,897 scored snapshots, the maximum
wall-time telemetry gap was 0.121 s; throttle hit its permitted limit on four
of 26,877 command frames, while other actuator channels had no saturation.
The maximum cumulative phase capture times were 51.237 s (establish),
72.078 s (turn), and 103.587 s (recover). The full replay reports contain
per-flight capture times, tracking errors, gaps, saturation counts, and
terminal ownership states.

On C, the loss-of-updates probe and three separate explicit takeover probes
passed. In each case the bridge retired the old writer and safely released
control. A paused native bridge probe passed after X-Plane finished loading.
An earlier native attempt timed out during startup and is retained in raw
records. These takeover probes use the authenticated API; physical yoke input
is not yet verified. No physical joystick or yoke was attached to this machine
for that test.

All 20 C-flight manifests recorded a clean worktree, the same frozen source,
installed bridge, pinned stock C172, and stock-scenery hashes. The original
X-Plane preferences, C172 preferences, and scenery configuration were restored
and verified byte-for-byte after X-Plane exited. Both temporary plugin bundles
were removed from the active directory and archived under
`~/X-Plane 12/Output/capvsar-backups/ai-pilot-sol-requal-20261010/`.

Evidence: [campaign B ledger](ai_pilot_requal_20261010_b_campaign.json),
[B replay report](ai_pilot_requal_20261010_b_report.json),
[campaign C ledger](ai_pilot_requal_20261010_c_campaign.json),
[C replay report](ai_pilot_requal_20261010_c_report.json), and
[fault probe hashes](ai_pilot_requal_20261010_probes.json).
Raw traces and stdout are under
`~/.cache/capvsar/ai-pilot/sol-campaign-20261010-{b,c}/`.

This qualification covers the stock C172 establish/turn/recover maneuver only.
Landing, physical takeover, and the custom C182 require their own criteria and
simulator evidence. Production live-control gates remain closed.
