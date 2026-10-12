# CAP V-SAR bug tracker

**Generated from `docs/bugs/tracker.json` by `scripts/render_bug_tracker.py` — edit the JSON, not this file.**

Source analysis: [`PROJECT_REVIEW_2026-09-08.md`](PROJECT_REVIEW_2026-09-08.md). Opened 2026-09-08. 217 items, 38 open.

IDs are the review's finding IDs. Suffixed letters (X-8a) are sub-items split out because they are worked separately.

## Counts

| | critical | high | medium | low | total |
|---|---|---|---|---|---|
| by severity | 14 | 58 | 79 | 66 | 217 |

| P0 | P1 | P2 | P3 |
|---|---|---|---|
| 20 | 58 | 76 | 63 |

| Component | Items |
|---|---|
| Deployment / infrastructure | 69 |
| Flight planner | 31 |
| Exercise console (backend) | 30 |
| Air Manager instruments | 28 |
| Exercise console (frontend) | 27 |
| X-Plane plugin / engine | 21 |
| Docs / record | 11 |

## Priority definitions

- **P0** — Blocks an exercise from running, or corrupts training integrity (truth leak, wrong physics). Fix before the first rehearsal session.
- **P1** — Degrades an exercise in progress or loses data. Fix before the full-mission rehearsal.
- **P2** — Correctness, robustness or realism gap that a participant would notice but work around.
- **P3** — Cleanup, tooling, docs. No exercise impact.

## Waves

_Wave dates track the illustrative calendar in docs/USE_CASE_SAREX_REHEARSAL.md (T-14/T-7/T-2 before a 17 Oct 2026 SAREX). Re-anchor to the real exercise date._

- **Wave 0** (11 items) — Now — make the work safe to do at all.
- **Wave 1** (27 items) — Before session 1 (base stand-up). Nothing flies; base, planner and comms must work.
- **Wave 2** (46 items) — Before session 2 (full mission, three aircraft, injected effects).
- **Wave 3** (109 items) — Before session 3 (dress rehearsal) and the live SAREX.
- **Wave 4** (24 items) — After the SAREX — architecture, tooling, CalTopo phase 2.

## Clusters

A cluster is a PR-sized unit of work: items that touch the same files and should be fixed, reviewed and merged together. The owner hint matters because three agents share this tree.

