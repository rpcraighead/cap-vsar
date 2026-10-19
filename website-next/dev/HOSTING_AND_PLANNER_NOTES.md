# Hosting and Flight Planner pages: what was read, evidence per claim, what is unverified

Pages: `website-next/site/hosting.html`, `website-next/site/flight-planner.html`. QA: `website-next/dev/qa/t45-hosting-planner-check.cjs` (83 checks, 375/768/905/1000/1280 px; results in `dev/screenshots/t45-qa.json`, screenshots `t45-*`).
Images added: `assets/img/planner-sar-dialog.webp` (1068x818, 36 KB), `assets/img/planner-weight-balance.webp` (988x1032, 38 KB). Both are crops of the planner's own dialogs run on a loopback port with example data (the server was stopped afterwards); no map, no address, no name. The hero image reuses the existing `planner-escon-square.webp`.

## Sources read
README.md, docker-compose.yml, services/exercise/Caddyfile, infra/ROUTER.md, docs/CONNECT.md, docs/LAB_HOSTED_DEPLOYMENT_PLAN.md, docs/WEB_HOSTING_AND_IDENTITY_PLAN.md, docs/CLOUD_RUN_COST_ESTIMATE.md, docs/USE_CASE_SAREX_REHEARSAL.md, docs/AM4_COMPAT.md, docs/mission-base-radio/README.md, docs/guide (sections 3, 5, 6, 8.3, appendix A), services/ai_pilot/README.md, xplane/PI_capvsar_df.py and PI_capvsar_flight_control.py (headers, station config, failure handling), exercise static JS (reconnect), CHANGELOG (2026-09-07, 2026-09-14, capacity entry), docs/BUG_TRACKER.md F-4, services/flightplanner (README, docs/USER_GUIDE.md, QUICKSTART, app.py routes and export-vsar, tests list), docs/SEARCH_PATTERN_CONVENTIONS.md, the sibling flight-planner-n499cp-v2 repo (git log, README).

## Hardware evidence (read-only)
- lscpu / free / nvidia-smi / lspci / ip link on 2026-10-19: 8-core 8-thread 9th-gen Core i7 (max 4.7 GHz), 30 GiB RAM, RTX 20-series 8 GB, NVMe, wired Ethernet only (no Wi-Fi interface), Linux. Page gives class level only. Observation not on the page: with no simulator running, ~8.4 GiB used and 7.4 of 8 GiB swap allocated (21 GiB "available"); this is stale-page swap, not proof of pressure, so it is not stated.
- X-Plane Log.txt: X-Plane 12.4.3, Vulkan, same CPU/GPU, so the simulator does run on this machine.
- Frame time: `frame_period_s` (sim/operation/misc/frame_rate_period) is recorded in the AI-pilot flight traces (`~/.cache/capvsar/ai-pilot/*.jsonl`, 210 files dated 2026-10-10..18, 405,695 positive samples). Median 13.09 ms, p95 22.49 ms, p99 34.78 ms, max 50.25 ms. Share slower than 60/45/30/20 fps: 17.9/5.3/1.05/0.09 percent. Caveats: graphics settings not recorded; whether Air Manager or web services were running not recorded; samples are per telemetry snapshot, not per frame; test flights at KSEE/KMYF/ESCON.
- Web stack idle (docker stats 2026-10-19): flightplanner 36 MiB, exercise 8 MiB, front door 17 MiB, mumble 7.5 MiB, CPU 0.00-0.07 percent. The four containers were running on this workstation's own Docker daemon (uptime 2 days). Earlier snapshot (CHANGELOG, 2026-09, lab server): exercise 39 MB, planner 59 MB, mumble 6 MB, CPU under 0.3 percent.
- 0.768 Mbit/s per received stream, 16 sessions default (= 8 dual-radio desks): LAB_HOSTED_DEPLOYMENT_PLAN section 8 and docs/mission-base-radio/README.md. An estimate, not measured.
- One X-Plane per aircraft station; Air Manager licence tied to hardware id; Air Player seats separate: CHANGELOG (capacity entry), docs/AM4_COMPAT.md. Two X-Plane instances on one machine: no document or test; page says "not tried here".

