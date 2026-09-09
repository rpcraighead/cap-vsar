# CAP V-SAR bug tracker

**Generated from `docs/bugs/tracker.json` by `scripts/render_bug_tracker.py` — edit the JSON, not this file.**

Source analysis: [`PROJECT_REVIEW_2026-09-08.md`](PROJECT_REVIEW_2026-09-08.md). Opened 2026-09-08. 82 items, 40 open.

IDs are the review's finding IDs. Suffixed letters (X-8a) are sub-items split out because they are worked separately.

## Counts

| | critical | high | medium | low | total |
|---|---|---|---|---|---|
| by severity | 8 | 21 | 34 | 19 | 82 |

| P0 | P1 | P2 | P3 |
|---|---|---|---|
| 10 | 22 | 34 | 16 |

| Component | Items |
|---|---|
| Air Manager instruments | 19 |
| Flight planner | 13 |
| Exercise console (frontend) | 12 |
| X-Plane plugin / engine | 12 |
| Exercise console (backend) | 12 |
| Deployment / infrastructure | 8 |
| Docs / record | 6 |

## Priority definitions

- **P0** — Blocks an exercise from running, or corrupts training integrity (truth leak, wrong physics). Fix before the first rehearsal session.
- **P1** — Degrades an exercise in progress or loses data. Fix before the full-mission rehearsal.
- **P2** — Correctness, robustness or realism gap that a participant would notice but work around.
- **P3** — Cleanup, tooling, docs. No exercise impact.

## Waves

_Wave dates track the illustrative calendar in docs/USE_CASE_SAREX_REHEARSAL.md (T-14/T-7/T-2 before a 17 Oct 2026 SAREX). Re-anchor to the real exercise date._

- **Wave 0** (1 items) — Now — make the work safe to do at all.
- **Wave 1** (10 items) — Before session 1 (base stand-up). Nothing flies; base, planner and comms must work.
- **Wave 2** (20 items) — Before session 2 (full mission, three aircraft, injected effects).
- **Wave 3** (31 items) — Before session 3 (dress rehearsal) and the live SAREX.
- **Wave 4** (20 items) — After the SAREX — architecture, tooling, CalTopo phase 2.

## Clusters

A cluster is a PR-sized unit of work: items that touch the same files and should be fixed, reviewed and merged together. The owner hint matters because three agents share this tree.