| Cluster | Name | Items | Coordination |
|---|---|---|---|
| C1 | Repo & release hygiene | O-1, O-1a | maintainer — git remote and release |
| C2 | Truth integrity & roles | P-2, X-1, X-2 | DONE (X-1 fixed; X-2 awaits .env tokens, sequenced behind L-2 and O-2) |
| C3 | Propagation engine correctness | P-1, P-3, P-4, P-5, P-6, P-7, P-8, P-12, P-13, P-9 | DONE (all ten items fixed) - Claude, xplane/PI_capvsar_df.py |
| C4 | Station identity & onboarding kit | O-2, O-2a | Claude — O-2 station config and kit (plugin + scripts/) |
| C5 | Deployment bootstrap & voice provisioning | O-3, F-5, O-4, O-6, O-5, O-7a | Claude — deploy.sh, compose, ms01 (has ssh access) |
| C6 | Offline mission base | F-1, L-8 | DONE for the console (F-1); L-8 is the planner's own copy, Codex's file |
| C7 | Console robustness | X-3, X-4, X-5, X-7, X-6, X-8 | Codex holds main.py for F-4's since-endpoints; X-6/X-8 wait for it |
| C8 | Base view & debrief | F-2, F-3, F-6, F-8 | DONE (F-2, F-3) |
| C9 | Radio console hardening | F-4, F-7, F-9, X-9, F-10, F-11, F-12, F-13 | Codex — mission-radio.js/html and radio.py; F-9..F-13 queue behind F-4 |
| C10 | Flight planner correctness | L-1, L-3, L-4, L-1a, L-11, L-12, L-14, L-5, L-6, L-7, L-7a, L-9, L-13 | Codex — services/flightplanner/app.py |
| C11 | Flight planner security & dependencies | L-2, L-10 | Codex — same file as C10, sequenced after it |
| C12 | Instrument runtime | I-1, I-2, O-7b, I-10, I-3, I-4, I-5, I-6, I-11, I-14, I-12, I-13, I-15, I-17 | Gemini — instruments/** outright, including the DF heads |
| C13 | Instrument tooling & shared libs | I-8, I-9a, I-7, I-9c | Gemini — instrument tooling; I-9a Lua harness is its first task |
| C14 | Contract & documentation truth | D-1, D-2, D-3, D-4, D-5, P-10, I-9b | docs only, safe in parallel |
| C15 | Service boundaries (architecture) | AI-22, AI-11, AI-1, AI-10, AI-12, AI-13, AI-2, AI-21, AI-23, AI-24, AI-3, AI-5, AI-6, AI-8, AI-9, AI-14, AI-15, AI-16, AI-17, AI-20, AI-4, V2-8, AI-18, AI-19, C15-1, P-11, C15-2 | unassigned — after C2 and C7 settle |
| C16 | Project review 2026-10-10 (waves A-D) | X2-1, O2-3, X2-2, B2-1, F2-1, I2-1, I2-3, L2-1, L2-4, O2-1, O2-2, O2-4, X2-3, X2-4, L2-6, P2-2, X2-8, F2-2, L2-13, B2-2, B2-4, B2-5, B2-7, B2-9, F2-3, F2-4, F2-5, F2-6, F2-7, I2-2, I2-4, L2-2, L2-3, L2-5, O2-5, O2-6, O2-7, O2-8, P2-1, P2-3, X2-5, X2-6, X2-7, A-1, L2-14, B2-10, B2-11, B2-3, B2-6, B2-8, F2-10, F2-11, F2-12, F2-8, F2-9, I2-5, I2-6, I2-7, I2-8, I2-9, L2-10, L2-11, L2-7, L2-8, L2-9, O2-10, O2-11, O2-12, O2-9, P2-4, P2-5, P2-6, P2-7, P2-8, P2-9, X2-10, X2-11, X2-12, X2-9, L2-12, O2-13, X2-13 | Claude (Sonnet 5.5) from docs/PROJECT_REVIEW_2026-10-10.md and docs/DECISIONS_2026-10-10.md |
| C17 | UI walkthrough 2026-10-11 and UX proposal | AI-7, L-15, X-10, X-11, X-12, X-13, X-14, O-8, U-1, U-2, U-3, U-4 | Claude (Fable) from docs/UX_REVIEW_2026-10-11.md; proposal phases 1-3 and the CalTopo plan are not tracker rows until scheduled |
| C18 | C182T package review 2026-10-11 | A2-2, A2-1, A2-10, A2-11, A2-13, A2-3, A2-4, A2-5, A2-14, A2-6, A2-7, A2-8, A2-9 | Claude (Fable) from docs/C182T_REVIEW_2026-10-11.md; AI pilot port on feat/c182-ai-pilot-baseline |

## Board

### Wave 0 — Now — make the work safe to do at all.

| ID | Pri | Sev | Title | Component | Cluster | Effort | Depends on | Status |
|---|---|---|---|---|---|---|---|---|
| [AI-7](#ai-7) | P0 | critical | AI Pilot web deck binds 0.0.0.0:8088 with no auth and permissive CORS | infra | C17 | M | — | fixed |
| [L-15](#l-15) | P0 | critical | Flight planner is an unauthenticated confused deputy holding instructor credentials | planner | C17 | M | X-11 | fixed |
| [O-1](#o-1) | P0 | critical | Repo has no working git history | infra | C1 | S | — | fixed |
| [X-10](#x-10) | P0 | critical | Literal codes ADMIN and INSTRUCTOR mint an instructor session without the token | console-api | C17 | S | — | fixed |
| [X-11](#x-11) | P0 | critical | enforce() fails open and /api/auth/me reports instructor to anonymous callers | console-api | C17 | S | — | fixed |
| [X2-1](#x2-1) | P0 | critical | Live DF telemetry (bearing_true, distance_nm) broadcast to anonymous /api/state and /ws | console-api | C16 | M | — | fixed |
| [O2-3](#o2-3) | P0 | high | Blank Mumble password deploys an open voice net | infra | C16 | S | — | fixed |
| [X2-2](#x2-2) | P0 | high | A revealed old sortie reveals the beacon of the scenario being flown | console-api | C16 | M | — | fixed |
| [X-12](#x-12) | P1 | high | Session cookie lacks Secure, session id is returned to JavaScript, and a GET creates the session | console-api | C17 | S | O-8 | fixed |
| [X-13](#x-13) | P1 | high | Roster codes are guessable, sessions are stored unhashed, and roster regeneration does not revoke them | console-api | C17 | M | — | fixed |
| [X-14](#x-14) | P1 | high | POST /api/radio/ics mutates shared radio state with no authorization | console-api | C17 | S | X-11 | fixed |

### Wave 1 — Before session 1 (base stand-up). Nothing flies; base, planner and comms must work.

| ID | Pri | Sev | Title | Component | Cluster | Effort | Depends on | Status |
|---|---|---|---|---|---|---|---|---|
| [F-1](#f-1) | P0 | critical | Mission-base pages are blank without internet (Leaflet from CDN) | console-ui | C6 | S | — | fixed |
| [O-2](#o-2) | P0 | critical | Plugin hardcodes console address and callsign — multi-aircraft not deployable | plugin | C4 | L | P-2 | fixed |
| [O-3](#o-3) | P0 | critical | Fresh deploy crash-loops; repo is not the deployment | infra | C5 | M | — | fixed |
| [P-1](#p-1) | P0 | critical | Terrain line-of-sight ray is mirrored | plugin | C3 | S | — | fixed |
| [P-2](#p-2) | P0 | critical | Plugin can never receive beacon truth, so the in-sim DF is deaf | plugin | C2 | M | X-1 | fixed |
| [X-1](#x-1) | P0 | critical | Beacon truth leaks through three unauthenticated endpoints | console-api | C2 | M | — | fixed |
| [X-2](#x-2) | P0 | critical | No authentication or role separation on any console endpoint | console-api | C2 | L | — | fixed |
| [F-5](#f-5) | P0 | high | Radio console setup path (verified working) | infra | C5 | S | O-3 | resolved |
| [L-1](#l-1) | P0 | high | X-Plane .fms export is malformed | planner | C10 | M | — | fixed |
| [B2-1](#b2-1) | P1 | high | Builder deleted the installed aircraft before building | infra | C16 | M | — | fixed |
| [F2-1](#f2-1) | P1 | high | Flight Planner link rewritten to unpublished port 8090 | console-ui | C16 | S | — | fixed |
| [I2-1](#i2-1) | P1 | high | GMA clearance recorder subscribes to nonexistent datarefs | instruments | C16 | S | — | fixed |
| [I2-3](#i2-3) | P1 | high | dial_add press callbacks are not an Air Manager 4.2 feature | instruments | C16 | M | — | fixed |
| [L2-1](#l2-1) | P1 | high | Unresolvable datum silently plans at a hard-coded point | planner | C16 | S | — | fixed |
| [L2-4](#l2-4) | P1 | high | Terrain profile reports 0 ft and ADEQUATE when USGS is unreachable | planner | C16 | S | — | fixed |
| [O-8](#o-8) | P1 | high | No single front door: Caddy fronts one backend and is bypassable on the LAN | infra | C17 | M | X-11, X-12 | fixed |
| [O2-1](#o2-1) | P1 | high | Two console route tests fail on FastAPI 0.143 | infra | C16 | S | — | fixed |
| [O2-2](#o2-2) | P1 | high | No reproducible test environment; planner and board suites not run | infra | C16 | M | — | fixed |
| [O2-4](#o2-4) | P1 | high | CAPVSAR_ENV never set so the production guard is inert | infra | C16 | S | — | fixed |
| [U-1](#u-1) | P1 | high | Planner SAR pattern generator cannot be opened (modal nested inside the hidden DB modal) | planner | C17 | S | — | fixed |
| [U-2](#u-2) | P1 | high | Setup QR badges never render (vendored QR library has a truncated Reed-Solomon table) | console-ui | C17 | M | — | fixed |
| [X2-3](#x2-3) | P1 | high | ScenarioIn.effects accepts NaN and unknown keys; one scenario breaks every client | console-api | C16 | S | — | fixed |
| [X2-4](#x2-4) | P1 | high | Radio stream and pages fail open on a roster-only console | console-api | C16 | S | — | fixed |
| [L2-6](#l2-6) | P1 | medium | Console push anchors the alert and beacon offset on waypoints[0] | planner | C16 | S | — | fixed |
| [O-2a](#o-2a) | P1 | medium | Participant CONNECT.md cited by the as-built does not exist | docs | C4 | S | O-2 | resolved |
| [P2-2](#p2-2) | P1 | medium | Per-beacon state not reset when the scenario changes under a running sortie | plugin | C16 | S | — | fixed |
| [X2-8](#x2-8) | P1 | medium | Scenario notes are not truth-filtered and the seed notes name the beacon | console-api | C16 | S | — | fixed |

### Wave 2 — Before session 2 (full mission, three aircraft, injected effects).

| ID | Pri | Sev | Title | Component | Cluster | Effort | Depends on | Status |
|---|---|---|---|---|---|---|---|---|
| [F-2](#f-2) | P1 | high | Base view keeps the previous sortie's alert circle and tracks | console-ui | C8 | S | — | fixed |
| [F-3](#f-3) | P1 | high | Debrief conflates all aircraft into one track | console-ui | C8 | M | — | fixed |
| [F-4](#f-4) | P1 | high | Radio console does not rejoin after a network blip | console-ui | C9 | M | — | fixed |
| [F2-2](#f2-2) | P1 | high | Airband timeouts tear down the tactical radio | console-ui | C16 | S | — | fixed |
| [I-1](#i-1) | P1 | high | DF faceplates repaint ~8 Hz regardless of change | instruments | C12 | M | — | fixed |
| [I-2](#i-2) | P1 | high | pcall around canvas_draw hides real errors | instruments | C12 | S | — | fixed |
| [L-2](#l-2) | P1 | high | Unauthenticated scenario push and CSRF-able database wipe | planner | C11 | M | X-2 | fixed |
| [L-3](#l-3) | P1 | high | Parallel-track generator can be driven into a 100M-iteration loop | planner | C10 | S | — | fixed |
| [L-4](#l-4) | P1 | high | Both gunicorn workers race to rebuild the aviation database | planner | C10 | S | — | fixed |
| [L2-13](#l2-13) | P1 | high | Planner, G1000 library and grid tool disagree on search-pattern conventions | planner | C16 | L | — | fixed |
| [O-4](#o-4) | P1 | high | Mumble channel tree exists only as hand-made rows in a runtime volume | infra | C5 | M | O-3 | fixed |
| [O-6](#o-6) | P1 | high | No backup, monitoring or pre-exercise smoke check | infra | C5 | M | O-3 | fixed |
| [O-7b](#o-7b) | P1 | high | G1000 MFD video stream never re-arms after a reconnect | instruments | C12 | M | — | open |
| [P-3](#p-3) | P1 | high | Scan mode destroys TIMEHOLD on 406 | plugin | C3 | S | — | fixed |
| [P-4](#p-4) | P1 | high | Radio horizon is one-sided | plugin | C3 | S | — | fixed |
| [P-5](#p-5) | P1 | high | Plugin disable/enable cycle kills the console link permanently | plugin | C3 | S | — | fixed |
| [X-3](#x-3) | P1 | high | SQLite writes block the event loop that carries radio audio | console-api | C7 | M | — | fixed |
| [X-4](#x-4) | P1 | high | Console restart mid-exercise orphans the sortie | console-api | C7 | M | — | fixed |
| [X-5](#x-5) | P1 | high | One wedged WebSocket client stalls every broadcast | console-api | C7 | S | — | fixed |
| [I-10](#i-10) | P1 | medium | TDFM-136B has no transmitter time-out timer | instruments | C12 | M | — | fixed |
| [X-7](#x-7) | P1 | medium | Sortie lifecycle leaks state between exercises | console-api | C7 | M | — | fixed |
| [B2-2](#b2-2) | P2 | medium | Builder and fetcher donor paths differ | infra | C16 | S | — | fixed |
| [B2-4](#b2-4) | P2 | medium | ACF patch application reported but not enforced | infra | C16 | S | — | fixed |
| [B2-5](#b2-5) | P2 | medium | Prop-lever TRIS offsets hard-coded without validation | infra | C16 | M | — | fixed |
| [B2-7](#b2-7) | P2 | medium | generate_manual.py hard-codes another checkout and bakes /home/ron paths into tracked HTML | docs | C16 | S | — | fixed |
| [B2-9](#b2-9) | P2 | medium | Docs site republishes manufacturer manuals | docs | C16 | S | — | fixed |
| [F2-3](#f2-3) | P2 | medium | Form 110 table rebuilt under the MRO's cursor | console-ui | C16 | S | — | fixed |
| [F2-4](#f2-4) | P2 | medium | Form 110 log lives only in page memory | console-ui | C16 | S | — | fixed |
| [F2-5](#f2-5) | P2 | medium | Shared role token stored in localStorage and solicited by prompt() | console-ui | C16 | S | — | fixed |
| [F2-6](#f2-6) | P2 | medium | Open redirect on the login page | console-ui | C16 | S | — | fixed |
| [F2-7](#f2-7) | P2 | medium | Debrief breaks after a sortie with no positions; no fetch error handling | console-ui | C16 | S | — | fixed |
| [I2-2](#i2-2) | P2 | medium | TDFM copilot-PTT dataref does not exist | instruments | C16 | S | — | fixed |
| [I2-4](#i2-4) | P2 | medium | DF audio restarts the noise loop on every update | instruments | C16 | S | — | fixed |
| [L-1a](#l-1a) | P2 | medium | Search-pattern labels are lost in the FMS export | planner | C10 | S | L-1 | fixed |
| [L2-2](#l2-2) | P2 | medium | FMS export has no waypoint cap | planner | C16 | S | — | fixed |
| [L2-3](#l2-3) | P2 | medium | Five endpoints still return Werkzeug HTML 500 on bad input | planner | C16 | M | — | fixed |
| [L2-5](#l2-5) | P2 | medium | Nav log plans on invented winds offline | planner | C16 | S | — | fixed |
| [O2-5](#o2-5) | P2 | medium | deploy.sh does not know the board service | infra | C16 | M | — | fixed |
| [O2-6](#o2-6) | P2 | medium | Board healthcheck cannot fail | infra | C16 | S | — | fixed |
| [O2-7](#o2-7) | P2 | medium | Runtime state lives inside the git checkout | infra | C16 | M | — | fixed |
| [O2-8](#o2-8) | P2 | medium | Backups have no restore path | infra | C16 | M | — | fixed |
| [P2-1](#p2-1) | P2 | medium | Plugin disable/enable leaks a network thread | plugin | C16 | S | — | fixed |
| [P2-3](#p2-3) | P2 | medium | Default console URL unreachable and transport failures never logged | plugin | C16 | S | — | fixed |
| [X2-5](#x2-5) | P2 | medium | Blocking SQLite auth lookups on the event loop | console-api | C16 | S | — | fixed |
| [X2-6](#x2-6) | P2 | medium | init_auth_db() runs a write transaction on every authenticated request | console-api | C16 | M | — | fixed |
| [X2-7](#x2-7) | P2 | medium | Shared-radio watchdog belongs to the first face; one slow face fails the whole radio | console-api | C16 | M | — | fixed |

### Wave 3 — Before session 3 (dress rehearsal) and the live SAREX.

| ID | Pri | Sev | Title | Component | Cluster | Effort | Depends on | Status |
|---|---|---|---|---|---|---|---|---|
| [AI-22](#ai-22) | P0 | critical | fly_arduplane_backend: a refused gate.acquire() left SITL flying the aircraft | infra | C15 | S | AI-21 | fixed |
| [A-1](#a-1) | P0 | high | CAP 487 retains the stock C172S airframe geometry and exterior | infra | C16 | L | — | open |
| [AI-11](#ai-11) | P0 | high | FDR records defaults as data and the live deck never subscribes a dataref (V2-7, red team RT-3) | infra | C15 | M | — | fixed |
| [A2-2](#a2-2) | P1 | high | Physics propeller is the C172 76-inch geometry; visual prop is 79 in | infra | C18 | S | — | open |
| [AI-1](#ai-1) | P1 | high | Legacy AI pilot entrypoints bypass maneuver validation | infra | C15 | M | — | fixed |
| [AI-10](#ai-10) | P1 | high | Controller and live deck silently share UDP receive port 49005 (V2-6, red team RT-2) | infra | C15 | M | — | open |
| [AI-12](#ai-12) | P1 | high | Direct backend: no human-input arbitration, and its own fault path never pauses (D-3, red team RT-4) | infra | C15 | M | — | open |
| [AI-13](#ai-13) | P1 | high | fly_card_h0.py flies the yoke with no gate, no lease, no lock and no pause (red team RT-5) | infra | C15 | M | — | open |
| [AI-2](#ai-2) | P1 | high | Complete live CAP 487 maneuver-controller acceptance | infra | C15 | M | AI-1 | open |
| [AI-21](#ai-21) | P1 | high | ArduPlane backend: release-to-MANUAL and the SITL attach window are unsafe per the Plane-4.7.1 source | infra | C15 | M | — | fixed |
| [AI-23](#ai-23) | P1 | high | ArduPlane boots into RTL with a default Home 8000 miles away and banks hard on attach | infra | C15 | M | AI-21 | fixed |
| [AI-24](#ai-24) | P1 | high | ArduPlane ACKs GUIDED_CHANGE_HEADING/ALTITUDE then ignores them and keeps loitering | infra | C15 | M | AI-23 | open |
| [AI-3](#ai-3) | P1 | high | Live RREF comma header discarded by AI pilot receiver | infra | C15 | S | — | fixed |
| [AI-5](#ai-5) | P1 | high | Live altitude selection does not establish commanded climb | infra | C15 | M | — | fixed |
| [AI-6](#ai-6) | P1 | high | Controller shutdown pause request does not pause live X-Plane | infra | C15 | M | — | fixed |
| [AI-8](#ai-8) | P1 | high | Complete full-sortie ArduPlane and FAA-grounded taxi control | infra | C15 | L | AI-1 | open |
| [AI-9](#ai-9) | P1 | high | UDP receiver accepts telemetry from any sender (red team RT-1) | infra | C15 | M | — | open |
| [O-5](#o-5) | P1 | high | Mumble server has no per-role ACLs and images float | infra | C5 | M | X-2, O-4 | fixed |
| [O-7a](#o-7a) | P1 | high | Air Manager seat count for three MO stations unconfirmed | infra | C5 | S | — | resolved |
| [A2-1](#a2-1) | P2 | medium | C182T ACF still has four cylinders | infra | C18 | S | — | open |
| [A2-10](#a2-10) | P2 | medium | No test pins the built ACF to the dimension master | infra | C18 | M | — | open |
| [A2-11](#a2-11) | P2 | medium | Calibration order: propeller and gear before the fuselage-Cd experiment | infra | C18 | M | A2-2, A2-3 | open |
| [A2-13](#a2-13) | P2 | medium | AI pilot: finish the C182T profile port (runner flag, bridge identity, taxi constants) | infra | C18 | M | — | open |
| [A2-3](#a2-3) | P2 | medium | Gear physics track 8.2 ft while the mesh was corrected to 9 ft | infra | C18 | M | — | open |
| [A2-4](#a2-4) | P2 | medium | Full-throttle power 214 HP vs 230 rated is unexplained | infra | C18 | M | A2-2 | open |
| [A2-5](#a2-5) | P2 | medium | Aircraft default paint shows N429CP while the ACF and ATC say CAP 487 | infra | C18 | S | — | open |
| [AI-14](#ai-14) | P2 | medium | ManeuverGate has no liveness coupling to its monitor (D-3, red team RT-6) | infra | C15 | M | — | open |
| [AI-15](#ai-15) | P2 | medium | Any local process can acquire or revoke aircraft control with no credential (red team RT-7) | infra | C15 | M | — | open |
| [AI-16](#ai-16) | P2 | medium | Taxi coordinator launders an unauthorized departure and lets a clarification hold skip return-to-start (red team RT-8) | infra | C15 | S | AI-8 | open |
| [AI-17](#ai-17) | P2 | medium | Stale skill file asserts PIC authority and four retired mutation tools; README count stale (red team RT-9, RT-12) | infra | C15 | S | — | open |
| [AI-20](#ai-20) | P2 | medium | ArduPlane backend bounded SITL trial (CONOPS gate G) | infra | C15 | M | AI-2 | open |
| [AI-4](#ai-4) | P2 | medium | Installed exercise aircraft predates CAP 487 identity and has prop lever load error | infra | C15 | M | — | fixed |
| [D-1](#d-1) | P2 | medium | CHANGELOG entries contradict the code they describe | docs | C14 | S | — | fixed |
| [D-2](#d-2) | P2 | medium | README and website contradict the code | docs | C14 | M | — | fixed |
| [D-3](#d-3) | P2 | medium | CONOPS and referenced infra docs are missing from the repo | docs | C14 | S | — | resolved |
| [D-4](#d-4) | P2 | medium | No LICENSE despite deriving from Laminar assets | docs | C14 | S | O-1 | fixed |
| [D-5](#d-5) | P2 | medium | Manufacturer artwork is still redistributed, as figure extracts and in git history | docs | C14 | M | D-4 | open |
| [F-6](#f-6) | P2 | medium | Unescaped server strings in four views (HTML injection) | console-ui | C8 | S | — | fixed |
| [F-7](#f-7) | P2 | medium | Legacy console: precedence bug and autoplay-blocked audio | console-ui | C9 | S | — | fixed |
| [F-8](#f-8) | P2 | medium | No bearing intersection maths despite the README | console-ui | C8 | M | — | fixed |
| [F-9](#f-9) | P2 | medium | New radio console has no Form 110 log | console-ui | C9 | M | — | fixed |
| [I-3](#i-3) | P2 | medium | Becker tone suppression bleeds across bands | instruments | C12 | S | — | fixed |
| [I-4](#i-4) | P2 | medium | Stored 406 frame falls through to live data | instruments | C12 | S | — | fixed |
| [I-5](#i-5) | P2 | medium | RT-600 long-press timers survive power-off | instruments | C12 | S | — | fixed |
| [I-6](#i-6) | P2 | medium | DF heads and TDFM ignore the electrical bus | instruments | C12 | M | — | fixed |
| [L-11](#l-11) | P2 | medium | Unknown departure/destination silently becomes a waypoint position | planner | C10 | S | — | fixed |
| [L-12](#l-12) | P2 | medium | Flight planner database is a file bind-mount, so SQLite journals escape it | planner | C10 | S | — | fixed |
| [L-14](#l-14) | P2 | medium | Planner suite fails: cruise and runway tests assume the retired 172S table | planner | C10 | S | L-7 | fixed |
| [L-5](#l-5) | P2 | medium | Search patterns leave uncovered ground and truncate silently | planner | C10 | M | — | fixed |
| [L-6](#l-6) | P2 | medium | Performance tables extrapolate silently and ignore tailwind | planner | C10 | M | — | fixed |
| [L-7](#l-7) | P2 | medium | Flight planner plans a different aircraft than the exercise flies | planner | C10 | M | — | fixed |
| [L-7a](#l-7a) | P2 | medium | Align simulator loading baseline with selected 182T POH sample | infra | C10 | M | L-7 | resolved |
| [L-8](#l-8) | P2 | medium | Planner has no offline map path | planner | C6 | M | F-1 | fixed |
| [L-9](#l-9) | P2 | medium | API returns HTML 500s and misreports push status | planner | C10 | M | — | fixed |
| [L2-14](#l2-14) | P2 | medium | FMS waypoint limit and the G1000 display of exported .fms unverified in a running X-Plane 12 | planner | C16 | S | — | open |
| [P-6](#p-6) | P2 | medium | 121.5 beacons produce a COSPAS-SARSAT decode | plugin | C3 | S | — | fixed |
| [P-7](#p-7) | P2 | medium | Signal bar stays lit between 406 bursts | plugin | C3 | S | — | fixed |
| [P-8](#p-8) | P2 | medium | Terrain masking is only -12 dB | plugin | C3 | S | P-1 | fixed |
| [V2-8](#v2-8) | P2 | medium | set_air_start.py does not zero body rates, so a recovered aircraft re-departs | infra | C15 | S | — | open |
| [X-6](#x-6) | P2 | medium | Untyped request bodies mutate scenario definitions | console-api | C7 | M | — | fixed |
| [X-8](#x-8) | P2 | medium | Console operational hygiene: retention, logging, health, shutdown, root | console-api | C7 | M | — | fixed |
| [X-9](#x-9) | P2 | medium | One Mumble client per browser socket, 16 max | console-api | C9 | M | — | fixed |
| [F-10](#f-10) | P2 | low | Mission base cannot monitor the airband SAR net | console-ui | C9 | L | — | fixed |
| [I-11](#i-11) | P2 | low | TDFM memory table is 6 generic channels, not a CAP fleet plan | instruments | C12 | M | — | fixed |
| [I-14](#i-14) | P2 | low | GMA 1347 ICS isolation and Split COM are lamp-only | instruments | C12 | L | — | fixed |
| [A2-14](#a2-14) | P3 | low | C182T document index | infra | C18 | S | — | open |
| [A2-6](#a2-6) | P3 | low | Package ships the C172 POM, G430/G530 and S-TEC manuals | infra | C18 | S | — | open |
| [A2-7](#a2-7) | P3 | low | c182t_checklists.py says full flaps are 30 deg | infra | C18 | S | — | open |
| [A2-8](#a2-8) | P3 | low | acf/_Va_kts is 0 | infra | C18 | S | — | open |
| [A2-9](#a2-9) | P3 | low | Builder hard-codes /home/ron paths | infra | C18 | S | — | open |
| [AI-18](#ai-18) | P3 | low | SIGTERM skips every shutdown safeguard (red team RT-11) | infra | C15 | S | — | open |
| [AI-19](#ai-19) | P3 | low | Advisory chat's no-action guard is a keyword list with no output filter (red team RT-13) | infra | C15 | S | — | open |
| [B2-10](#b2-10) | P3 | low | Tracked fig_c182t_aircraft.png is a render of Laminar's C172 model | docs | C16 | S | — | open |
| [B2-11](#b2-11) | P3 | low | c182t_corrections radial scale ignores the JSON axis | infra | C16 | S | — | fixed |
| [B2-3](#b2-3) | P3 | low | Selection icon renders the literal text &bull; | infra | C16 | S | — | fixed |
| [B2-6](#b2-6) | P3 | low | Flap animation range disagrees with patched travel | infra | C16 | S | — | fixed |
| [B2-8](#b2-8) | P3 | low | Doc generators' dependencies undeclared | docs | C16 | S | — | fixed |
| [F-11](#f-11) | P3 | low | No operational sidetone on the new radio console | console-ui | C9 | S | — | fixed |
| [F2-10](#f2-10) | P3 | low | Setup 'Target Exercise Scenario' control is decorative | console-ui | C16 | S | — | fixed |
| [F2-11](#f2-11) | P3 | low | One malformed control frame permanently drops the radio | console-ui | C16 | S | — | fixed |
| [F2-12](#f2-12) | P3 | low | Legacy radio: spacebar PTT keys from focused controls; failed POST logged as sent | console-ui | C16 | S | — | fixed |
| [F2-8](#f2-8) | P3 | low | Hard-coded host on the headset help page | console-ui | C16 | S | — | fixed |
| [F2-9](#f2-9) | P3 | low | Every bearing-log failure reads 'callsign not reporting'; reads ignore errors | console-ui | C16 | S | — | fixed |
| [I2-5](#i2-5) | P3 | low | LS and BURST timers read 00:00 before any signal | instruments | C16 | S | — | fixed |
| [I2-6](#i2-6) | P3 | low | Becker STORE tone suppression survives a power cycle | instruments | C16 | S | — | fixed |
| [I2-7](#i2-7) | P3 | low | Master switch and CB panel never publish on load | instruments | C16 | S | — | fixed |
| [I2-8](#i2-8) | P3 | low | G1000 watchdog stacks video nodes and hides its banner | instruments | C16 | M | — | fixed |
| [I2-9](#i2-9) | P3 | low | TDFM squelch-defeat push sets st.squelch_defeat but nothing reads it | instruments | C16 | S | — | open |
| [L2-10](#l2-10) | P3 | low | Internet tile fallbacks bypass the offline cache | planner | C16 | S | — | fixed |
| [L2-11](#l2-11) | P3 | low | get_climb snaps both ends to the nearest row | planner | C16 | S | — | fixed |
| [L2-7](#l2-7) | P3 | low | Apply to Route drops DATUM and relabels the pattern | planner | C16 | S | — | fixed |
| [L2-8](#l2-8) | P3 | low | CS01 carries a fictitious leg | planner | C16 | S | — | fixed |
| [L2-9](#l2-9) | P3 | low | d-TPP cycle computed from the calendar month | planner | C16 | S | — | fixed |
| [O2-10](#o2-10) | P3 | low | Planner port 8090 in preflight, deploy and docs | infra | C16 | S | — | fixed |
| [O2-11](#o2-11) | P3 | low | .ci-out/ not gitignored | infra | C16 | S | — | fixed |
| [O2-12](#o2-12) | P3 | low | scripts/wg-peer.sh drives a removed WireGuard container | infra | C16 | S | — | fixed |
| [O2-9](#o2-9) | P3 | low | pymumble pinned by commit tarball without a hash | infra | C16 | S | — | fixed |
| [P2-4](#p2-4) | P3 | low | compute() re-reads self.scn mid-tick | plugin | C16 | S | — | fixed |
| [P2-5](#p2-5) | P3 | low | Radio horizon uses MSL heights | plugin | C16 | S | — | fixed |
| [P2-6](#p2-6) | P3 | low | Wall clock, no pause awareness | plugin | C16 | S | — | fixed |
| [P2-7](#p2-7) | P3 | low | fetch_scenario comment promises an unimplemented fallback | plugin | C16 | S | — | fixed |
| [P2-8](#p2-8) | P3 | low | self.net not initialised | plugin | C16 | S | — | fixed |
| [P2-9](#p2-9) | P3 | low | Pause freezing and TLS trust of the plugin unverified in X-Plane | plugin | C16 | S | — | open |
| [U-3](#u-3) | P3 | low | Instructor console prints BRG NaN when the DF dictionary is redacted | console-ui | C17 | S | — | fixed |
| [U-4](#u-4) | P3 | low | Setup page says codes are 6 characters; they are 40 | console-ui | C17 | S | — | fixed |
| [X2-10](#x2-10) | P3 | low | Role tokens accepted as ?token= and logged in access logs | console-api | C16 | S | — | fixed |
| [X2-11](#x2-11) | P3 | low | Deleting a scenario with a running sortie strands it | console-api | C16 | S | — | fixed |
| [X2-12](#x2-12) | P3 | low | /api/setup accepts untyped fields and mints arbitrary roles | console-api | C16 | S | — | fixed |
| [X2-9](#x2-9) | P3 | low | Concurrent sortie start/stop races; stop re-stamps | console-api | C16 | S | — | fixed |

### Wave 4 — After the SAREX — architecture, tooling, CalTopo phase 2.

| ID | Pri | Sev | Title | Component | Cluster | Effort | Depends on | Status |
|---|---|---|---|---|---|---|---|---|
| [C15-1](#c15-1) | P2 | medium | Split the console into store + routers with role middleware | console-api | C15 | L | X-1, X-2, X-3 | fixed |
| [I-8](#i-8) | P2 | medium | Panel registrar writes Air Manager's database on hardcoded assumptions | instruments | C13 | M | O-2 | fixed |
| [I-9a](#i-9a) | P2 | medium | No Lua execution harness in the repo | instruments | C13 | M | — | fixed |
| [P-10](#p-10) | P2 | medium | DATAREF_CONTRACT.md does not match what the plugin publishes | docs | C14 | M | — | fixed |
| [P-11](#p-11) | P2 | medium | Server fallback propagation diverges from the plugin | console-api | C15 | M | — | fixed |
| [C15-2](#c15-2) | P3 | low | Consolidate five geodesy implementations | console-api | C15 | M | — | fixed |
| [F-12](#f-12) | P3 | low | APX/EFJ control-head keys are artwork only | console-ui | C9 | M | — | fixed |
| [F-13](#f-13) | P3 | low | Net names are generic, not CAP nomenclature | console-ui | C9 | S | — | resolved |
| [I-12](#i-12) | P3 | low | TDFM Guard is not an independent receiver | instruments | C12 | M | — | fixed |
| [I-13](#i-13) | P3 | low | TDFM scan is a cosmetic flag | instruments | C12 | S | — | fixed |
| [I-15](#i-15) | P3 | low | GMA 1347 clearance recorder records nothing | instruments | C12 | M | — | fixed |
| [I-17](#i-17) | P3 | low | DF audio has no signal-to-noise degradation | instruments | C12 | M | — | fixed |
| [I-7](#i-7) | P3 | low | Shared instrument libraries are copy-pasted | instruments | C13 | M | — | fixed |
| [I-9b](#i-9b) | P3 | low | cap_fm_* variables have no producer and no contract | instruments | C14 | S | — | fixed |
| [I-9c](#i-9c) | P3 | low | Deploy coverage and manifest claims are wrong | instruments | C13 | S | — | fixed |
| [L-10](#l-10) | P3 | low | Planner dependency and container hygiene | planner | C11 | M | — | fixed |
| [L-13](#l-13) | P3 | low | Planner direct-handler tests fail with real Flask installed | planner | C10 | S | — | fixed |
| [L2-12](#l2-12) | P3 | low | Export rate limiter is per-process | planner | C16 | S | — | open |
| [O-1a](#o-1a) | P3 | low | Generated handbook committed deliberately | infra | C1 | S | O-1 | resolved |
| [O2-13](#o2-13) | P3 | low | Dockerfile base images not pinned by digest | infra | C16 | S | — | open |
| [P-12](#p-12) | P3 | low | Plugin reporting cadence and heading source are off | plugin | C3 | S | — | fixed |
| [P-13](#p-13) | P3 | low | Signal model has no dB calibration and multipath is scripted | plugin | C3 | L | P-1 | fixed |
| [P-9](#p-9) | P3 | low | Fixed 24 terrain probes, no earth curvature | plugin | C3 | M | P-1 | fixed |
| [X2-13](#x2-13) | P3 | low | ICS pilot/observer seats share a callsign so the first joiner's seat decides for a shared radio | console-api | C16 | M | — | open |

## Detail

### AI-7

**AI Pilot web deck binds 0.0.0.0:8088 with no auth and permissive CORS**

`P0` · `critical` · `bug` · Deployment / infrastructure · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort M · wave 0 · **fixed**

- **Files:** `services/ai_pilot/static/board.html:558-566`, `services/ai_pilot/web_server.py:156-199`, `services/ai_pilot/web_server.py:388-389`, `services/ai_pilot/web_server.py:406`, `services/ai_pilot/web_server.py:58-68`, `services/ai_pilot/web_server.py:65`, `services/ai_pilot/web_server.py:70-87`, `services/ai_pilot/web_server.py:90-96`
- **Problem:** web_server.py binds 0.0.0.0:8088 by default with no authentication on any route, and returns Access-Control-Allow-Origin: * on every JSON response with a matching permissive do_OPTIONS. Any website loaded in any browser on the network can therefore read and drive it cross-origin. The mutating endpoints are consequential: POST /api/board/raw overwrites docs/BOARD.md wholesale, /api/board/task and /api/board/toggle rewrite the agent dispatch queue that Claude, Codex and Gemini execute from, /api/chat drives the LLM agent, and /api/fdr/start|stop|analyze control the flight data recorder. This is an ENGINEERING surface, not a participant one, and it is a different trust domain from the exercise console: it should not be placed behind the participant portal. It is also not containerized and not in docker-compose, so deploy-time hardening does not reach it. maneuver_server.py on 127.0.0.1:8089 is bound to loopback, which is its only real control; it has an Origin and content-type check plus a lease gate, but no identity. Sources: docs/WEB_HOSTING_AND_IDENTITY_PLAN.md section 2 (2026-09-09) and a five-service auth audit on 2026-09-13. Verified present in the working tree at commit 6690d35. SEPARATELY OBSERVED 2026-09-13: the same two response paths send no cache headers at all and reply HTTP/1.0 - _send_json() (web_server.py:58-68) and _send_file() (web_server.py:70-87) set no Cache-Control, ETag or Last-Modified. With nothing telling it otherwise a browser may serve /api/board from cache heuristically, so the board UI can show stale data and the Refresh Board button appears to do nothing. This was reproduced against a live board tab where the disk, the API and the served page all agreed at 9 tasks. The failure is silent in both directions because fetchBoard() (static/board.html:558-566) swallows a failed fetch into console.error and returns, leaving the last-rendered board on screen with no indication it has stopped updating - the UI cannot distinguish 'nothing changed' from 'I am showing you a cached or failed answer'.
- **Fix:** Bind 127.0.0.1 by default and require an explicit flag to expose it. Replace ACAO:* with an exact allowlist. Require a locally configured credential on all mutating routes, especially /api/board/raw. Keep the deck on the management/WireGuard path rather than the participant front door. Note access.py cannot be reused as-is: it is FastAPI-coupled and reads the exercise SQLite database, while this is a stdlib http.server. ALSO IN SCOPE (same functions, one edit): send Cache-Control: no-store on every /api/* response from _send_json(), and appropriate caching headers from _send_file(); and give the board UI a visible staleness indicator - surface a failed or stale fetch in the page (last-updated timestamp plus an explicit error state) rather than only console.error. Fixed 2026-09-13 (4fec7b4). Loopback default with explicit --expose, exact origin allowlist, bearer-credentialled writes, Cache-Control: no-store on /api/*, and a visible staleness indicator in the board UI.
- **Done when:** Default start binds loopback only; a cross-origin page cannot read /api/board; POST /api/board/raw without the credential returns 403; BOARD.md is unchanged after an unauthenticated attempt. Additionally: curl -D- /api/board shows Cache-Control: no-store; a board tab left open reflects a task added by another client within one poll interval without a manual reload; and with the server stopped, the page visibly indicates it is not updating instead of silently showing the last good render. Verified: 188 ai_pilot tests and 29 subtests pass. The agent left 9 failing; fixtures and the refusal tests were completed during review, including that an unauthenticated /api/board/raw returns 401 and leaves BOARD.md byte-identical.

### L-15

**Flight planner is an unauthenticated confused deputy holding instructor credentials**

`P0` · `critical` · `bug` · Flight planner · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort M · wave 0 · **fixed**

- **Files:** `services/flightplanner/app.py:1098-1113`, `services/flightplanner/app.py:1138-1143`, `services/flightplanner/app.py:1298`, `services/flightplanner/app.py:1993`
- **Problem:** The planner holds CAPVSAR_TOKEN_INSTRUCTOR and CAPVSAR_TOKEN_BASE in its own environment and attaches them to server-side POSTs into the exercise console via _console_headers(). It has no sessions, no login and no import of access.py; only 2 of its 21 routes check anything, and that check accepts either a matching token OR merely an Origin header whose netloc equals the request host, which a non-browser client sets freely. An unauthenticated caller who can reach the planner can therefore create scenarios and broadcast messages to every console with INSTRUCTOR privilege. The fallback at app.py:1141 makes it worse: a missing _BASE token silently falls back to the _INSTRUCTOR token, so a misconfiguration escalates rather than fails. This is an architectural property, not a dev shortcut - putting single sign-on in front of the planner does not fix it, because the privilege comes from a server-held credential rather than from the caller. Sources: docs/WEB_HOSTING_AND_IDENTITY_PLAN.md section 2 (2026-09-09) and a five-service auth audit on 2026-09-13. Verified present in the working tree at commit 6690d35.
- **Fix:** Propagate the CALLER's identity to the console instead of presenting a server-held credential: accept the participant session on the planner, and either forward it or exchange it for a short-lived scoped token bound to that user, exercise and operation. Remove the _BASE to _INSTRUCTOR fallback so a missing token fails closed. Authenticate the planner's own mutating routes. Fixed 2026-09-13 (commit 0705780, Codex job A). _console_headers(role) is deleted; no CAPVSAR_TOKEN reference remains anywhere in the planner, so the server holds no credential it could lend. Requests forward the caller's own X-CAPVSAR-Token, Authorization or capvsar_session and verify it against the console's /api/auth/me before any write. Origin is treated as a CSRF check rather than proof of identity.
- **Done when:** An unauthenticated planner request cannot cause any console write. A caller holding only aircrew rights cannot create a scenario. Removing CAPVSAR_TOKEN_BASE produces an error, never an instructor-privileged call. Verified: 88 tests and 17 subtests pass in the planner suite, and grep finds no CAPVSAR_TOKEN in services/flightplanner/app.py. The export test was strengthened rather than adapted - it still sets CAPVSAR_TOKEN_INSTRUCTOR and _BASE to distinct values and asserts the caller's token reaches both console writes, proving the environment tokens are ignored. CONSEQUENCE: /api/sar/export-vsar creates a scenario, which the console gates at instructor, so an AOBD holding only aircrew rights can no longer perform the pattern push the SAREX narrative describes. The console would always have refused it; the borrowed credential hid that. This is open question 2 in the seat user stories and needs a decision.
- **Depends on:** X-11

### O-1

**Repo has no working git history**

`P0` · `critical` · `task` · Deployment / infrastructure · cluster C1 (Repo & release hygiene) · effort S · wave 0 · **fixed**

- **Files:** `repo root`
- **Problem:** Codex published a v0.1 baseline to Gitea and GitHub on 2026-09-08 with ignore rules covering credentials, runtime state and build output. But this working tree still has no `.git/` and `git` is not installed on this machine, so agents editing here still cannot diff, revert or see what another tool changed — which is the actual failure mode the finding was about.
- **Fix:** This directory is now a real checkout: git init in place, origin set to ssh://git@192.0.2.121:2222/ron/capvsar.git (git.rpc-cyberflight.com does not resolve from this host - use the IP), local main tracking origin/main. Everything that had accumulated in the working tree since v0.1 (RBAC/setup wizard, O-2, radio/DF work, docs, tests) was captured as one commit on top of v0.1 without checking out or discarding anything already on disk, then pushed. .env.example, missing on disk with no explanation, was reconstructed from the env vars the code actually reads and committed separately. Pushed to Gitea only - not mirrored to GitHub here, since this repo's IP-redaction convention (if any, cf. flight-planner-n499cp-v2 scripts/redact_ips.py) was not established before pushing somewhere public.
- **Done when:** git log and git status work in /home/ron/Projects/cap-vsar (this directory), confirmed. origin/main on Gitea matches local main (pushed c517617). GitHub mirroring is a separate, deliberately deferred decision.

### X-10

**Literal codes ADMIN and INSTRUCTOR mint an instructor session without the token**

`P0` · `critical` · `bug` · Exercise console (backend) · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort S · wave 0 · **fixed**

- **Files:** `services/exercise/app/access.py:211-215`, `services/exercise/app/routers/auth.py:36-54`, `services/exercise/app/routers/auth.py:82-97`
- **Problem:** authenticate_code() treats the literal strings ADMIN and INSTRUCTOR as valid participant codes whenever CAPVSAR_TOKEN_INSTRUCTOR is set in the environment. It checks only that the token EXISTS; it never compares the caller's input against it. GET /join/ADMIN is therefore a plain unauthenticated URL that mints an Exercise Director session, sets the cookie and redirects to /. Because instructor satisfies every other role in SATISFIED_BY, this grants sortie control, scenario deletion, effects injection and truth reveal. It defeats X-1: that fix gates beacon_lat/lon behind 'a presented instructor token', but an instructor SESSION is obtainable without presenting one, so any LAN or WireGuard participant can read the beacon before reveal. Sources: docs/WEB_HOSTING_AND_IDENTITY_PLAN.md section 2 (2026-09-09) and a five-service auth audit on 2026-09-13. Verified present in the working tree at commit 6690d35.
- **Fix:** Remove the shortcut branch entirely. An instructor session must require the configured token or a rostered instructor credential. Add a regression test asserting that /join/ADMIN, /join/INSTRUCTOR and POST /api/auth/login with those codes all return 401 while CAPVSAR_TOKEN_INSTRUCTOR is set. Fixed 2026-09-13 (commit 944f093). The ADMIN/INSTRUCTOR shortcut is removed from authenticate_code(); an instructor authenticates with a roster credential or the configured token like every other role.
- **Done when:** GET /join/ADMIN and /join/INSTRUCTOR return 401/redirect-to-error with an instructor token configured; no session row is created; the truth-leak regression in tests/test_console.py still passes. Verified by reproducing the attack against the fixed console: /join/ADMIN, /join/INSTRUCTOR and the case variant /join/admin are all refused with no session cookie set, and POST /api/auth/login with those codes returns 401. Covered by BackdoorCodeTests in tests/test_setup_auth.py, including the specific path from /join/ADMIN to beacon truth.

### X-11

**enforce() fails open and /api/auth/me reports instructor to anonymous callers**

`P0` · `critical` · `bug` · Exercise console (backend) · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort S · wave 0 · **fixed**

- **Files:** `services/exercise/app/access.py:361-379`, `services/exercise/app/routers/auth.py:57-68`, `services/exercise/app/main.py:107-112`, `.env.example:26-28`
- **Problem:** access.enforce() returns (allowing the call) when no matching env token is configured and no session is active - an explicit 'open for local dev' branch. Every gated mutating endpoint therefore accepts anonymous requests in that state. .env.example ships all three CAPVSAR_TOKEN_* values blank, so the default deployment is unauthenticated; main.py logs a warning naming the open roles but starts anyway. Compounding it, GET /api/auth/me actively reports {authenticated: true, role: instructor} to any anonymous caller in the same state, so the UI renders full instructor controls for a stranger. Sources: docs/WEB_HOSTING_AND_IDENTITY_PLAN.md section 2 (2026-09-09) and a five-service auth audit on 2026-09-13. Verified present in the working tree at commit 6690d35.
- **Fix:** Deny by default. enforce() must raise when it cannot positively identify a satisfying session or token. Gate the dev convenience behind an explicit opt-in flag (e.g. CAPVSAR_DEV_OPEN=1) that is refused when a production marker is set, and fail startup rather than warn when required identity configuration is missing. /api/auth/me must return authenticated:false when there is no session. Fixed 2026-09-13 (commit 944f093). enforce() now denies when no credential is configured instead of returning. Opening the console is deliberate via CAPVSAR_DEV_OPEN, refused when CAPVSAR_ENV is production. /api/auth/me no longer claims an instructor identity for anonymous callers.
- **Done when:** With all CAPVSAR_TOKEN_* unset and no dev flag, the app refuses to start; with the dev flag, a startup banner states it. Anonymous POST to a gated route returns 403. /api/auth/me returns authenticated:false with no session. Verified: anonymous POST /api/scenarios returns 403 with tokens configured and 503 with none; /api/auth/me reports authenticated false. Covered by DenyByDefaultTests, including that CAPVSAR_DEV_OPEN is honoured only outside production. Two suites that had been passing on the fail-open were corrected rather than relaxed. 140 tests and 23 subtests pass.

### X2-1

**Live DF telemetry (bearing_true, distance_nm) broadcast to anonymous /api/state and /ws**

`P0` · `critical` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 0 · **fixed**

- **Files:** `services/exercise/app/hub.py`, `services/exercise/app/roles.py`, `services/exercise/app/routers/system.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** Aircraft df is reduced to receiver state for every viewer but the instructor; /ws and the ticker render per socket (hub.broadcast_state). tests/test_console.py::TruthBoundaryByViewer.
- **Done when:** 

### O2-3

**Blank Mumble password deploys an open voice net**

`P0` · `high` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 0 · **fixed**

- **Files:** `docker-compose.yml`, `scripts/deploy.sh`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** Compose :? and deploy.sh check.
- **Done when:** 

### X2-2

**A revealed old sortie reveals the beacon of the scenario being flown**

`P0` · `high` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 0 · **fixed**

- **Files:** `services/exercise/app/routers/sorties.py`, `services/exercise/app/store.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** Sorties snapshot their beacon at start; /track withholds a revealed sortie's beacon and df from non-instructors while an unrevealed sortie flies the same beacon; start returns a warning when the scenario was revealed before.
- **Done when:** 

### X-12

**Session cookie lacks Secure, session id is returned to JavaScript, and a GET creates the session**

`P1` · `high` · `bug` · Exercise console (backend) · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort S · wave 0 · **fixed**

- **Files:** `services/exercise/app/routers/auth.py:42-54`, `services/exercise/app/routers/auth.py:82-97`, `services/exercise/app/access.py:159-165`
- **Problem:** Three separate weaknesses in one flow. (1) The capvsar_session cookie is set httponly/samesite=lax but WITHOUT secure=True, and because exercise :8700 stays published in plaintext alongside Caddy (see O-8) the cookie crosses the wire in the clear on the default path. (2) POST /api/auth/login also returns session_id in the JSON body, handing JavaScript a bearer secret that httponly was meant to withhold. (3) GET /join/{code} is a state-changing request that creates a session and sets a cookie - no POST confirmation and no CSRF protection, and the code sits in the URL path where it lands in browser history and proxy logs. access.py additionally accepts the session id as a ?session= query parameter. Sources: docs/WEB_HOSTING_AND_IDENTITY_PLAN.md section 2 (2026-09-09) and a five-service auth audit on 2026-09-13. Verified present in the working tree at commit 6690d35.
- **Fix:** Set secure=True on the session cookie once TLS is the only path (sequence with O-8). Stop returning session_id in the login response body. Make /join/{code} render a confirmation page and require a CSRF-protected POST to consume the code. Remove ?session= and ?token= query-parameter acceptance for hosted deployment. Fixed 2026-09-13 (5cadad0). Secure cookie, no session id in the login body, CSRF-protected POST join replacing the state-changing GET, ?session= removed.
- **Done when:** Login response body carries no session id; the cookie has Secure; GET /join/{code} creates no session row until the POST; query-parameter auth is rejected. Verified: 144 console tests and 23 subtests pass.
- **Depends on:** O-8

### X-13

**Roster codes are guessable, sessions are stored unhashed, and roster regeneration does not revoke them**

`P1` · `high` · `bug` · Exercise console (backend) · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort M · wave 0 · **fixed**

- **Files:** `services/exercise/app/access.py:284-358`, `services/exercise/app/access.py:176-202`
- **Problem:** save_exercise_setup() generates participant codes that are sequential and derived from public callsigns - INSTR-1, PLT-423, OBS-423, SCN-423, MRO-1, UDF-1 - so anyone who knows the aircraft callsign can guess the aircrew and instructor codes, and codes are matched case-insensitively. A per-row random token column is generated and stored but never read by any code path, so the one unguessable credential in the schema is dead. Separately, session ids are stored in the sessions table in plaintext rather than hashed, expired rows are filtered on read but never deleted so the table grows without bound, and save_exercise_setup() does DELETE FROM roster without cascading to sessions - regenerating a roster invalidates every code while leaving the sessions minted from them valid for their full 24 hours. Sources: docs/WEB_HOSTING_AND_IDENTITY_PLAN.md section 2 (2026-09-09) and a five-service auth audit on 2026-09-13. Verified present in the working tree at commit 6690d35.
- **Fix:** Make the stored per-row token the actual credential and make codes non-guessable, or require the token alongside the code. Hash session ids at rest. Delete expired sessions on a schedule. Cascade roster regeneration and membership removal to session revocation, and re-validate role on each request rather than trusting the role copied into the session. Fixed 2026-09-13 (5cadad0). Badges are label plus a 32-hex random token; session ids stored as sha256 and minted with secrets.token_urlsafe(32); expired rows reclaimed; triggers revoke sessions on roster delete or code change. Distributed badges must be reissued.
- **Done when:** Regenerating a roster terminates sessions derived from the old roster within the target window; expired rows are pruned; no plaintext session id is recoverable from the database. Verified by attack: /join/INSTR-1 (the guessable label) is refused while the full 40-character badge is accepted.

### X-14

**POST /api/radio/ics mutates shared radio state with no authorization**

`P1` · `high` · `bug` · Exercise console (backend) · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort S · wave 0 · **fixed**

- **Files:** `services/exercise/app/radio.py:85`
- **Problem:** POST /api/radio/ics changes shared ICS and channel state for the whole exercise and carries no access.enforce() call and no session check. Any participant, or any host that can reach :8700, can rewrite the net structure mid-exercise. Neighbouring radio reads (/api/radio/config, /api/radio/rx) are likewise ungated, and the /ws and /api/radio/stream sockets authenticate with a same-origin header check that is skipped entirely when Origin is absent, which is the normal case for a non-browser client. Sources: docs/WEB_HOSTING_AND_IDENTITY_PLAN.md section 2 (2026-09-09) and a five-service auth audit on 2026-09-13. Verified present in the working tree at commit 6690d35.
- **Fix:** Gate POST /api/radio/ics behind base_or_instructor. Establish identity - not just origin - on /ws and /api/radio/stream, and recheck membership periodically during an open socket so revocation propagates. Fixed 2026-09-13 (5cadad0). POST /api/radio/ics requires base or instructor.
- **Done when:** Anonymous POST /api/radio/ics returns 403; a non-browser client with no Origin header is rejected from /ws rather than admitted. Verified: anonymous POST /api/radio/ics returns 403.
- **Depends on:** X-11

### F-1

**Mission-base pages are blank without internet (Leaflet from CDN)**

`P0` · `critical` · `bug` · Exercise console (frontend) · cluster C6 (Offline mission base) · effort S · wave 1 · **fixed**

- **Files:** `services/exercise/app/static/base.html:5,62`, `services/exercise/app/static/index.html:5,109`, `services/exercise/app/static/debrief.html:5,54`
- **Problem:** Leaflet 1.9.4 loads from unpkg.com with no local copy. On a base LAN with no internet base.js:4 throws on `L` being undefined, so the WebSocket never connects and the status board and bearing log are gone — the whole view, not just the map.
- **Fix:** Fixed 2026-09-08: Leaflet 1.9.4 vendored to services/exercise/app/static/vendor/leaflet/ (js, css and the five dist images leaflet.css references, 192 KB) and the three views point at it. tests/test_console.py::OfflineAssets asserts no view pulls a remote script or stylesheet, that the vendored files are served at the paths the pages request, and that the CSS's images/ resolve. The planner's own CDN and tile dependency is separate and still open (L-8).
- **Done when:** Load /base with outbound internet blocked: map tiles may be blank but aircraft, status board and bearing log work.

### O-2

**Plugin hardcodes console address and callsign — multi-aircraft not deployable**

`P0` · `critical` · `bug` · X-Plane plugin / engine · cluster C4 (Station identity & onboarding kit) · effort L · wave 1 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:86-87`, `scripts/deploy_xplane_plugin.py`, `scripts/deploy_mo_panel.py`, `scripts/build_c182t_package.py`
- **Problem:** Corrected 2026-09-08: participant onboarding is NOT absent. The canonical repo has docs/CONNECT.md (join guide), scripts/wg-peer.sh (prints a WireGuard peer config and QR for a named participant), scripts/deploy.sh (idempotent stack deploy) and infra/ROUTER.md. What remains real and unchanged: the plugin hardcodes CONSOLE and CALLSIGN with no per-station override, so three aircraft still means three hand-edited copies; the deploy scripts are Linux-only; build_c182t_package.py hardcodes /home/ron; and there is no single station kit bundling plugin + instruments + panel + aircraft + CA cert for a member to install.
- **Fix:** xplane/PI_capvsar_df.py now loads CONSOLE/CALLSIGN/PLUGIN_KEY from capvsar_station.ini beside wherever the plugin is deployed (_load_station_config()), falling back independently per-key to the historical single-station defaults so an install with no ini is unchanged. CAPVSAR_TOKEN_PLUGIN still overrides the ini plugin_key. scripts/build_station_kit.py generates a per-station kit (plugin + generated ini + the four Air Manager instruments + a README), optionally zipped. The tracked plugin source is now byte-identical across every station, so deploy_xplane_plugin.py hash checks mean something again. NOT bundled, deliberately: the C182T aircraft package (build_c182t_package.py derives it from the recipient's own local Laminar install, not redistributable) and a CA certificate (issued per ms01 deployment, not present in this repo).
- **Done when:** tests/test_engine.py: _load_station_config() falls back to defaults with no ini, applies per-key overrides from an ini, and confirms CAPVSAR_TOKEN_PLUGIN beats the ini. End-to-end: scripts/build_station_kit.py --callsign CAP-2 built a kit, and importing that kit's PI_capvsar_df.py directly (own directory, own ini) yielded CALLSIGN=CAP-2 and the kit's plugin_key — the same tracked source picking up a different station identity from its own directory. Deployed via scripts/deploy_xplane_plugin.py to this machine's X-Plane install (no station.ini present there, so behavior is unchanged from before this fix).
- **Depends on:** P-2

### O-3

**Fresh deploy crash-loops; repo is not the deployment**

`P0` · `critical` · `bug` · Deployment / infrastructure · cluster C5 (Deployment bootstrap & voice provisioning) · effort M · wave 1 · **fixed**

- **Files:** `docker-compose.yml:120`, `services/flightplanner/app.py:113`
- **Problem:** Sharpened 2026-09-08. Confirmed: scripts/deploy.sh creates only mumble/data. Compose also bind-mounts services/exercise/data, services/flightplanner/data/aviation_data.db (as a FILE) and services/exercise/radio-public - none of which deploy.sh creates and all correctly gitignored as runtime state. So a fresh clone plus deploy.sh still crash-loops the flight planner: Docker materialises the missing aviation_data.db path as a directory and sqlite3.connect fails at import. The live ms01 stack works only because those paths were created by hand at some earlier point.
- **Fix:** Fixed 2026-09-08. scripts/deploy.sh now creates every host path compose bind-mounts - services/exercise/data, services/exercise/radio-public and services/flightplanner/data/charts - and touches aviation_data.db as an empty file, which SQLite accepts. The file case is the one that mattered: Docker silently creates a missing DIRECTORY mount, but for a FILE mount it creates a directory where the file belongs, which is why gunicorn crash-looped. It also publishes Caddy's root CA into radio-public, a step nobody had scripted - Caddy mints it into a named volume the console cannot read, so /radio-ca.crt served nothing anywhere the file had not been hand-copied.
- **Done when:** Verified by cloning the repo to a temp dir on ms01 and running the real script against a stubbed docker: four paths created, the 0-byte database accepted by sqlite3, the CA published, second run idempotent. Committed 0e2e0d1 (amended). NOT yet proven end-to-end with a real `docker compose up` on a clean host - that needs a spare machine.

### P-1

**Terrain line-of-sight ray is mirrored**

`P0` · `critical` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 1 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:595-599`
- **Problem:** interp() walks aircraft to beacon with `fr`, but `ray = b_ft + (ac_ft - b_ft) * fr` puts the beacon's altitude at the aircraft end. Ridges near the beacon never block; high ground near the aircraft falsely blocks. Terrain masking — a headline training effect — is inverted.
- **Fix:** ray = ac_ft + (b_ft - ac_ft) * fr.
- **Done when:** New test with a non-flat terrain stub (ridge at 30/60/90 % of path) asserting blocked vs clear in both directions.

### P-2

**Plugin can never receive beacon truth, so the in-sim DF is deaf**

`P0` · `critical` · `bug` · X-Plane plugin / engine · cluster C2 (Truth integrity & roles) · effort M · wave 1 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:947-967`, `services/exercise/app/main.py:406-408`
- **Problem:** The plugin polls /api/state, which withholds truth until reveal, then sets active=1 with lat/lon at 0/0 or the previous exercise's beacon. Distance to Null Island exceeds the radio horizon, so the authoritative DF engine produces nothing for the whole exercise unless the instructor reveals at the start.
- **Fix:** Fixed 2026-09-08, both halves. Console: GET /api/plugin/scenario returns the running sortie with truth, gated on CAPVSAR_TOKEN_PLUGIN, 503 when no key is configured so it cannot be open by accident. Plugin: net_worker now polls that endpoint with the key (PLUGIN_KEY, from CAPVSAR_TOKEN_PLUGIN; O-2 will move it into the station config alongside CONSOLE and CALLSIGN) and sends the same key on /api/positions, which is now gated too. A refused channel (403/503/404) clears scn['active'] so the DF goes silent instead of homing on a null beacon, and logs the reason once per transition.
- **Done when:** tests/test_plugin_net.py (9 checks) covers the endpoint choice, the key header, and each refusal path; tests/test_console.py asserts the payload carries every field the plugin reads. Still to confirm in the sim: a bearing appears on the DF head during an unrevealed sortie.
- **Depends on:** X-1

### X-1

**Beacon truth leaks through three unauthenticated endpoints**

`P0` · `critical` · `bug` · Exercise console (backend) · cluster C2 (Truth integrity & roles) · effort M · wave 1 · **fixed**

- **Files:** `services/exercise/app/main.py:116-131`, `services/exercise/app/main.py:208-212`, `services/exercise/app/main.py:297-316`
- **Problem:** Hub.snapshot() is the only place truth is filtered and only /api/state and /ws use it. GET /api/scenarios returns every beacon_lat/lon; GET /api/sorties/{id}/track returns `beacon` for a running unrevealed sortie; snapshot() pops lat/lon but leaves beacon_elev_ft. Any participant reads the answer in one request, defeating the design's core teaching mechanism.
- **Fix:** Fixed 2026-09-08: one public_scenario() serializer in main.py strips beacon_lat/lon/elev_ft unless truth is explicitly allowed; /api/scenarios returns truth only for a presented instructor token; /api/sorties/{id}/track returns beacon only once that sortie is revealed, and now also reports `revealed` so the debrief's 'never revealed' branch is reachable. Regression test tests/test_console.py walks every scenario/sortie response for a value within ~100 m of truth.
- **Done when:** Automated test: with a running unrevealed sortie, no response body from any GET endpoint contains a coordinate within 100 m of truth.

### X-2

**No authentication or role separation on any console endpoint**

`P0` · `critical` · `bug` · Exercise console (backend) · cluster C2 (Truth integrity & roles) · effort L · wave 1 · **fixed**

- **Files:** `services/exercise/app/main.py`, `docker-compose.yml:73`
- **Problem:** Any LAN/WireGuard participant can stop a sortie, reveal the beacon, delete scenarios or rewrite injected effects. Only the radio stream has an access code and it defaults to empty. /ws has no origin check although the radio socket does.
- **Fix:** Superseded 2026-09-08 by the full Exercise Setup / RBAC system (services/exercise/app/access.py): session-cookie and QR/short-code participant login (/join/<code>, /login) with a roster generated per exercise by the Setup wizard, role tokens (instructor/base/aircrew/ground_team/plugin) enforced on every mutating route and view, instructor satisfies base, /ws origin-checked. The old CAPVSAR_TOKEN_* shared-secret env vars are preserved only for backward compatibility with the plugin/scripts, not required for participant roles — the earlier REMAINING item (setting those on ms01) no longer gates this fix. Covered by tests/test_setup_auth.py (23 tests) and tests/test_console.py::RoleGates.
- **Done when:** A non-instructor session (base/aircrew/ground_team) gets 403 on reveal/stop/scenario mutation; /setup and / redirect unauthenticated or non-instructor sessions; /join/<code> and /login establish a working session cookie. Covered by tests/test_setup_auth.py and tests/test_console.py::RoleGates.

### F-5

**Radio console setup path (verified working)**

`P0` · `high` · `bug` · Deployment / infrastructure · cluster C5 (Deployment bootstrap & voice provisioning) · effort S · wave 1 · **resolved**

- **Files:** `services/exercise/radio-public/ (missing)`, `docker-compose.yml:67`, `services/exercise/app/static/mission-radio.html:52,54`
- **Problem:** Caddy serves /radio-ca.crt from a directory that does not exist in the repo, so tablets cannot reach the secure context getUserMedia requires and the console blocks at mission-radio.js:148. radio-art/README.md, linked as the setup notes, does not exist either.
- **Fix:** WRONG FINDING, corrected 2026-09-08 by testing the live system. Both halves were false. The setup notes exist and are linked correctly - static/radio-help.html (6 KB), referenced from mission-radio.html's footer and its secure-context overlay; there is no radio-art/README.md because radio-art/ holds the two faceplate SVGs, not documentation. And services/exercise/radio-public/ exists on ms01 containing mission-base-ca.crt: GET /radio-ca.crt returns 200 with a real PEM certificate, and https://ms01:8743/radio answers 200. Tablets can reach the secure context today. Only residue: nothing in the repo creates radio-public/ for a fresh deployment, which is O-3's scope, not a separate defect.
- **Done when:** A tablet with no prior trust can download the CA from /radio-ca.crt, install it, and key the radio.
- **Depends on:** O-3

### L-1

**X-Plane .fms export is malformed**

`P0` · `high` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort M · wave 1 · **fixed**

- **Files:** `services/flightplanner/app.py:620,636`, `services/flightplanner/tests/test_sar.py:115`
- **Problem:** The v1100 waypoint line is `type ident airway|DRCT altitude lat lon`; the code emits `11 SS01 5500.0 lat lon`, dropping DRCT so the altitude is parsed as the airway. Type 11 means a named fix in the navdata, but SS01/DATUM do not exist. CYCLE 2401 is hardcoded. The test asserts the broken format, locking it in.
- **Fix:** Emit type 28 with a +lat_lon ident and the DRCT column for user waypoints; derive CYCLE from the date; fix the test to assert the real format.
- **Done when:** Load an exported pattern in X-Plane 12 and fly the first two legs from the G1000 flight plan page.

### B2-1

**Builder deleted the installed aircraft before building**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 1 · **fixed**

- **Files:** `scripts/build_c182t_package.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 8.
- **Fix:** Resolved by 57663ec (staged build, backup).
- **Done when:** 

### F2-1

**Flight Planner link rewritten to unpublished port 8090**

`P1` · `high` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 1 · **fixed**

- **Files:** `services/exercise/app/static/charts.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** Rewrite removed; test scans app/static/*.js for :8090.
- **Done when:** 

### I2-1

**GMA clearance recorder subscribes to nonexistent datarefs**

`P1` · `high` · `bug` · Air Manager instruments · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 1 · **fixed**

- **Files:** `instruments/mo-audio-panel-gma1347/logic.lua`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 6.
- **Fix:** sim/atc/com1_rx and com2_rx. Live check pending. Supersedes the I-15 verification.
- **Done when:** 

### I2-3

**dial_add press callbacks are not an Air Manager 4.2 feature**

`P1` · `high` · `bug` · Air Manager instruments · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 1 · **fixed**

- **Files:** `instruments/_shared/lib/knob_push.lua`, `instruments/cap-fm-tdfm-136b/logic.lua`, `instruments/mo-audio-panel-gma1347/logic.lua`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 6.
- **Fix:** knob_push() transparent button over the knob. Live check pending (hold TDFM main encoder 2 s).
- **Done when:** 

### L2-1

**Unresolvable datum silently plans at a hard-coded point**

`P1` · `high` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 1 · **fixed**

- **Files:** `services/flightplanner/app.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** 400 with a clear message; a datum is required.
- **Done when:** 

### L2-4

**Terrain profile reports 0 ft and ADEQUATE when USGS is unreachable**

`P1` · `high` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 1 · **fixed**

- **Files:** `services/flightplanner/app.py`, `services/flightplanner/static/js/app.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** Unknown terrain is reported as unknown; the badge says NO TERRAIN DATA.
- **Done when:** 

### O-8

**No single front door: Caddy fronts one backend and is bypassable on the LAN**

`P1` · `high` · `task` · Deployment / infrastructure · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort M · wave 1 · **fixed**

- **Files:** `services/exercise/Caddyfile:9-12`, `docker-compose.yml:67`, `docker-compose.yml:105`, `docker-compose.yml:146`, `scripts/firewall.sh:10-14`, `infra/ROUTER.md:24-29`
- **Problem:** The Caddy container is a single-purpose proxy - reverse_proxy exercise:8700, with tls internal and site names hardcoded to ms01, ms01.local and 192.0.2.151 - existing to give tablets a trusted secure context for microphone access. flightplanner has no TLS front at all and is not in the Caddyfile. Because exercise :8700 and flightplanner :8090 remain published as plaintext HTTP on the LAN, the TLS front is bypassable and the non-Secure session cookie and any header or query-parameter token cross the wire in the clear on the default path. firewall.sh notes that Docker's iptables rules precede ufw's, so ufw does not filter published container ports and the router forward list is the real boundary. There is consequently no one place a user can log in once and reach the console, the mission base view and the planner. Sources: docs/WEB_HOSTING_AND_IDENTITY_PLAN.md section 2 (2026-09-09) and a five-service auth audit on 2026-09-13. Verified present in the working tree at commit 6690d35. INVESTIGATED 2026-09-13: path-mounting the planner behind one hostname is NOT viable without changing the planner first, which is what the identity plan warned about when it said to use a separate subdomain if the planner's URL construction makes path mounting brittle. Measured: services/flightplanner/static/js/app.js issues 13 absolute fetches rooted at / (lines 21, 63, 373, 396, 498, 667, 757, 903, 921, 939, 1057, 1165, 1208 - /api/tile-sources, /api/calculate-route, /api/sar/export-vsar and the rest), and templates/index.html and guide.html carry absolute hrefs (href="/", href="/guide", href="/guide/quickstart"). Mounted under /planner/ every one of those would resolve against the console instead. The exercise console has no such problem.
- **Fix:** Fixed 2026-09-14 (472d3bb, 655b905). Caddy is the sole participant front door on 443, with port 80 limited to the public CA bootstrap and HTTPS redirects. Exercise 8700 and planner 8090 are no longer published. The planner is prefix-safe at /planner/ through ProxyFix, generated template URLs, local tile URLs and prefixed frontend requests. The authenticated root portal lists applications by role. The AI Pilot engineering deck remains separate. deploy.sh now rebuilds local source images and repairs the exercise SQLite bind-mount ownership before restart. X-Plane uses a per-process CA bundle and an HTTPS station config rather than broad system trust.
- **Done when:** Live on ms01 2026-09-14: cross-machine HTTPS health, CA bootstrap, redirect, roster login, portal, base, planner and prefixed tile-source checks all returned the expected 200/302/308 responses; direct connections to 8700 and 8090 were refused. scripts/preflight.py reported ALL PASS for front door, private backends, Mumble channels/ACL, chart source and CA publication. The installed station credential reached /api/plugin/scenario over verified HTTPS with the process-local CA bundle. Automated: 93 planner tests + 17 subtests, 38 setup/auth tests + 6 subtests, and 21 radio tests passed; Caddy and Compose configs validated on ms01.
- **Depends on:** X-11, X-12

### O2-1

**Two console route tests fail on FastAPI 0.143**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 1 · **fixed**

- **Files:** `tests/test_console.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** route_paths() walks lazy included routers.
- **Done when:** 

### O2-2

**No reproducible test environment; planner and board suites not run**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 1 · **fixed**

- **Files:** `requirements-dev.txt`, `scripts/run_tests.sh`, `scripts/ci_local.sh`, `.gitea/workflows/ci.yml`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** scripts/run_tests.sh runs root, ai_pilot, planner and board in separate processes. Not run on Python 3.12 here (unavailable).
- **Done when:** 

### O2-4

**CAPVSAR_ENV never set so the production guard is inert**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 1 · **fixed**

- **Files:** `docker-compose.yml`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** CAPVSAR_ENV: production.
- **Done when:** 

### U-1

**Planner SAR pattern generator cannot be opened (modal nested inside the hidden DB modal)**

`P1` · `high` · `bug` · Flight planner · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort S · wave 1 · **fixed**

- **Files:** `services/flightplanner/templates/index.html`
- **Problem:** The DB-update modal's div was never closed, so #modal-sar sat inside a display:none element; the SAR button did nothing. Pre-dates the 2026-10-10 review.
- **Fix:** Closed the div; tests/test_ux_fixes.py parses the template and asserts every modal is a child of body.
- **Done when:** 

### U-2

**Setup QR badges never render (vendored QR library has a truncated Reed-Solomon table)**

`P1` · `high` · `bug` · Exercise console (frontend) · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort M · wave 1 · **fixed**

- **Files:** `services/exercise/app/routers/auth.py`, `services/exercise/app/static/setup.js`, `services/exercise/requirements.txt`
- **Problem:** qrcode.min.js threw 'code length overflow' for every join URL; the levels that did render used fallback ECC blocks and would not scan.
- **Fix:** Badges are rendered server-side as SVG by segno at /api/setup/badge/{id}.svg (instructor-gated, origin must match the Host); the client library is deleted.
- **Done when:** 

### X2-3

**ScenarioIn.effects accepts NaN and unknown keys; one scenario breaks every client**

`P1` · `high` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 1 · **fixed**

- **Files:** `services/exercise/app/models.py`, `services/exercise/app/hub.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** effects is EffectsIn (forbid extras, finite numbers); hub JSON uses allow_nan=False and the ticker survives a bad value.
- **Done when:** 

### X2-4

**Radio stream and pages fail open on a roster-only console**

`P1` · `high` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 1 · **fixed**

- **Files:** `services/exercise/app/radio.py`, `services/exercise/app/routers/pages.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** Sessionless radio join and anonymous page loads are allowed only on an explicit dev-open console with no base credential. Completes X-14.
- **Done when:** 

### L2-6

**Console push anchors the alert and beacon offset on waypoints[0]**

`P1` · `medium` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 1 · **fixed**

- **Files:** `services/flightplanner/app.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** search_centre for all three patterns.
- **Done when:** 

### O-2a

**Participant CONNECT.md cited by the as-built does not exist**

`P1` · `medium` · `bug` · Docs / record · cluster C4 (Station identity & onboarding kit) · effort S · wave 1 · **resolved**

- **Files:** `docs/ (missing CONNECT.md)`, `vault: Projects/as-built/AsBuilt_CAPVSAR.md`
- **Problem:** The as-built tells participants their instructions are at docs/CONNECT.md in the repository. That file does not exist, so the one pointer a new member is given leads nowhere — the same onboarding gap as O-2, but already promised in writing.
- **Fix:** WRONG FINDING, corrected 2026-09-08. docs/CONNECT.md exists in the canonical repo on ms01 and is a complete participant guide (Mumble client per platform, server details, nets, PTT). It was absent only from the local working tree this review was written against. Now pulled down. No work needed.
- **Done when:** A member who has never seen the project can get onto the voice net and the base console from that page alone.
- **Depends on:** O-2

### P2-2

**Per-beacon state not reset when the scenario changes under a running sortie**

`P1` · `medium` · `bug` · X-Plane plugin / engine · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 1 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 5.
- **Fix:** beacon_key in the scenario dict; flight loop clears held bearing, decode and scan hold.
- **Done when:** 

### X2-8

**Scenario notes are not truth-filtered and the seed notes name the beacon**

`P1` · `medium` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 1 · **fixed**

- **Files:** `services/exercise/app/roles.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** notes travel with the truth fields.
- **Done when:** 

### F-2

**Base view keeps the previous sortie's alert circle and tracks**

`P1` · `high` · `bug` · Exercise console (frontend) · cluster C8 (Base view & debrief) · effort S · wave 2 · **fixed**

- **Files:** `services/exercise/app/static/base.js:43,83-85`, `services/exercise/app/static/app.js:144-145`
- **Problem:** alertCircle is created once and never updated or removed and `centred` never resets; trackLines/bearingLayer are never cleared on a new sortie. Base staff plot against the previous scenario's search area. Expired aircraft also leak their trackLines entry.
- **Fix:** Fixed 2026-09-08. base.js now tracks the sortie id from the state snapshot and calls clearSortieLayers() when it changes, removing the alert circle and its marker (the marker was never even held in a variable), the beacon marker, aircraft markers, tracks and bearings, and resetting `centred`. Also fixed a leak the review only half-described: when an aircraft went quiet for 30 s and came back, a NEW polyline replaced trackLines[callsign] and orphaned the old one on the map permanently - it now resumes the existing track instead. An expired aircraft's marker is removed but its flown track is deliberately kept, because that is history base staff still need.
- **Done when:** Verified by driving a real browser session through two sorties over CDP: with the fix, tracks and bearings go to 0 and map layers drop 9 -> 5; against pre-F-2 code the previous sortie's track and bearing survive (tracks 1, bearings 1, layers 9 -> 7).

### F-3

**Debrief conflates all aircraft into one track**

`P1` · `high` · `bug` · Exercise console (frontend) · cluster C8 (Base view & debrief) · effort M · wave 2 · **fixed**

- **Files:** `services/exercise/app/static/debrief.js:45,68-72,90-98`, `services/exercise/app/main.py:301`
- **Problem:** /track returns callsign per position but the debrief treats them as one track: with three aircraft the polyline zigzags between them, 'track flown' sums inter-aircraft jumps and closest approach is meaningless — the scoring the SET relies on. Heading is also derived via atan2(dlon, dlat) with no cos(lat), ~10 deg bias at 33 N, although hdg_true is stored and simply not returned.
- **Fix:** Fixed 2026-09-08, both halves. Server: /api/sorties/{id}/track now returns hdg_true, which was stored on every position and discarded by the query. Client: debrief.js groups positions by callsign - one faint full track, one playback polyline and one labelled marker per aircraft, each in its own colour - and scores each aircraft separately for closest approach, track flown, direct line and efficiency. Heading uses the recorded hdg_true when present, and the fallback now scales longitude by cos(latitude), which the old inline calculation omitted (~10 deg of error at 33N).
- **Done when:** Verified in a headless browser against a seeded three-aircraft sortie (180 positions): three separate scored rows - CAP-1 0.00 nm 'overhead the beacon', CAP-2 3.34 nm 'did not close', CAP-3 1.96 nm 'localised' - three labelled markers, no JS errors. tests/test_console.py covers the hdg_true half.

### F-4

**Radio console does not rejoin after a network blip**

`P1` · `high` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort M · wave 2 · **fixed**

- **Files:** `services/exercise/app/static/mission-radio.js:184`, `services/exercise/app/static/base.js:19-30`
- **Problem:** The radio deliberately does not auto-reconnect, so a Wi-Fi blip silently drops the base station off the voice net with only a text notice. Base and legacy reconnect but lose bearings and messages broadcast during the outage: messages are fetched only at page load and bearings have no list endpoint at all.
- **Fix:** Rejoin with backoff plus an audible alarm on the radio; add GET /api/bearings?since= and ?since= on messages; refetch on reconnect.
- **Done when:** Drop the tablet's Wi-Fi for 30 s: the radio rejoins audibly and the base view backfills what it missed.

### F2-2

**Airband timeouts tear down the tactical radio**

`P1` · `high` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `services/exercise/app/static/mission-radio.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** Both timeout paths call airbandLost().
- **Done when:** 

### I-1

**DF faceplates repaint ~8 Hz regardless of change**

`P1` · `high` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort M · wave 2 · **fixed**

- **Files:** `instruments/becker-sar-df-517/logic.lua:755-758`, `instruments/rhotheta-rt-600/logic.lua:574-577`, `instruments/*/lib/cap_df.lua:95`
- **Problem:** The 250 ms tick repaints unconditionally and df.on_change fires redraw() from all three subscription groups every engine tick — roughly 8 Hz of ~100 _txt calls each rebuilding a style string, whether anything changed or not. This is CPU the MO station spends for nothing and it widens the canvas_draw reentrancy window.
- **Fix:** Fixed 2026-09-08. In cap_df.lua and DF heads' logic.lua, added snapshot-based change detection so redraw only occurs on whole-second timer boundaries or true bearing/signal/flag state changes, eliminating ~8 Hz idle repaint load.
- **Done when:** Air Manager CPU drops measurably with a static signal; display still updates within 250 ms of a real change.

### I-2

**pcall around canvas_draw hides real errors**

`P1` · `high` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort S · wave 2 · **fixed**

- **Files:** `instruments/becker-sar-df-517/logic.lua:163`, `instruments/rhotheta-rt-600/logic.lua:141`
- **Problem:** The pcall was added for a reentrancy error the Air Manager log shows only twice, each immediately followed by the missing-callback signature that was separately fixed — and zero occurrences since. It now silently swallows every synchronous canvas_draw failure.
- **Fix:** Fixed 2026-09-08. Dropped the swallowing pcall around canvas_draw in both becker-sar-df-517/logic.lua and rhotheta-rt-600/logic.lua.
- **Done when:** Exercise pages 1-3 and scan mode; Air Manager log stays clean.

### L-2

**Unauthenticated scenario push and CSRF-able database wipe**

`P1` · `high` · `bug` · Flight planner · cluster C11 (Flight planner security & dependencies) · effort M · wave 2 · **fixed**

- **Files:** `services/flightplanner/app.py:1406,816`
- **Problem:** /api/sar/export-vsar has no auth or rate limit and its free-text fields flow unbounded into scenario name/notes/alert_text and a broadcast to every console. /api/update-database takes no body, so a plain cross-site form POST triggers a DB wipe and reload. The README still advertises Cloud Run --allow-unauthenticated.
- **Fix:** Require the base token on the push; JSON-only with a CSRF-safe method on update-database; length caps on all free text.
- **Done when:** Unauthenticated push returns 401; a cross-site form POST to update-database is rejected.
- **Depends on:** X-2

### L-3

**Parallel-track generator can be driven into a 100M-iteration loop**

`P1` · `high` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort S · wave 2 · **fixed**

- **Files:** `services/flightplanner/app.py:591,1360-1361`
- **Problem:** num_legs is capped and spacing floored, but length_nm/width_nm are unbounded: width_nm=1e7 with spacing 0.1 is 1e8 sweeps, from an endpoint reachable without auth.
- **Fix:** Cap width and length (<= 60 NM) and total legs.
- **Done when:** Oversized request returns 400 quickly.

### L-4

**Both gunicorn workers race to rebuild the aviation database**

`P1` · `high` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort S · wave 2 · **fixed**

- **Files:** `services/flightplanner/app.py:357,300,317,334`, `services/flightplanner/Dockerfile`
- **Problem:** auto_update_if_empty() runs at import in both workers, so two threads concurrently DELETE/INSERT the same SQLite file; lock errors are swallowed by bare except: pass, silently dropping rows. update_status is per-process so /api/update-status answers inconsistently.
- **Fix:** Do the update once (a CLI command or a lock file); log exceptions instead of swallowing them.
- **Done when:** Cold start with an empty DB twice: row counts match the source both times.

### L2-13

**Planner, G1000 library and grid tool disagree on search-pattern conventions**

`P1` · `high` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort L · wave 2 · **fixed**

- **Files:** `services/flightplanner/app.py`, `docs/SEARCH_PATTERN_CONVENTIONS.md`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** Decision D2: DATUM + SSnn = end of leg nn, no inset in the geometry, planner conversions, shared fixture (24 cases) asserted in both repos. scripts/fly_search_grid.py left alone deliberately (autopilot flight-test work).
- **Done when:** 

### O-4

**Mumble channel tree exists only as hand-made rows in a runtime volume**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C5 (Deployment bootstrap & voice provisioning) · effort M · wave 2 · **fixed**

- **Files:** `services/exercise/app/radio.py:29-34,181`, `docker-compose.yml`, `vault: Projects/as-built/AsBuilt_CAPVSAR.md`
- **Problem:** Corrected twice. The channel tree exists on ms01 (hand-inserted into mumble-server.sqlite) AND is documented in docs/MUMBLE_CHANNELS.md, which gives the full tree, the rationale, and the one manual step still outstanding: the ACL on the Instructor/SET channel denying Enter. So this is neither undocumented nor a first-join failure. What remains real: the rows live only in a gitignored runtime volume with nothing in the repo to recreate them, radio.py carries its own hardcoded copy of four names, and the instructor-channel ACL is still a manual step per the doc.
- **Fix:** services/exercise/app/mumble_channels.py is now the single source of truth for the tree (docs/MUMBLE_CHANNELS.md); radio.py imports its CHANNELS from it instead of an independent hardcoded copy. scripts/provision_mumble.py recreates the whole tree idempotently by inspecting ms01's live mumble-server.sqlite schema directly (Murmur has no config-file channel definition) and also finishes the previously-manual Instructor/SET ACL: deny Enter to @all, grant Enter+Speak to a new @instructor group, at ACL priorities 0/1 so the grant overrides the deny per mumble.info/documentation/administration/acl. scripts/deploy.sh now stops mumble, runs the provisioner, restarts it, on every deploy. Also caught and fixed a real naming drift: the doc's own tree diagram said "Instructor / SET" while its setup steps and the live database both said "Instructor - SET".
- **Done when:** tests/test_provision_mumble.py, 4 cases, built against ms01's actual live schema (inspected via docker cp + sqlite3, not assumed): a brand-new server gets the whole tree; the Instructor/SET ACL rows land with correct priority and permission bits; an already hand-provisioned tree (ms01's real state) is left byte-for-byte untouched aside from the two new ACL rows; running twice changes nothing the second time. NOT yet run against ms01's actual live mumble-server.sqlite - that needs stopping the live voice server and was left for explicit sign-off.
- **Depends on:** O-3

### O-6

**No backup, monitoring or pre-exercise smoke check**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C5 (Deployment bootstrap & voice provisioning) · effort M · wave 2 · **fixed**

- **Files:** `docker-compose.yml`, `ms01`
- **Problem:** ms01 carries all services, the SQLite database and the voice bridge; the router carries everyone's WireGuard; there is no backup of exercise.db, no monitoring, and radio-https has no healthcheck. An exercise-day failure loses the record with no warning.
- **Fix:** scripts/preflight.py checks the exercise console's /api/health, the full Mumble channel tree plus the Instructor/SET ACL (reading the shared mumble_channels.py tree, same source O-4 provisions from), the flight planner's VFR tile source via the MapServer metadata endpoint (not a guessed tile coordinate - a 404 on an out-of-pyramid tile looks identical to the service being down otherwise), and the published browser-radio CA cert. scripts/backup_exercise_db.py takes an online SQLite backup (Connection.backup(), safe against a live writer - not a raw file copy, which can capture a torn snapshot) with 14-day retention pruning; a crontab line is in the script's own docstring, not installed anywhere by this change. radio-https (Caddy) gained a healthcheck in docker-compose.yml - it had none, so a Caddy that stopped proxying looked identical to a healthy one to `docker compose ps`. Nightly cron installed on ms01 (03:00, backs up to /mnt/nfs3/capvsar/backups/exercise-db - NFS3, the WD NAS at 192.0.2.144, mounted on ms01 for this specifically; it had no client mount before this). backup() gained retry-on-transient-failure after the first live run against that fresh mount hit exactly the kind of one-off I/O error a network destination can produce, with no retry of its own in sqlite3's backup API.
- **Done when:** preflight.py manually run against both a cold stack (nothing running: fails loudly, one specific reason per check) and a fully mocked warm one (provisioned test Mumble db, mock health server, placeholder CA cert: all five checks pass) - the tracker's own stated verify criterion. tests/test_backup_exercise_db.py, 4 cases, caught a real bug during development: same-second backups collided on a 1-second-resolution filename and silently overwrote each other, fixed by moving to microsecond resolution. Backup verified to survive a database with an open connection, and to prune only backups older than the retention window.
- **Depends on:** O-3

### O-7b

**G1000 MFD video stream never re-arms after a reconnect**

`P1` · `high` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort M · wave 2 · **open**

- **Files:** `Air Manager stock G1000 instrument logic.lua:90-100`, `~/Air Manager/log.txt`
- **Problem:** SimVideoStreamClient loses the connection every few minutes; the stock instrument calls video_stream_add() once at load, so after a reconnect the MFD tile is frozen on its last frame. Every MO station hits this.
- **Fix:** Created instruments/g1000-mfd-watchdog wrapper instrument monitoring frame arrival, displaying stale overlay on freeze, and auto re-arming video_stream_add() upon timeout/reconnect. Verified offline in tests/test_am.py; left open pending live flight station verification.
- **Done when:** A one-hour session with no frozen MFD; log shows reconnects with recovered video.

### P-3

**Scan mode destroys TIMEHOLD on 406**

`P1` · `high` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 2 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:645-652,755-759,693`
- **Problem:** Scan steps the receiver to alt1/alt2 between bursts; the next tick finds it untuned and calls silent(), clearing `held`. With scan_enable=1 — the 517's normal 406 posture — the bearing vanishes the instant each 440 ms burst ends instead of holding, which is exactly the behaviour the training relies on.
- **Fix:** Fixed 2026-09-08. The untuned path now distinguishes scan stepping from being parked on the wrong channel. When scan has stepped off the crew's channel between bursts it calls silent(keep_hold=True) then hold_or_drop(), the same treatment the between-bursts gap already got, so TIMEHOLD carries the bearing across the step. Tuning away by hand still drops it. Added tuned_hz() so 'what the crew selected' and 'what the receiver is on this instant' are separate questions rather than duplicated logic.
- **Done when:** New test: 406 beacon with scan enabled holds a bearing between bursts.