## Verdict as written
Probably yes for one aircraft plus browser seats; not demonstrated for the combination. The sizing paragraph and the "median >= 30 fps and slowest 1 percent above 20" rule are labelled as recommendation (mine, not from the repo).

## Other hosting claims and their evidence
- Front door 443, port 80 serves only the CA, 64738 TCP+UDP voice, board on its own port/opt-in profile, internal ports not published: docker-compose.yml, Caddyfile, infra/ROUTER.md.
- Plugin reports to the console over HTTPS using a station ini; keeps last scenario when the console is unreachable: PI_capvsar_df.py (truth_note "DF keeps its last scenario until it answers", `_transport_failure`).
- Browser reconnect 1 s doubling to 30 s, radio releases PTT/disables mic then rejoins, Form 110 log in sessionStorage, backfill since-endpoints: charts.js vsarConnect, mission-radio.js connectionLost/scheduleReconnect, mission-base-radio README, BUG_TRACKER F-4 (fixed). The "drop Wi-Fi for 30 s" acceptance test has no recorded real-network run.
- Google sign-in needs internet; badge-code fallback hides the Google button: guide section 5.1/5.3.
- Planner offline behaviour (weather marked simulated, still-air note, unknown terrain not sea level, cached FAA tiles): tests/test_honesty.py, USER_GUIDE section 4.1.
- Air Player LAN streaming: CHANGELOG 2026-09-07 (design/streaming architecture). Not verified across Wi-Fi here.
- Language model: the flying controllers have no model in the path (README "no voice or LLM dependency"; the AI Pilot page already says so). Legacy agent code points at a separate machine.
- Instructor-SET channel never offered on base radio: comms.html and mumble channel docs.

## Flight Planner claims
- History dates: sibling git log (first commit 2026-02-15 "built with Claude Sonnet 4.5"; 2026-03-16 terrain/diagrams/Cloud Run; 2026-07-05 map-first UI and guide); CHANGELOG 2026-09-07 (integration); monorepo `git log -- services/flightplanner` (2026-09-11 offline CAP 487, 09-13 L-15, 09-14 front door, 10-10 honesty fixes); sibling README "built in under 4 hours"; README "N499CP 172S profile has been removed". The page names no tail number, domain or squadron number.
- Features: app.py routes and USER_GUIDE. Push to V-SAR sends only scenario (alert centre, 5 NM radius, practice beacon offset 2.5 NM by default on a hash bearing) plus a broadcast message; it needs role "instructor" (app.py ~line 1362). **Discrepancy:** exercise guide section 6.2 says Push "sends the same pattern to the Mission Base map"; the code sends no waypoints and the console has no waypoint model, so the page follows the code.
- .fms: 97 pattern waypoints (guide and USER_GUIDE); USER_GUIDE says loading on the G1000 in a running X-Plane 12 was not checked; the exercise guide's "loads cleanly" is a goal statement, not evidence. Page uses the cautious version.
- Pattern geometry agreement: docs/SEARCH_PATTERN_CONVENTIONS.md (a few metres); exercise guide says within 25 m; page says "a few meters".
- W&B example: 1924 + 180 + 170 + 40 + 60 gal x 6 lb = 2674 lb, CG 39.07 in, within limits (computed by the planner).
- Mission Safety Officer row was dropped: the guide gives that role terrain duties but does not say they use the planner.

## Not verified
Whole-system load; Wi-Fi capacity; Air Player over Wi-Fi; Mumble/Air Player reconnect; two X-Plane instances; whether the exercise box would run the web stack natively without Docker for other devices' microphones (needs the HTTPS door); that the AI-pilot frame times were taken at exercise graphics settings; planner test counts (not re-run).

## Nav change needed on other pages
Two new links in the header and footer of every existing page, and an inline CSS rule because ten links overflow 901-1020 px. See the report to the orchestrator. The new pages already carry both.