| Cluster | Name | Items | Coordination |
|---|---|---|---|
| C1 | Repo & release hygiene | O-1, O-1a | maintainer — git remote and release |
| C2 | Truth integrity & roles | P-2, X-1, X-2 | DONE (X-1 fixed; X-2 awaits .env tokens, sequenced behind L-2 and O-2) |
| C3 | Propagation engine correctness | P-1, P-3, P-4, P-5, P-6, P-7, P-8, P-12, P-13, P-9 | Claude — xplane/PI_capvsar_df.py, sole editor |
| C4 | Station identity & onboarding kit | O-2, O-2a | Claude — O-2 station config and kit (plugin + scripts/) |
| C5 | Deployment bootstrap & voice provisioning | O-3, F-5, O-4, O-6, O-5, O-7a | Claude — deploy.sh, compose, ms01 (has ssh access) |
| C6 | Offline mission base | F-1, L-8 | DONE for the console (F-1); L-8 is the planner's own copy, Codex's file |
| C7 | Console robustness | X-3, X-4, X-5, X-7, X-6, X-8 | Codex holds main.py for F-4's since-endpoints; X-6/X-8 wait for it |
| C8 | Base view & debrief | F-2, F-3, F-6, F-8 | DONE (F-2, F-3) |
| C9 | Radio console hardening | F-4, F-7, F-9, X-9, F-10, F-11, F-12, F-13 | Codex — mission-radio.js/html and radio.py; F-9..F-13 queue behind F-4 |
| C10 | Flight planner correctness | L-1, L-3, L-4, L-1a, L-11, L-12, L-5, L-6, L-7, L-9 | Codex — services/flightplanner/app.py |
| C11 | Flight planner security & dependencies | L-2, L-10 | Codex — same file as C10, sequenced after it |
| C12 | Instrument runtime | I-1, I-2, O-7b, I-10, I-3, I-4, I-5, I-6, I-11, I-14, I-12, I-13, I-15, I-17 | Gemini — instruments/** outright, including the DF heads |
| C13 | Instrument tooling & shared libs | I-8, I-9a, I-7, I-9c | Gemini — instrument tooling; I-9a Lua harness is its first task |
| C14 | Contract & documentation truth | D-1, D-2, D-3, D-4, P-10, I-9b | docs only, safe in parallel |
| C15 | Service boundaries (architecture) | C15-1, P-11, C15-2 | unassigned — after C2 and C7 settle |

## Board

### Wave 0 — Now — make the work safe to do at all.

| ID | Pri | Sev | Title | Component | Cluster | Effort | Depends on | Status |
|---|---|---|---|---|---|---|---|---|
| [O-1](#o-1) | P0 | critical | Repo has no working git history | infra | C1 | S | — | fixed |

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
| [O-2a](#o-2a) | P1 | medium | Participant CONNECT.md cited by the as-built does not exist | docs | C4 | S | O-2 | resolved |

### Wave 2 — Before session 2 (full mission, three aircraft, injected effects).

| ID | Pri | Sev | Title | Component | Cluster | Effort | Depends on | Status |
|---|---|---|---|---|---|---|---|---|
| [F-2](#f-2) | P1 | high | Base view keeps the previous sortie's alert circle and tracks | console-ui | C8 | S | — | fixed |
| [F-3](#f-3) | P1 | high | Debrief conflates all aircraft into one track | console-ui | C8 | M | — | fixed |
| [F-4](#f-4) | P1 | high | Radio console does not rejoin after a network blip | console-ui | C9 | M | — | fixed |
| [I-1](#i-1) | P1 | high | DF faceplates repaint ~8 Hz regardless of change | instruments | C12 | M | — | fixed |
| [I-2](#i-2) | P1 | high | pcall around canvas_draw hides real errors | instruments | C12 | S | — | fixed |
| [L-2](#l-2) | P1 | high | Unauthenticated scenario push and CSRF-able database wipe | planner | C11 | M | X-2 | fixed |
| [L-3](#l-3) | P1 | high | Parallel-track generator can be driven into a 100M-iteration loop | planner | C10 | S | — | fixed |
| [L-4](#l-4) | P1 | high | Both gunicorn workers race to rebuild the aviation database | planner | C10 | S | — | fixed |
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
| [L-1a](#l-1a) | P2 | medium | Search-pattern labels are lost in the FMS export | planner | C10 | S | L-1 | open |

### Wave 3 — Before session 3 (dress rehearsal) and the live SAREX.

| ID | Pri | Sev | Title | Component | Cluster | Effort | Depends on | Status |
|---|---|---|---|---|---|---|---|---|
| [O-5](#o-5) | P1 | high | Mumble server has no per-role ACLs and images float | infra | C5 | M | X-2, O-4 | fixed |
| [O-7a](#o-7a) | P1 | high | Air Manager seat count for three MO stations unconfirmed | infra | C5 | S | — | resolved |
| [D-1](#d-1) | P2 | medium | CHANGELOG entries contradict the code they describe | docs | C14 | S | — | open |
| [D-2](#d-2) | P2 | medium | README and website contradict the code | docs | C14 | M | — | open |
| [D-3](#d-3) | P2 | medium | CONOPS and referenced infra docs are missing from the repo | docs | C14 | S | — | resolved |
| [D-4](#d-4) | P2 | medium | No LICENSE despite deriving from Laminar assets | docs | C14 | S | O-1 | open |
| [F-6](#f-6) | P2 | medium | Unescaped server strings in four views (HTML injection) | console-ui | C8 | S | — | open |
| [F-7](#f-7) | P2 | medium | Legacy console: precedence bug and autoplay-blocked audio | console-ui | C9 | S | — | open |
| [F-8](#f-8) | P2 | medium | No bearing intersection maths despite the README | console-ui | C8 | M | — | open |
| [F-9](#f-9) | P2 | medium | New radio console has no Form 110 log | console-ui | C9 | M | — | open |
| [I-3](#i-3) | P2 | medium | Becker tone suppression bleeds across bands | instruments | C12 | S | — | fixed |
| [I-4](#i-4) | P2 | medium | Stored 406 frame falls through to live data | instruments | C12 | S | — | open |
| [I-5](#i-5) | P2 | medium | RT-600 long-press timers survive power-off | instruments | C12 | S | — | open |
| [I-6](#i-6) | P2 | medium | DF heads and TDFM ignore the electrical bus | instruments | C12 | M | — | open |
| [L-11](#l-11) | P2 | medium | Unknown departure/destination silently becomes a waypoint position | planner | C10 | S | — | open |
| [L-12](#l-12) | P2 | medium | Flight planner database is a file bind-mount, so SQLite journals escape it | planner | C10 | S | — | open |
| [L-5](#l-5) | P2 | medium | Search patterns leave uncovered ground and truncate silently | planner | C10 | M | — | open |
| [L-6](#l-6) | P2 | medium | Performance tables extrapolate silently and ignore tailwind | planner | C10 | M | — | open |
| [L-7](#l-7) | P2 | medium | Flight planner ships 172S performance data under a 182T label | planner | C10 | M | — | open |
| [L-8](#l-8) | P2 | medium | Planner has no offline map path | planner | C6 | M | F-1 | open |
| [L-9](#l-9) | P2 | medium | API returns HTML 500s and misreports push status | planner | C10 | M | — | open |
| [P-6](#p-6) | P2 | medium | 121.5 beacons produce a COSPAS-SARSAT decode | plugin | C3 | S | — | open |
| [P-7](#p-7) | P2 | medium | Signal bar stays lit between 406 bursts | plugin | C3 | S | — | open |
| [P-8](#p-8) | P2 | medium | Terrain masking is only -12 dB | plugin | C3 | S | P-1 | open |
| [X-6](#x-6) | P2 | medium | Untyped request bodies mutate scenario definitions | console-api | C7 | M | — | open |
| [X-8](#x-8) | P2 | medium | Console operational hygiene: retention, logging, health, shutdown, root | console-api | C7 | M | — | open |
| [X-9](#x-9) | P2 | medium | One Mumble client per browser socket, 16 max | console-api | C9 | M | — | open |
| [F-10](#f-10) | P2 | low | Mission base cannot monitor the airband SAR net | console-ui | C9 | L | — | open |
| [I-11](#i-11) | P2 | low | TDFM memory table is 6 generic channels, not a CAP fleet plan | instruments | C12 | M | — | fixed |
| [I-14](#i-14) | P2 | low | GMA 1347 ICS isolation and Split COM are lamp-only | instruments | C12 | L | — | fixed |
| [F-11](#f-11) | P3 | low | No operational sidetone on the new radio console | console-ui | C9 | S | — | open |

### Wave 4 — After the SAREX — architecture, tooling, CalTopo phase 2.

| ID | Pri | Sev | Title | Component | Cluster | Effort | Depends on | Status |
|---|---|---|---|---|---|---|---|---|
| [C15-1](#c15-1) | P2 | medium | Split the console into store + routers with role middleware | console-api | C15 | L | X-1, X-2, X-3 | open |
| [I-8](#i-8) | P2 | medium | Panel registrar writes Air Manager's database on hardcoded assumptions | instruments | C13 | M | O-2 | open |
| [I-9a](#i-9a) | P2 | medium | No Lua execution harness in the repo | instruments | C13 | M | — | fixed |
| [P-10](#p-10) | P2 | medium | DATAREF_CONTRACT.md does not match what the plugin publishes | docs | C14 | M | — | open |
| [P-11](#p-11) | P2 | medium | Server fallback propagation diverges from the plugin | console-api | C15 | M | — | open |
| [C15-2](#c15-2) | P3 | low | Consolidate five geodesy implementations | console-api | C15 | M | — | open |
| [F-12](#f-12) | P3 | low | APX/EFJ control-head keys are artwork only | console-ui | C9 | M | — | open |
| [F-13](#f-13) | P3 | low | Net names are generic, not CAP nomenclature | console-ui | C9 | S | — | open |
| [I-12](#i-12) | P3 | low | TDFM Guard is not an independent receiver | instruments | C12 | M | — | fixed |
| [I-13](#i-13) | P3 | low | TDFM scan is a cosmetic flag | instruments | C12 | S | — | fixed |
| [I-15](#i-15) | P3 | low | GMA 1347 clearance recorder records nothing | instruments | C12 | M | — | fixed |
| [I-17](#i-17) | P3 | low | DF audio has no signal-to-noise degradation | instruments | C12 | M | — | fixed |
| [I-7](#i-7) | P3 | low | Shared instrument libraries are copy-pasted | instruments | C13 | M | — | open |
| [I-9b](#i-9b) | P3 | low | cap_fm_* variables have no producer and no contract | instruments | C14 | S | — | fixed |
| [I-9c](#i-9c) | P3 | low | Deploy coverage and manifest claims are wrong | instruments | C13 | S | — | open |
| [L-10](#l-10) | P3 | low | Planner dependency and container hygiene | planner | C11 | M | — | open |
| [O-1a](#o-1a) | P3 | low | Generated handbook committed deliberately | infra | C1 | S | O-1 | resolved |
| [P-12](#p-12) | P3 | low | Plugin reporting cadence and heading source are off | plugin | C3 | S | — | open |
| [P-13](#p-13) | P3 | low | Signal model has no dB calibration and multipath is scripted | plugin | C3 | L | P-1 | open |
| [P-9](#p-9) | P3 | low | Fixed 24 terrain probes, no earth curvature | plugin | C3 | M | P-1 | open |

## Detail

### O-1

**Repo has no working git history**

`P0` · `critical` · `task` · Deployment / infrastructure · cluster C1 (Repo & release hygiene) · effort S · wave 0 · **fixed**

- **Files:** `repo root`
- **Problem:** Codex published a v0.1 baseline to Gitea and GitHub on 2026-09-08 with ignore rules covering credentials, runtime state and build output. But this working tree still has no `.git/` and `git` is not installed on this machine, so agents editing here still cannot diff, revert or see what another tool changed — which is the actual failure mode the finding was about.
- **Fix:** This directory is now a real checkout: git init in place, origin set to ssh://git@192.0.2.121:2222/ron/capvsar.git (git.rpc-cyberflight.com does not resolve from this host - use the IP), local main tracking origin/main. Everything that had accumulated in the working tree since v0.1 (RBAC/setup wizard, O-2, radio/DF work, docs, tests) was captured as one commit on top of v0.1 without checking out or discarding anything already on disk, then pushed. .env.example, missing on disk with no explanation, was reconstructed from the env vars the code actually reads and committed separately. Pushed to Gitea only - not mirrored to GitHub here, since this repo's IP-redaction convention (if any, cf. flight-planner-n499cp-v2 scripts/redact_ips.py) was not established before pushing somewhere public.
- **Done when:** git log and git status work in /home/ron/Projects/cap-vsar (this directory), confirmed. origin/main on Gitea matches local main (pushed c517617). GitHub mirroring is a separate, deliberately deferred decision.

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

### O-2a

**Participant CONNECT.md cited by the as-built does not exist**

`P1` · `medium` · `bug` · Docs / record · cluster C4 (Station identity & onboarding kit) · effort S · wave 1 · **resolved**

- **Files:** `docs/ (missing CONNECT.md)`, `vault: Projects/as-built/AsBuilt_CAPVSAR.md`
- **Problem:** The as-built tells participants their instructions are at docs/CONNECT.md in the repository. That file does not exist, so the one pointer a new member is given leads nowhere — the same onboarding gap as O-2, but already promised in writing.
- **Fix:** WRONG FINDING, corrected 2026-09-08. docs/CONNECT.md exists in the canonical repo on ms01 and is a complete participant guide (Mumble client per platform, server details, nets, PTT). It was absent only from the local working tree this review was written against. Now pulled down. No work needed.
- **Done when:** A member who has never seen the project can get onto the voice net and the base console from that page alone.
- **Depends on:** O-2

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
- **Fix:** scripts/preflight.py checks the exercise console's /api/health, the full Mumble channel tree plus the Instructor/SET ACL (reading the shared mumble_channels.py tree, same source O-4 provisions from), the flight planner's VFR tile source via the MapServer metadata endpoint (not a guessed tile coordinate - a 404 on an out-of-pyramid tile looks identical to the service being down otherwise), and the published browser-radio CA cert. scripts/backup_exercise_db.py takes an online SQLite backup (Connection.backup(), safe against a live writer - not a raw file copy, which can capture a torn snapshot) with 14-day retention pruning; a crontab line is in the script's own docstring, not installed anywhere by this change. radio-https (Caddy) gained a healthcheck in docker-compose.yml - it had none, so a Caddy that stopped proxying looked identical to a healthy one to `docker compose ps`.
- **Done when:** preflight.py manually run against both a cold stack (nothing running: fails loudly, one specific reason per check) and a fully mocked warm one (provisioned test Mumble db, mock health server, placeholder CA cert: all five checks pass) - the tracker's own stated verify criterion. tests/test_backup_exercise_db.py, 4 cases, caught a real bug during development: same-second backups collided on a 1-second-resolution filename and silently overwrote each other, fixed by moving to microsecond resolution. Backup verified to survive a database with an open connection, and to prune only backups older than the retention window.
- **Depends on:** O-3

### O-7b

**G1000 MFD video stream never re-arms after a reconnect**

`P1` · `high` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort M · wave 2 · **open**

- **Files:** `Air Manager stock G1000 instrument logic.lua:90-100`, `~/Air Manager/log.txt`
- **Problem:** SimVideoStreamClient loses the connection every few minutes; the stock instrument calls video_stream_add() once at load, so after a reconnect the MFD tile is frozen on its last frame. Every MO station hits this.
- **Fix:** Wrapper instrument that re-arms the stream on reconnect, or a watchdog timer that re-calls video_stream_add when frames stop arriving.
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

### L-1a

**Search-pattern labels are lost in the FMS export**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort S · wave 2 · **open**

- **Files:** `services/flightplanner/app.py:635`, `services/flightplanner/app.py:517-554`
- **Problem:** Found reviewing the L-1 fix. The pattern generators label points DATUM, SS01..SSnn, CS01, PS01, and the AOBD briefs the crew on those names - but the FMS writer now derives the identifier purely from coordinates, so the G1000 shows '+33.187_-117.079' for every leg. The brief says 'turn at SS04' and nothing in the cockpit says SS04. The plan still flies the correct positions; only the label is lost.
- **Fix:** Determine whether X-Plane 12 accepts an arbitrary identifier on a type 28 record and treats the lat/lon columns as authoritative. If it does, emit the generator's label (sanitised to the character set the FMS allows) and keep the coordinates in the columns. If it does not, say so in the user guide so the AOBD briefs coordinates instead.
- **Done when:** Load an exported pattern in X-Plane 12 and read the leg names on the G1000 flight plan page.
- **Depends on:** L-1

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

### D-1

**CHANGELOG entries contradict the code they describe**

`P2` · `medium` · `bug` · Docs / record · cluster C14 (Contract & documentation truth) · effort S · wave 3 · **open**

- **Files:** `CHANGELOG.md`
- **Problem:** The pymumble bridge is marked 'proposed only' in two entries although it is implemented; the '/radio' APX 6500 entry now describes /radio-legacy; the Becker pcall entry claims an error the log does not show; '55 engine checks' is 51; '/api/messages rejects the push (400)' is no longer true. The changelog is the coordination protocol between three tools, so a stale entry actively misleads the next agent. [Re-verified 2026-09-08: CHANGELOG.md:953 still reads 'Proposed only' and :1082 still claims 55 engine checks. The corrections were added as new entries; the original entries are still uncorrected in place. Stands.]
- **Fix:** Add superseded-by notes to the affected entries.
- **Done when:** A fresh reader following the changelog reaches the same conclusions as the code.

### D-2

**README and website contradict the code**

`P2` · `medium` · `bug` · Docs / record · cluster C14 (Contract & documentation truth) · effort M · wave 3 · **open**

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

`P2` · `medium` · `bug` · Docs / record · cluster C14 (Contract & documentation truth) · effort S · wave 3 · **open**

- **Files:** `repo root`, `scripts/build_c182t_package.py`
- **Problem:** There is no LICENSE file, and the aircraft package is built by copying and patching Laminar Research's shipped C172SP. Now that the repo is going to GitHub this needs an answer: what is redistributable, and what must be built locally from the user's own X-Plane install.
- **Fix:** Add a LICENSE for the project's own code and a NOTICE stating that Laminar assets are not redistributed and the package is generated from a local install.
- **Done when:** The public repo contains no Laminar-derived binary.
- **Depends on:** O-1

### F-6

**Unescaped server strings in four views (HTML injection)**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C8 (Base view & debrief) · effort S · wave 3 · **open**

- **Files:** `services/exercise/app/static/base.js:114`, `services/exercise/app/static/debrief.js:105`, `services/exercise/app/static/app.js:80`, `services/exercise/app/static/radio.js:453`
- **Problem:** Message bodies, senders and channel names are interpolated into innerHTML unescaped, and any LAN client can POST /api/messages with markup.
- **Fix:** Escape on render, as legacy radio.js:467 already does.
- **Done when:** A message containing a script tag renders as text.

### F-7

**Legacy console: precedence bug and autoplay-blocked audio**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort S · wave 3 · **open**

- **Files:** `services/exercise/app/static/radio.js:530,535-559`
- **Problem:** a && b || c.startsWith() throws when sender is undefined (masked today by a server default), and incoming traffic resumes the AudioContext and speaks outside a user gesture, so iPad Safari stays silent until something is clicked.
- **Fix:** Fix the precedence; require a gesture to arm audio, as the new console correctly does. If /radio-legacy is retired (C9) this closes with it.
- **Done when:** iPad hears the first incoming call after joining.

### F-8

**No bearing intersection maths despite the README**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C8 (Base view & debrief) · effort M · wave 3 · **open**

- **Files:** `services/exercise/app/static/base.js:99-102`, `README.md`
- **Problem:** Bearings are drawn as flat-earth 40 NM rays (fine at that scale) but nothing computes intersections or a confidence area, although the README advertises 'bearing logging & intersection cuts'. Base staff must eyeball the crossing. Bearing entry also requires typing the callsign rather than picking a reporting aircraft.
- **Fix:** Compute pairwise intersections and a simple confidence polygon; add a callsign dropdown.
- **Done when:** Three bearings produce a plotted cut area matching a hand plot.

### F-9

**New radio console has no Form 110 log**

`P2` · `medium` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort M · wave 3 · **open**

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

`P2` · `medium` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort S · wave 3 · **open**

- **Files:** `instruments/becker-sar-df-517/logic.lua:378,392,402`
- **Problem:** `msg and msg.has_pos or s.cs_has_pos` means a STORED frame without a position displays the live frame's position — the student reads a stored beacon as having a position it never carried.
- **Fix:** Explicit if/else on the stored message.
- **Done when:** Store a positionless frame; page 4 shows no position.

### I-5

**RT-600 long-press timers survive power-off**

`P2` · `medium` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort S · wave 3 · **open**

- **Files:** `instruments/rhotheta-rt-600/logic.lua:479-481,386`
- **Problem:** Release returns early when the unit is unpowered, leaving press_at armed, and power_off does not stop the timers, so f1_long fires clear_average() after shutdown.
- **Fix:** Stop timers in power_off and on the early-return path.
- **Done when:** Hold F1, power off, release: no averaging reset.

### I-6

**DF heads and TDFM ignore the electrical bus**

`P2` · `medium` · `bug` · Air Manager instruments · cluster C12 (Instrument runtime) · effort M · wave 3 · **open**

- **Files:** `instruments/becker-sar-df-517/logic.lua:588`, `instruments/cap-fm-tdfm-136b/logic.lua:353-358`, `instruments/mo-audio-panel-gma1347/logic.lua:389`
- **Problem:** Both DF heads and the TDFM power up with the battery and avionics master off; only the GMA follows avionics_power_on, and even it ignores bus_volts. For a trainer whose value is procedural traps, the most basic one is missing.
- **Fix:** Gate all four instruments on the avionics bus and bus voltage.
- **Done when:** Cold aircraft: no instrument lights until the master is on.

### L-11

**Unknown departure/destination silently becomes a waypoint position**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort S · wave 3 · **open**

- **Files:** `services/flightplanner/app.py:626-628`, `services/flightplanner/app.py:639-641`
- **Problem:** Pre-existing, surfaced while generating a sample for the L-1 review. When get_airport() misses - an unknown identifier, or the aviation database still downloading - the export falls back to the first/last waypoint's coordinates and elevation 0.0, and emits them under the requested airport code. The observed sample put KSEE at 33.170,-117.079 (a search waypoint) instead of Gillespie Field, with no warning anywhere. A crew loading that plan departs from the wrong place.
- **Fix:** Return a 400 naming the identifier that could not be resolved, or emit the record only when the lookup succeeds. Never substitute an unrelated position under an airport code.
- **Done when:** Exporting with an unknown ADEP returns an error rather than a plausible-looking file.

### L-12

**Flight planner database is a file bind-mount, so SQLite journals escape it**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort S · wave 3 · **open**

- **Files:** `docker-compose.yml:121`, `services/flightplanner/app.py:25`
- **Problem:** Found while fixing O-3. Compose mounts aviation_data.db as a single FILE at /app/aviation_data.db. SQLite writes its rollback journal beside the database, so -journal and -wal files land in the container's own /app layer rather than on the host. A crash mid-write leaves the journal on a discarded layer and the database with no way to roll back. O-3 works around the symptom by pre-creating the file; this is the underlying shape.
- **Fix:** Mount the DIRECTORY - ./services/flightplanner/data:/app/data - and point DATABASE_PATH at /app/data/aviation_data.db so the journal stays with the database. The host file does not move, so no migration. Left for Codex because app.py is its lane and it had uncommitted work there.
- **Done when:** A write leaves its journal on the host volume, not inside the container.

### L-5

**Search patterns leave uncovered ground and truncate silently**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort M · wave 3 · **open**

- **Files:** `services/flightplanner/app.py:591-595,543,532,554`
- **Problem:** Parallel track places int(width/spacing) tracks starting on the box edge, so a 4 NM box at 1 NM spacing leaves the last mile unsearched and wastes half the first track; CAP practice is tracks at S/2, 3S/2. Creeping line silently truncates at max_legs with no warning that coverage is incomplete. heading_mag is emitted for expanding square but not the other two.
- **Fix:** Half-spacing offset and ceil; return a coverage-truncated flag; emit heading_mag consistently.
- **Done when:** Generated coverage matches the requested box within one track spacing.

### L-6

**Performance tables extrapolate silently and ignore tailwind**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort M · wave 3 · **open**

- **Files:** `services/flightplanner/app.py:711,736-740,665,937`
- **Problem:** get_cruise is nearest-neighbour rather than interpolating; takeoff/landing clamp to the last table row, understating distance above 6000 ft or 30 C; negative headwind (tailwind) is ignored; and when wind >= TAS ground speed clamps to zero and the leg then reports zero time and fuel, so an impossible leg looks cheap.
- **Fix:** Interpolate; refuse or flag beyond-table inputs; handle tailwind; error on GS <= 0.
- **Done when:** A leg with a 100 kt headwind reports an error, not zero fuel.

### L-7

**Flight planner ships 172S performance data under a 182T label**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort M · wave 3 · **open**

- **Files:** `services/flightplanner/app.py:64-102`, `services/flightplanner/README.md`
- **Problem:** AIRCRAFT_DATABASE holds 2550 lb / 53 gal 172S figures while the aircraft, the handbook and the simulator package are all a 3100 lb / 87 gal 182T. Fuel and endurance planning for every sortie is computed from the wrong airframe.
- **Fix:** Replace with 182T POH data (matching the .acf the build script produces), or relabel the profile honestly.
- **Done when:** Planned endurance matches the handbook's 5.5 h figure.

### L-8

**Planner has no offline map path**

`P2` · `medium` · `bug` · Flight planner · cluster C6 (Offline mission base) · effort M · wave 3 · **open**

- **Files:** `services/flightplanner/templates/index.html:8,447`, `services/flightplanner/static/js/app.js:83-97`, `services/flightplanner/app.py:1490`
- **Problem:** Leaflet and Google Fonts load from CDNs and tiles come straight from ArcGIS. The server-side tile cache only runs under __main__, never under gunicorn, and the frontend never requests /tiles/ anyway, so the charts volume is dead weight and USER_GUIDE.md's claim that cached tiles are used first is false.
- **Fix:** Vendor Leaflet and fonts; wire the frontend to /tiles/; pre-cache the exercise area into the existing volume.
- **Done when:** Plan a route with outbound internet blocked.
- **Depends on:** F-1

### L-9

**API returns HTML 500s and misreports push status**

`P2` · `medium` · `bug` · Flight planner · cluster C10 (Flight planner correctness) · effort M · wave 3 · **open**

- **Files:** `services/flightplanner/app.py:894-897,1001-1008,1397,1438,1463`
- **Problem:** Unguarded int()/float() on client JSON returns Werkzeug HTML that the JS then fails to parse. The 'no sortie running' branch is dead because the console no longer 400s, so the UI always claims the message was broadcast to an active sortie even when nothing was persisted. The push also sets beacon_elev_ft to 0.0 (sea level, which the propagation model then uses) and places the beacon exactly on the planned datum, handing the trainee the answer.
- **Fix:** Guard parsing and return JSON errors; report persisted vs broadcast honestly; carry a real beacon elevation; offset the beacon from the datum.
- **Done when:** Bad input returns JSON 400; a pushed scenario does not sit on the planned datum.

### P-6

**121.5 beacons produce a COSPAS-SARSAT decode**

`P2` · `medium` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 3 · **open**

- **Files:** `xplane/PI_capvsar_df.py:824`
- **Problem:** decode_tick is called without the on_406 gate used elsewhere, so an analog beacon shows SYNC OK and a hex ident — teaching a student that a 121.5 signal carries beacon identity.
- **Fix:** Gate decode_tick on the 406 band.
- **Done when:** 121.5 scenario shows no decoded ident.

### P-7

**Signal bar stays lit between 406 bursts**

`P2` · `medium` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 3 · **open**

- **Files:** `xplane/PI_capvsar_df.py:783,805`
- **Problem:** cap/df/signal is published before the burst gate, so the bar shows full strength while nothing is being received, and squelch evaluates the continuous value rather than the gated one.
- **Fix:** Publish the gated value; evaluate squelch against it.
- **Done when:** Signal bar pulses with the 50 s burst cadence.

### P-8

**Terrain masking is only -12 dB**

`P2` · `medium` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 3 · **open**

- **Files:** `xplane/PI_capvsar_df.py:772`
- **Problem:** Blocked paths attenuate by *0.06, so a fully masked beacon at 2 NM still yields signal 0.375 and a valid bearing. Real knife-edge diffraction loss is 20-40 dB, so the masking effect barely teaches anything inside ~4 NM.
- **Fix:** Deepen the loss to a realistic knife-edge range and recheck the existing masking tests.
- **Done when:** Masked beacon at 2 NM drops below squelch.
- **Depends on:** P-1

### X-6

**Untyped request bodies mutate scenario definitions**

`P2` · `medium` · `bug` · Exercise console (backend) · cluster C7 (Console robustness) · effort M · wave 3 · **open**

- **Files:** `services/exercise/app/main.py:235,277-283,143,219`
- **Problem:** start_sortie and set_effects take raw dicts, bypassing Pydantic; set_effects merges arbitrary keys straight into the scenario row, so a mid-exercise effect change permanently rewrites the scenario definition for every future sortie. No lat/lon range checks. Positional INSERT ... VALUES (?x15) breaks on the next schema change.
- **Fix:** Pydantic models; store effects on the sortie, not the scenario; range-check coordinates; named columns.
- **Done when:** Changing effects mid-sortie leaves the scenario row untouched.

### X-8

**Console operational hygiene: retention, logging, health, shutdown, root**

`P2` · `medium` · `bug` · Exercise console (backend) · cluster C7 (Console robustness) · effort M · wave 3 · **open**

- **Files:** `services/exercise/app/main.py:300-302,442-444,149`, `services/exercise/Dockerfile`
- **Problem:** Partly addressed 2026-09-08: connections now close (was a leak per request) and X-3 added WAL. STILL OPEN: positions has no retention and /track is unpaginated; main.py has no logging (two print() calls aside); the healthcheck never touches the database; the ticker task is not cancelled on shutdown; the container runs as root.
- **Fix:** Retention policy plus pagination; structured logging; DB-touching healthcheck; cancel the ticker in lifespan; non-root user.
- **Done when:** A long exercise does not grow /track unboundedly; logs show sortie lifecycle events.

### X-9

**One Mumble client per browser socket, 16 max**

`P2` · `medium` · `bug` · Exercise console (backend) · cluster C9 (Radio console hardening) · effort M · wave 3 · **open**

- **Files:** `services/exercise/app/radio.py:141`
- **Problem:** Each browser socket spawns a pymumble thread at a 10 ms loop rate against a 16-session cap. A base desk running two radio faces consumes two of the sixteen and appears as two users on the net.
- **Fix:** Share one Mumble client per operator across their radio faces, or raise and document the cap with measured CPU.
- **Done when:** A dual-radio desk appears once on the net.

### F-10

**Mission base cannot monitor the airband SAR net**

`P2` · `low` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort L · wave 3 · **open**

- **Files:** `services/exercise/app/static/mission-radio.js`, `services/exercise/app/radio.py`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. The MRO must watch the VHF-FM tactical net and the VHF-AM aeronautical SAR frequency at the same time; the console joins one Mumble channel at a time. The retired /radio-legacy console had a second airband station (Icom IC-A120) and the rewrite dropped it, so the base can no longer hear aircraft calling on the air-to-ground frequency while working the tactical net.
- **Fix:** A second simultaneous receive channel on the console, with independent volume and its own log identity. Note the 16-session cap in X-9 - two channels per operator doubles the session count.
- **Done when:** One operator hears both nets at once and can key the correct one.

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

### F-11

**No operational sidetone on the new radio console**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort S · wave 3 · **open**

- **Files:** `services/exercise/app/static/mission-radio.js:251`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. The only oscillator is the 660 Hz headset-test beep. There is no talk-permit chirp on channel grant and no squelch tail, so an operator gets no acoustic confirmation that the radio actually keyed. NOTE: the audit proposed porting playP25Chirp/playP25Tail/playAmSquelchBurst from radio.js - those functions do not exist anywhere in the tree. This is new work, not a port.
- **Fix:** Synthesise a talk-permit chirp on grant and a squelch tail on release.
- **Done when:** Keying produces an audible grant tone before speech is passed.

### C15-1

**Split the console into store + routers with role middleware**

`P2` · `medium` · `task` · Exercise console (backend) · cluster C15 (Service boundaries (architecture)) · effort L · wave 4 · **open**

- **Files:** `services/exercise/app/main.py`, `services/missionbase/`, `services/tracking/`
- **Problem:** main.py holds scenario truth, telemetry ingest, the WebSocket hub, SQLite and (via radio.py) the real-time voice bridge on one event loop. X-3 is the symptom, and the CalTopo relay and IC/AOBD views both land here next. The empty services/missionbase/ and services/tracking/ directories are the right instinct.
- **Fix:** store.py (SQLite, WAL, rehydration, truth serializer) plus exercise / tracking / missionbase / radio routers behind one app; move the Mumble bridge off the main loop.
- **Done when:** Same behaviour, with the truth serializer provably applied in one place.
- **Depends on:** X-1, X-2, X-3

### I-8

**Panel registrar writes Air Manager's database on hardcoded assumptions**

`P2` · `medium` · `bug` · Air Manager instruments · cluster C13 (Instrument tooling & shared libs) · effort M · wave 4 · **open**

- **Files:** `scripts/register_mo_panel.py:25,50,97-100,107-168,171-172,182`
- **Problem:** It hardcodes 26 panel columns and magic values, syncs sqlite_sequence for two of four tables, pkills Air Manager without confirmation, relaunches from a /home/ron path, and never updates an existing layout so position edits never propagate. Panel geometry is triplicated across info.xml, this script and generate_assets.py with no cross-check. Streaming=true is set only through the SQLite path, so the --zip route ships a dead MFD.
- **Fix:** Confirm before killing; parameterise the DB path; update existing layouts; single source for geometry; put Streaming in info.xml.
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

`P2` · `medium` · `bug` · Docs / record · cluster C14 (Contract & documentation truth) · effort M · wave 4 · **open**

- **Files:** `docs/DATAREF_CONTRACT.md:43,59,67-74,107`
- **Problem:** The contract is the interface between the plugin and every faceplate, and it is wrong in five places: cap/scenario/* is documented writable for offline testing but active is read-only; bearing extremes are documented as +/- spread/2 but published one-sided; 'slant range' is ground great-circle; BYTE[15] returns length 0 undecoded; and five effect names are undocumented.
- **Fix:** Correct the contract to the code, or change the code where the contract is the better design (writable scenario datarefs are genuinely useful offline).
- **Done when:** A faceplate author can work from the contract alone.

### P-11

**Server fallback propagation diverges from the plugin**

`P2` · `medium` · `bug` · Exercise console (backend) · cluster C15 (Service boundaries (architecture)) · effort M · wave 4 · **open**

- **Files:** `services/exercise/app/propagation.py:37-71`
- **Problem:** The server model uses a 1.5 s burst window against the plugin's 0.44 s, never invalidates between bursts, matches band as the string '406', and has no squelch, averaging, timehold, tuning, terrain or airframe modelling. It runs whenever the plugin omits df, so an instructor can be shown a different DF picture than the sim computes.
- **Fix:** Shrink propagation.py to the mock-bridge stub it effectively is and make the plugin authoritative everywhere, per existing policy.
- **Done when:** Instructor HUD matches the cockpit in a sim-connected exercise.

### C15-2

**Consolidate five geodesy implementations**

`P3` · `low` · `task` · Exercise console (backend) · cluster C15 (Service boundaries (architecture)) · effort M · wave 4 · **open**

- **Files:** `services/flightplanner/app.py`, `services/exercise/app/propagation.py`, `services/exercise/mock_bridge.py`, `services/exercise/app/static/debrief.js`, `xplane/PI_capvsar_df.py`
- **Problem:** Bearing/distance is implemented five times with the same R_NM constant; debrief.js has already drifted (missing cos(lat) in heading). [Re-verified 2026-09-08 against the complete tree: exactly five files carry their own geodesy. Stands.]
- **Fix:** One shared Python geodesy module for the two services; the plugin keeps its standalone copy tested against it; the JS uses one helper.
- **Done when:** A cross-implementation test agrees within 1 m over 100 NM.

### F-12

**APX/EFJ control-head keys are artwork only**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort M · wave 4 · **open**

- **Files:** `services/exercise/app/static/mission-radio.js`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. SCAN, MON, SQL and EMER appear on the SVG faceplates but have no hit regions in the JS at all - grep finds none of those names. MON (squelch open) is what an operator actually reaches for to pull a marginal signal from an aircraft low in terrain, which is a real trained skill.
- **Fix:** Add hit regions and behaviour, starting with MON.
- **Done when:** MON opens the squelch and marginal traffic becomes audible.

### F-13

**Net names are generic, not CAP nomenclature**

`P3` · `low` · `bug` · Exercise console (frontend) · cluster C9 (Radio console hardening) · effort S · wave 4 · **open**

- **Files:** `services/exercise/app/radio.py:29-34`
- **Problem:** Raised by the 2026-09-08 radio ecosystem audit (Gemini), verified against the tree. Channels read PRIMARY / ALTERNATE / MISSION BASE / BRIEFING. Real heads show zone and channel tags from the fleet plan, and reading them correctly is part of the operator's job. Related to I-11 - the airborne and ground plans should agree.
- **Fix:** Adopt the same channel naming as I-11 so cockpit and base refer to a channel identically. Verify names against CAPR 100-1 rather than inventing them.
- **Done when:** A channel briefed by name is identifiable on both the aircraft radio and the base console.

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

`P3` · `low` · `bug` · Air Manager instruments · cluster C13 (Instrument tooling & shared libs) · effort M · wave 4 · **open**

- **Files:** `instruments/*/lib/cap_df.lua`, `instruments/*/lib/lcd.lua`, `instruments/*/lib/dcu.lua`, `tests/test_faceplate.py:126-129`
- **Problem:** cap_df.lua, cap_df_audio.lua, dcu.lua, lcd.lua and three WAVs are byte-identical across the Becker and RT-600 (lcd.lua also in the TDFM). A test enforces the DF pair but not the TDFM copy, so that one can drift silently.
- **Fix:** instruments/_shared/ copied in by the deploy scripts, with a test asserting installed copies match the shared source.
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

`P3` · `low` · `bug` · Air Manager instruments · cluster C13 (Instrument tooling & shared libs) · effort S · wave 4 · **open**

- **Files:** `scripts/deploy_df_instruments.py:14-17,47`, `instruments/*/info.xml:20-25`
- **Problem:** The deploy script handles two of four instruments although the website claims it deploys all four; TDFM and GMA have no deploy script; stale target files are never removed; and every info.xml claims FSX/P3D/FS2020 support although all four are X-Plane only. [Re-verified 2026-09-08: deploy_df_instruments.py still lists 2 of 4 instruments; TDFM and GMA have no deploy script. Stands.]
- **Fix:** Deploy all four, prune stale files, correct the manifests.
- **Done when:** One command deploys four instruments to a clean Air Manager.

### L-10

**Planner dependency and container hygiene**

`P3` · `low` · `bug` · Flight planner · cluster C11 (Flight planner security & dependencies) · effort M · wave 4 · **open**

- **Files:** `services/flightplanner/requirements.txt`, `services/flightplanner/Dockerfile`, `services/flightplanner/app.py:807`
- **Problem:** requests==2.31.0 carries CVE-2024-35195 and CVE-2024-47081; gunicorn and Werkzeug are unpinned; the container runs as root; the healthcheck hits / rather than a DB-verifying endpoint; serve_tile accepts .. in chart_type (not currently exploitable but unnecessary); _winds_cache grows unbounded; the aviation DB is OurAirports, not FAA NASR, with no cycle date shown.
- **Fix:** Bump and pin; non-root user; /api/health; whitelist chart_type; bound the cache; display the data cycle.
- **Done when:** pip-audit clean; health endpoint fails when the DB is missing.

### O-1a

**Generated handbook committed deliberately**

`P3` · `low` · `bug` · Deployment / infrastructure · cluster C1 (Repo & release hygiene) · effort S · wave 4 · **resolved**

- **Files:** `.gitignore`, `docs/manual/`
- **Problem:** `docs/manual/*.odt|docx` are ignored but the 3.3 MB `.pdf` and `.html` are not, although scripts/generate_manual.py regenerates both on every run.
- **Fix:** Resolved by decision: Codex's v0.1 baseline entry states the generated handbook PDF/HTML are tracked deliberately as the published artefact. No change needed; expect churn in those two files on every manual rebuild.
- **Done when:** Decision recorded in the CHANGELOG v0.1 baseline entry.
- **Depends on:** O-1

### P-12

**Plugin reporting cadence and heading source are off**

`P3` · `low` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort S · wave 4 · **open**

- **Files:** `xplane/PI_capvsar_df.py:432,962,972,1018`
- **Problem:** REPORT_S=2 but the loop sleeps 3 s; the first report is (0,0,0) before any flight loop; psi is the OpenGL-frame heading where true_psi is correct; a null in scenario JSON would throw in the dataref accessor.
- **Fix:** Align the sleep with REPORT_S, skip the first empty report, use true_psi, coerce nulls.
- **Done when:** Track starts at the aircraft's real position with 2 s spacing.

### P-13

**Signal model has no dB calibration and multipath is scripted**

`P3` · `low` · `enhancement` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort L · wave 4 · **open**

- **Files:** `xplane/PI_capvsar_df.py:770,828-830`
- **Problem:** 25/d^2 saturates at 5 NM for every band, so a 0.1 W 121.5 beacon and a 5 W 406 beacon differ only in cadence and decode, not range. Multipath is a deterministic 40 deg step for 12 of every 36 s, independent of terrain or range, so it reads as a scripted glitch rather than a reflection.
- **Fix:** Calibrate to a real link budget per band; drive multipath from the terrain probe that already runs.
- **Done when:** Detection ranges differ per band and match published ELT figures within a training tolerance.
- **Depends on:** P-1

### P-9

**Fixed 24 terrain probes, no earth curvature**

`P3` · `low` · `bug` · X-Plane plugin / engine · cluster C3 (Propagation engine correctness) · effort M · wave 4 · **open**

- **Files:** `xplane/PI_capvsar_df.py:94,593`
- **Problem:** 24 probes means 1.25 NM spacing at 30 NM, skipping narrow ridges, and the straight ray ignores the ~200 ft mid-path curvature bulge at that range.
- **Fix:** Scale probe count with distance; add the curvature term.
- **Done when:** A narrow ridge at 25 NM blocks.
- **Depends on:** P-1