### P-4

**Radio horizon is one-sided**

`P1` · `high` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 2 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:738`, `services/exercise/app/propagation.py:37-40`
- **Problem:** Uses sqrt(max(alt - beacon_elev, 0)), which is zero when the aircraft is below the beacon: an aircraft in a valley 500 ft below a ridge-top beacon 1 NM away hears nothing.
- **Fix:** Fixed 2026-09-08. Both ends of the path now raise the horizon: 1.23*(sqrt(h_ac)+sqrt(h_bcn)) in feet MSL, in the plugin and in the server's propagation.py fallback, kept identical. The old form used the aircraft's height above the beacon, which went to zero the moment the beacon sat higher - an aircraft in a valley below a ridge-top beacon 1 NM away was ruled out of range. Terrain between the two remains a separate question, answered by the LOS probe.
- **Done when:** Test with the aircraft below beacon elevation at 1 NM: signal present.

### P-5

**Plugin disable/enable cycle kills the console link permanently**

`P1` · `high` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 2 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:555-560,945`
- **Problem:** XPluginDisable sets self.stop and never clears it, so the thread started by XPluginEnable exits immediately. Datarefs keep publishing stale state with no console link and no error.
- **Fix:** Fixed 2026-09-08. XPluginEnable creates a fresh threading.Event, so a disable/enable cycle no longer starts a worker that exits on its first check. XPluginDisable joins with a 1 s timeout - bounded because the worker may be inside a 4 s urlopen and X-Plane must not block on it; it is a daemon and the event is set, so it exits regardless.
- **Done when:** Reload the plugin in X-Plane; positions resume on /base.

### X-3

**SQLite writes block the event loop that carries radio audio**

`P1` · `high` · `bug` · Exercise console (backend) · cluster C7 (Console robustness) · effort M · wave 2 · **fixed**

- **Files:** `services/exercise/app/main.py:26-29,237,257,269,281,353,369,391`, `services/exercise/app/radio.py:223-243`
- **Problem:** Synchronous sqlite3 calls inside async handlers share the loop with 20 ms PCM frames for the Mumble bridge. Every commit fsyncs on a bind mount; a stalled commit trips the audio buffer check and unkeys the operator mid-transmission. No WAL, no timeout, connections never closed.
- **Fix:** Fixed 2026-09-08. db() is now a context manager that commits, rolls back and CLOSES (it leaked a connection per request), opens with timeout=5s, and the database is in WAL mode with synchronous=NORMAL. Every write in an async handler now goes through db_call() -> run_in_threadpool, so no commit runs on the loop carrying the Mumble bridge's 20 ms frames. The sync handlers were already threadpooled by FastAPI. Only startup seeding still touches the database on the loop, before any traffic.
- **Done when:** Hold PTT while an instructor starts a sortie and logs bearings: no audio dropout, no 'connection delayed' notice.

### X-4

**Console restart mid-exercise orphans the sortie**

`P1` · `high` · `bug` · Exercise console (backend) · cluster C7 (Console robustness) · effort M · wave 2 · **fixed**

- **Files:** `services/exercise/app/main.py:98-104,137-150,334,401-403`
- **Problem:** hub.sortie/scenario/aircraft/messages live only in process and are never rehydrated from SQLite on startup. After a restart the plugin's positions are discarded, /api/messages returns empty because it reads memory not the table, and the DB row keeps stopped=NULL forever.
- **Fix:** Fixed 2026-09-08. rehydrate() runs in lifespan: the most recent sortie with stopped IS NULL is reloaded with its scenario and last 100 messages. Aircraft are deliberately NOT restored - their positions are seconds stale and plugins re-report within seconds; a stale aircraft on the map is worse than a briefly empty one.
- **Done when:** Restart the container mid-sortie: aircraft reappear and the sortie can still be stopped and revealed.

### X-5

**One wedged WebSocket client stalls every broadcast**

`P1` · `high` · `bug` · Exercise console (backend) · cluster C7 (Console robustness) · effort S · wave 2 · **fixed**

- **Files:** `services/exercise/app/main.py:106-114`
- **Problem:** Hub.broadcast awaits send_text sequentially with no timeout, so one wedged tablet blocks the 1 Hz ticker and every HTTP handler that broadcasts. Half-open sockets never raise and are never dropped.
- **Fix:** Fixed 2026-09-08. broadcast() now sends to all clients concurrently with a 1 s per-client timeout (Hub.SEND_TIMEOUT_S) and drops anyone who times out or raises. A half-open socket never raises, so a timeout rather than an exception is what notices it.
- **Done when:** Suspend a tablet mid-exercise; other consoles keep updating.

### I-10

**TDFM-136B has no transmitter time-out timer**

`P1` · `medium` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort M · wave 2 · **fixed**

