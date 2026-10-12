# AI pilot C172 qualification campaign — 2026-10-10

**Result: 20/20 scored flights passed**, including ten consecutive baseline
flights and all ten predeclared disturbed entries. Every flight ended with a
confirmed simulator pause and retired writer. This qualifies only the pinned
stock C172 establish/20° turn/recover scenario under the stated engineering
criteria. Production live-control gates remain closed.

Frozen source: `379fce3b73b0f83888060c1b5fd2904c2987e939` on
`feat/ai-pilot-first-cycle`. Every flight manifest reported a clean worktree,
the same source and installed bridge hashes, the same stock C172 ACF SHA-256
`b9c3c35c956ac5bee8c74fc9cbf933c6ecdfab73db9ad22862022aa3a20ab847`,
and scenery SHA-256
`49b5754d5da7fee87bcc198a6131c205f7bd10fd96364d074f66c9df706eb1f0`.
The campaign plan SHA-256 was
`74454d224deb86002eea03b1ac72f7af6944831ba7d7dde1ae017c90e29151d2`.
The ten baseline flights followed one another with no failures, tuning or code
changes. All twenty raw traces were independently replayed after the campaign.

The observer required ten continuous seconds within ±3° heading, ±75 ft
indicated altitude, ±3 KIAS, ±3° bank and ±150 fpm in each phase. Maximum
per-phase simulation deadlines were 120 seconds; all phases captured. Times
below are cumulative simulation seconds from the first scored snapshot.

| Entry | Establish | Turn capture | Recover | Max wall gap (s) | Score |
| --- | ---: | ---: | ---: | ---: | --- |
| baseline_01 | 20.5 | 41.3 | 62.4 | 0.125 | PASS |
| baseline_02 | 19.4 | 40.2 | 61.4 | 0.124 | PASS |
| baseline_03 | 19.4 | 40.2 | 61.4 | 0.129 | PASS |
| baseline_04 | 19.4 | 40.2 | 61.3 | 0.130 | PASS |
| baseline_05 | 19.3 | 40.0 | 61.2 | 0.135 | PASS |
| baseline_06 | 19.4 | 40.2 | 61.4 | 0.142 | PASS |
| baseline_07 | 19.4 | 40.1 | 61.2 | 0.124 | PASS |
| baseline_08 | 19.4 | 40.2 | 61.4 | 0.135 | PASS |
| baseline_09 | 19.4 | 40.1 | 61.3 | 0.123 | PASS |
| baseline_10 | 19.4 | 40.1 | 61.3 | 0.154 | PASS |
| heading_left | 19.3 | 40.1 | 61.2 | 0.133 | PASS |
| heading_right | 19.4 | 40.2 | 61.4 | 0.140 | PASS |
| low | 51.3 | 72.2 | 93.3 | 0.128 | PASS |
| high | 50.3 | 97.2 | 118.5 | 0.126 | PASS |
| slow | 20.3 | 41.1 | 62.2 | 0.124 | PASS |
| fast | 23.6 | 44.4 | 65.6 | 0.134 | PASS |
| left_high_slow | 48.5 | 69.2 | 95.7 | 0.134 | PASS |
| right_low_fast | 44.1 | 64.8 | 86.0 | 0.143 | PASS |
| left_low_fast | 43.6 | 64.4 | 85.5 | 0.143 | PASS |
| right_high_slow | 48.5 | 69.2 | 95.8 | 0.147 | PASS |

Across 16,150 scored snapshots, the maximum wall-time telemetry gap was
0.154 s, below the 0.5 s limit. No scored-flight interventions occurred.
Throttle reached its permitted limit on four of 16,130 command frames;
roll, pitch, yaw and trim reached no limits. The full machine-readable report
records per-phase maximum heading, altitude and speed errors, individual
saturation counts, interventions, and terminal ownership/pause states. The
largest recovery time was 118.474 simulation seconds (the high-entry run);
it remained within the per-phase deadlines.

The loss-of-updates fault probe passed: the atomic frame watchdog paused
X-Plane, released override and retired the writer. The explicit authenticated
takeover probe passed on the third attempt: it entered MANUAL, released
control, and rejected the retired writer's later command. Two earlier takeover
attempts failed during startup because an atomic frame expired before the
probe reached the takeover step. Their traces are retained. This is a startup
reliability issue to investigate before broader qualification; it does not
alter the completed 20-flight scored campaign. The physical-yoke takeover
path has not been implemented or tested.

A paused native bridge readback/rejection probe passed after X-Plane finished
loading; earlier probe attempts timed out during simulator startup and are
retained in the raw evidence directory. The simulator exited normally after
testing. Backed-up X-Plane preferences, stock C172 preferences, and scenery
configuration were restored and verified byte-for-byte. The six temporary
plugin/config files were removed from the active directory and archived under
`~/X-Plane 12/Output/capvsar-backups/ai-pilot-sol-20261010/`.

[Campaign ledger](ai_pilot_sol_campaign_20261010_ledger.json),
[full replay report](ai_pilot_sol_campaign_20261010_report.json), and
[fault-probe evidence](ai_pilot_sol_probes_20261010.json) contain hashes for
all raw records. Raw JSONL traces and trial stdout are under
`/home/ron/.cache/capvsar/ai-pilot/sol-campaign-20261010-a/`.
The paused native probe is under `/home/ron/.cache/capvsar/ai-pilot/`.

The next architecture step is separate: implement and qualify taxi, takeoff,
landing, stall/recovery and then the custom C182 with appropriate aircraft
limits. First resolve the activation timing issue and test physical takeover.