- **Files:** `instruments/cap-fm-tdfm-136b/logic.lua`, `tests/test_tdfm.py`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. The Lua logic transmits for as long as cap_fm_ptt is held. The real TDFM-136 has a hardware TOT (CAP standard 60 s) that unkeys, warns on the LCD and locks out until the key is released. Recognising a TOT cutoff and diagnosing a stuck mic is an ICUT practical exam item, and the ground web radio already has a 60 s server lease - so the aircraft is the only station that can jam the net indefinitely.
- **Fix:** Fixed 2026-09-08. Implemented 60-second transmit timeout timer in cap-fm-tdfm-136b/logic.lua that automatically force-unkeys, displays '*** TIME OUT ***' warning on the active LCD line, and enforces lockout until PTT release. Verified by tests/test_tdfm.py.
- **Done when:** A held PTT unkeys at 60 s with a visible warning and will not re-key until released.

### X-7

**Sortie lifecycle leaks state between exercises**

`P1` · `medium` · `bug` · Exercise console (backend) · cluster C7 (Console robustness) · effort M · wave 2 · **fixed**

- **Files:** `services/exercise/app/main.py:234-250,364,390,158-160`
- **Problem:** Starting a sortie while one runs leaves the old row un-stopped; after /stop, hub.sortie persists so bearings and messages keep attaching to the stopped sortie; log_bearing 404s for an aircraft whose last position is older than 30 s, which is plausible in real ops.
- **Fix:** Fixed 2026-09-08. Starting a sortie closes any still-open one (they used to keep stopped=NULL forever, so the debrief list showed two running and rehydrate would resume the wrong one). Bearings and messages no longer attach to a stopped sortie. A bearing whose aircraft has expired from the live map now falls back to that aircraft's last recorded position for the sortie instead of 404ing - a bearing passed over voice is often typed in after the 30 s expiry. DEVIATION from the tracker's suggested fix: hub.sortie is deliberately NOT cleared on stop, because reveal happens at debrief AFTER stop and needs it. POST /api/exercise/reset was not added; nothing needs it yet.
- **Done when:** Back-to-back sorties produce clean, separable records.

### B2-2

**Builder and fetcher donor paths differ**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `scripts/build_c182t_package.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 8.
- **Fix:** Resolved by 57663ec.
- **Done when:** 

### B2-4

**ACF patch application reported but not enforced**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `scripts/build_c182t_package.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 8.
- **Fix:** Resolved by 57663ec.
- **Done when:** 

### B2-5

**Prop-lever TRIS offsets hard-coded without validation**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 2 · **fixed**

- **Files:** `scripts/build_c182t_package.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 8.
- **Fix:** find_knob_tris asserts the counts.
- **Done when:** 

### B2-7

**generate_manual.py hard-codes another checkout and bakes /home/ron paths into tracked HTML**

`P2` · `medium` · `bug` · Docs / record · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `scripts/generate_manual.py`, `docs/manual/CAP_VSAR_Flight_Operations_Handbook.html`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 8.
- **Fix:** Repo-relative paths; HTML regenerated; the tracked PDF still has the old figures.
- **Done when:** 

### B2-9

**Docs site republishes manufacturer manuals**

`P2` · `medium` · `bug` · Docs / record · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `scripts/build_docs_site.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 8.
- **Fix:** Conservative default: vendor manuals no longer copied; links to docs/SOURCES.md. Ron to confirm the licensing call.
- **Done when:** 

### F2-3

**Form 110 table rebuilt under the MRO's cursor**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `services/exercise/app/static/mission-radio.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** Incremental row insertion; no rebuild while a traffic cell has focus.
- **Done when:** 

### F2-4

**Form 110 log lives only in page memory**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `services/exercise/app/static/mission-radio.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** Autosaved to sessionStorage and restored on load.
- **Done when:** 

### F2-5

**Shared role token stored in localStorage and solicited by prompt()**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `services/exercise/app/static/charts.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** Token path removed; 401/403 redirects to /login?next=.
- **Done when:** 

### F2-6

**Open redirect on the login page**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `services/exercise/app/static/login.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** safeNext() accepts only same-origin single-slash paths.
- **Done when:** 

### F2-7

**Debrief breaks after a sortie with no positions; no fetch error handling**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `services/exercise/app/static/debrief.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** State reset before the early return; .ok and exception handling.
- **Done when:** 

### I2-2

**TDFM copilot-PTT dataref does not exist**

`P2` · `medium` · `bug` · Air Manager instruments · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `instruments/cap-fm-tdfm-136b/logic.lua`, `docs/DATAREF_CONTRACT.md`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 6.
- **Fix:** Subscription and the contract's claim removed; cap_fm_ptt is the PTT path.
- **Done when:** 

### I2-4

**DF audio restarts the noise loop on every update**

`P2` · `medium` · `bug` · Air Manager instruments · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `instruments/_shared/lib/cap_df_audio.lua`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 6.
- **Fix:** noise_playing flag; transitions only.
- **Done when:** 

### L-1a

**Search-pattern labels are lost in the FMS export**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort S · wave 2 · **fixed**

- **Files:** `services/flightplanner/app.py:635`, `services/flightplanner/app.py:517-554`
- **Problem:** Found reviewing the L-1 fix. The pattern generators label points DATUM, SS01..SSnn, CS01, PS01, and the AOBD briefs the crew on those names - but the FMS writer now derives the identifier purely from coordinates, so the G1000 shows '+33.187_-117.079' for every leg. The brief says 'turn at SS04' and nothing in the cockpit says SS04. The plan still flies the correct positions; only the label is lost.
- **Fix:** Implemented: type 28 records preserve generator labels as uppercase ASCII letters/digits/underscores and keep separate coordinate columns, per https://developer.x-plane.com/article/flightplan-files-v11-fms-file-format/ (applies to X-Plane 12). File structure, labels and sanitization tested. Running X-Plane/G1000 display check remains unperformed and is documented in USER_GUIDE.md.
- **Done when:** Load an exported pattern in X-Plane 12 and read the leg names on the G1000 flight plan page.
- **Depends on:** L-1

### L2-2

**FMS export has no waypoint cap**

`P2` · `medium` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `services/flightplanner/app.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** MAX_FMS_ENTRIES = 99 counting departure and destination; generate-pattern reports exceeds_fms_limit. The real X-Plane/G1000 limit is unverified in the sim (see L2-14).
- **Done when:** 

### L2-3

**Five endpoints still return Werkzeug HTML 500 on bad input**

`P2` · `medium` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 2 · **fixed**

- **Files:** `services/flightplanner/app.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** _num/_text/_points helpers and a JSON errorhandler under /api/.
- **Done when:** 

### L2-5

**Nav log plans on invented winds offline**

`P2` · `medium` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `services/flightplanner/app.py`, `services/flightplanner/static/js/app.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** Simulated winds are not planned on; the route is planned in still air and says so.
- **Done when:** 

### O2-5

**deploy.sh does not know the board service**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 2 · **fixed**

- **Files:** `scripts/deploy.sh`, `docker-compose.yml`, `services/board/README.md`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** Board is an opt-in compose profile; deploy.sh enables it only when configured.
- **Done when:** 

### O2-6

**Board healthcheck cannot fail**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `services/board/app/main.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** 503 when the repo is not a checkout.
- **Done when:** 

### O2-7

**Runtime state lives inside the git checkout**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 2 · **fixed**

- **Files:** `docker-compose.yml`, `scripts/backup_exercise_db.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** CAPVSAR_STATE_DIR (default unchanged); backup includes the Mumble DB.
- **Done when:** 

### O2-8

**Backups have no restore path**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 2 · **fixed**

- **Files:** `scripts/backup_exercise_db.py`, `docs/LAB_HOSTED_DEPLOYMENT_PLAN.md`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** --restore mode, documented procedure, schema test.
- **Done when:** 

### P2-1

**Plugin disable/enable leaks a network thread**

`P2` · `medium` · `bug` · X-Plane plugin / engine · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 5.
- **Fix:** Worker captures its stop Event.
- **Done when:** 

### P2-3

**Default console URL unreachable and transport failures never logged**

`P2` · `medium` · `bug` · X-Plane plugin / engine · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 5.
- **Fix:** Front-door default; first failure and recovery logged once; SSL error class logged.
- **Done when:** 

### X2-5

**Blocking SQLite auth lookups on the event loop**

`P2` · `medium` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 2 · **fixed**

- **Files:** `services/exercise/app/routers/comms.py`, `services/exercise/app/radio.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** Session lookups use run_in_threadpool.
- **Done when:** 

### X2-6

**init_auth_db() runs a write transaction on every authenticated request**

`P2` · `medium` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 2 · **fixed**

- **Files:** `services/exercise/app/access.py`, `services/exercise/app/store.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** Schema init at startup only; one-SELECT session lookup; sweep on the ticker; synchronous=NORMAL and busy_timeout on auth_db().
- **Done when:** 

### X2-7

**Shared-radio watchdog belongs to the first face; one slow face fails the whole radio**

`P2` · `medium` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 2 · **fixed**

- **Files:** `services/exercise/app/radio.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** Radio-owned watchdog cancelled in close(); a full queue drops that face only.
- **Done when:** 

### AI-22

**fly_arduplane_backend: a refused gate.acquire() left SITL flying the aircraft**

`P0` · `critical` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort S · wave 3 · **fixed**

- **Files:** `scripts/fly_arduplane_backend.py`
- **Problem:** gate.acquire() sat OUTSIDE the try/finally that calls cleanup(). On the first live attach (2026-09-17) ArduPlane booted into RTL and banked the aircraft to 80 degrees before acquire() ran; the gate correctly refused with 'Aircraft outside the configured airborne exercise envelope', the ValueError propagated out of main(), and cleanup() never ran - so SITL kept the X-Plane joystick/throttle override and kept flying CAP 487 into a spiral dive (4474 ft -> 1825 ft, 183 KIAS) until the process was killed by hand. Same class as AI-21: a path where SITL outlives its supervisor.
- **Fix:** acquire() and submit() moved inside the try, with a ValueError handler that records the refusal as the cleanup reason. Every path after the SITL process starts now reaches cleanup(), which parks ArduPlane, stops SITL, clears both overrides and re-engages the GFC 700. Verified by dry run; 73 offline tests pass.
- **Done when:** A refused acquire (aircraft outside the envelope) stops SITL, clears override_joystick/override_throttles to 0 and hands the aircraft to the GFC 700.
- **Depends on:** AI-21

### A-1

**CAP 487 retains the stock C172S airframe geometry and exterior**

`P0` · `high` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort L · wave 3 · **open**

- **Files:** `scripts/build_c182t_package.py`, `scripts/fetch_flightgear_c182.py`, `scripts/convert_flightgear_c182.py`, `tests/test_flightgear_c182.py`, `docs/FLIGHTGEAR_C182_GPL_PLAN.md`, `docs/SOURCES.md`, `README.md`, `NOTICE`, `docs/C182T_DIMENSION_MASTER.md`, `scripts/c182t_dimension_master.json`, `scripts/measure_c182t.py`, `tests/test_c182t_measurements.py`, `tests/fixtures/c182t_landmarks.json`, `docs/C182T_MEASUREMENT_HARNESS.md`
- **Problem:** The CAP 487 builder copies Laminar's Cessna 172 SP package and patches identity, engine, propeller, weights, fuel, cowl flaps and V-speeds, but it does not replace the Plane Maker body, wing, tail, gear or exterior meshes. A direct ACF comparison found no airframe-geometry changes, and the installed fuselage.obj, wings.obj, fuselage_gear.obj and fuselage_prop.obj are byte-for-byte identical to the stock 172 files. CAP 487 therefore presents and partly flies as a C172S under C182T identity and performance data. The real 182T is 29 ft long and 9 ft 4 in high; the 172S is 27 ft 2 in long and 8 ft 11 in high, with material differences in cowling, fuselage, landing gear, tail and three-blade propeller despite their similar span.
- **Fix:** Local prototype implemented 2026-09-11. The builder now requires the pinned HHS81/c182s donor at commit 1359d63393c7fc9145953b081d151d93627e791a, converts its shared C182S/T exterior from AC3D to OBJ8 without Blender, and replaces the stock C172 fuselage, wing, gear, propeller, glass, light and broken-part attachment slots. It generates a CAP 487 texture, animates the primary control surfaces and three-blade propeller from X-Plane datarefs, and embeds the donor GPL text, provenance manifest and local-prototype notice in the generated aircraft. Donor and generated assets remain outside the Apache git tree. The installed package was rebuilt after preserving the prior aircraft beside it as Cessna 182T NAV III.pre-flightgear-20260911-20260911. The public-release alternatives and GPL source/notice gate are recorded in docs/FLIGHTGEAR_C182_GPL_PLAN.md. A-1 remains open because the Plane Maker aerodynamic geometry is still inherited from the C172 and the exterior has not yet passed an X-Plane visual and dimensional acceptance. STAGE 3 STARTED 2026-09-15 (0d6da2a): propeller diameter corrected 79.255 -> 78.9998 in, inside the TCDS 77.5-79.0 band. Checked for a global scale fault first and ruled it out - errors run -4.64 to +2.16 percent with differing signs, so the regions are independently wrong. Corrections are parametric and version-controlled (scripts/c182t_corrections.json) rather than baked into a mesh, because the donor is GPL and stays outside the repo, and the same module is applied by both the converter and the harness so what is measured is what is emitted; --raw still reproduces the stage-2 baseline. The hub and axis are fixed points of the transform, so no animation pivot moved. SUPERSEDED 2026-09-15 - see verify: main_wheel_track and horizontal_tail_span were BOTH corrected later the same day, so this sentence no longer describes the state. A-1 stays open on Plane Maker aerodynamic geometry, full X-Plane visual acceptance of the corrected exterior, and the registration's aft-fuselage placement; the production licence route left scope by decision D-7. VISUAL ACCEPTANCE RUN 2026-09-18 (acceptance item 4, first time performed): about forty UDP-driven screenshots of the parked aircraft - exterior orbit from four quarters plus overhead and close, full control deflection against a neutral reference, night with every switch on, and the pilot's seat. PASS: silhouette, CAPP 130-2 scheme, three-blade propeller and disc, wheel fairings, donor door outlines and rivets, and the primary control-surface animations (elevator 21 deg, rudder 24, ailerons +15/-20, confirmed by dataref readback and by frame differencing against the neutral frame). FAIL, in priority order: (1) the donor exterior is drawn into the cockpit view single-sided, because write_obj8() sets ATTR_no_cull only in glass mode: a mirrored pair of correctly mounted donor windscreen-corner probes at x +/-0.55, y 0.37, z 0.00 appears to float over the cowl because the surrounding cowl and frame skin is back-facing and culled from inside, the exterior glazing (which does carry ATTR_no_cull) lies across the windscreen and the MFD, the window apertures fringe black at the culled skin edges, and both struts show livery colour. A fore-and-aft misregistration was tested and DISPROVED - the exterior encloses the interior with 8-20 cm of roof clearance at every station and the two windscreens agree within 10 cm; (2) PlaneX, Plane.002X and Plane.003X are 1.8 m light-halo billboard quads swept into the lights object by texture-bucket selection and drawn through the cabin; (3) no LIGHT_NAMED or LIGHT_PARAM point light exists anywhere in the package, so nothing glows or casts at night, and the beacon and strobe have no geometry at all because BeaconOff and Strobe sit in KNOWN_UNCONVERTED as dimension landmarks; (4) the donor's black decal stripe bleeds through the red fin because the repaint multiplies by donor luminance without masking it; (5) the tailcone red/white boundary aliases where mesh triangles exceed the four-level subdivision; (6) registration and USAF AUXILIARY titles remain on the cabin - the known degenerate aft-fuselage UV column; (7) overall length, overall height and wheel base remain outside their bands at 28 ft 3.4 in, 9 ft 0.9 in and 64.4 in. NOT VERIFIED: flap travel and panel night lighting, both of which need the battery on; this pass deliberately left the aircraft unpowered. PARTIAL FIX 2026-09-18, verified in the running simulator: finding (2) is CLOSED - PlaneX/Plane.002X/Plane.003X are excluded and the exclusion is now applied to the texture bucket as well, so the pale wedges over the windscreen and the MFD are gone from the pilot's view; a before-and-after from the same seat also shows the earlier attribution of those wedges to the exterior glazing was wrong. Finding (3) is HALF closed - LIGHT_NAMED point lights are emitted for nav left/right, nav tail, both strobes, beacon, landing and taxi, with names taken from X-Plane 12's own Resources/bitmaps/world/lites/lights.txt and positions measured from the donor's lamp objects after corrections, a missing lamp raising rather than defaulting; Strobe spans both wingtips as one object so it yields a light at each span end rather than one in the cabin. Confirmed powered: bus 24.5 V, nav 1.00, beacon cycling 0.00-0.88, landing/taxi 0.79, and photographed at night from three quarters. Beacon and strobe GEOMETRY is still absent. Separately, FLAP TRAVEL IS NOW VERIFIED (38.0 deg down, 0.0 up, both flaps visibly deflected) - it needed the battery on, which the acceptance run had deliberately not done. tests/test_flightgear_c182.py 36 -> 43, each new test observed to fail against the unfixed code first. Findings (1), (4), (5), (6) and (7) are untouched. FINDING (1) CLOSED 2026-09-18: the windscreen-corner probes - the 'handle floating over the cowl' as reported - are emitted into their own draw group wrapped in ANIM_hide 0.000000 0.500000 sim/graphics/view/view_is_external, the same dataref and values Laminar uses for pilot.obj in this package, so they draw from outside and are hidden from the 3-D cockpit; readback confirms view_is_external is 0.0 in the cockpit and 1.0 outside. Hidden, not deleted: triangles are conserved 24,908 -> 24,908, Airframe 11,287 -> 10,487 plus 800 in Airframe.cockpit_hidden, and the texture is byte-identical because the split runs after the livery is rasterised. Capture is by CONNECTED COMPONENT welded by vertex position and only when the whole component lies inside a region, so the main skin - one component spanning the aeroplane - can never be taken however the boxes are drawn; a region capturing nothing raises, because these boxes are measured against the corrected geometry. The two regions took exactly the 800 triangles measured in the acceptance run and nothing else. Verified in the simulator from the framing that showed the fault. tests 43 -> 50; the two safety properties were re-run with the rules weakened (any-vertex capture, index welding) and both tests fail as they should.
- **Done when:** Completed: the pinned archive SHA-256 matched d81628fff8489af41d312c0e0bc14e1de2ac10a50d6c0c75f937441f81343fbe; a clean staging and installed build applied 40/40 ACF patches and generated 26,867 structurally valid OBJ8 triangles; all ten stock exterior/crash attachment slots point to the new C182 objects or an intentional blank; the installed main OBJ SHA-256 matches staging; converter and donor-integrity tests pass (5/5); console/radio regression suites pass (90 tests and 17 subtests). Orthographic projections confirm the axes and silhouette. The donor-native overall bounds are about 8.50 m long, 10.91 m span and 3.22 m high, so it is an approximate visual donor rather than the authoritative 8.84 m by 10.97 m by 2.84 m dimensional acceptance master. Outstanding: load it in X-Plane and inspect exterior/cockpit/night views, animation and alignment; resolve the donor dimension differences against a C182T three-view; calibrate Plane Maker body, wing, tail, gear, mass, CG and aerodynamics against the selected POH; and complete the production license route before any redistribution. Stage 1 of the dimensional correction (measurement master) completed 2026-09-11: targets sourced from the FAA-approved 182T NAV III GFC 700 POH (182TPHBUS-00/-01), TCDS 3A13 Rev 66 and Cessna's Dec 2015 Rev C Specification and Description, recorded with page and SHA-256 in docs/C182T_DIMENSION_MASTER.md and scripts/c182t_dimension_master.json. The POH fixes normal ground attitude (nose strut approximately 2 in, wings level), the datum (lower front face of firewall, so the cockpit anchor is FS 0), and the endpoints: length runs spinner apex to rudder trailing edge and the 36 ft 0 in span includes wingtip strobes. Nine items including wing root, hinge-line, tail and individual gear stations are unpublished and are recorded as unknown rather than invented. Preliminary donor deltas under these endpoint rules: span -0.37%, length -3.83%, wheel base -3.64%, track -4.64%, height +8.58%, propeller 79.17 in against a 77.5-79.0 in certificated band; no uniform or per-axis scale reconciles these. The donor's nose wheel contact sits 131 mm below its main-wheel plane, so its height and propeller ground clearance are provisional until the mesh is re-posed. Still outstanding: the stage-2 measurement harness, the regional geometry correction, X-Plane visual acceptance, Plane Maker calibration and the production license route. X-Plane 12 visual acceptance run 2026-09-11: the exterior FAILS. The sim was first found rendering a stale pre-rebuild load (X-Plane loaded the aircraft at 09:50:47, the rebuild wrote at 09:56:11), which mimics the stock 172SP exactly; acceptance runs must issue sim/operation/reload_aircraft first. After reload: cabin reads see-through to the Laminar interior, CAP 487 registration renders mirrored, and a magenta patch appears at the firewall. Ruled out with data: texture alpha (flightgear_c182t.png is 100% opaque), inverted winding (closed convex objects measure 100% outward; a flipped model would read 0%), and interior protrusion (skin half-width 0.635 m vs Laminar cockpit 0.560 m, floor clears seats by 65 mm). Defect found and guarded: bucket selection keys on texture name, so all 37 untextured donor objects of 88 were dropped silently - 28 correctly (ground-service clutter and duplicate LODs) but by accident, and 9 as real gaps (Strobe, NavLight.L/R, NavlightTransp, BeaconOff, and the four Windscreen interior/side parts). Strobe and BeaconOff matter dimensionally: published span is defined with strobes installed and published height is measured to the fin tip. convert_flightgear_c182.py now classifies every donor object via DELIBERATELY_EXCLUDED/KNOWN_UNCONVERTED and assert_all_objects_classified raises on anything uncovered; the guard is a pure function testable without the donor cache (suite now 9 donor-free tests). Behaviour-preserving: all five OBJs rebuild byte-identical. Also confirmed 0 of 40 ACF patches touch wing/body/gear/tail geometry. Still outstanding: the see-through cabin, mirrored registration and magenta firewall patch are unexplained; the 9 unconverted objects are not yet emitted; Plane Maker geometry, dimensional correction and the production license route are untouched. Second X-Plane session 2026-09-11 isolated the fault but did NOT find the cause. Swapping only ACF slot 15: stock fuselage.obj renders the cabin SOLID, our flightgear_c182t.obj renders it see-through with a magenta firewall patch - so the Laminar interior is not overdrawing and the fault is in the converted object. Eliminated against our object, each tested in the sim: texture alpha (rebuilt RGB), object header (stock TEXTURE/TEXTURE_LIT/TEXTURE_NORMAL and GLOBAL_specular 1.0), all ANIM blocks stripped, a single group with one TRIS and no other geometry, glass rebuilt fully opaque, and ACF slot 18 restored to stock wings.obj. Data is clean: 16,081 VT lines with zero NaN/Inf, zero zero-length or non-unit normals, UVs 0.004-0.996, and the cabin skin measures 98.4% outward on the port side. An offline OBJ8 rasteriser (z-buffer, backface cull) renders the same data as a complete solid fuselage with openings only at the window apertures. Correction to the previous note: the glazing change was wrong - Windscreen.Int/.Int.Back/.Side.Left/.Side.Right are interior surfaces (2/320, 2/66, 0/49, 0/49 outward/inward), now in a documented INTERIOR_ONLY set; dropped glazing did NOT cause the see-through cabin. The converter also narrowed KNOWN_UNCONVERTED to five light fixtures (Strobe, NavLight.L/R, NavlightTransp, BeaconOff) and changed create_cap_texture's rotate(180) to FLIP_TOP_BOTTOM, which remains UNVERIFIED because the hardcoded stamp coordinates were never confirmed against a UV island. Process notes: a zero-geometry object in glass slot 19 crashes X-Plane on load; pgrep -x 'X-Plane-x86_64' never matches (comm is 'Main Thread') and a false 'sim is down' reading led to a second instance whose RakNet UDP init failed, requiring a restart. Next unit: hand-write a minimal OBJ8 box at the cabin station and test occlusion offline before touching a live flight. ROOT CAUSE FOUND 2026-09-11: the see-through cabin is a triangle-winding bug. X-Plane winds triangles opposite to the stored vertex normal - Laminar's own objects/fuselage.obj shows 0.0% winding/normal agreement across 752 cabin-side and 212 tailcone faces - while AC3D winds the other way and _build_mesh emitted AC3D's ref order directly, giving 83.8% agreement, so X-Plane culled the near-side skin of every surface. That one fault explains all symptoms: the exposed cabin, the tailcone and cowl still looking solid (you see the inside of the far wall), and the magenta firewall patch (interior showing through culled cowl skin); it also explains why header, texture, alpha, ANIM and grouping all tested negative, since faces were discarded before any of that applied. The earlier offline rasteriser missed it because it culled using the same convention the converter assumed. Fix: _build_mesh emits each triangle's refs reversed while normals stay computed from the original order, moving the cabin band from 82.8% winding-outward / 83.8% agreement to 3.8% / 2.9% against the stock reference's 8.0% / 0.0%. Locked by WindingConventionTests.test_winding_opposes_the_stored_normal (donor-free); converter suite now 10 tests. CAVEAT: verified offline only - the corrected build has not been seen rendering in X-Plane, and one aircraft reload is needed to confirm. Still outstanding regardless: the CAP 487 registration placement (hardcoded UV stamp coordinates, unverified) and the five unconverted light fixtures. CONFIRMED IN X-PLANE 2026-09-11: the winding fix works. A fresh sim start (12:02:37) loaded the corrected objects (installed 11:59:42) and the 12:03:50 capture shows a SOLID cabin, the magenta firewall patch GONE, correctly transparent windows and a proper C182 silhouette - the see-through cabin, magenta patch and exposed interior were all the one winding bug. The offline-only caveat is lifted. Revealed by the fix: the CAP 487 registration is still wrong - on the PORT side it renders mirrored and sits too low, running off the fuselage side into the belly curve. Since the port side is painted by the un-flipped stamp at texel (1590,505), the atlas-band identification was wrong and the FLIP_TOP_BOTTOM change was applied to the wrong stamp; placement and per-side orientation remain unverified. Settle it empirically by stamping a labelled asymmetric test grid across the atlas and reading off which region paints which side, since two attempts to derive it from UV geometry failed. Exterior now confirmed working for geometry, winding, cabin, glass, gear, wing, tail, control surfaces and nav light; still outstanding are the registration and the five unconverted light fixtures, plus the untouched stock-C172 Plane Maker geometry. Flight-model audit 2026-09-11 with correction. The repeated claim that CAP 487 'flies like a C172' is NOT supported: the C172S and C182T share essentially the same wing, and the installed ACF measures 36.20 ft span (+0.56% vs 36 ft 0 in) and 173.04 ft2 area (-0.55% vs 174.0 ft2) on NACA 2412, with mass (1,970/3,100 lb), engine (230 HP, 2,400 RPM, RCP_INJ) and propeller (3 blades, 2,400 design RPM) already correct. '0 of 40 patches touch geometry' is true but misleading about aerodynamic effect. What WAS wrong: control-surface travels were stock C172S values - elevator 20/15 against TCDS 3A13 28/21, rudder 20 against 24, flap full 30 against 38, ailerons already correct at 20/15. Five patches added to ACF_PATCHES (now 45), each verified to match exactly one ACF record, applied, and LIVE-VERIFIED after reload: acf_elev_up 28.0, acf_elev_dn 21.0, acf_rudd_lr 24.0, acf_ail1_up 20.0, acf_ail1_dn 15.0. Added tests/test_c182t_flight_model.py (7 donor-free tests) in its own file to avoid the lane handed to Codex. Still outstanding in the flight model: horizontal tail span 11.20 ft vs the POH's 11 ft 8 in (-4.0%, geometry, untouched); vertical tail has no published target and is recorded unknown; and CG limits cannot be compared until the mapping between ACF z and the Cessna fuselage-station datum is derived - do not compare _cgZ_fwd 2.90/_cgZ_aft 3.90 ft to the TCDS 33.0-46.0 inch range before then. CG envelope corrected 2026-09-11 and the ACF datum blocker resolved. The firewall is still not located in X-Plane's frame and did not need to be: %MAC is datum independent, and TCDS 3A13 gives MAC 58.8 in with the MAC leading edge at FS 25.98 in. That required settling one convention: _wing/0/_part_z is the root QUARTER-CHORD, not the leading edge - a 1.30 ft / 27% MAC difference. Confirmed empirically against the donor mesh (which shares the ACF part frame, itself confirmed by the ACF engine reference at -1.134 m sitting 14 cm aft of the donor prop disc at -1.274 m): predicted vs measured wing LE agree within 11-12 mm at two clean spanwise stations against a 396 mm discriminator, and tip chord measures 3.63 ft vs the ACF's 3.60 ft. Integrating the ACF planform gives MAC 58.04 in vs TCDS 58.8 in (-1.3%), a third independent confirmation - with span +0.56% and area -0.55% - that the C172S-derived wing is already a correct C182T wing. Corrected: _cgZ_fwd 2.900 ft (18.73% MAC) -> 2.571 ft (FS 33.0 in, 11.94% MAC); _cgZ_aft 3.900 ft (39.40% MAC) -> 3.641 ft (FS 46.0 in, 34.05% MAC). The stock aft limit sat 5.35% MAC (~3.1 in) aft of the certificated limit, the stability-reducing direction. LIMITATION: the TCDS forward limit is weight-scheduled and X-Plane takes one value, so the most forward certificated point is used - correct at light weights, permissive at heavy ones; modelling the taper needs a loading-system change. acf/_cgZ left at 2.900 ft as the reference CG, now inside the envelope at 18.73% MAC. LIVE-VERIFIED after reload: X-Plane reports the limits relative to the reference CG, acf_cgZ_fwd -0.1003 m and acf_cgZ_aft +0.2259 m, matching 2.571-2.900 and 3.641-2.900 to the millimetre. ACF_PATCHES now 47; tests/test_c182t_flight_model.py now 11 tests. Flight model still outstanding: horizontal tail span 11.20 ft vs the POH's 11 ft 8 in (-4.0%), and the vertical tail, which has no published target and stays unknown. Stage 2 offline metrology completed 2026-09-11: scripts/measure_c182t.py emits deterministic JSON and side/front/top SVGs using named donor landmarks, strict existing parser, separate structural/rendered bounds and axis-derived propeller disc. Numeric fixture tests run without donor access. Prop diameter 79.255 in fails the 79.0 in hard maximum; main wheel track 102.992 in (-4.64%) and horizontal tail span 143.026 in (+2.16%) fail proposed tolerances. Ground-contact re-posing makes length, height, wheelbase and clearance provisional until the two-inch nose-strut condition is verified. Package span/height acceptance is blocked by unconverted Strobe/BeaconOff. All 9 unknowns and absolute donor FS for all 15 reference stations remain unmeasured; no donor firewall datum is invented. Two fresh donor-only builds plus reports are byte-identical (14 files), fixture replay equals live report, 25 converter/harness tests pass live or 24 pass plus one optional live skip with real cache reads denied. Console/radio 90 passed plus 17 subtests; git diff --check passes. Durable caches and test venv moved under ~/.cache/capvsar/ with strict hashes and compatibility links. See docs/C182T_MEASUREMENT_HARNESS.md. No geometry corrections or simulator actions in this unit. A-1 remains open; prior concurrent flight-model progress is preserved. Horizontal tail span corrected 2026-09-11 (flight-model lane, concurrent with the harness unit): the POH three-view (Fig 1-1 Sheet 1 p.1-3) gives 11 ft 8 in and the ACF had the stock C172S 11.200 ft, so _wing/8 and _wing/9 _semilen_SEG go 5.300 -> 5.53333 ft, giving exactly 3.5560 m; aircraft reloads clean. This is the surface the elevator acts on and the elevator got its certificated 28/21 travel earlier today, so leaving it 4% undersized would have kept pitch authority short by another route. Chords unchanged so per-side area rises 20.70 -> 21.55 ft2 (+4.1%); direction is right but NO source publishes a C182T horizontal tail AREA, so only span is verified and the area is a consequence, not a target. Null result: the ACF's Vs 51 / Vso 41 KIAS already match POH Fig 2-2 airspeed indicator markings exactly (green 51-140, white 41-100) and were not touched. Added docs/C182T_FLIGHT_TEST_CARD.md with sourced POH targets - stall speeds at 3,100 lb for flaps up/20/FULL at both CG limits, 924 FPM sea-level climb, 150 KTAS max, 145 KTAS at 80%/7,000 ft, takeoff and landing distances - each with entry conditions, tolerance and guidance on reading a miss. Point A3 (power-off stall, FULL flap, expect 41 KIAS) is the most diagnostic, since full flap was 30 deg until today and is now the certificated 38. Added scripts/capture_flight_test.py, READ-ONLY telemetry capture (RREF subscriptions only, no DREF writes, no commands) so live control stays reserved for services.ai_pilot.maneuver_server per AI-1/AI-2; smoke-tested against the live sim and it correctly flagged the current 2,782 lb loading against the card's 3,100 lb condition. ACF_PATCHES now 49; tests/test_c182t_flight_model.py now 14 tests. IMPORTANT: every flight-model correction made today is verified STATICALLY ONLY - correct value in the correct ACF record, confirmed by dataref after reload. None is verified in flight. Flight model remaining: the vertical tail (no published target, stays unknown) and the in-flight validation itself, now blocked only on someone flying the card. EXTERIOR LIVERY SOURCED 2026-09-15: the CAP 487 registration rendered mirrored and ran off into the belly curve because both stamps sat at x>=1530 while the measured side panels end at 1479 (painted onto the tailcone), and because starboard needs a 180-degree ROTATION - u runs leftward viewed from that side AND v is inverted - where the code used FLIP_TOP_BOTTOM, which leaves exactly the horizontal mirror observed. The scheme itself had been invented from an impression; it is now taken from CAPP 130-2 'CAP Aircraft Painting and Marking' 4 October 2021 (SHA-256 8aead1f9ca5f60793c879359e7b77ff134a26b8f50d4131fc1f20fbea6932f0b), whose line drawing A is a SKYLANE: white upper, BLUE lower, RED vertical tail, gray/red stripes on the division, registration in WHITE 12-inch vertical block, UNITED STATES AIR FORCE AUXILIARY on the aft fuselage (CAPR 130-2 15.5). Colours sampled from that drawing's paint legend: Matterhorn White AF3102, Blue 753046, Gray 753048, CAP Red A07313. Insignia are deliberately absent - CAPP 130-2 says ALL DECALS PROVIDED BY CAP and CAPR 130-2 15.2 forbids wing logos and tail flashes. Rectangle painting was replaced by scheme_colour()/paint_scheme(), which decides colour from 3D POSITION and rasterises through the mesh UVs: the fuselage sides unwrap as axis-aligned bands (corr +/-1.00) but the belly and wings do not (+0.01..+0.90, -0.66..+0.85), so rectangles left the belly white and the fin a red band. Straddling triangles subdivide to 4 levels so a 2-inch stripe survives; repaint takes 3 s. New colour is multiplied by donor luminance so baked window frames, door outlines and rivets survive, and the repaint is masked to skin so a panel bbox does not paint unrelated atlas islands. OUTSTANDING: the registration sits on the cabin, not the aft fuselage, because the donor maps the aft fuselage side to a DEGENERATE SINGLE COLUMN at x=2204 with no width to paint into - re-UV work.  HORIZONTAL TAIL SPAN, MESH, CORRECTED 2026-09-15 - NOT the 2026-09-11 entry of the same name, which was the ACF flight model; both now exist and must not be conflated. The recorded blocking reason was wrong: Airframe does NOT carry the stabiliser. At z 4.8-6.3 it holds 738 vertices at |x|<=0.2 (tailcone and fin) and 156 at |x| 1.600-1.816 with nothing between - tip caps only; the surface is the Elevator object (427 verts, |x| 0.510-1.821) plus ElevatorTrim. The transform therefore never touches Airframe broadly: it selects the tail by a z-window proven to contain zero wing vertices (wings are at z 0.548-1.815, three metres forward), checked before writing and pinned by a test that feeds a wingtip to the selector and requires rejection. region_scale_with_root_blend anchors at the root station |x|=0.51 m where the elevator meets the fuselage, so that junction is a fixed point and cannot tear; a scale about the CENTRELINE would have dragged it inboard. Elevator and ElevatorTrim take the same transform whole, preserving the donor's 0.189 in per side overhang rather than flushing it. Harness-measured: error 3.026 in (+2.162%) -> 0.003 in (+0.002%), inside 138.6-141.4 in; every other dimension unchanged, wing_span still -0.374%. tests/fixtures/c182t_landmarks.json regenerated - it still carried the old 1.8164 m half-span, so the replay tests were self-consistent against geometry the converter no longer emits. Package rebuilt: 436 vertices for the propeller, 594 for the tail. A-1 STAYS OPEN: main_wheel_track remains deliberately blocked (the POH drawing does not say whether its dimension lines mark wheel centre or tyre outer face; the readings are -4.64% and +1.34%, so the ambiguity flips the SIGN and it is a reading of the source, not a measurement), and Plane Maker aerodynamic geometry, X-Plane visual acceptance of the corrected exterior and the production license route are untouched. MAIN WHEEL TRACK CORRECTED 2026-09-15, and the reading behind it is INFERRED rather than read. The POH is not held by anyone on this project, so the ambiguity that had blocked this - the drawing does not annotate whether its dimension lines mark wheel centre or tyre outer face, and the two readings flip the SIGN (-4.64% too narrow vs +1.34% too wide) - was settled on three converging grounds rather than by looking. (1) The POH's own NOTE, for the companion gear dimension on the same three-view, measures wheel base to the main wheel CENTRE LINE (dimension master line 96, POH Fig 1-1 Sheet 2 NOTE); a drawing annotating one gear dimension to the centreline is not measuring the other to the tyre faces. (2) Consistency, which is arithmetic: overall length -2.48%, overall height -2.78% and wheel base -3.64% are all undersized, so centre-to-centre makes the gear uniformly small like the rest of the airframe, whereas the outer-face reading makes track the ONLY oversized dimension on the model and has it 1.34% wide while its own wheelbase is 3.64% short. (3) Standard convention measures landing gear track centre to centre; FAA-H-8083-31B uses 'tread' for the TYRE's rubber crown, which is the likely origin of the doubt. SOURCES CHECKED AND SILENT: EASA/FAA TCDS 3A13 gives datum, levelling means and 6.00x6 main tyre size but no tread; Cessna's Specification and Description Skylane 182T Dec 2015 Rev C lists height, length, span, cabin and doors and no wheel track at all. THE TRANSFORM is gear_track_widen, not a spanwise scale: scaling the wheel about an inboard root would widen the TYRE as well as move it, taking the donor's 164 mm wheel to 193 mm, so MainWheel and WheelFairing TRANSLATE rigidly by 0.0636 m (2.5 in) per side while only MainStrut ramps, its inboard attachment at |x|=0.938 m held fixed and its outboard end taking the full delta - the spring leg flexing outward rather than growing. Verified: tyre width unchanged to 1e-9 at 0.1641 m, fairing width unchanged at 0.2366 m, strut attachment moved 0.000000 m, wheel centre 1.3080 -> 1.3716 m. Harness: main_wheel_track -4.637% -> -0.000%, measured 107.9996 in against a 108.0 in target; every other dimension unchanged. Seen in X-Plane after rebuild and reload, gear intact with no tear at the strut. All three stage-3 dimensions are now corrected and nothing in the profile is blocked. This is the MESH, not the ACF flight model's gear geometry. A-1 STAYS OPEN: Plane Maker aerodynamic geometry, full X-Plane visual acceptance of the corrected exterior, the registration's aft-fuselage placement (blocked by a degenerate donor UV column) and the production license route are all untouched. DECISION D-7 (Ron, 2026-09-15): the PRODUCTION LICENCE ROUTE is out of scope and A-1 no longer carries it as outstanding work. The prototype stays local and the exterior continues on technical merit. Recorded in docs/FLIGHTGEAR_C182_GPL_PLAN.md; full reasoning belongs in the vault decisions file. Ron's reasoning is that the exterior is converging on the real C182T shape, so the result is progressively less like the HHS81 donor's model and closer to what Cessna designed. That is right about the direction of travel, and three things it does NOT change are recorded so nobody re-derives them. (1) No percentage clears derivation: the corrections are parametric transforms applied to the donor mesh at load time and build_c182t_package.py refuses to run without the pinned donor cache, so the build is derivative however far the vertices move. No action needed - the architecture already handles it, with the donor outside the repo, GPL text and provenance inside the generated package, and the repo itself Apache. (2) The binding constraint on redistributing the BUILT PACKAGE is the Laminar Research C172 cockpit and systems it contains, per the plan's own 'Current decision' and release-gate item 4 - not the donor and not Cessna, and it does not move with mesh accuracy because it is not about the mesh. (3) The repository mirror is unaffected: donor and Laminar files are already excluded from the repo, so D-6's public mirror is not gated on this. On Cessna: design patents on a 1956-origin airframe are long expired; what remains live is trademark and trade dress - the Cessna and Skylane marks and the tail script - none of which this package applies, since it wears CAP markings drawn from CAPP 130-2 rather than traced. Scope decision about a local prototype, not legal advice. A-1's remaining outstanding work is therefore Plane Maker aerodynamic geometry, full X-Plane visual acceptance of the corrected exterior, and the registration's aft-fuselage placement. FLIGHT MODEL FLOWN 2026-09-15, two points, both MISS, and the result moves the diagnosis. B1 rate of climb: 825 fpm at sea level against 924 +/-10%, -10.7%, extrapolated from 800 fpm measured at 720 ft by a fit over 2,602 stabilised samples (ROC = 824.9 - 0.0428h, decay 42.8 fpm per 1,000 ft); the raw figure misses by 13.4% so the verdict does not depend on the correction. C1 max speed: 130.1 KTAS against 150 +/-5, -13.3%, over 1,139 samples with spread 0.0 and drift 0.0 - fully stabilised. Both at 3,100 lb max gross, CG FS 44.4-44.5 in (aft, inside the 40.9-46.0 certificated envelope at max gross), flaps 0, confirmed standard day (OAT 10.0 C vs ISA 10.0 C, density ratio 0.9285 vs ISA 0.9284, wind 0). The aft CG reduces tail download and would if anything FLATTER climb, so it does not excuse the shortfall. THE CARD'S SUGGESTED DIAGNOSIS IS WRONG FOR THIS DATA: it says a low B1 means engine or propeller modelling, but at the C1 condition the engine turns 2400.002 RPM against a rated 2400 at 29.3 inHg and makes 214.0 HP against a rated 230, which is 93%, and the propeller governor holds rated RPM exactly. A 7% power shortfall cannot produce a 13.3% speed shortfall - power required goes as the cube of speed, so 93% power costs about 2.4% of speed. Inverting the measurement, (130.1/150)^3 = 0.652 against 0.930 of actual power implies about 1.43x the drag, or that much less propulsive efficiency. That is DRAG or PROPELLER EFFICIENCY, both Plane Maker parameters rather than mesh geometry, and it corroborates this item's own outstanding note that Plane Maker aerodynamic geometry is still inherited from the C172 and never calibrated against the 182T POH. Today's exterior corrections cannot be the cause: X-Plane takes drag from the ACF, not the OBJ. The 93% power figure is a second, smaller finding worth its own look. Traces B1_run2_20260915-224521.jsonl and C1_run1_20260915-230143.jsonl; reduction by scripts/reduce_climb_point.py and scripts/reduce_cruise_point.py. C2 and Group D unflown; Group A remains blocked by the 90 KIAS maneuver-gate floor. ROOT CAUSE OF THE FLIGHT-MODEL MISSES FOUND 2026-09-15, by diff rather than inference. Comparing Cessna_182T_G1000.acf against the Laminar Cessna_172SP.acf it was copied from, restricted to aerodynamic parameters: _wing/ has 16,228 parameters of which exactly TWO differ (_wing/8 and _wing/9 _semilen_SEG, both 5.53333, the horizontal stabiliser half-span corrected 2026-09-11), and _body/ has 7,356 parameters of which ZERO differ. Wing area, chord, airfoil, sweep, dihedral and every fuselage cross-section that sets parasite drag are byte-identical to the C172SP. This item has always recorded that 0 of 40 ACF patches touch wing/body/gear/tail geometry; this is the first measurement of what that COSTS in flight. The flight test agrees to 2.5%: at the C1 condition the engine makes 214.0 HP, and scaling published max speeds by the cube root of power gives 126 x (214/180)^(1/3) = 133.5 KTAS for a C172 airframe against 150 x (214/230)^(1/3) = 146.4 KTAS for a C182T airframe; measured was 130.1 KTAS, 2.5% from the C172 prediction and 11.2% from the C182T one. B1 follows by the same reasoning - climb rate is excess power over weight, and this is 172 aerodynamics lifting 3,100 lb, beyond the 172's own 2,550 lb maximum - so both misses have ONE cause. This retires the card's suggested diagnosis for a low B1 ('engine or propeller modelling, not geometry'): the engine turns rated RPM at 29.3 inHg and makes 93% of rated power, and a 7% power shortfall cannot produce a 13.3% speed shortfall. It does NOT license editing drag parameters to make numbers come out - the defect is an unconverted aerodynamic definition and the fix is the Plane Maker calibration against the 182T POH already listed here. DECISION D-8 (Ron, 2026-09-15): AIRCRAFT FIDELITY FORKS FROM EXERCISE-SYSTEM DEVELOPMENT. A-1 no longer gates the SAREX path; it becomes a fidelity track with its own timeline. Reason: the flight-test work was bogging down system development. The fork is available because the exercise system barely touches the aircraft - xplane/ contains ZERO references to the 182T because the DF propagation engine is a global plugin in Resources/plugins, the MO panels are Air Manager, and the radio, console and planner are separate services, so the Becker and RT-600 are already not fitted to this airframe. A-1 is the only open P0 and gates nothing the exercise needs; Session 1 runs with the aeroplane as it is. THREE OPTIONS REMAIN OPEN, not yet decided: (1) re-scope only, zero engineering, the 182 stays and keeps flying like a 172 as a recorded defect; (2) switch the exercise aircraft to the stock Cessna_172SP_G1000.acf, which is Laminar-calibrated and would delete A-1, the Plane Maker calibration, the GPL donor dependency and D-7's subject - but costs the planner, because services/flightplanner/app.py carries a real C182T POH performance model (get_cruise from Figs 5-6/5-12) and flying a 172 against a 182 plan recreates the L-7a defect fixed this morning; (3) chase the POH. CORRECTION AFFECTING OPTION 3 AND THE WHEEL TRACK: this session recorded that nobody has the POH and declined to fetch one on D-5 grounds. Both halves were wrong - services/flightplanner/app.py line 124 carries a PUBLIC URL to the C182T NAV III POH which the planner already cites as its performance source, and docs/C182T_DIMENSION_MASTER.md records a SHA-256 for the approved AFM. Consulting a source is not redistributing it; D-5 concerns page images shipped in the tree. Therefore the Plane Maker calibration's nine 'unknowns' may be sourceable, and the main_wheel_track correction - settled as centre-to-centre by convergent inference EXPLICITLY BECAUSE the drawing could not be consulted - now rests on a false premise and should be checked against the figure. The inference may still be correct; it is the reason that has failed, not necessarily the answer.

### AI-11

**FDR records defaults as data and the live deck never subscribes a dataref (V2-7, red team RT-3)**

`P0` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **fixed**

- **Files:** `services/ai_pilot/fdr.py:sample_current_frame`, `services/ai_pilot/xplane_udp.py:get_dref`, `services/ai_pilot/web_server.py:run_web_server`, `services/ai_pilot/diagnostics.py:evaluate_frames`
- **Problem:** Three defects that compound. (1) get_dref returns a never-invalidated cache with 0.0 defaults, so a dead link records lat 0, lon 0, 0 KIAS, DF power on, 121.500 selected, and stamps sim_time_s with the WALL CLOCK (default=time.time()). (2) run_web_server constructs the client, controller, agent and recorder and none of them ever calls subscribe_dref; in --live mode only legacy DATA packets (indices 3/20, off by default in X-Plane) populate anything, so heading, attitude, AGL, VVI, engine and every cap/df/* dataref are defaults forever. (3) The diagnostic engine then grades the recording as a DF coverage FAIL rather than a dead link, and its duration clamps to 0.0 if a real sim time ever follows a wall-clock frame. The README's 'read telemetry from live X-Plane 12' is speed and position at best, and only if the operator configures a Data Output the README never mentions. HANDOFF-claude-fixes-2026-09-13 called V2-7 'a debrief graded on fabricated telemetry'; that is exactly what this produces.
- **Fix:** Subscribe every dataref the deck displays and the FDR records; carry per-dataref receive timestamps and record NaN/None past a staleness window; make sim_time_s NaN rather than wall clock; have the engine emit a 'telemetry link not established' finding and refuse to grade when position/DF validity never arrived.
- **Done when:** DONE 2026-09-18. The four RT-3 xfail(strict) markers in services/ai_pilot/tests/test_redteam.py are removed and the tests pass, so they are now the regression guard. (1) xplane_udp stamps every genuine observation on the monotonic clock and exposes get_dref(max_age_s=), get_dref_age_s, is_dref_fresh, observed_datarefs and link_established; send_dref's optimistic echo of an OUTGOING command is deliberately not stamped, with a test for that. (2) FlightDataRecorder subscribes all 60 datarefs it records at construction, so the live deck no longer depends on a hand-configured legacy Data Output; float readings past a 2 s staleness window are NaN rather than 0.0; sim_time_s is NaN rather than the wall clock; each frame carries link_established. (3) The engine reports 'Telemetry link not established' and refuses to grade, on positive evidence only (all link flags down, or every recorded position NaN) so partial frames in its own unit tests still grade; duration is None rather than a clamped 0.0 when sim times are unknown or do not share a clock. web_server.py was NOT touched, avoiding the open AI-7 job in that file. Suites: services/ai_pilot 220 passed / 22 xfailed (was 209/26); root 434 passed with only the known environmental test_panel failure.

### A2-2

**Physics propeller is the C172 76-inch geometry; visual prop is 79 in**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort S · wave 3 · **open**

- **Files:** `scripts/build_c182t_package.py`, `scripts/c182t_dimension_master.json`
- **Problem:** _blad/0/_semilen_SEG 3.200 ft (76.8 in disc) against the TCDS/POH 79 in; chords and 10/40 deg pitch range are the C172 two-blade's and unsourced. 6 % less disc area; a candidate for the C1 cruise shortfall.
- **Fix:** Patch _blad/0/_semilen_SEG 3.291667; take 30-in-station blade angles from FAA TCDS 3A13 p.33 for _min_pitch/_max_pitch; leave chord unless sourced.
- **Done when:** measure_c182t harness and ACF agree on 79.0 in; C1 re-flown at 3,100 lb and recorded.

### AI-1

**Legacy AI pilot entrypoints bypass maneuver validation**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **fixed**

- **Files:** `services/ai_pilot/lightweight_agent.py`, `services/ai_pilot/web_server.py`, `services/ai_pilot/agent_bridge.py`
- **Problem:** Legacy substring chat matching can execute a negated takeoff instruction and announces a clearance without ATC state. Direct-write web/tool routes bypass the new airborne maneuver gate. The new maneuver_server isolates its controller but cannot exclude unrelated legacy processes from X-Plane.
- **Fix:** Retire or migrate legacy mutation entrypoints to an explicit authority/phase contract, including control ownership shared by every writer. Do not expose autonomous ground phases until clearance state and command semantics are implemented.
- **Done when:** Negated and quoted instructions never write controls; all enabled entrypoints honor takeover and one control owner; takeoff cannot manufacture its own clearance.

### AI-10

**Controller and live deck silently share UDP receive port 49005 (V2-6, red team RT-2)**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **open**

- **Files:** `services/ai_pilot/xplane_udp.py:_init_socket`, `services/ai_pilot/maneuver_server.py`, `services/ai_pilot/web_server.py`
- **Problem:** SO_REUSEADDR lets a second XPlaneUDPClient bind the same port; the dynamic-port fallback only runs if bind raises, which REUSEADDR prevents. maneuver_server and `web_server --live` both take the default 49005, so X-Plane's replies reach one of them and the other starves: for the controller that is Stale telemetry -> lease revoked -> sim/operation/pause_on in flight. This is V2-6 from the 2026-09-12 review, never ingested (see AI-9..AI-19 provenance).
- **Fix:** Remove SO_REUSEADDR; let bind fail and fall back to a dynamic port as the code already intends; give web_server its own default port; the instance lock (AI-13) closes the rest.
- **Done when:** services/ai_pilot/tests/test_redteam.py: remove the xfail marker on test_rt2_a_second_client_on_the_same_port_falls_back_or_refuses and the test must pass; it then guards the fix.

### AI-12

**Direct backend: no human-input arbitration, and its own fault path never pauses (D-3, red team RT-4)**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **open**

- **Files:** `services/ai_pilot/direct_backend.py:_run`, `services/ai_pilot/direct_backend.py:_step`, `services/ai_pilot/direct_backend.py:CONTROL_DREFS`
- **Problem:** Decision D-3 says 'Yoke: human always wins.' The backend writes yoke_pitch/roll/heading_ratio at 10 Hz with no sim/operation/override flag, never subscribes sim/joystick/*, and _step has no takeover hook, so a hand on the physical yoke races the loop frame by frame instead of winning; the only takeover is a software release(). Separately, _run's fault path calls _neutralize() and breaks but never pause() - the docstring on _envelope_fault says 'second line of defence: do not rely on the gate noticing first', but the second line stops at centred controls with 0.45 throttle and nobody flying. With the gate present the gate pauses; without it (AI-13) nothing does.
- **Fix:** Decide the arbitration model (X-Plane override + joystick delta detection, or explicit deadman) and implement it; make the loop's fault path pause when it is the last line of defence.
- **Done when:** services/ai_pilot/tests/test_redteam.py: remove the xfail marker on test_rt4a and test_rt4b and the test must pass; it then guards the fix.

### AI-13

**fly_card_h0.py flies the yoke with no gate, no lease, no lock and no pause (red team RT-5)**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **open**

- **Files:** `scripts/fly_card_h0.py`, `scripts/fly_direct_backend.py`, `services/ai_pilot/maneuver_server.py`
- **Problem:** The README states the direct backend gets 'the control lease, the strictly-increasing sequence, the exercise envelope and capture detection ... exactly as they do to the autopilot backend'. True for fly_direct_backend.py; false for fly_card_h0.py, which constructs XPlaneDirectBackend directly (lines 81-84), never imports ManeuverGate, never calls pause(), and is the script that has been flown five times. Neither yoke-writing script takes /tmp/cap-vsar-maneuver-controller.lock, so 'do not run it at the same time as maneuver_server' is advice: two writers on the same surfaces is reachable.
- **Fix:** Route the H0 card through ManeuverGate (acquire/submit/tick) like fly_direct_backend.py; have every X-Plane writer take the same flock; pause on fault.
- **Done when:** services/ai_pilot/tests/test_redteam.py: remove the xfail marker on test_rt5a, test_rt5b, test_rt5c and the test must pass; it then guards the fix.

### AI-2

**Complete live CAP 487 maneuver-controller acceptance**

`P1` · `high` · `task` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **open**

- **Files:** `services/ai_pilot/maneuvers.py`, `services/ai_pilot/maneuver_server.py`, `services/ai_pilot/README.md`, `scripts/launch_xplane12.sh`, `docs/bugs/CODEX_RESUME_AI_PILOT.md`, `services/ai_pilot/direct_backend.py`, `services/ai_pilot/tests/test_direct_backend.py`, `scripts/fly_direct_backend.py`, `scripts/fly_card_h0.py`, `docs/C182T_H0_CONTROL_LAW_FINDINGS.md`, `docs/C182T_HANDLING_TEST_MATRIX.md`
- **Problem:** The supervised airborne maneuver gate and X-Plane adapter are covered by packet-level tests, but live CAP 487 handling, G1000/GFC 700 annunciations, capture, pilot takeover, pause, and disconnect behavior remain unverified. The 2026-09-11 acceptance attempt could not start X-Plane because NVIDIA userspace 595.91.07 did not match the loaded 595.84 kernel module.
- **Fix:** 2026-09-11: live heading capture (12.742 s), FLC altitude capture (50.555 s), out-of-block command refusal, pilot takeover, old-lease refusal and shutdown pause verified. User confirmed FLC-to-ALT, AP disconnect and shutdown pause. Corrected telemetry-loss trial dropped 48 packets for 5.007 s: stale telemetry revoked lease in 1.900 s after drop began, pause_on passed through, direct pause readback=1. Telemetry recovered without reacquisition and old lease returned HTTP 400. Controller/relay stopped and subscriptions cancelled. Initial loss trial was invalid due to old direct subscriptions and remains documented. AI-2 stays open for installed CAP 487 package verification (AI-4); manual recovery verified by user report and four seconds of live pause=0, altitude 4199.636 ft, 122.422 KIAS, bank 0.576 degrees and VVI -0.224 ft/min. Explicit visual confirmation of the latest automatic fault pause has not been supplied; direct telemetry proved pause=1. AI-4 package has now been corrected and installed with static validation; fresh X-Plane load and visual cockpit verification remain pending. Direct surface-control backend and card H0 campaign 2026-09-11: added services/ai_pilot/direct_backend.py (XPlaneDirectBackend), which flies the primary flight controls rather than the GFC 700 and so covers aircraft with no autopilot, implemented against the EXISTING maneuvers.FlightBackend protocol so the lease, sequence, envelope and capture detection all still apply; maneuvers.py was NOT modified and the gate was never bypassed. Extended along the axes the handling cards need: apply_test_input (H0, bounded/ramped/self-expiring single-axis inputs), select_bank (H2), select_airspeed for speed-on-pitch (H1/H3), set_flaps (H4) and elevator trim. Card H0 (control and trim confidence, 100 KIAS clean) was attempted FIVE times and remains UNFLOWN - it has not yet reached its first control input from a stabilized reference condition. Each attempt terminated on a different real control-law defect, all five now fixed and locked by offline tests, none of which the pre-existing 53 offline tests caught: (1) step test inputs and no turn coordination, fixed with a trapezoidal ramp and sideslip PI; (2a) throttle bang-bang 0.150-1.000 swinging speed 94.7-108.8 about a 100 target, caused by a PURE INTEGRATOR at 0.1 throttle/sec/knot, fixed with PI; (2b) a standing sideslip through the climb that the heading loop masked by holding +1.6 deg of right bank, fixed with a right-rudder feedforward scaling with throttle and inversely with dynamic pressure; (3) an abrupt roll that was NOT the input - the ramp was verified correct on the trace, climbing 0.0077 to 0.1000 over exactly 1.0 s with the aileron tracking to four decimals - but a STEP IN THE RECOVERY, where the heading loop commanded the aileron limit in a single 100 ms tick the instant the input expired, held it saturated 1.2 s, reached 14.3 deg/s and overshot from -20.7 to +9.2 deg; fixed with rate damping on both inner loops and a slew-rate limiter on all three surfaces applied last before the wire (a ramped input passes through untouched at 0.10/s against a 0.40 limit). Run 3 was ALSO not a valid test point: it entered 22 knots fast, the throttle went to the idle stop and the integral wound to its -0.35 limit for ten seconds where integrating could not change the output, then had to unwind off the stop, so speed sailed through the target to 94.1 KIAS in a 274 fpm descent - the condition the first input was flown from; fixed with conditional integration, since clamping the integral TERM is not anti-windup. (4) Added a criteria-based stabilization gate to scripts/fly_card_h0.py (kias +/-2, alt +/-60 ft, vs +/-120 fpm, bank +/-2 deg, held 4 s continuous, 120 s timeout, exit 3 on failure, --force stamps the run as invalid), which immediately caught the aircraft sitting 107 ft low for two full minutes at 100.0 KIAS, -3 fpm and -0.2 deg bank, correcting none of it: a pure proportional cascade reaches equilibrium the moment pitch equals its command, which it can do at a standing altitude error because the pitch the VS loop asks for at that error is also the attitude that flies level - every loop satisfied with the aircraft in the wrong place; fixed with a bounded, conditionally-integrated altitude trim term, without which the card's reference condition is not reachable and the card cannot be flown at all. (5) The backend engaged on an aircraft the autopilot had left trimmed to +0.432 nose-up and held full nose-DOWN elevator saturated at -0.400 for seven seconds while the aircraft pitched UP to 11.5 deg and climbed at 1,533 fpm, terminating on the gate's own 90 KIAS floor; nothing in the control law was wrong, it had no trim authority and no way to know it was out-trimmed, because a saturated surface and a slow one look identical from the response alone. docs/C182T_HANDLING_TEST_MATRIX.md had listed 'no trim' as a BLOCKED reason for H0 before any of this was flown. Fixed with an autotrim loop that adopts the aircraft's real trim by readback and WILL NOT WRITE TRIM IT HAS NOT FIRST MEASURED, frozen during a pitch test input, and kept out of CONTROL_DREFS so release leaves the aircraft trimmed rather than slamming trim to neutral. CORRECTION to the pre-flight assessment: the matrix named capture rate as the instrumentation risk; it was not. The real gap was that a saturated surface and a slow one are indistinguishable from the response alone, so three of the five defects were invisible until COMMANDED SURFACE POSITIONS were logged beside the response. Traces now record the pre-rate-limit demand next to each issued command, trim position and trim RATE, all integrator states, and body_rate_age_s (inf when the damping terms were flown as zero for want of data) so a zero meaning 'not rolling' and a zero meaning 'no data' never look alike. Body rates and trim are auxiliary datarefs held OUTSIDE the freshness gate, so losing a damping channel degrades the damping rather than neutralizing the controls on an airborne aircraft. After run 5 the aircraft was left at 77 KIAS at full power out of trim; recovered by direct write to 81.4 KIAS at 3,908 ft and the pilot paused the simulator. Procedural finding: run 5 engaged during a transient left by the previous run's release, and the entry check tested envelope compliance only, not steadiness. Handling cards now: H0 unblocked but UNFLOWN, H2 unblocked 90-110 KIAS and blocked at 80, H3 and H4 unblocked and unflown, H1 and H5-H7 still BLOCKED on the gate's 90 KIAS floor - which is the specific guard against an autonomous system flying to the stall and is NOT recommended for removal. services/ai_pilot/tests/test_direct_backend.py is now 80 offline tests (from 53), the ai_pilot suite 150, none requiring X-Plane. NOTHING here is recorded as a handling pass or fail, no gain is validated, and none of it validates the aircraft or closes A-1. Full findings with trace evidence in docs/C182T_H0_CONTROL_LAW_FINDINGS.md.
- **Done when:** Observe and record representative heading and altitude capture, command rejection outside the envelope, pilot takeover, pause, and disconnect behavior in X-Plane 12; confirm the cockpit annunciations agree with controller state and that only one process owns the controls.
- **Depends on:** AI-1

### AI-21

**ArduPlane backend: release-to-MANUAL and the SITL attach window are unsafe per the Plane-4.7.1 source**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **fixed**

- **Files:** `services/ai_pilot/arduplane_backend.py`, `scripts/fly_arduplane_backend.py`, `services/ai_pilot/tests/test_arduplane_backend.py`, `xplane/ardupilot/cap487.parm`, `docs/ARDUPLANE_TRIAL.md`
- **Problem:** Source review of ArduPilot Plane-4.7.1 (docs/ARDUPLANE_TRIAL.md, 2026-09-17 handoff design review) found three defects in the backend as built. (1) release() sets MANUAL: ModeManual passes raw stick to the surfaces with no limits (mode_manual.cpp:4-15); with the rig's joystick axes unmapped, the SITL X-Plane backend turns an axis reading 0 into PWM ~667 and the inverted throttle axis into ~2333 (SIM_XPlane.cpp:497-498, AP_RCProtocol_FDM.cpp:39), which clamp to full aileron and full throttle; with no joystick row at all RC is never valid and throttle is 0 (reverse_thrust.cpp:132-137). MANUAL is only safe with a proven RC map. (2) SITL writes ENGN_thro_use and the yoke datarefs every frame in every mode from its first DATA packet (SIM_XPlane.cpp:684-688, :621-627); it boots MANUAL with no valid RC, so the engine goes to idle the moment SITL attaches, until select() puts it in GUIDED. (3) SITL re-sends override_joystick=1/override_throttles=1 every frame and has no exit hook, so after it is stopped the override stays latched with the last yoke values; the launcher does not own the SITL process and never clears them on a normal detach (only the lost-heartbeat path does). Verified correct: ARMING_REQUIRE 0 suffices (AP_Arming.cpp:306), guided heading is true (mode_guided.cpp:52), COMMAND_INT with explicit frame is required (GCS_Common.cpp:5294,5340), param3 of GUIDED_CHANGE_HEADING is m/s^2 with a 0.05 floor (GCS_MAVLink_Plane.cpp:745), z==0/-1 is DENIED (:685), all cap487.parm names exist.
- **Fix:** 2026-09-17. (1) release() no longer uses MANUAL. _hand_back() parks ArduPlane in LOITER - the only mode that flies itself with no RC - or FBWA when a valid centred RC position was measured at engagement (_rc_rest is not None); last_commands['hand_back_mode'] records which. (2) New services/ai_pilot/sitl_lifecycle.py owns the SITL process: SitlProcess.start/wait_for_mavlink/stop (SIGTERM then SIGKILL), clear_overrides(), park_on_gfc700() which presses g1000n1_ap only when servos_on is 0 and g1000n1_hdg only when heading mode is not already set, and detach() which enforces the one safe order - release, stop SITL, clear both overrides, engage the GFC 700. scripts/fly_arduplane_backend.py now starts and stops SITL itself (--no-sitl to attach to an external one), waits for heartbeat + GLOBAL_POSITION_INT + 2.5 s after the first heartbeat before commanding (SITL decodes gyros with the XP11 convention until its 1 Hz version query is answered), and routes every exit and refusal through a single cleanup(). (3) _command_altitude refuses a z of 0 or -1 before sending, which ArduPlane answers DENIED to. (4) preflight() reports the HEARTBEAT armed bit and the launcher refuses with exit 5 when disarmed. Tests: test_arduplane_backend 35->41 (HandBackModeTests: FBWA with proven RC, LOITER without, never MANUAL across four RC shapes, heading accel never 0, altitude 0 refused, armed bit), test_mavlink_min 17->18, new test_sitl_lifecycle 14 (detach ordering asserted: overrides cleared only after SITL stops, GFC 700 only after that, no toggle of a live AP). ai_pilot suite 206->227. Offline only - NOT flown; Leg 3 and AI-20 remain open.
- **Done when:** release() chooses LOITER unless a valid centred RC position was measured at engagement (then FBWA), with tests; the launcher starts SITL, waits for heartbeat + GLOBAL_POSITION_INT + the version RREF, calls select() at once, and on detach parks in LOITER, stops SITL, writes both overrides to 0, then engages the GFC 700 HDG+ALT via the g1000n1_* commands; guided_change_altitude refuses z in {0,-1}; a test asserts heading accel is never sent as 0; preflight asserts the HEARTBEAT armed bit. Then Leg 3 (AI-20) can be attempted.

### AI-23

**ArduPlane boots into RTL with a default Home 8000 miles away and banks hard on attach**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **fixed**

- **Files:** `xplane/ardupilot/cap487.parm`, `services/ai_pilot/arduplane_backend.py`, `scripts/fly_arduplane_backend.py`, `docs/ARDUPLANE_TRIAL.md`
- **Problem:** First successful live attach (2026-09-17): SITL connected correctly - heartbeat 0.07 s, ARMED, GLOBAL_POSITION_INT agreeing with X-Plane true altitude to within 2 ft - but the pre-flight block reported ArduPilot in mode 11 (RTL), not MANUAL/FBWA. SITL's log shows 'Home: -35.363262 149.165237' (Canberra, its built-in default), so on taking the joystick/throttle override it immediately banked toward a home point on the other side of the planet: roll went to -80 deg and vertical speed to -4370 fpm within seconds of attach. The launcher only WARNED about the unexpected mode and continued. cap487.parm does not set INITIAL_MODE, and nothing sets or validates Home.
- **Fix:** 2026-09-17. secure_on_attach() added to ArduPlaneBackend: sends DO_SET_HOME (param1=1, use current location) and forces LOITER the moment SITL is reachable, before the pre-flight checks and long before gate.acquire(); raises if the mode is refused so the launcher detaches instead of continuing. cap487.parm sets INITIAL_MODE 12. The launcher now REFUSES (exit 6) rather than warning when the reported mode is outside LOITER/GUIDED/FBWA/MANUAL. Also found and fixed in the same pass: WP_LOITER_RAD defaulted to 60 m, which at 110 KIAS demands atan(v^2/rg) = 80 degrees of bank - LOITER was obediently flying an impossible circle; set to 800 m (~22 deg, inside ROLL_LIMIT_DEG 25). Verified live on 2026-09-17: SITL secured into LOITER with no departure and bank stayed within -22 to -30 degrees for the whole flight. 77 offline tests pass.
- **Done when:** cap487.parm sets INITIAL_MODE to a mode that holds attitude without RC; the launcher refuses to proceed (not merely warns) when the reported mode is not an expected one, and forces a known mode before the aircraft can depart; Home is either set from the X-Plane position or the mode is one that does not use it. Re-run Leg 3 and confirm roll stays inside the gate's limit through the attach window.
- **Depends on:** AI-21

### AI-24

**ArduPlane ACKs GUIDED_CHANGE_HEADING/ALTITUDE then ignores them and keeps loitering**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **open**

- **Files:** `xplane/ardupilot/cap487.parm`, `services/ai_pilot/arduplane_backend.py`, `docs/ARDUPLANE_TRIAL.md`, `docs/bugs/AI-24_ARDUPLANE_GUIDED_TUNING.md`
- **Problem:** Leg 3 flew on 2026-09-17 (trace arduplane_backend_20260917-230653.jsonl): ArduPlane was in GUIDED, the gate accepted, and 33 samples of 'executing' ran with no fault - but the aircraft flew a continuous left circle (heading 261 -> 178 through a full 360 and onward) and descended 4,616 -> 2,974 ft, tracking neither the commanded heading 300 nor altitude 4,500. Both MAV_CMD_GUIDED_CHANGE_HEADING and _ALTITUDE were ACKed MAV_RESULT_ACCEPTED - select() raises otherwise - so ArduPilot accepted the commands and did not act on them; the behaviour is ModeGuided's default loiter. Prime suspect is the GUIDED_* heading controller: cap487.parm sets GUIDED_P 5000 / GUIDED_I 0 / GUIDED_D 0, values invented as placeholders with no knowledge of the correct scale for that AC_PID. TECS is equally unvalidated - the descent was never arrested. Entry condition was benign: stable GFC 700 handoff at 4,677 ft, 110 KIAS, wings level, no terrain or weather factor.
- **Fix:** 
- **Done when:** From a stable handoff, a commanded heading is captured within 3 degrees and held, and a commanded altitude within 100 ft with VS under 150 fpm, for 3 s - i.e. the gate emits 'achieved' (trial cases T1 and T2). Bank stays inside ROLL_LIMIT_DEG throughout and the aircraft stays in the 3,000-6,000 ft block.
- **Depends on:** AI-23

### AI-3

**Live RREF comma header discarded by AI pilot receiver**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort S · wave 3 · **fixed**

- **Files:** `services/ai_pilot/xplane_udp.py`, `services/ai_pilot/tests/test_udp_protocol.py`
- **Problem:** Live X-Plane 12.4.3 replies begin RREF comma, while the receiver accepted only RREF NUL, leaving all maneuver observations missing.
- **Fix:** Accept observed comma and existing NUL headers; test receive dispatch, callbacks, cached values and rejection of unrelated headers.
- **Done when:** 64 AI-pilot tests and 23 subtests pass; live status reports finite telemetry aged 0.028 seconds. Console/radio: 86 passed.

### AI-5

**Live altitude selection does not establish commanded climb**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **fixed**

- **Files:** `services/ai_pilot/maneuvers.py`
- **Problem:** Live target 4200 ft from 3999 ft remained near 3997 ft after roughly 40 seconds. Selected altitude read 4200 but VVI selector read 0 and autopilot state 18; controller remained executing. Cause not yet established.
- **Fix:** Implemented G1000 FLC command for altitude changes with explicit 110-KIAS exercise target and pilot-managed power; existing FLC is not toggled off. Automated tests pass; supervised live FLC and cockpit capture verification pending.
- **Done when:** Live FLC target 4200 ft at 110 KIAS captured in 50.555 s from 3984.975 ft. AP readback 106 during FLC with altitude arm and 16386 after capture; measured capture 4191.494 ft, 112.099 KIAS, 91.618 ft/min. Cockpit visual confirmation remains part of open AI-2. User confirmed FLC-to-ALT cockpit transition near 4200 ft.

### AI-6

**Controller shutdown pause request does not pause live X-Plane**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **fixed**

- **Files:** `services/ai_pilot/xplane_udp.py`, `services/ai_pilot/maneuver_server.py`
- **Problem:** Clean SIGINT shutdown while owning control called set_paused(True), but subsequent live sim/time/paused readback was 0. Current implementation writes sim/time/paused; pause delivery/effect is unverified and failed this trial. User was instructed to pause locally.
- **Fix:** Installed DataRefs.txt confirms sim/time/paused is read-only. Replaced writes with Commands.txt pause_on/pause_off explicit commands and added regression coverage. Live pause readback verification pending.
- **Done when:** Live shutdown pause verified with sim/time/paused=1 and user visual confirmation. Live telemetry-loss fault also sent pause_on at 1.900 s after relay drop began, revoked lease and produced pause=1. Autopilot modes were preserved during the fault. After telemetry restoration, old lease returned HTTP 400.

### AI-8

**Complete full-sortie ArduPlane and FAA-grounded taxi control**

`P1` · `high` · `task` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort L · wave 3 · **open**

- **Files:** `services/ai_pilot/taxi.py`, `services/ai_pilot/tests/test_taxi.py`, `services/ai_pilot/README.md`
- **Problem:** The intended AI Mission Pilot must taxi out, take off, fly the mission, land, and taxi back to its recorded starting point. ArduPlane is the planned full-flight backend for aircraft without an accepted onboard autopilot, but no SITL/MAVLink adapter, airport-surface graph, taxi actuator, clearance state, or end-to-end control handoff exists. The retired scripted controller writes X-Plane directly and cannot be revived because it can manufacture takeoff authority and bypass the serialized maneuver gate.
- **Fix:** Foundation added 2026-09-15: taxi.py is a pure deterministic coordinator around AI/planner-proposed routes. It records the starting point; requires the return route to end there; keeps taxi, runway-crossing, line-up-and-wait and takeoff authority distinct; validates ATC versus crew authority source; consumes crossing authority one runway at a time; fails closed to a progressive-taxi request on uncertainty; and requires the aircraft to be wholly runway-clear before return taxi. The first ten offline tests failed before the module existed; two more failed against successive implementations until departure-authority-source enforcement and a separate lined-up hold state were added. All twelve now pass. FAA basis: AIM 4-3-18, 4-3-21 and 2-3-5 plus 14 CFR 91.129(i). Still required: sourced airport surface data, ATC/crew clearance input, runway/hold-line position monitoring, bounded steering/throttle/brake commands, ArduPlane SITL and MAVLink adapter, one-owner handoff among GFC 700/ArduPlane/direct flight-test control, taxi-out/takeoff/mission/landing/taxi-back state integration, and live X-Plane acceptance.
- **Done when:** A representative towered-airport sortie starts from a named parking position, follows only the cleared taxi route, stops at every unauthorized hold line, never treats taxi instructions as runway-entry authority, completes ArduPlane takeoff/mission/autoland with exclusive control ownership, exits and becomes wholly runway-clear, receives a distinct return taxi clearance, and stops at the recorded starting position. Repeat at an untowered airport with recorded crew traffic checks. Inject stale telemetry, ambiguous routing, loss of clearance state, and an attempted second controller; every case stops safely without guessing. Static policy tests, MAVLink packet-intent tests, SITL trials, and supervised X-Plane 12 acceptance all pass.
- **Depends on:** AI-1

### AI-9

**UDP receiver accepts telemetry from any sender (red team RT-1)**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **open**

- **Files:** `services/ai_pilot/xplane_udp.py:_listen_loop`, `services/ai_pilot/xplane_udp.py:_init_socket`
- **Problem:** _listen_loop does `data, _addr = recvfrom()` and never compares _addr with self.host; the socket is bound to 0.0.0.0. Any host on the LAN can inject RREF replies - subscription ids are small sequential integers - and so can keep a stale aircraft looking fresh and in-envelope (defeating pause-on-telemetry-loss) or feed the direct backend false attitude to steer against. Reproduced with a forged packet from 127.0.0.2.
- **Fix:** Drop datagrams whose source address is not the configured X-Plane host; bind the receive socket to the interface facing X-Plane (127.0.0.1 when local) rather than 0.0.0.0.
- **Done when:** services/ai_pilot/tests/test_redteam.py: remove the xfail marker on test_rt1_forged_telemetry_from_another_host_is_ignored and the test must pass; it then guards the fix.

### O-5

**Mumble server has no per-role ACLs and images float**

`P1` · `high` · `bug` · Deployment / infrastructure · cluster C5 (Deployment bootstrap & voice provisioning) · effort M · wave 3 · **fixed**

- **Files:** `docker-compose.yml (mumble service)`, `services/exercise/app/radio.py:307`
- **Problem:** CERTREQUIRED=false, ALLOWHTML=true, a single shared server password, no channel ACLs, USERS=100, and mumble-server:latest / caddy:2 unpinned. The radio console's callsign is free-form, so a student can present as MISSION BASE on the net.
- **Fix:** Images pinned by digest to what was already running and tested on ms01 (mumblevoip/mumble-server, caddy:2) - not "latest" silently drifting under a live voice net. Per-role channel ACLs on Instructor/SET are provision_mumble.py's work, shared with O-4 (same mechanism, same script). radio.py's /api/radio/stream now derives the callsign from an authenticated RBAC session (access.get_session_from_request) when one exists, ignoring whatever the client claims - a base-role student can no longer type "MISSION BASE" or "INSTRUCTOR" and impersonate another station. No session (RBAC not configured for the exercise) falls back to the client-supplied callsign as before, matching access.py's fail-open design elsewhere. CERTREQUIRED=false, ALLOWHTML=true and USERS=100 were NOT changed - those are the training net's deliberate low-friction-join posture, not oversights, and changing them wasn't asked for or verified against real join friction.
- **Done when:** tests/test_radio.py: two new cases - an authenticated session's callsign overrides a conflicting client-claimed one; no session falls back to the client-supplied callsign unchanged. All 15 radio tests and all 72 console+radio+setup_auth tests pass together. Image pins verified against ms01's actual running container digests via `docker inspect`, not guessed tags.
- **Depends on:** X-2, O-4

### O-7a

**Air Manager seat count for three MO stations unconfirmed**

`P1` · `high` · `task` · Deployment / infrastructure · cluster C5 (Deployment bootstrap & voice provisioning) · effort S · wave 3 · **resolved**

- **Files:** `Plan v0.8 §9.4`
- **Problem:** The containerization entry says to confirm spare AM4 licences against AM4_COMPAT.md, which does not exist. Three MO seats are assumed, not verified — a blocker discovered on exercise day would be expensive.
- **Fix:** WRONG FINDING, corrected 2026-09-08. docs/AM4_COMPAT.md exists in the canonical repo and records the licence position: spare AM4 licences cover the DF heads and MO COM panel, and it explicitly distinguishes Air Manager from Air Player seats (sold separately) for crew stations that only display. The CHANGELOG citation resolved all along.
- **Done when:** Three MO stations activate simultaneously in a rehearsal.

### A2-1

**C182T ACF still has four cylinders**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort S · wave 3 · **open**

- **Files:** `scripts/build_c182t_package.py`
- **Problem:** acf/_num_cylinders is the C172's 4; the IO-540 has six. Engine model and G1000 lean-assist show a four-cylinder engine.
- **Fix:** Add `P acf/_num_cylinders 6` to ACF_PATCHES; rebuild.
- **Done when:** Built ACF reads 6; G1000 engine page shows six EGT/CHT bars.

### A2-10

**No test pins the built ACF to the dimension master**

`P2` · `medium` · `improvement` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort M · wave 3 · **open**

- **Files:** `tests/test_c182t_flight_model.py`, `scripts/c182t_dimension_master.json`
- **Problem:** ACF_PATCHES and the sourced JSON both carry 182T values with no check that they agree; A2-1/A2-2 survived because nothing listed the C172 fields left unpatched.
- **Fix:** Test that asserts each sourced ACF field against the JSON and reports every _engn/_prop/_blad/_gear field still at its C172 value.
- **Done when:** Test fails on the current ACF for A2-1/A2-2 and passes after they are fixed.

### A2-11

**Calibration order: propeller and gear before the fuselage-Cd experiment**

`P2` · `medium` · `improvement` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort M · wave 3 · **open**

- **Files:** `docs/C182T_FLIGHT_MODEL_CALIBRATION.md`
- **Problem:** The staged Cd=0.100 experiment would calibrate drag against the wrong propeller.
- **Fix:** Sequence: A2-2, A2-3, re-fly B1/C1, then the Cd experiment.
- **Done when:** Calibration doc updated with the sequence and results.
- **Depends on:** A2-2, A2-3

### A2-13

**AI pilot: finish the C182T profile port (runner flag, bridge identity, taxi constants)**

`P2` · `medium` · `improvement` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort M · wave 3 · **open**

- **Files:** `scripts/ai_pilot_ksee_kmyf.py`, `scripts/ai_pilot_surface.py`, `services/ai_pilot/experiment.py`, `services/ai_pilot/ground_guidance.py`, `xplane/capvsar_mission.py`
- **Problem:** Controllers take an AircraftProfile (feat/c182-ai-pilot-baseline) but the runners, Scenario.aircraft_name and the taxi throttle constants still name the C172; C182T tuning is unvalidated.
- **Fix:** Add --profile, record it in manifests, confirm verify_identity accepts CAP 487, then fly the trial order in docs/C182T_AI_PILOT_PORT_2026-10-11.md and retune.
- **Done when:** A C182T sortie scored by the independent observers with tuning_validated flipped and traces cited.

### A2-3

**Gear physics track 8.2 ft while the mesh was corrected to 9 ft**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort M · wave 3 · **open**

- **Files:** `scripts/build_c182t_package.py`, `scripts/c182t_corrections.json`
- **Problem:** _gear/1,2 attach (x 1.6 ft, latE -57 deg, leg 3.0 ft) is the C172SP's; wheelbase 65 in vs 66.5 in. Wheels drawn ~5 in outboard of the contact points each side.
- **Fix:** Set gear attach/latE/lonE so contact track = 9 ft 0 in and wheelbase = 66.5 in (both in the dimension master); re-run measure_c182t.py.
- **Done when:** Harness reports physics contact points and mesh wheel centres within 1 in.

### A2-4

**Full-throttle power 214 HP vs 230 rated is unexplained**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort M · wave 3 · **open**

- **Files:** `docs/C182T_FLIGHT_MODEL_CALIBRATION.md`
- **Problem:** C1 recorded 214 HP at 2400 RPM near sea level; ambient explains ~2 %. Candidates: A2-2, _max_MP_limit, _engine_friction_ratio.
- **Fix:** Fix A2-2 first, re-fly C1, then isolate one parameter at a time with c182t_flight_model_experiment.py.
- **Done when:** C1 HP within 3 % of the POH sea-level figure or the shortfall attributed to one named parameter.
- **Depends on:** A2-2

### A2-5

**Aircraft default paint shows N429CP while the ACF and ATC say CAP 487**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort S · wave 3 · **open**

- **Files:** `scripts/build_c182t_package.py`, `scripts/adapt_cap_livery.py`, `README.md`
- **Problem:** The builder makes the adapted N429CP C172 artwork the default texture and icon; its own docstring rules out real registrations on a different simulated type; the artwork's author/URL are unknown.
- **Fix:** Repaint the registration block to CAP 487 in adapt_cap_livery.py, or make the CAP 487 livery the default and keep N429CP as a named option; fix the README line.
- **Done when:** Default load shows one identity on skin, G1000 and ATC.

### AI-14

**ManeuverGate has no liveness coupling to its monitor (D-3, red team RT-6)**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **open**

- **Files:** `services/ai_pilot/maneuvers.py:ManeuverGate.acquire`, `services/ai_pilot/maneuver_server.py:monitor`
- **Problem:** D-3: 'monitor death revokes the lease, pauses the sim, refuses new acquire() until restart.' The first two happen; the third does not - after _fault the gate re-arms on the next acquire() with no requirement that anything is ticking. maneuver_server's monitor thread returns on an exception and nothing tells the gate, after which acquire+submit still write to X-Plane and no tick() will ever notice stale or out-of-envelope telemetry. The pause-on-telemetry-loss promise lives entirely in a daemon thread.
- **Fix:** Give the gate a heartbeat: refuse acquire/submit and self-fault when tick() has not run within max_age_seconds; latch a 'poisoned' state after a fault that only process restart clears.
- **Done when:** services/ai_pilot/tests/test_redteam.py: remove the xfail marker on test_rt6a and test_rt6b and the test must pass; it then guards the fix.

### AI-15

**Any local process can acquire or revoke aircraft control with no credential (red team RT-7)**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **open**

- **Files:** `services/ai_pilot/maneuver_server.py:Handler.do_POST`
- **Problem:** /api/acquire and /api/takeover ignore their JSON body; the only checks are Content-Type and a same-origin test that non-browser clients never trigger. The README calls the deck 'loopback-only' as if that were a boundary. On the workstation, loopback includes Codex, Gemini and Claude Code running with shell access - any of them can seize or drop the aircraft. test_maneuvers proves the bare POST succeeds and treats it as correct.
- **Fix:** Require the same locally configured bearer credential the web deck already uses (CAPVSAR_AI_PILOT_TOKEN) on acquire, takeover and maneuver.
- **Done when:** services/ai_pilot/tests/test_redteam.py: remove the xfail marker on test_rt7_seizing_or_revoking_control_needs_a_credential and the test must pass; it then guards the fix.

### AI-16

**Taxi coordinator launders an unauthorized departure and lets a clarification hold skip return-to-start (red team RT-8)**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort S · wave 3 · **open**

- **Files:** `services/ai_pilot/taxi.py:mark_airborne`, `services/ai_pilot/taxi.py:load_route`
- **Problem:** mark_airborne() has no phase check: from HOLDING_SHORT_DEPARTURE with no takeoff authority it succeeds silently and the machine proceeds as a normal flight - the one component whose stated job is that this never happens silently (test_taxi.py itself calls it from PARKED). load_route accepts an OUTBOUND route from HOLDING_FOR_CLARIFICATION regardless of whether the aircraft was mid-RETURN, so reporting uncertainty during the return taxi and loading an outbound route skips the 'sortie ends where it began' rule, which is only enforced on routes that declare themselves RETURN. Scope note, not a defect: the crossing rule trusts the route's own surface labels; a crossing labelled TAXIWAY needs no clearance until AI-8's surface graph exists.
- **Fix:** mark_airborne must raise or record a violation unless phase is CLEARED_FOR_TAKEOFF; carry a 'return owed' flag from landing until RETURNED_TO_START and refuse OUTBOUND routes while it is set.
- **Done when:** services/ai_pilot/tests/test_redteam.py: remove the xfail marker on test_rt8a and test_rt8b and the test must pass; it then guards the fix.
- **Depends on:** AI-8

### AI-17

**Stale skill file asserts PIC authority and four retired mutation tools; README count stale (red team RT-9, RT-12)**

`P2` · `medium` · `docs` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort S · wave 3 · **open**

- **Files:** `services/ai_pilot/skills/xplane-pilot/SKILL.md`, `services/ai_pilot/agent_bridge.py:export_hermes_skill`, `services/ai_pilot/README.md`
- **Problem:** The file on disk in a skills/ directory - the path Hermes, Codex, Gemini and Claude Code all discover - tells a model it may 'act as Pilot-in-Command' with execute_checklist, command_flight_phase, set_autopilot and spawn_on_runway, all of which are in RETIRED_MUTATION_TOOLS. export_hermes_skill() writes the correct observation-only text but nothing installs it. Whether Hermes on cainfra02 loads this copy is UNRESOLVED (unreachable from the reviewing host); coding agents working in this tree read it regardless. Also: the README's direct-backend section says '150 across the service'; the suite collects 200 and Codex's own CHANGELOG entry says 200.
- **Fix:** Replace SKILL.md with the export_hermes_skill() text (or delete it and generate at install); fix the count.
- **Done when:** services/ai_pilot/tests/test_redteam.py: remove the xfail marker on test_rt9 and test_rt12 and the test must pass; it then guards the fix.

### AI-20

**ArduPlane backend bounded SITL trial (CONOPS gate G)**

`P2` · `medium` · `task` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **open**

- **Files:** `services/ai_pilot/arduplane_backend.py`, `services/ai_pilot/mavlink_min.py`, `scripts/fly_arduplane_backend.py`, `scripts/setup_ardupilot_sitl.sh`, `xplane/ardupilot/xplane_plane_cap487.json`, `xplane/ardupilot/cap487.parm`, `docs/ARDUPLANE_TRIAL.md`
- **Problem:** The ArduPlane FlightBackend is built and tested offline (2026-09-17: 29 backend tests, 14 MAVLink codec tests) but has never flown. The AI Mission Pilot CONOPS gate G requires a bounded SITL trial that either demonstrates X-Plane 12 compatibility, CAP 487 tuning and coherent takeover, or records why the X-Plane autopilot remains the backend. Two things are unverified and rig-specific: the joystick axis indices in xplane_plane_cap487.json, and whether SITL re-asserts sim/operation/override/override_joystick after a MANUAL-mode release (trial case T4). The `--backend arduplane` switch on maneuver_server is deliberately deferred until the trial has flown.
- **Fix:** 2026-09-17 handoff session (Ron authorized): SITL built at Plane-4.7.1 (dbe7921) but NEVER ATTACHED to the aircraft - no ArduPlane leg was flown and gate G is undecided. Two other legs flew and captured through the real gate: XPlaneAutopilotBackend commanded 210/4500 captured 209.3/4500 roll +0.8 VS -0; XPlaneDirectBackend commanded 240/3600 captured 240.6/3603 at 110.0 KIAS roll -0.6 VS +1 fpm (trace direct_backend_20260917-211851.jsonl), taking the aircraft directly from a live GFC 700. Handoff findings, which are the part of gate G the CONOPS calls coherent takeover: (1) the aircraft does not hold itself between controllers - a ~30 s gap after releasing the autopilot departed CAP 487 twice, 70 deg bank/-3700 fpm and then inverted, so handoffs must be OVERLAPPED and each backend must disengage the incumbent itself via servos_off_any; this also means the ArduPlane handoff is a process lifecycle, not a mode change, because SITL seizes override_joystick on attach and cannot coexist with the GFC 700. (2) The gate fault path fired for real at AGL 999 against the 1000 ft floor, revoking the lease and pausing the sim - it presents as frozen telemetry. (3) The 3000-6000 ft block is tight over terrain east of Ramona; fly west over the coastal plain. (4) pymavlink will not install on this workstation, validating the stdlib codec. See docs/ARDUPLANE_TRIAL.md trial log for the full record.
- **Done when:** docs/ARDUPLANE_TRIAL.md pre-checks P1-P9 pass and cases T1-T8 are recorded with trace filenames, the parameters actually used, and the gate G decision in the CONOPS's own words (adopt / X-Plane autopilot remains because ...), written by the person who flew it. Authorizing the trial is the technical lead's decision with Mission Pilot validators.
- **Depends on:** AI-2

### AI-4

**Installed exercise aircraft predates CAP 487 identity and has prop lever load error**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort M · wave 3 · **fixed**

- **Files:** `scripts/build_c182t_package.py`
- **Problem:** Installed Cessna_182T_G1000.acf declares N499CP. X-Plane Log.txt reports prop_lever.obj line 187 IDX10 index out of range and a non-power-of-two prop_lever.png. Repository rename alone did not update this installed package.
- **Fix:** Fixed builder IDX10 remainder encoding (four trailing indices now use IDX) and resampled generated prop texture from 194x87 to 256x128. Built staging package and installed only tailnum, selection icons, prop object/texture, and CAP livery rename with backups; file hashes verify all other installed content preserved. Backup: /home/ron/X-Plane 12/Output/capvsar-backups/AI4-20260911-083735
- **Done when:** Installed static checks pass: all 30 ACF patches match, tailnum CAP 487, 125 vertices, 534 in-range indices/178 triangles, 256x128 texture, unchanged vertex/UV/index sequence, single prop-lever attachment. Console/radio: 86 passed, 8891 warnings in 2.62s. Remains open pending fresh X-Plane load log and visual cockpit/prop-lever confirmation. CLOSED 2026-09-15, both halves. LOG: added scripts/check_xplane_log.py, which fails on exactly the two regressions this item is about - an IDX10 / index-out-of-range line naming prop_lever.obj, and a non-power-of-two texture warning naming prop_lever.png - rather than on any line that happens to mention them. It requires the FILE to be named, because a bare 'index out of range' from another object is not this defect and failing on it would train the reader to ignore the check. It also carries --require-aircraft, since X-Plane appends to Log.txt across reloads and a log can be clean purely because it predates the package under test; by hand during this work a grep for 'power of two' matched the GL_ARB_texture_non_power_of_two extension string present in every log, which is the false positive the tests now pin. Run against the live 501-line log after a fresh load of Cessna_182T_G1000.acf: clean, rc=0. 15 tests. VISUAL: done by screenshot rather than by a human at the workstation, which the brief allowed for anyone who can actually see the cockpit. Entered the 3D cockpit over UDP, pitched the pilot's head to -45 degrees to bring the pedestal into frame, drove sim/cockpit2/engine/actuators/prop_ratio_all from 1.00 to 0.00 with readback confirming 1.000 and 0.000, and captured a frame at each. The lever renders, and it moves: differencing the two quadrant crops leaves a narrow vertical band of strong change at x 261-344, y 158-384, 0.35% of the crop - the signature of a lever travelling in its slot rather than a lighting or camera shift. A clean log alone was explicitly NOT treated as sufficient, and the tool says so on every clean run.

### D-1

**CHANGELOG entries contradict the code they describe**

`P2` · `medium` · `bug` · Docs / record · cluster C14 (Contract & documentation truth) · effort S · wave 3 · **fixed**

- **Files:** `CHANGELOG.md`
- **Problem:** The pymumble bridge is marked 'proposed only' in two entries although it is implemented; the '/radio' APX 6500 entry now describes /radio-legacy; the Becker pcall entry claims an error the log does not show; '55 engine checks' is 51; '/api/messages rejects the push (400)' is no longer true. The changelog is the coordination protocol between three tools, so a stale entry actively misleads the next agent. [Re-verified 2026-09-08: CHANGELOG.md:953 still reads 'Proposed only' and :1082 still claims 55 engine checks. The corrections were added as new entries; the original entries are still uncorrected in place. Stands.]
- **Fix:** Add superseded-by notes to the affected entries.
- **Done when:** A fresh reader following the changelog reaches the same conclusions as the code.

### D-2

**README and website contradict the code**

`P2` · `medium` · `bug` · Docs / record · cluster C14 (Contract & documentation truth) · effort M · wave 3 · **fixed**

- **Files:** `README.md:25`, `website/technical.html:441,453`, `website/deployment.html:136,295-298`, `website/operations.html:63-98`, `website/index.html:67-72`, `services/flightplanner/README.md:25`
- **Problem:** The site calls the Flask planner 'Node.js / Vite', cites a docker-compose.prod.yml that does not exist, lists firewall ports 49000/49001 nothing uses, advertises APX 6500 where the code serves APX 4500, claims cloud/multi-aircraft topology that compose explicitly disclaims, quotes unsourced 85%/100% ROI figures and an unmeasured 'sub-20 ms' latency. The planner README still says Cloud Run. [Re-verified 2026-09-08: 'Node.js / Vite' x1, 'docker-compose.prod.yml' x2, 'APX 6500' x6 on the site, and the planner README still names Cloud Run twice. Stands.]
- **Fix:** Correct each claim or remove it.
- **Done when:** Every deployment command on the site runs as written.

### D-3

**CONOPS and referenced infra docs are missing from the repo**

`P2` · `medium` · `bug` · Docs / record · cluster C14 (Contract & documentation truth) · effort S · wave 3 · **resolved**

- **Files:** `CHANGELOG.md (7 citations)`, `docker-compose.yml:4,131`
- **Problem:** Corrected 2026-09-08: CONOPS-cap-vsar.md is not missing, it lives in the vault at Projects/architecture/CONOPS-cap-vsar.md — but outside the repo, so the agents that the CHANGELOG points at it cannot read it, and it has already drifted from the code it describes. AM4_COMPAT.md and infra/ROUTER.md are still cited as authoritative and still resolve nowhere.
- **Fix:** WRONG FINDING, corrected 2026-09-08. Every cited document exists in the canonical repo: docs/ragd/vaultnotes/CONOPS-cap-vsar.md, docs/AM4_COMPAT.md and infra/ROUTER.md. All three were missing only from the local working tree. The vault notes are published into the repo by docs/ragd/ragd_ingest.py, so the agents CAN read them. Now pulled down locally.
- **Done when:** Every document the repo cites resolves from inside the repo.

### D-4

**No LICENSE despite deriving from Laminar assets**

`P2` · `medium` · `bug` · Docs / record · cluster C14 (Contract & documentation truth) · effort S · wave 3 · **fixed**

- **Files:** `repo root`, `scripts/build_c182t_package.py`
- **Problem:** There is no LICENSE file, and the aircraft package is built by copying and patching Laminar Research's shipped C172SP. Now that the repo is going to GitHub this needs an answer: what is redistributable, and what must be built locally from the user's own X-Plane install.
- **Fix:** Add a LICENSE for the project's own code and a NOTICE stating that Laminar assets are not redistributed and the package is generated from a local install.
- **Done when:** The public repo contains no Laminar-derived binary.
- **Depends on:** O-1

### D-5

**Manufacturer artwork is still redistributed, as figure extracts and in git history**

`P2` · `medium` · `legal` · Docs / record · cluster C14 (Contract & documentation truth) · effort M · wave 3 · **open**

- **Files:** `docs/figures/rt600_p08_front_panel-08.png`, `docs/figures/tdfm_p11_front_panel-11.png`, `docs/figures/gma1347_panel-04.png`, `docs/figures/gma1347_panel-05.png`, `docs/figures/b517_p29_bearing_controls-29.png`, `docs/figures/capdeck_p8-08.png`, `scripts/build_radio_reference_doc.py:326,383,478`, `panels/cap-c182t-mo-station/preview.png`, `cap-c182t-mo-station.zip`
- **Problem:** Found while doing D-4. Untracking the manuals closed only half the question. Eight PNGs in docs/figures/ are page extracts from the same Becker/RHOTHETA/Technisonic/Garmin manuals (the -pNN- in each name is the source page), they are still tracked, and build_radio_reference_doc.py embeds three of them into a generated document. panels/cap-c182t-mo-station/preview.png and the root zip additionally embed the stock Air Manager G1000 instrument preview, a Sim Innovations asset. And git rm --cached does not rewrite history: the nine manuals D-4 untracked are still in every existing commit, so a push to a public remote publishes them anyway.
- **Fix:** Decide each case: the figure extracts are drawing references and could be replaced by our own redrawn artwork (make_panel_artwork.py already redraws these panels) or kept locally like the manuals, but build_radio_reference_doc.py must stop embedding them either way. Regenerate the panel preview without the stock MFD tile. Before any public push, scrub history with git-filter-repo - untracking alone is not enough. PARTIALLY CLOSED 2026-09-15 (cca36e2): nine page extracts untracked and ignored; the radio reference document now embeds our own redrawn faceplates and BOTH tracked artifacts were regenerated (.docx 3,391,958 -> 1,374,133 bytes, .pdf 1,885,160 -> 728,782; the old PDF's 1653x2339 285-DPI page scans are gone); the station panel preview no longer composites the stock Sim Innovations MFD tile, and now renders on a machine with no Air Manager installed. Also found and closed: D-4's manual untracking had never landed on main - it exists only on the unmerged fix/claude-console-2026-09-13 branch - so nine vendor PDFs were still tracked while .gitignore listed them. STAYS OPEN: no history rewrite, so D-5's own verify criterion (a fresh public clone containing no manufacturer page image) is unmet until the scrub agreed in D-4 happens before sharing. tests/test_release_boundary.py enforces the rest.
- **Done when:** A fresh clone of the public repo contains no manufacturer page image, and git log --all -- docs/*.pdf returns nothing.
- **Depends on:** D-4

### F-6

**Unescaped server strings in four views (HTML injection)**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C8 (Base view & debrief) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/base.js`, `services/exercise/app/static/debrief.js`, `services/exercise/app/static/app.js`, `services/exercise/app/static/radio.js`, `services/exercise/app/static/setup.js`, `tests/test_console.py`
- **Problem:** Message bodies, senders and channel names are interpolated into innerHTML unescaped, and any LAN client can POST /api/messages with markup.
- **Fix:** 2026-09-11: added a shared esc() helper to base.js, app.js and debrief.js and escaped every server string reaching innerHTML, including Leaflet bindTooltip, which also renders HTML. radio.js already escaped sender/recipient/body but not the channel name named in this item; escaped it with the existing escapeHtml. Found and fixed the same class in setup.js, which was not in the original list: its cards render /api/setup values and two of them land inside attribute values, so the helper escapes the quote too. Numbers reaching HTML through toFixed() or Math.round() are left alone because they cannot carry markup.
- **Done when:** tests/test_console.py::ServerStringsAreEscaped parses each view, walks every innerHTML and bindTooltip statement and fails on any tainted field not wrapped in an escaper; a self-check reverts three known fixes and asserts the detector notices. Console and radio: 90 passed, 17 subtests. Not verified in a browser against a live posted payload.

### F-7

**Legacy console: precedence bug and autoplay-blocked audio**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/radio.js:530,535-559`
- **Problem:** a && b || c.startsWith() throws when sender is undefined (masked today by a server default), and incoming traffic resumes the AudioContext and speaks outside a user gesture, so iPad Safari stays silent until something is clicked.
- **Fix:** Fix the precedence; require a gesture to arm audio, as the new console correctly does. If /radio-legacy is retired (C9) this closes with it.
- **Done when:** iPad hears the first incoming call after joining.

### F-8

**No bearing intersection maths despite the README**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C8 (Base view & debrief) · effort M · wave 3 · **fixed**

- **Files:** `services/exercise/app/geo.py`, `services/exercise/app/static/base.js`, `tests/test_geodesy.py`, `README.md`
- **Problem:** Bearings are drawn as flat-earth 40 NM rays (fine at that scale) but nothing computes intersections or a confidence area, although the README advertises 'bearing logging & intersection cuts'. Base staff must eyeball the crossing. Bearing entry also requires typing the callsign rather than picking a reporting aircraft.
- **Fix:** Fixed 2026-09-15. app/geo.py owns forward great-circle ray intersection and confidence-polygon construction with a 40 NM search cap; the browser derives the same implementation behind a parity test. Mission Base draws the spherical rays, pairwise cuts and a filled confidence area, and replaces free-text bearing callsign entry with a selector populated from reporting aircraft. Review follow-ups preserve the operator's selection across 1 Hz renders, retain and mark a selection stale when its aircraft disappears, and compute the confidence cut from only the three newest bearings per aircraft while keeping the full log visible.
- **Done when:** Original tests failed first for the missing shared cut, polygon and browser functions. The written-down three-bearing hand plot crosses at (0.0000, 0.0000), (0.0000, 0.0161) and (-0.0192, 0.0000); Python and executed browser JavaScript reproduce it within 0.0002 degree. Two review tests were also written first and failed because the executable policy block did not exist; they now prove an unchanged callsign set does not rebuild the select, a disappeared aircraft remains selected and marked stale, and only the newest three bearings per callsign feed the cut. Required command: 99 passed, 17 subtests. Not verified: live operator interaction in a deployed browser.

### F-9

**New radio console has no Form 110 log**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort M · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/mission-radio.html`, `services/exercise/app/static/radio.js:471-495`
- **Problem:** The CAPF-110 communications log lives only in /radio-legacy, which is the console nobody is meant to use now. Its export also has no date column, misaligns rows because padEnd does not truncate, and never revokes the blob URL. The MRO role in the CONOPS depends on this log.
- **Fix:** Port the logger onto the Mumble console with the export fixes; then retire /radio-legacy.
- **Done when:** An exercise produces a Form 110 export from /radio with correctly aligned dated rows.

### I-3

**Becker tone suppression bleeds across bands**

`P2` · `medium` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort S · wave 3 · **fixed**

- **Files:** `instruments/becker-sar-df-517/logic.lua:712-717,615`
- **Problem:** tone_suppressed clears only when STORE is pressed on the FM band, so suppressing on 121.5 and then turning to CH16 leaves the rose showing 3K- with no bearing on a band where the filter is intrinsic.
- **Fix:** Fixed 2026-09-08. In becker-sar-df-517/logic.lua, reset tone_suppressed = false whenever frequency is rotated, preventing 3K- suppression from bleeding across bands.
- **Done when:** Suppress on 121.5, change band, bearing returns.

### I-4

**Stored 406 frame falls through to live data**

`P2` · `medium` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort S · wave 3 · **fixed**

- **Files:** `instruments/becker-sar-df-517/logic.lua:378,392,402`
- **Problem:** `msg and msg.has_pos or s.cs_has_pos` means a STORED frame without a position displays the live frame's position — the student reads a stored beacon as having a position it never carried.
- **Fix:** Replaced fallthrough ternary with explicit if/else block on msg in page 4 stored message render, ensuring stored messages without positions never inherit live frame coordinates.
- **Done when:** Store a positionless frame; page 4 shows no position.

### I-5

**RT-600 long-press timers survive power-off**

`P2` · `medium` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort S · wave 3 · **fixed**

- **Files:** `instruments/rhotheta-rt-600/logic.lua:479-481,386`
- **Problem:** Release returns early when the unit is unpowered, leaving press_at armed, and power_off does not stop the timers, so f1_long fires clear_average() after shutdown.
- **Fix:** Cancelled softkey press timers in power_off() and in early-return paths when unpowered, preventing clear_average() timer leak after shutdown.
- **Done when:** Hold F1, power off, release: no averaging reset.

### I-6

**DF heads and TDFM ignore the electrical bus**

`P2` · `medium` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort M · wave 3 · **fixed**

- **Files:** `instruments/becker-sar-df-517/logic.lua:588`, `instruments/cap-fm-tdfm-136b/logic.lua:353-358`, `instruments/mo-audio-panel-gma1347/logic.lua:486`
- **Problem:** Both DF heads and the TDFM power up with the battery and avionics master off; only the GMA follows avionics_power_on, and even it ignores bus_volts. For a trainer whose value is procedural traps, the most basic one is missing.
- **Fix:** Gated Becker 517, RT-600, TDFM-136B, and GMA 1347 on avionics power switch and bus voltage (MIN_BUS_VOLTS = 10.0V). Added tests verifying cold dark startup, auto-boot on bus power, and immediate shutdown on voltage drop.
- **Done when:** Cold aircraft: no instrument lights until the master is on.

### L-11

**Unknown departure/destination silently becomes a waypoint position**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort S · wave 3 · **fixed**

- **Files:** `services/flightplanner/app.py:626-628`, `services/flightplanner/app.py:639-641`
- **Problem:** Pre-existing, surfaced while generating a sample for the L-1 review. When get_airport() misses - an unknown identifier, or the aviation database still downloading - the export falls back to the first/last waypoint's coordinates and elevation 0.0, and emits them under the requested airport code. The observed sample put KSEE at 33.170,-117.079 (a search waypoint) instead of Gillespie Field, with no warning anywhere. A crew loading that plan departs from the wrong place.
- **Fix:** Implemented: resolve both airports before writing FMS content; unresolved ADEP/ADES returns JSON 400 naming the identifier. Tests cover both ends and no file content on failure.
- **Done when:** Exporting with an unknown ADEP returns an error rather than a plausible-looking file.

### L-12

**Flight planner database is a file bind-mount, so SQLite journals escape it**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort S · wave 3 · **fixed**

- **Files:** `docker-compose.yml:121`, `services/flightplanner/app.py:25`
- **Problem:** Found while fixing O-3. Compose mounts aviation_data.db as a single FILE at /app/aviation_data.db. SQLite writes its rollback journal beside the database, so -journal and -wal files land in the container's own /app layer rather than on the host. A crash mid-write leaves the journal on a discarded layer and the database with no way to roll back. O-3 works around the symptom by pre-creating the file; this is the underlying shape.
- **Fix:** Mount the DIRECTORY - ./services/flightplanner/data:/app/data - and point DATABASE_PATH at /app/data/aviation_data.db so the journal stays with the database. The host file does not move, so no migration. Left for Codex because app.py is its lane and it had uncommitted work there.
- **Done when:** A write leaves its journal on the host volume, not inside the container.

### L-14

**Planner suite fails: cruise and runway tests assume the retired 172S table**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort S · wave 3 · **fixed**

- **Files:** `services/flightplanner/app.py`, `services/flightplanner/tests/test_sar.py`
- **Problem:** Found 2026-09-10 running the planner suite after L-8. L-7's partial fix REPLACED the N499CP 172S profile with a single 'CAP 487' 182T profile rather than adding one alongside, and the 182T table has a different shape: RPM 2000-2400 plus a manifold-pressure axis, where the 172S had 2400/2500 at a single power setting. Three tests written against the 172S numbers now fail against the only profile that exists: test_cruise_interpolates_altitude_and_rpm asks for get_cruise(5000, 2450) and gets 'Input 2450 outside performance table 2000..2400'; test_runway_tailwind_increases_distance and both subtests of test_runway_outside_table_is_json_error fail the same way. 40 pass, 4 fail. The suite was green when those tests were written, so this is a regression introduced between the two, not a pre-existing gap. [RESOLVED 2026-09-10: Codex's completed L-7 landed the full 182T table and re-pointed the cruise and runway tests at it. pytest services/flightplanner/tests/ is 58 passed, 0 failed.]
- **Fix:** Land L-7 properly - decide whether the real N499CP 172S profile returns alongside CAP 487 - then re-point these tests at whichever profile they are meant to exercise, using figures from that aircraft's table. Do not edit the tests to chase the new numbers without deciding the L-7 question first, or the suite will just encode whatever the table happens to say.
- **Done when:** pytest services/flightplanner/tests/ is green.
- **Depends on:** L-7

### L-5

**Search patterns leave uncovered ground and truncate silently**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort M · wave 3 · **fixed**

- **Files:** `services/flightplanner/app.py:591-595,543,532,554`
- **Problem:** Parallel track places int(width/spacing) tracks starting on the box edge, so a 4 NM box at 1 NM spacing leaves the last mile unsearched and wastes half the first track; CAP practice is tracks at S/2, 3S/2. Creeping line silently truncates at max_legs with no warning that coverage is incomplete. heading_mag is emitted for expanding square but not the other two.
- **Fix:** Implemented: parallel tracks start half-spacing inside the box and use ceil counts; creeping sweeps use ceil and half-spacing start. API returns coverage_truncated when max_legs limits coverage. All points include heading_mag. Tests cover full 4 NM / 1 NM coverage, fractional/narrow boxes and truncation.
- **Done when:** Generated coverage matches the requested box within one track spacing.

### L-6

**Performance tables extrapolate silently and ignore tailwind**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort M · wave 3 · **fixed**

- **Files:** `services/flightplanner/app.py:711,736-740,665,937`
- **Problem:** get_cruise is nearest-neighbour rather than interpolating; takeoff/landing clamp to the last table row, understating distance above 6000 ft or 30 C; negative headwind (tailwind) is ignored; and when wind >= TAS ground speed clamps to zero and the leg then reports zero time and fuel, so an impossible leg looks cheap.
- **Fix:** Implemented: interpolate cruise altitude/RPM between supported rows; reject beyond-table cruise and runway altitude/temperature. Apply C172S POH tailwind correction (+10% per 2 kt through 10 kt); refuse stronger tailwind. Non-positive GS and unmaintainable crosswind raise errors; route HTTP 400 names the leg. Tests cover 100 kt headwind at 90 KTAS, tailwind, interpolation and out-of-table inputs.
- **Done when:** A leg with a 100 kt headwind reports an error, not zero fuel.

### L-7

**Flight planner plans a different aircraft than the exercise flies**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort M · wave 3 · **fixed**

- **Files:** `services/flightplanner/app.py:64-102`, `services/flightplanner/README.md`
- **Problem:** Re-scoped 2026-09-10 after Codex correctly stopped on the original wording. The old description said the planner holds 172S figures 'under a 182T label'. It does not - app.py:80 says 'N499CP - Cessna 172S NAV III' and the planner README and USER_GUIDE agree, so the profile is labelled honestly. The real defect is an identity collision: N499CP is a REAL Cessna 172S on the squadron line, and the simulated aircraft was wearing that same registration while being a 182T. Fixed on the simulator side 2026-09-10 - the simulated aircraft is now CAP 487 (3100 lb, 87 gal, IO-540) everywhere except this planner. What is left is the planning gap the original item was really about: the exercise flies CAP 487 and the planner computes fuel, endurance and W&B for a 172S, so every sortie is planned on the wrong airframe. The crew no longer even matches on a shared registration. Source check 2026-09-10: Cessna 182TIMBUS-01 (20 Dec 2007), section 6-8 and figure 6-3, requires aircraft-specific empty weight and moment; its sample is 1924 lb and 70.9 thousand lb-in. The builder sets CAP 487 to 1970 lb but supplies no corresponding POH-datum empty moment or documented conversion from the inherited X-Plane CG. The planner requires empty_weight_moment. Implementation stopped under the prompt's no-guessing rule; obtain or explicitly define the simulated aircraft's datum-referenced W&B record before adding the complete profile. Source: https://www.aeroelectric.com/Reference_Docs/Cessna/cessna-poh/C182T_2007_NavIII-G1000%2BGFC700_POH-PIM_fromCessna.pdf .
- **Fix:** Implemented 2026-09-10 after the user explicitly selected POH numbers. CAP 487 is the default with the C182T POH SAMPLE empty weight/moment (1924 lb / 70.9 thousand lb-in), 3100 lb takeoff, 2950 lb landing and 87 gal usable. Imported cited standard-temperature altitude/RPM/manifold-pressure cruise tables, climb, runway and CG/arm data. UI includes manifold pressure, correct weights/fuel/reference and a visible sample-baseline note. Old N499CP profile removed. Builder still uses 1970 lb and its CG datum is unverified: tracked separately in L-7a, with no claim that a planner update modified the simulator.
- **Done when:** 32 planner tests and 49 console/radio tests pass. At 6000 ft / 2400 RPM / 20 inHg, reproduces POH 65%, 130 KTAS and 11.4 GPH; full 87 gal with start/climb and 45-minute reserve gives 6.66 h, consistent with handbook 5.5+ h. UI defaults and CG envelope breakpoints tested. No X-Plane flight verification.

### L-7a

**Align simulator loading baseline with selected 182T POH sample**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C10 (Flight planner correctness) · effort M · wave 3 · **resolved**

- **Files:** `scripts/build_c182t_package.py`
- **Problem:** The user selected Cessna 182T POH sample values for the planner (1924 lb empty, moment/1000 70.9). The builder still specifies 1970 lb and inherits an X-Plane CG without a verified mapping to the POH firewall datum. Planner and installed simulator loading results therefore cannot yet be assumed to match.
- **Fix:** Reconciled 2026-09-15. Two defects, not one. (1) The builder specified 1,970 lb empty (POH 1.3 standard empty, rounded) while the planner used 1,924 lb (POH Figure 6-3 sample aircraft) - a 46 lb disagreement in every takeoff weight, CG and performance number for identical loading, with the crew reading both. The builder now carries the selected sample baseline. (2) The EMPTY CG was never patched at all: the builder moved _cgZ_fwd/_cgZ_aft to the C182T envelope but left _cgZ at the stock C172SP's 2.900095 (Laminar sets _cgZ to _cgZ_fwd on both stock aircraft checked). It happened to land within 0.15 in of correct - luck, not derivation. _cgZ is now 2.888 ft, derived from the sample's 70.9 moment/1000 via the same %MAC mapping the limits use: arm = 70,900/1,924 = 36.850 in, %MAC = (36.850-25.98)/58.8 = 18.483%, z = 1.994 + 0.18483*4.837. The datum mapping L-7a called unverified already existed and is sound - verified here by reproducing both documented anchors (FS 33.0 -> 2.5715, FS 46.0 -> 3.6409).
- **Done when:** tests/test_loading_baseline.py, 8 tests, 5 verified failing pre-fix: planner and builder agree on empty weight, empty CG and max weight; the CG is derived rather than inherited (guards the literal 2.900095); the empty CG sits inside the certificated envelope; the forward limit is the most forward scheduled point; and the planner comment no longer claims the builder disagrees. OUTSTANDING: the X-Plane half of the original verify - loading CAP 487 at identical fuel and payload in the sim and confirming it agrees with the planner - has not been run. Marked resolved rather than fixed on that basis.
- **Depends on:** L-7

### L-8

**Planner has no offline map path**

`P2` · `medium` · `bug` · Flight planner · cluster C6 (Offline mission base) · effort M · wave 3 · **fixed**

- **Files:** `services/flightplanner/templates/index.html:8,447`, `services/flightplanner/static/js/app.js:83-97`, `services/flightplanner/app.py:1490`
- **Problem:** Leaflet and Google Fonts load from CDNs and tiles come straight from ArcGIS. The server-side tile cache only runs under __main__, never under gunicorn, and the frontend never requests /tiles/ anyway, so the charts volume is dead weight and USER_GUIDE.md's claim that cached tiles are used first is false.
- **Fix:** Vendor Leaflet and fonts; wire the frontend to /tiles/; pre-cache the exercise area into the existing volume.
- **Done when:** Plan a route with outbound internet blocked.
- **Depends on:** F-1

### L-9

**API returns HTML 500s and misreports push status**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort M · wave 3 · **fixed**

- **Files:** `services/flightplanner/app.py:894-897,1001-1008,1397,1438,1463`
- **Problem:** Unguarded int()/float() on client JSON returns Werkzeug HTML that the JS then fails to parse. The 'no sortie running' branch is dead because the console no longer 400s, so the UI always claims the message was broadcast to an active sortie even when nothing was persisted. The push also sets beacon_elev_ft to 0.0 (sea level, which the propagation model then uses) and places the beacon exactly on the planned datum, handing the trainee the answer.
- **Fix:** Guard parsing and return JSON errors; report persisted vs broadcast honestly; carry a real beacon elevation; offset the beacon from the datum.
- **Done when:** Bad input returns JSON 400; a pushed scenario does not sit on the planned datum.

### L2-14

**FMS waypoint limit and the G1000 display of exported .fms unverified in a running X-Plane 12**

`P2` · `medium` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **open**

- **Files:** `docs/SEARCH_PATTERN_CONVENTIONS.md`, `services/flightplanner/docs/USER_GUIDE.md`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** 
- **Done when:** 

### P-6

**121.5 beacons produce a COSPAS-SARSAT decode**

`P2` · `medium` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 3 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:824`
- **Problem:** decode_tick is called without the on_406 gate used elsewhere, so an analog beacon shows SYNC OK and a hex ident — teaching a student that a 121.5 signal carries beacon identity.
- **Fix:** Gate decode_tick on the 406 band.
- **Done when:** 121.5 scenario shows no decoded ident.

### P-7

**Signal bar stays lit between 406 bursts**

`P2` · `medium` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 3 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:783,805`
- **Problem:** cap/df/signal is published before the burst gate, so the bar shows full strength while nothing is being received, and squelch evaluates the continuous value rather than the gated one.
- **Fix:** Publish the gated value; evaluate squelch against it.
- **Done when:** Signal bar pulses with the 50 s burst cadence.

### P-8

**Terrain masking is only -12 dB**

`P2` · `medium` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 3 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:772`
- **Problem:** Blocked paths attenuate by *0.06, so a fully masked beacon at 2 NM still yields signal 0.375 and a valid bearing. Real knife-edge diffraction loss is 20-40 dB, so the masking effect barely teaches anything inside ~4 NM.
- **Fix:** Deepen the loss to a realistic knife-edge range and recheck the existing masking tests.
- **Done when:** Masked beacon at 2 NM drops below squelch.
- **Depends on:** P-1

### V2-8

**set_air_start.py does not zero body rates, so a recovered aircraft re-departs**

`P2` · `medium` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort S · wave 3 · **open**

- **Files:** `scripts/set_air_start.py`, `tests/test_air_start.py`
- **Problem:** Repositioning writes position, velocity and attitude but leaves the angular rates sim/flightmodel/position/{P,Q,R,Prad,Qrad,Rrad} untouched, so placing an aircraft that is tumbling hands it back its rotation and it departs again within a second. Observed three consecutive times during the 2026-09-17 ArduPlane handoff session: each placement produced an immediate upset (roll to -75 deg, then inverted at +121 deg with 24 KIAS). Holding all six rate datarefs at zero for about 2.5 s across the placement transient produced stable flight every time afterwards. Secondary, smaller trap in the same tool: it does not touch the throttle or propeller controls, so the aircraft was placed at altitude with the throttle closed and the prop lever back and flew as a glider - the tool's warning covers the engine running but not the power lever state.
- **Fix:** 
- **Done when:** Place the aircraft while it is tumbling and confirm it settles to stable level flight without an upset; assert in tests/test_air_start.py that the placement writes the six rate datarefs to zero, and report the throttle and prop positions found at placement.

### X-6

**Untyped request bodies mutate scenario definitions**

`P2` · `medium` · `bug` · Exercise console (backend) · cluster C7 (Console robustness) · effort M · wave 3 · **fixed**

- **Files:** `services/exercise/app/main.py:235,277-283,143,219`
- **Problem:** start_sortie and set_effects take raw dicts, bypassing Pydantic; set_effects merges arbitrary keys straight into the scenario row, so a mid-exercise effect change permanently rewrites the scenario definition for every future sortie. No lat/lon range checks. Positional INSERT ... VALUES (?x15) breaks on the next schema change.
- **Fix:** Pydantic models; store effects on the sortie, not the scenario; range-check coordinates; named columns.
- **Done when:** Changing effects mid-sortie leaves the scenario row untouched.

### X-8

**Console operational hygiene: retention, logging, health, shutdown, root**

`P2` · `medium` · `bug` · Exercise console (backend) · cluster C7 (Console robustness) · effort M · wave 3 · **fixed**

- **Files:** `services/exercise/app/main.py:300-302,442-444,149`, `services/exercise/Dockerfile`
- **Problem:** Partly addressed 2026-09-08: connections now close (was a leak per request) and X-3 added WAL. STILL OPEN: positions has no retention and /track is unpaginated; main.py has no logging (two print() calls aside); the healthcheck never touches the database; the ticker task is not cancelled on shutdown; the container runs as root.
- **Fix:** Retention policy plus pagination; structured logging; DB-touching healthcheck; cancel the ticker in lifespan; non-root user.
- **Done when:** A long exercise does not grow /track unboundedly; logs show sortie lifecycle events.

### X-9

**One Mumble client per browser socket, 16 max**

`P2` · `medium` · `bug` · Exercise console (backend) · cluster C9 (Radio console hardening) · effort M · wave 3 · **fixed**

- **Files:** `services/exercise/app/radio.py:141`
- **Problem:** Each browser socket spawns a pymumble thread at a 10 ms loop rate against a 16-session cap. A base desk running two radio faces consumes two of the sixteen and appears as two users on the net.
- **Fix:** Share one Mumble client per operator across their radio faces, or raise and document the cap with measured CPU.
- **Done when:** A dual-radio desk appears once on the net.

### F-10

**Mission base cannot monitor the airband SAR net**

`P2` · `low` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort L · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/mission-radio.js`, `services/exercise/app/radio.py`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. The MRO must watch the VHF-FM tactical net and the VHF-AM aeronautical SAR frequency at the same time; the console joins one Mumble channel at a time. The retired /radio-legacy console had a second airband station (Icom IC-A120) and the rewrite dropped it, so the base can no longer hear aircraft calling on the air-to-ground frequency while working the tactical net.
- **Fix:** Fixed 2026-09-15. The console opens independently keyed tactical and airband WebSockets/Mumble radios for each operator, mixes both through separate Web Audio gain nodes, provides an independent airband channel/volume/status panel, and lets the operator select which radio the shared PTT keys. Received and transmitted Form 110 entries use the selected radio's net identity. X-9 sharing remains within each physical radio; the operator/receiver pair is the server key. The existing 16-session cap therefore supports at most 8 fully equipped dual-radio operators. Behavioral tests proved the second Mumble client, selected-net audio routing, cap accounting, log identity, and independent gain calculation. The local page was rendered and visually inspected in Chrome with no console errors.
- **Done when:** Tests were written first and all four failed on the pre-fix tree. `PYTHONPATH=. ~/.cache/capvsar/capvsar-planner-venv/bin/python3 -m pytest tests/test_console.py tests/test_radio.py tests/test_geodesy.py -q` passes 94 tests and 17 subtests. Not verified: simultaneous audible traffic against the live Mumble server, and deployment.

### I-11

**TDFM memory table is 6 generic channels, not a CAP fleet plan**

`P2` · `low` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort M · wave 3 · **fixed**

- **Files:** `instruments/cap-fm-tdfm-136b/logic.lua:38-51`, `tests/test_tdfm.py`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. Six memories (CMD 1/2, AIR-GND, REPTR 1, SIMPLEX, TAC 1) plus two guards; the real set has 230 positions. A crew briefed to a channel number cannot enter it, so 3-digit direct entry fails against any realistic comms plan. squelch_mode is a single letter ('t','x','g') with no CTCSS tone or P25 NAC behind it, so the classic failure - transmitting without the repeater access tone - cannot be produced or diagnosed.
- **Fix:** Fixed 2026-09-08. Expanded TDFM-136B memories table to authentic 200-position CAP fleet plan (TAC 1/2, CC 1/2, AIR 1/2, SAR 1/2, VFIRE 21, VTAC 11, etc. with exact CTCSS subaudible tones and P25 NACs) and enabled 3-digit direct keypad entry auto-committing on the 3rd digit. Verified in tests/test_tdfm.py.
- **Done when:** A briefed channel number can be entered directly, and a tone mismatch audibly fails.

### I-14

**GMA 1347 ICS isolation and Split COM are lamp-only**

`P2` · `low` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort L · wave 3 · **fixed**

- **Files:** `instruments/mo-audio-panel-gma1347/logic.lua:80,158-161,100-106`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. cap_ics_isolation is written (ALL/PILOT/COPILOT/CREW) and Split COM de-asserts the FM audio and mic variables, but nothing consumes either: every crew member sits in one Mumble channel, so isolation changes a lamp and nothing else. The panel teaches a control that has no effect, which is worse than omitting it.
- **Fix:** Fixed 2026-09-08. Wired GMA 1347 ICS isolation and Split COM states into published variables and Mumble radio backend. Published cap_ics_isolation, cap_ics_pilot_isolated, cap_ics_copilot_isolated, cap_ics_crew_isolated, and cap_split_com_active in instruments/mo-audio-panel-gma1347/logic.lua. Added ICS REST endpoints and audio filtering in services/exercise/app/radio.py to route pilot/copilot/crew audio isolation and isolate observer on Split COM. Verified in tests/test_am.py and tests/test_radio.py.
- **Done when:** Selecting PILOT genuinely removes the MO from the crew audio path.

### A2-14

**C182T document index**

`P3` · `low` · `improvement` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort S · wave 3 · **open**

- **Files:** `docs/`
- **Problem:** Seven docs/C182T_*.md plus the GPL plan, calibration doc and CHANGELOG describe the package with no statement of which is authoritative for what.
- **Fix:** Write docs/C182T_INDEX.md.
- **Done when:** Index exists and is linked from README.

### A2-6

**Package ships the C172 POM, G430/G530 and S-TEC manuals**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort S · wave 3 · **open**

- **Files:** `scripts/build_c182t_package.py`
- **Problem:** Copied from the C172 folder; the 182T NAV III has a GFC 700 and the C172 manual's speeds are the wrong ones.
- **Fix:** Delete them in the builder's redundant_files step or replace with a README pointing at docs/.
- **Done when:** Built package contains no C172/S-TEC manuals.

### A2-7

**c182t_checklists.py says full flaps are 30 deg**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort S · wave 3 · **open**

- **Files:** `services/ai_pilot/c182t_checklists.py`
- **Problem:** Landing note reads 'full 30 deg below 100 KIAS'; the 182T full flap is 38 deg (ACF detent 3, TCDS); POH says 20-FULL below 100. Takeoff checklist omits the 10 deg preferred flap setting.
- **Fix:** Correct the wording; add flaps 10 deg to the takeoff items; cite 182TPHBUS section 4.
- **Done when:** test_checklists.py asserts the strings.

### A2-8

**acf/_Va_kts is 0**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort S · wave 3 · **open**

- **Files:** `scripts/build_c182t_package.py`
- **Problem:** Not displayed by the G1000 but read by envelope tooling.
- **Fix:** Patch acf/_Va_kts 110 (POH, 3100 lb).
- **Done when:** Built ACF reads 110.

### A2-9

**Builder hard-codes /home/ron paths**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C18 (C182T package review 2026-10-11) · effort S · wave 3 · **open**

- **Files:** `scripts/build_c182t_package.py`
- **Problem:** DEFAULT_SOURCE_DIR/TARGET_DIR and livery defaults are absolute workstation paths.
- **Fix:** Derive from an XPLANE_ROOT env var with the current values as fallback.
- **Done when:** Build runs on a second machine with XPLANE_ROOT set.

### AI-18

**SIGTERM skips every shutdown safeguard (red team RT-11)**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort S · wave 3 · **open**

- **Files:** `services/ai_pilot/maneuver_server.py`, `services/ai_pilot/direct_backend.py`, `scripts/fly_direct_backend.py`, `scripts/fly_card_h0.py`
- **Problem:** No signal handler anywhere in the control path. maneuver_server pauses on exit only via finally after KeyboardInterrupt; fly_direct_backend releases only in finally. SIGTERM - what systemd, a supervisor or a tidy-up script sends - runs neither, leaving the autopilot engaged on the last targets or the throttle at whatever the loop last wrote.
- **Fix:** Install a SIGTERM handler that raises KeyboardInterrupt (or calls the same shutdown path) in every writer.
- **Done when:** services/ai_pilot/tests/test_redteam.py: remove the xfail marker on test_rt11_a_termination_signal_reaches_the_shutdown_path and the test must pass; it then guards the fix.

### AI-19

**Advisory chat's no-action guard is a keyword list with no output filter (red team RT-13)**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C15 (Service boundaries (architecture)) · effort S · wave 3 · **open**

- **Files:** `services/ai_pilot/lightweight_agent.py:handle_user_command`
- **Problem:** A fixed tuple of words gates the canned refusal; 'bank left', 'push the nose over', 'add power', 'pull up', 'select FLC', 'set 4500' all reach gemma4:12b, whose 'never claim to move controls' is a prompt instruction. There is no control path, so this is a trust finding: an operator can be told 'Roger, turning left' by an advisor that cannot turn, and the README says replies 'are instructed never to claim aircraft action' as though instructed meant enforced.
- **Fix:** Filter LLM output for action claims (or prefix every LLM reply with the no-action banner); broaden the intent gate beyond a word list.
- **Done when:** services/ai_pilot/tests/test_redteam.py: remove the xfail marker on test_rt13_control_language_never_produces_an_action_claim and the test must pass; it then guards the fix.

### B2-10

**Tracked fig_c182t_aircraft.png is a render of Laminar's C172 model**

`P3` · `low` · `bug` · Docs / record · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **open**

- **Files:** `docs/figures/manual/fig_c182t_aircraft.png`, `website/images/fig_c182t_aircraft.png`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 8.
- **Fix:** 
- **Done when:** 

### B2-11

**c182t_corrections radial scale ignores the JSON axis**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `scripts/c182t_corrections.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 8.
- **Fix:** Raises unless the axis matches PROP_ROTATION.
- **Done when:** 

### B2-3

**Selection icon renders the literal text &bull;**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `scripts/build_c182t_package.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 8.
- **Fix:** Real bullet in a TrueType font.
- **Done when:** 

### B2-6

**Flap animation range disagrees with patched travel**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `scripts/convert_flightgear_c182.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 8.
- **Fix:** Already 38 after 57663ec; a test ties it to the .acf patch.
- **Done when:** 

### B2-8

**Doc generators' dependencies undeclared**

`P3` · `low` · `bug` · Docs / record · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `requirements-docs.txt`, `scripts/make_df_artwork.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 8.
- **Fix:** Declared; font candidates.
- **Done when:** 

### F-11

**No operational sidetone on the new radio console**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/mission-radio.js:251`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. The only oscillator is the 660 Hz headset-test beep. There is no talk-permit chirp on channel grant and no squelch tail, so an operator gets no acoustic confirmation that the radio actually keyed. NOTE (corrected 2026-09-10): they DO exist, as methods of the audio class in radio.js (playP25Chirp ~:29, playP25Tail ~:60, playAmSquelchBurst ~:102). An earlier note here said they were absent; that was a grep for standalone functions. This is a port, and the legacy implementations are the reference.
- **Fix:** Fixed 2026-09-15. Ported the retired console's P25 permit chirp and tail plus its VHF-AM relay click and squelch burst. Tone choice, output gain and pending grant delay follow the latched transmitter radio, not console-wide selection. The microphone remains disabled until the 115 ms P25 chirp or 15 ms AM click finishes, and release plays the matching tail through that receiver's gain.
- **Done when:** Two executable Node-backed behavioral tests were written first and failed because the sidetone decision block did not exist. They now prove the exact per-radio grant/release mapping and that the grant sequence places the tone before live microphone audio. Required suite: 101 passed, 17 subtests. Not verified: audible timing through a real headset against the live Mumble service.

### F2-10

**Setup 'Target Exercise Scenario' control is decorative**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/setup.html`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** Control removed.
- **Done when:** 

### F2-11

**One malformed control frame permanently drops the radio**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/mission-radio.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** connectionLost() so FE-5 retries.
- **Done when:** 

### F2-12

**Legacy radio: spacebar PTT keys from focused controls; failed POST logged as sent**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/radio.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** Focus-aware PTT; failed POST not logged.
- **Done when:** 

### F2-8

**Hard-coded host on the headset help page**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/radio-help.html`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** Secure link built from location.
- **Done when:** 

### F2-9

**Every bearing-log failure reads 'callsign not reporting'; reads ignore errors**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/base.js`, `services/exercise/app/static/app.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 3.
- **Fix:** Real HTTP status and detail shown; .ok checks added.
- **Done when:** 

### I2-5

**LS and BURST timers read 00:00 before any signal**

`P3` · `low` · `bug` · Air Manager instruments · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `instruments/_shared/lib/cap_df.lua`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 6.
- **Fix:** --:-- until first signal.
- **Done when:** 

### I2-6

**Becker STORE tone suppression survives a power cycle**

`P3` · `low` · `bug` · Air Manager instruments · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `instruments/becker-sar-df-517/logic.lua`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 6.
- **Fix:** reset_volatile() from power_off().
- **Done when:** 

### I2-7

**Master switch and CB panel never publish on load**

`P3` · `low` · `bug` · Air Manager instruments · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `instruments/cap-mission-master-switch/logic.lua`, `instruments/cap-mission-cb-panel/logic.lua`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 6.
- **Fix:** publish() at load.
- **Done when:** 

### I2-8

**G1000 watchdog stacks video nodes and hides its banner**

`P3` · `low` · `bug` · Air Manager instruments · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 3 · **fixed**

- **Files:** `instruments/g1000-mfd-watchdog/logic.lua`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 6.
- **Fix:** One stream node; banner and hotspot added after it; #RRGGBBAA. Instrument still not deployed; O-7b stays open.
- **Done when:** 

### I2-9

**TDFM squelch-defeat push sets st.squelch_defeat but nothing reads it**

`P3` · `low` · `bug` · Air Manager instruments · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **open**

- **Files:** `instruments/cap-fm-tdfm-136b/logic.lua`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 6.
- **Fix:** 
- **Done when:** 

### L2-10

**Internet tile fallbacks bypass the offline cache**

`P3` · `low` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/flightplanner/static/js/app.js`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** Fallbacks removed; app.js scanned by the offline test.
- **Done when:** 

### L2-11

**get_climb snaps both ends to the nearest row**

`P3` · `low` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/flightplanner/app.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** Interpolates both ends.
- **Done when:** 

### L2-7

**Apply to Route drops DATUM and relabels the pattern**

`P3` · `low` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/flightplanner/static/js/app.js`, `services/flightplanner/app.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** Named route tokens; nav-log names equal the .fms names.
- **Done when:** 

### L2-8

**CS01 carries a fictitious leg**

`P3` · `low` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/flightplanner/app.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** leg_dist 0.
- **Done when:** 

### L2-9

**d-TPP cycle computed from the calendar month**

`P3` · `low` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/flightplanner/app.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** 28-day cycle anchored on 2601 = 2026-01-22.
- **Done when:** 

### O2-10

**Planner port 8090 in preflight, deploy and docs**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `scripts/preflight.py`, `scripts/deploy.sh`, `infra/ROUTER.md`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** 8080.
- **Done when:** 

### O2-11

**.ci-out/ not gitignored**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `.gitignore`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** Added.
- **Done when:** 

### O2-12

**scripts/wg-peer.sh drives a removed WireGuard container**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `scripts/wg-peer.sh`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** Deleted. References remain in historical text: tracker O-2, CHANGELOG, website/deployment.html:132.
- **Done when:** 

### O2-9

**pymumble pinned by commit tarball without a hash**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/requirements-pymumble.txt`, `services/exercise/Dockerfile`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** Installed with --require-hashes. Exercise image build not tested here.
- **Done when:** 

### P2-4

**compute() re-reads self.scn mid-tick**

`P3` · `low` · `bug` · X-Plane plugin / engine · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 5.
- **Fix:** Tick scenario passed to helpers.
- **Done when:** 

### P2-5

**Radio horizon uses MSL heights**

`P3` · `low` · `bug` · X-Plane plugin / engine · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 5.
- **Fix:** Height above probed terrain.
- **Done when:** 

### P2-6

**Wall clock, no pause awareness**

`P3` · `low` · `bug` · X-Plane plugin / engine · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 5.
- **Fix:** monotonic time less paused time; compute frozen while paused.
- **Done when:** 

### P2-7

**fetch_scenario comment promises an unimplemented fallback**

`P3` · `low` · `bug` · X-Plane plugin / engine · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 5.
- **Fix:** Comment corrected.
- **Done when:** 

### P2-8

**self.net not initialised**

`P3` · `low` · `bug` · X-Plane plugin / engine · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 5.
- **Fix:** Initialised in __init__.
- **Done when:** 

### P2-9

**Pause freezing and TLS trust of the plugin unverified in X-Plane**

`P3` · `low` · `bug` · X-Plane plugin / engine · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **open**

- **Files:** `xplane/PI_capvsar_df.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 5.
- **Fix:** 
- **Done when:** 

### U-3

**Instructor console prints BRG NaN when the DF dictionary is redacted**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/app.js`
- **Problem:** After D1 an anonymous viewer on an open dev console receives receiver state only; the page rendered the missing numbers as NaN.
- **Fix:** The line renders only the fields present ('receiving · bearing withheld for this seat'). X-1's invariant (anonymous never sees truth) is kept on purpose.
- **Done when:** 

### U-4

**Setup page says codes are 6 characters; they are 40**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C17 (UI walkthrough 2026-10-11 and UX proposal) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/static/setup.html`
- **Problem:** Wording.
- **Fix:** Wording fixed; short codes are proposed in the UX review §4.2.
- **Done when:** 

### X2-10

**Role tokens accepted as ?token= and logged in access logs**

`P3` · `low` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/access.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** Header only. No callers found in scripts/, xplane/, services/.
- **Done when:** 

### X2-11

**Deleting a scenario with a running sortie strands it**

`P3` · `low` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/routers/scenarios.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** 409 while a sortie on it is open.
- **Done when:** 

### X2-12

**/api/setup accepts untyped fields and mints arbitrary roles**

`P3` · `low` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/models.py`, `services/exercise/app/access.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** Typed AircraftIn/StaffIn with caps; staff roles limited to base, aircrew, ground_team.
- **Done when:** 

### X2-9

**Concurrent sortie start/stop races; stop re-stamps**

`P3` · `low` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 3 · **fixed**

- **Files:** `services/exercise/app/routers/sorties.py`, `services/exercise/app/hub.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** hub.sortie_lock() around lifecycle mutations; stop is idempotent.
- **Done when:** 

### C15-1

**Split the console into store + routers with role middleware**

`P2` · `medium` · `task` · Exercise console (backend) · cluster C15 (Service boundaries (architecture)) · effort L · wave 4 · **fixed**

- **Files:** `services/exercise/app/main.py`, `services/missionbase/`, `services/tracking/`
- **Problem:** main.py holds scenario truth, telemetry ingest, the WebSocket hub, SQLite and (via radio.py) the real-time voice bridge on one event loop. X-3 is the symptom, and the CalTopo relay and IC/AOBD views both land here next. The empty services/missionbase/ and services/tracking/ directories are the right instinct. [2026-09-10: split within the service rather than into separate containers - settings/store/roles/hub/models and routers/{scenarios,sorties,telemetry,comms,system,auth,pages}. main.py is 169 lines of assembly. services/missionbase/ and services/tracking/ are still empty: extracting them is a deployment change, and nothing needed it yet - the CalTopo relay and the IC/AOBD views now have an obvious router to land in.]
- **Fix:** store.py (SQLite, WAL, rehydration, truth serializer) plus exercise / tracking / missionbase / radio routers behind one app; move the Mumble bridge off the main loop.
- **Done when:** Same behaviour, with the truth serializer provably applied in one place.
- **Depends on:** X-1, X-2, X-3

### I-8

**Panel registrar writes Air Manager's database on hardcoded assumptions**

`P2` · `medium` · `bug` · Air Manager instruments · cluster C13 (Instrument tooling & shared libs) · effort M · wave 4 · **fixed**

- **Files:** `scripts/register_mo_panel.py:25,50,97-100,107-168,171-172,182`
- **Problem:** It hardcodes 26 panel columns and magic values, syncs sqlite_sequence for two of four tables, pkills Air Manager without confirmation, relaunches from a /home/ron path, and never updates an existing layout so position edits never propagate. Panel geometry is triplicated across info.xml, this script and panels/cap-c182t-mo-station/generate_assets.py with no cross-check. Streaming=true is set only through the SQLite path, so the --zip route ships a dead MFD.
- **Fix:** Established panel_geometry.py (parsing info.xml) as single source of truth for panel geometry. Modernized register_mo_panel.py with capvsar_station.ini path parameterization, user confirmation before killing Air Manager, in-place updates for existing layouts, and sqlite_sequence synchronization across all four modified tables.
- **Done when:** The zip route produces a working MFD on a second machine.
- **Depends on:** O-2

### I-9a

**No Lua execution harness in the repo**

`P2` · `medium` · `bug` · Air Manager instruments · cluster C13 (Instrument tooling & shared libs) · effort M · wave 4 · **fixed**

- **Files:** `tests/am.py`, `tests/test_am.py`
- **Problem:** The ctypes Lua 5.4 harness the CHANGELOG describes as the independent verification route is not in the repo; luacheck.py is syntax-only and nothing executes any logic.lua. Page and scan state machines, audio state, press handling and the TDFM/GMA handshake have no tests at all. [Re-verified 2026-09-08 against the complete tree: only scripts/luacheck.py (syntax) and tests/test_lcd_text.py exist; no ctypes/liblua harness anywhere. Stands.]
- **Fix:** Fixed 2026-09-08. Implemented tests/am.py using system liblua5.4 via ctypes providing complete Air Manager 4.2 API simulation (si_variable_*, xpl_*, timer_*, canvas_draw, etc.). Added tests/test_am.py covering all 4 instruments, shuffled lib/ load order, timer progression, and GMA 1347 COM3 MIC interlock.
- **Done when:** All four instruments load, power on and draw in CI.

### P-10

**DATAREF_CONTRACT.md does not match what the plugin publishes**

`P2` · `medium` · `bug` · Docs / record · cluster C14 (Contract & documentation truth) · effort M · wave 4 · **fixed**

- **Files:** `docs/DATAREF_CONTRACT.md:43,59,67-74,107`
- **Problem:** The contract is the interface between the plugin and every faceplate, and it is wrong in five places: cap/scenario/* is documented writable for offline testing but active is read-only; bearing extremes are documented as +/- spread/2 but published one-sided; 'slant range' is ground great-circle; BYTE[15] returns length 0 undecoded; and five effect names are undocumented.
- **Fix:** Correct the contract to the code, or change the code where the contract is the better design (writable scenario datarefs are genuinely useful offline).
- **Done when:** A faceplate author can work from the contract alone.

### P-11

**Server fallback propagation diverges from the plugin**

`P2` · `medium` · `bug` · Exercise console (backend) · cluster C15 (Service boundaries (architecture)) · effort M · wave 4 · **fixed**

- **Files:** `services/exercise/app/propagation.py:37-71`
- **Problem:** The server model uses a 1.5 s burst window against the plugin's 0.44 s, never invalidates between bursts, matches band as the string '406', and has no squelch, averaging, timehold, tuning, terrain or airframe modelling. It runs whenever the plugin omits df, so an instructor can be shown a different DF picture than the sim computes.
- **Fix:** Shrink propagation.py to the mock-bridge stub it effectively is and make the plugin authoritative everywhere, per existing policy.
- **Done when:** Instructor HUD matches the cockpit in a sim-connected exercise.

### C15-2

**Consolidate five geodesy implementations**

`P3` · `low` · `task` · Exercise console (backend) · cluster C15 (Service boundaries (architecture)) · effort M · wave 4 · **fixed**

- **Files:** `services/flightplanner/app.py`, `services/exercise/app/propagation.py`, `services/exercise/mock_bridge.py`, `services/exercise/app/static/debrief.js`, `xplane/PI_capvsar_df.py`
- **Problem:** Bearing/distance is implemented five times with the same R_NM constant; debrief.js has already drifted (missing cos(lat) in heading). [Re-verified 2026-09-08 against the complete tree: exactly five files carry their own geodesy. Stands.] [2026-09-10: the debrief.js drift cited here was already fixed under F-3 - re-verified. Consolidated as far as the deployment boundaries allow: app/geo.py is the one implementation inside the exercise console (propagation.py and mock_bridge.py import it). The plugin runs in X-Plane's interpreter, the planner is a separate container and two copies are browser JS, so those cannot import it; tests/test_geodesy.py pins all five to the same answers instead, and was checked against a deliberately rounded radius and a reintroduced F-3 bug.]
- **Fix:** One shared Python geodesy module for the two services; the plugin keeps its standalone copy tested against it; the JS uses one helper.
- **Done when:** A cross-implementation test agrees within 1 m over 100 NM.

### F-12

**APX/EFJ control-head keys are artwork only**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort M · wave 4 · **fixed**

- **Files:** `services/exercise/app/static/mission-radio.js`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. SCAN, MON, SQL and EMER appear on the SVG faceplates but have no hit regions in the JS at all - grep finds none of those names. MON (squelch open) is what an operator actually reaches for to pull a marginal signal from an aircraft low in terrain, which is a real trained skill.
- **Fix:** Fixed 2026-09-15. Added an executable hit region over the EFJohnson faceplate's actual MON artwork; the APX artwork has no MON-labelled key, so no unrelated control was invented. Each receiver owns its own monitor flag. Normal receive audio uses a documented training RMS squelch threshold, while MON bypasses that threshold for the selected receiver only and visibly annunciates MONITOR.
- **Done when:** Three executable Node-backed behavioral tests were written first and failed because the monitor policy block did not exist. They now prove one receiver's MON toggle does not alter the other, a marginal frame rejected by normal squelch passes with MON open, and the EFJ artwork coordinates produce a MON hit while APX correctly produces none. Required suite: 104 passed, 17 subtests. Not verified: audible marginal traffic through a live Mumble/headset session; the 0.012 RMS value is a training threshold, not calibrated hardware performance.

### F-13

**Net names are generic, not CAP nomenclature**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort S · wave 4 · **resolved**

- **Files:** `services/exercise/app/radio.py:29-34`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. Channels read PRIMARY / ALTERNATE / MISSION BASE / BRIEFING. Real heads show zone and channel tags from the fleet plan, and reading them correctly is part of the operator's job. Related to I-11 - the airborne and ground plans should agree.
- **Fix:** WON'T FIX by decision D-6 (2026-09-15), recorded in vault DECISIONS-cap-vsar-2026-09-12.md. The base console's net names stay generic. CAPR 100-1 puts channel names and codeplugs in the restricted NPP and no approved four-net mapping exists in the repo or vault; Codex stopped rather than inventing plausible CAP nomenclature, which was correct. Two reasons the generic names are preferred rather than merely tolerated: a simulator channel name that could be MISTAKEN for a real comms plan risks negative transfer to aircrew, and this repository is bound for a public mirror, which makes restricted channel data a D-5 release-gate question rather than an F-13 one. Follow-up for Ron before that mirror: I-11 already shipped CAP fleet-plan names in instruments/cap-fm-tdfm-136b/logic.lua - check their sourcing.
- **Done when:** Not verified: no authoritative mapping exists in the available sources, so the item remains open and no implementation or test was attempted.

### I-12

**TDFM Guard is not an independent receiver**

`P3` · `low` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort M · wave 4 · **fixed**

- **Files:** `instruments/cap-fm-tdfm-136b/logic.lua`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. There is a guard volume knob, a G1/G2 switch and a guard_rx flag, but only one active frequency is published. The real set has two receiver modules and guard traffic breaks into main audio, which is how mission base reaches an aircraft working another channel.
- **Fix:** Fixed 2026-09-08. Implemented dedicated Guard receiver secondary channel path in instruments/cap-fm-tdfm-136b/logic.lua. Published cap_fm_guard_frequency_hz, cap_fm_guard_channel, cap_fm_guard_channel_name, cap_fm_guard_ctcss_tone, cap_fm_guard_p25_nac, cap_fm_guard_volume, and cap_fm_main_volume. Guard audio and squelch are dual-gated and monitored continuously regardless of Main channel selection. Verified in tests/test_tdfm.py.
- **Done when:** Guard traffic is audible while the main receiver is working another channel.

### I-13

**TDFM scan is a cosmetic flag**

`P3` · `low` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort S · wave 4 · **fixed**

- **Files:** `instruments/cap-fm-tdfm-136b/logic.lua`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. toggle_scan() shows an 'S' on the LCD. It does not cycle a scan list, halt on a carrier, or resume.
- **Fix:** Fixed 2026-09-08. Implemented full scan operational engine in instruments/cap-fm-tdfm-136b/logic.lua. 250 ms dwell timer cycles programmed channels (1..20); halts instantly upon carrier detection (cap_fm_main_rx); holds for 2000 ms hang time on carrier loss before resuming; pauses on PTT; clean teardown on toggle/power off. Verified in tests/test_tdfm.py.
- **Done when:** Scan visibly stops on an active channel and resumes.

### I-15

**GMA 1347 clearance recorder records nothing**

`P3` · `low` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort M · wave 4 · **fixed**

- **Files:** `instruments/mo-audio-panel-gma1347/logic.lua:187-197`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. PLAY flashes its annunciator for 1200 ms. The real recorder holds the last ~2.5 minutes of COM audio and replays it in reverse chunks - which is exactly what a crew reaches for after missing a grid reference read over the radio.
- **Fix:** Fixed 2026-09-08. Implemented digital clearance recorder in instruments/mo-audio-panel-gma1347/logic.lua with a 16-block circular buffer tracking COM1, COM2, and COM3 transmissions up to 2.5 minutes. Pressing PLAY plays back the latest recorded transmission and illuminates the annunciator; successive presses step backwards through historical blocks; any non-PLAY key immediately aborts playback. Published cap_recorder_playing, cap_recorder_block, cap_recorder_count, cap_recorder_text. Verified in tests/test_am.py.
- **Done when:** A missed transmission can be replayed from the panel.

### I-17

**DF audio has no signal-to-noise degradation**

`P3` · `low` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort M · wave 4 · **fixed**

- **Files:** `instruments/*/lib/cap_df_audio.lua`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. The WAV loops play at fixed fidelity scaled only by the volume knob, so the beacon is either pristine or silent. Real DF audio buries the sweep in noise at range or behind terrain, and learning to hear a weak signal in hiss is the skill being trained.
- **Fix:** Fixed 2026-09-08. Synthesized deterministic band-limited discriminator noise in scripts/make_df_audio.py (elt_noise.wav) and updated instruments/becker-sar-df-517/lib/cap_df_audio.lua and instruments/rhotheta-rt-600/lib/cap_df_audio.lua (byte-identical) to dynamically mix noise inversely against cap/df/signal. Distant and terrain-masked beacons are audibly degraded with receiver hiss. Verified in tests/test_am.py and scripts/make_df_audio.py --check.
- **Done when:** A distant or masked beacon is audibly noisy rather than absent.

### I-7

**Shared instrument libraries are copy-pasted**

`P3` · `low` · `bug` · Air Manager instruments · cluster C13 (Instrument tooling & shared libs) · effort M · wave 4 · **fixed**

- **Files:** `instruments/*/lib/cap_df.lua`, `instruments/*/lib/lcd.lua`, `instruments/*/lib/dcu.lua`, `tests/test_faceplate.py:126-129`
- **Problem:** cap_df.lua, cap_df_audio.lua, dcu.lua, lcd.lua and four WAVs (elt_analog_clean, elt_analog_df, elt_noise, elt_406_burst) are byte-identical across the Becker and RT-600 (lcd.lua also in the TDFM). A test enforces the DF pair but not the TDFM copy, so that one can drift silently.
- **Fix:** Extracted lcd.lua, cap_df.lua, cap_df_audio.lua, dcu.lua and four ELT WAVs into instruments/_shared/. Synchronized at deploy time via deploy_df_instruments.py. Replaced pairwise test with test_faceplate.py check enforcing all copies match _shared/.
- **Done when:** Editing _shared updates all instruments on deploy; drift fails the test.

### I-9b

**cap_fm_* variables have no producer and no contract**

`P3` · `low` · `bug` · Air Manager instruments · cluster C14 (Contract & documentation truth) · effort S · wave 4 · **fixed**

- **Files:** `instruments/cap-fm-tdfm-136b/logic.lua:480-525`, `instruments/mo-audio-panel-gma1347/logic.lua:78-79`, `docs/DATAREF_CONTRACT.md`
- **Problem:** cap_fm_ptt, cap_fm_main_rx and cap_fm_guard_rx are consumed but nothing writes them and they are absent from DATAREF_CONTRACT.md, so the TDFM/GMA handshake is undocumented and half-wired. [Re-verified 2026-09-08: cap_fm_main_rx and cap_fm_ptt are subscribed in cap-fm-tdfm-136b/logic.lua:480,508 and written by nothing in the tree. Stands.]
- **Fix:** Fixed 2026-09-08. Created cap_fm_ptt, cap_fm_main_rx, cap_fm_guard_rx in cap-fm-tdfm-136b/logic.lua, dual-bound observer PTT to X-Plane copilot PTT dataref, added /api/radio/rx activity tracking in radio.py, and documented all si_variable_* contracts in Part 5 of DATAREF_CONTRACT.md.
- **Done when:** Contract lists every si_variable both instruments use.

### I-9c

**Deploy coverage and manifest claims are wrong**

`P3` · `low` · `bug` · Air Manager instruments · cluster C13 (Instrument tooling & shared libs) · effort S · wave 4 · **fixed**

- **Files:** `scripts/deploy_df_instruments.py:14-17,47`, `instruments/*/info.xml:20-25`
- **Problem:** The deploy script handles two of four instruments although the website claims it deploys all four; TDFM and GMA have no deploy script; stale target files are never removed; and every info.xml claims FSX/P3D/FS2020 support although all four are X-Plane only. [Re-verified 2026-09-08: deploy_df_instruments.py still lists 2 of 4 instruments; TDFM and GMA have no deploy script. Stands.]
- **Fix:** Expanded deploy_df_instruments.py to deploy all four instruments and synchronize _shared/ assets; pruned stale target files and empty directories; updated panel info.xml to remove legacy FSX/P3D/FS2020 simulator claims and include Streaming=true for G1000 MFD.
- **Done when:** One command deploys four instruments to a clean Air Manager.

### L-10

**Planner dependency and container hygiene**

`P3` · `low` · `bug` · Flight planner · cluster C11 (Flight planner security & dependencies) · effort M · wave 4 · **fixed**

- **Files:** `services/flightplanner/requirements.txt`, `services/flightplanner/Dockerfile`, `services/flightplanner/app.py:807`
- **Problem:** requests==2.31.0 carries CVE-2024-35195 and CVE-2024-47081; gunicorn and Werkzeug are unpinned; the container runs as root; the healthcheck hits / rather than a DB-verifying endpoint; serve_tile accepts .. in chart_type (not currently exploitable but unnecessary); _winds_cache grows unbounded; the aviation DB is OurAirports, not FAA NASR, with no cycle date shown.
- **Fix:** Fixed 2026-09-15 (b5f1fe3). requests pinned 2.31.0 -> 2.32.5, past CVE-2024-35195 and CVE-2024-47081; gunicorn and Werkzeug pinned (they were unpinned entirely, so the image rebuilt to whatever shipped that day), Werkzeug held at 3.0.x because Flask 3.0.0 does not support 3.1. Container runs as `planner` with APP_UID/APP_GID build args, because /app/data is a bind mount whose owner the host decides. /api/health opens the database read-only and returns 503 when it is missing; an empty database reports populated:false but stays healthy, since a fresh container legitimately starts before the first download. A data_source table records source URL, fetch time and row count per dataset, so the OurAirports vintage is visible rather than implied to be an FAA cycle. _winds_cache bounded at 512, oldest first. serve_tile's chart_type was never actually reachable as traversal (dict key, <int:> converters); the membership test states that invariant explicitly.
- **Done when:** 13 tests in services/flightplanner/tests/test_hygiene.py, 10 verified failing pre-fix. Planner suite 93 -> 106 passed.

### L-13

**Planner direct-handler tests fail with real Flask installed**

`P3` · `low` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort S · wave 4 · **fixed**

- **Files:** `services/flightplanner/tests/test_sar.py`
- **Problem:** Found 2026-09-10: direct-handler request-bound and security tests expect the optional Flask stub dictionary response. Real jsonify fails outside application context.
- **Fix:** Explicitly mock jsonify in direct-handler unit tests. New HTTP regressions use Flask test_client to check actual JSON and status.
- **Done when:** 29 planner tests pass with Flask installed.

### L2-12

**Export rate limiter is per-process**

`P3` · `low` · `bug` · Flight planner · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 4 · **open**

- **Files:** `services/flightplanner/app.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 4.
- **Fix:** 
- **Done when:** 

### O-1a

**Generated handbook committed deliberately**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C1 (Repo & release hygiene) · effort S · wave 4 · **resolved**

- **Files:** `.gitignore`, `docs/manual/`
- **Problem:** `docs/manual/*.odt|docx` are ignored but the 3.3 MB `.pdf` and `.html` are not, although scripts/generate_manual.py regenerates both on every run.
- **Fix:** Resolved by decision: Codex's v0.1 baseline entry states the generated handbook PDF/HTML are tracked deliberately as the published artefact. No change needed; expect churn in those two files on every manual rebuild.
- **Done when:** Decision recorded in the CHANGELOG v0.1 baseline entry.
- **Depends on:** O-1

### O2-13

**Dockerfile base images not pinned by digest**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort S · wave 4 · **open**

- **Files:** `services/exercise/Dockerfile`, `services/flightplanner/Dockerfile`, `services/board/Dockerfile`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 7.
- **Fix:** 
- **Done when:** 

### P-12

**Plugin reporting cadence and heading source are off**

`P3` · `low` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 4 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:432,962,972,1018`
- **Problem:** REPORT_S=2 but the loop sleeps 3 s; the first report is (0,0,0) before any flight loop; psi is the OpenGL-frame heading where true_psi is correct; a null in scenario JSON would throw in the dataref accessor.
- **Fix:** Align the sleep with REPORT_S, skip the first empty report, use true_psi, coerce nulls.
- **Done when:** Track starts at the aircraft's real position with 2 s spacing.

### P-13

**Signal model has no dB calibration and multipath is scripted**

`P3` · `low` · `enhancement` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort L · wave 4 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:770,828-830`
- **Problem:** 25/d^2 saturates at 5 NM for every band, so a 0.1 W 121.5 beacon and a 5 W 406 beacon differ only in cadence and decode, not range. Multipath is a deterministic 40 deg step for 12 of every 36 s, independent of terrain or range, so it reads as a scripted glitch rather than a reflection.
- **Fix:** Calibrate to a real link budget per band; drive multipath from the terrain probe that already runs.
- **Done when:** Detection ranges differ per band and match published ELT figures within a training tolerance.
- **Depends on:** P-1

### P-9

**Fixed 24 terrain probes, no earth curvature**

`P3` · `low` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort M · wave 4 · **fixed**

- **Files:** `xplane/PI_capvsar_df.py:94,593`
- **Problem:** 24 probes means 1.25 NM spacing at 30 NM, skipping narrow ridges, and the straight ray ignores the ~200 ft mid-path curvature bulge at that range.
- **Fix:** Scale probe count with distance; add the curvature term.
- **Done when:** A narrow ridge at 25 NM blocks.
- **Depends on:** P-1

### X2-13

**ICS pilot/observer seats share a callsign so the first joiner's seat decides for a shared radio**

`P3` · `low` · `bug` · Exercise console (backend) · cluster C16 (Project review 2026-10-10 (waves A-D)) · effort M · wave 4 · **open**

- **Files:** `services/exercise/app/radio.py`
- **Problem:** See docs/PROJECT_REVIEW_2026-10-10.md section 2.
- **Fix:** 
- **Done when:** 

