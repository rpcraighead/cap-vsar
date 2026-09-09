# Project change log

Record implementation changes, research findings, and design decisions here.
Clearly distinguish proposed work from completed implementation.

## 2026-09-09 — CAP-VSAR Website unification: Distributed SAREX, Virtual ICS & CalTopo integration

**Status: completed, validated across all HTML documents with zero broken anchors/assets.**

Unified all recent system developments, tactical avionics enhancements, exercise director workflows, and mission maps into the public CAP-branded marketing and technical website (`website/`):

- **Created `website/sarex.html` (Distributed SAREX & Incident Command System)**:
  - Articulates the monthly training cadence rationale (overcoming live flight friction, avgas fuel costs, weather groundings, and maintenance bottlenecks).
  - Contrasts three operational modalities: In-Person Squadron Lab, Hybrid Multi-Station Base, and 100% Completely Virtual Distributed Wing SAREX.
  - Documents the complete simulated ICS hierarchy (Incident Commander, Air Operations Branch Director, Operations/Planning, Mission Radio Operators 1 & 2 with Form 110 comms, Ground UDF teams with mobile PTT, and Mission Pilot / Observer aircrews).
  - Highlights CalTopo Phase 2 Common Operating Picture (COP) integration: live telemetry streaming, bearing line-of-position (LOP) vector triangulation, and bi-directional SAR pattern exchange (.fms / GPX).
  - Outlines 4 realistic operational search scenarios (Pauma Valley 406 ELT, Mountain Repeater Net, Air-to-Ground Handoff, Stuck-MIC Net Recovery).
- **Updated `website/operations.html`**:
  - Added **Exercise Director Setup & Mobile QR Dispatch** section detailing 1–4 aircraft stepper provisioning and scannable QR badge cards for rapid smartphone onboarding.
  - Added **California Wing Mountain Repeaters Matrix** detailing standard national dual-pair conventions (148.125 / 143.550 MHz primary, 148.150 / 143.700 MHz secondary) and summit relay PL/NAC codes (Mt. Diablo, Santiago Peak, Mt. Palomar, Oat Mountain, Blue Ridge, Palm Springs).
  - Corrected historical APX 6500 references to APX 4500 (resolving review finding D-2).
- **Updated `website/cockpit.html`**:
  - Added **Tactical Communications & Audio Integration** section covering Technisonic TDFM-136B dedicated Guard receiver (GD1/GD2), 60s transmit time-out timer (TOT), 20-channel priority scan engine, 240 memory channels, and Garmin GMA 1347 Table 6A.3.2 ICS isolation modes and rolling 2.5-minute digital clearance recorder.
  - Documented acoustic RF SNR hiss degradation (`elt_noise.wav`) on Becker 517 and RT-600 direction finding instruments.
  - Upgraded footer to standard 4-column brand grid.
- **Updated `website/technical.html` & `website/deployment.html`**:
  - Added automated test verification suite section (`#testing`) validating `test_engine.py`, `test_faceplate.py`, and `test_panel.py`.
  - Corrected flight planner tech stack specification (Flask/Gunicorn, not Node.js/Vite) in `technical.html`.
  - Added Step 5 to deployment guide documenting `scripts/build_station_kit.py` and `capvsar_station.ini` for turnkey multi-station aircraft provisioning.
- **Cross-Navigation & Link Integrity**:
  - Added `Distributed SAREX & ICS` to navigation bars across all 6 pages.
  - Verified 100% link, image, and anchor target resolution across all pages with zero broken references.

## 2026-09-09 — O-4/O-5/O-6 live on ms01; two independent git histories reconciled; NFS3 backup target

**Status: deployed and verified on ms01 directly, not just tested locally.**

Applying the Mumble work below to ms01 surfaced a problem bigger than the
deploy itself: `/srv/capvsar` on ms01 had 6 local commits (beacon-truth/role
tokens, base-view reset, radio audit findings, O-3) that had never reached
Gitea - its `origin` remote had no working credential, so every push had
presumably been failing silently or was never attempted. Generated a
repo-scoped Gitea deploy key for ms01, fetched, and merged the two histories
(both branched from `v0.1`) conflict by conflict rather than picking a side
by default: `access.py`, `main.py`, `base.js`, and the test/engine files all
resolved in favor of the desktop session's version after *confirming* -
diffing directly, not trusting diffstat - that it was a strict superset of
what ms01 had. `docs/bugs/tracker.json` the same way: 23 items differed in
status, all 23 in the same direction. Re-ran the full test suite on ms01
itself afterward, against its actual Python 3.12 and pinned production
dependency versions, not assumed compatible from a different machine.

Deploying then found two real bugs neither local testing nor code review had
caught:

- `provision_mumble.py` couldn't open `mumble-server.sqlite` as the deploying
  user - it's owned by the mumble container's internal uid with group-only
  read. `deploy.sh` now runs it under `sudo`; the Instructor/SET ACL, which
  had silently never been written on the first deploy attempt because of
  this, is now actually in ms01's live database.
- The `radio-https` healthcheck (added below) was broken two ways at once:
  `wget -k` is `--convert-links`, not a cert-bypass flag, and
  `https://localhost` sends a TLS SNI the Caddyfile has no site block for, so
  Caddy errored the handshake instead of serving anything. Neither had ever
  actually been run against the container before landing. Fixed with
  `curl --resolve`, pinned to loopback to also dodge a hairpin-NAT hang
  connecting to the LAN IP from inside the container.

Mounted NFS3 (WD NAS, `192.0.2.144:/mnt/HD/HD_a2/NFS3`, documented
lab-wide for backups/cold storage) on ms01 for the first time - it had no
client mount at all - and pointed the nightly backup cron
(`0 3 * * *`, installed) at `/mnt/nfs3/capvsar/backups/exercise-db` instead
of the same local disk `exercise.db` itself lives on. The very first live
run against that freshly-touched NFS directory hit a one-off
`sqlite3.OperationalError` from inside `Connection.backup()` - confirmed
transient (the next two manual attempts succeeded immediately) but real:
`backup_exercise_db.py` now retries transient failures and cleans up any
partial file on every failed attempt, not only a successful-but-empty one.

### Verification

- `sudo python3 scripts/preflight.py` on ms01: **ALL PASS** (console health,
  full Mumble tree, the Instructor/SET ACL, tile source, CA cert).
- `docker compose ps`: all four services healthy, including `radio-https`
  for the first time since it gained a healthcheck.
- A real backup landed on the real NFS3 mount (262144 bytes, read back and
  verified), then removed as a test artifact.
- No one was connected to Mumble at deploy time (checked first); the actual
  interruption was under two minutes.

## 2026-09-09 — Mumble infrastructure: provisioned tree, ACLs, callsign integrity, backups, preflight (O-4, O-5, O-6)

**Status: code complete and tested locally. NOT yet applied to ms01's live
Mumble server or scheduled on ms01 - see "Still needs a live decision" below.**

Inspected ms01's actual `mumble-server.sqlite` directly (via `docker cp` and
Python's `sqlite3`, not assumed) before writing anything, since Murmur's ACL
schema (`grantpriv`/`revokepriv` bitmasks, not simple allow/deny columns) and
permission bit values aren't things worth guessing for a security control.
That inspection also surfaced a real naming drift: `docs/MUMBLE_CHANNELS.md`'s
own tree diagram said "Instructor / SET" while its setup steps, and the live
database, both already said "Instructor - SET".

**O-4 - the channel tree now has one source of truth.**
`services/exercise/app/mumble_channels.py` holds it; `radio.py` reads its
`CHANNELS` from there instead of an independent hardcoded four-name copy.
`scripts/provision_mumble.py` recreates the whole tree idempotently in
`mumble-server.sqlite` (every write checks for the exact row it would create
first) and finishes the ACL step `docs/MUMBLE_CHANNELS.md` always said was
still manual: deny `Enter` to `@all` on Instructor/SET, grant it back to a new
`instructor` group, at ACL priorities 0/1 so the grant overrides the deny for
whoever's actually in that group (per mumble.info's admin docs: later/higher
priority overrides earlier for the same permission bit). `scripts/deploy.sh`
now stops mumble, runs the provisioner, restarts it, on every deploy.

**O-5 - images pinned, callsigns can't be forged.** `mumblevoip/mumble-server`
and `caddy` are pinned by digest to what was already running and verified on
ms01 (`docker inspect`), not `:latest` silently drifting under a live voice
net. `/api/radio/stream` now resolves an authenticated RBAC session
(`access.get_session_from_request`, which works unmodified against a
WebSocket - Starlette's `WebSocket` and `Request` share the same
`HTTPConnection` base for `.cookies`/`.headers`/`.query_params`) and uses
*that* callsign, ignoring whatever the client claims, when a session exists.
A base-role student can no longer type "MISSION BASE" or "INSTRUCTOR" into
the browser radio and impersonate another station. No session - RBAC not
configured for the exercise, the common case today - falls back to the
client-supplied callsign exactly as before. `CERTREQUIRED`/`ALLOWHTML`/
`USERS=100` were deliberately left alone: that's this training net's
low-friction-join posture, not an oversight, and changing it wasn't asked for.

**O-6 - a stack that fails loudly instead of silently.**
`scripts/preflight.py` checks the console's `/api/health`, the full Mumble
tree plus the Instructor/SET ACL, the flight planner's VFR tile source (via
the MapServer metadata endpoint - a 404 on an out-of-pyramid tile coordinate
looks identical to the service being down, so that's not what this checks),
and the published browser-radio CA cert. `scripts/backup_exercise_db.py`
takes an online SQLite backup (`Connection.backup()`, safe against a database
a live process still has open - not a raw file copy, which can capture a torn
snapshot) with 14-day retention pruning; a crontab line lives in the script's
own docstring, nothing installed by this change. `radio-https` (Caddy) gained
a `docker-compose.yml` healthcheck - it had none, so a Caddy that stopped
proxying looked identical to a healthy one to `docker compose ps`.

### Validation

- `tests/test_provision_mumble.py` (4 cases) against fixtures built from
  ms01's real schema: fresh-server tree creation, correct ACL priority/bits,
  an already-hand-provisioned tree left byte-for-byte untouched aside from
  the two new ACL rows, and idempotency on a second run.
- `tests/test_radio.py` gained 2 cases for the session-callsign override and
  its fallback; all 15 pass, all 72 console+radio+setup_auth tests pass
  together.
- `tests/test_backup_exercise_db.py` (4 cases) **caught a real bug**: backups
  taken in the same second collided on a 1-second-resolution filename and
  silently overwrote each other - exactly the failure mode worse than no
  backup. Fixed by moving to microsecond resolution before this shipped.
- `preflight.py` run by hand against a cold stack (fails loudly, one specific
  reason per check, matching O-6's own stated verify criterion) and a fully
  mocked warm one (provisioned test Mumble db, mock health endpoint,
  placeholder CA cert - all five checks pass).

### Still needs a live decision

Nothing above touched ms01. Applying it means: `docker compose pull` (new
pinned digests), stopping mumble to run `provision_mumble.py` against the
real `mumble-server.sqlite`, and redeploying `radio-https`/`exercise` for the
healthcheck and callsign-integrity code - a real, if brief, interruption to
anyone currently on the voice net. Scheduling the nightly backup cron job is
a separate, similarly live decision. Both were left for explicit sign-off
rather than done unasked.

## 2026-09-09 — This tree is now a real git checkout (O-1)

**Status: complete.**

`git` is installed on this machine (wasn't as of the 2026-09-08 correction
below), but `/home/ron/Projects/cap-vsar` still had no `.git/` even though
`v0.1` had been pushed to Gitea and GitHub — so no agent editing here could
diff, revert, or see what another tool changed, which was the actual failure
mode O-1 tracked regardless of whether a baseline existed somewhere else.

Looked up the real Gitea remote via its API with a token (`ron/capvsar`,
private; `git.rpc-cyberflight.com` doesn't resolve from this host, use
`192.0.2.121` directly) rather than guess one. `git init` in place, added
`origin`, fetched, then pointed local `main` at `origin/main` **without a
checkout** — `git branch main origin/main` + `git symbolic-ref HEAD
refs/heads/main` populates history and moves HEAD without touching a single
file on disk, so nothing already in the working tree could be silently
overwritten by files coming from `v0.1`. Diffed the resulting stage against
known secret patterns before committing.

Everything that had accumulated since `v0.1` — RBAC/setup wizard, O-2,
radio/DF fidelity work, docs, tests, 67 files — landed in one commit,
`6c2b3d4`. Separately noticed and restored `.env.example`, which was missing
from the working tree with nothing in this log explaining why; rebuilt from
the env vars the code actually reads rather than guessed, committed as
`c517617`. Both pushed to Gitea's `origin/main`.

**Deliberately not done here: GitHub.** `flight-planner-n499cp-v2` mirrors to
GitHub through an IP-redaction pass (`scripts/redact_ips.py`) before
anything public sees it; whether `cap-vsar` needs the same treatment wasn't
established, so pushing to a public mirror was left alone rather than assumed
safe.

### Verification

- `git log`, `git status`, `git diff` all work in this directory now —
  O-1's stated verify criterion.
- `git status` is clean and `up to date with 'origin/main'` after the push.

## 2026-09-09 — Per-station config: capvsar_station.ini and a kit builder (O-2)

**Status: complete.**

`xplane/PI_capvsar_df.py` hardcoded `CONSOLE`, `CALLSIGN`, and (partially)
`PLUGIN_KEY`, so three aircraft meant three hand-edited copies of the tracked
plugin — the actual failure mode O-2 tracked, since it also meant
`deploy_xplane_plugin.py`'s hash check could never agree across stations.

`_load_station_config()` now reads `[station] console / callsign /
plugin_key` from `capvsar_station.ini` next to wherever the plugin is
deployed, independently per key, falling back to the historical single-station
defaults for anything the ini doesn't set. No ini present (every existing
install today) means no behavior change. `CAPVSAR_TOKEN_PLUGIN`, the
documented env-var mechanism, still overrides the ini's `plugin_key`.

`scripts/build_station_kit.py` is the kit builder: given `--callsign` and
`--console`, it validates and copies the tracked plugin source unmodified,
generates that station's `capvsar_station.ini`, bundles the four Air Manager
instruments (station-agnostic, same for every aircraft), writes an install
README, and optionally zips it (`--zip`). Deliberately **not** bundled: the
C182T G1000 aircraft package (`build_c182t_package.py` derives it from the
recipient's own local Laminar Cessna 172SP install — not redistributable
content) and a CA certificate (issued per ms01 deployment, not present in
this repo). The kit's README says so and points at the right place instead.

### Validation

- `tests/test_engine.py` gained coverage for `_load_station_config()`: no-ini
  fallback, independent per-key ini overrides, and the env-var-beats-ini
  precedence. All 73 checks pass (66 prior + 7 new), 0 failures.
- End-to-end: built a real kit for `CAP-2` with `build_station_kit.py`, then
  imported *that kit's* `PI_capvsar_df.py` directly — own directory, own
  ini — and got `CALLSIGN=CAP-2` and the kit's `plugin_key` back from the
  same tracked source that every other station also ships unmodified.
- Deployed the updated plugin to this machine's X-Plane install via
  `scripts/deploy_xplane_plugin.py`; hash check now reports `current`. No
  `capvsar_station.ini` exists there yet, so this station's runtime behavior
  is unchanged — confirming the fallback path, not just the override path.

### Remaining for a real multi-aircraft stand-up

Each additional station still needs someone to actually run
`build_station_kit.py` with its callsign and hand the kit over — this makes
that a five-minute, config-only step instead of a source edit, it doesn't do
it automatically. The aircraft package and CA cert gaps noted above are
unrelated pre-existing gaps, not introduced or worsened here.

## 2026-09-08 — Exercise Setup Screen, Scannable QR Participant Onboarding, and Role-Based Access Control (RBAC)

**Status: complete. Setup wizard, QR code engine, authentication, RBAC, session store, and test suite implemented.**

Implemented an Exercise Director Setup system (`/setup`), scannable QR code and short-code onboarding (`/join/{code}`, `/login`), and Role-Based Access Control (RBAC) across all consoles and mutating endpoints:

### 1. Exercise Setup Wizard (`/setup`)
- **Fleet Sizing & Configuration**: Exercise Director can select between 1 and 4 aircraft using an interactive stepper. For each aircraft, tail number (e.g. `N499CP`, `N99885`), tactical call sign (`CAP 423`, `CAP 415`), direction-finder head (Becker SAR-DF 517 or RHOTHETA RT-600), and crew positions (Mission Pilot, Mission Observer, Mission Scanner) are configurable.
- **Ground Operations & Staffing**: Configurable assignments for Mission Radio Operators (MRO 1 for primary VHF-FM net, MRO 2 for aeronautical airband watch) and mobile Urban Direction Finding ground teams (UDF 1, UDF 2).
- **Roster & Badge Generation**: Automatically produces participant access codes (`INSTR-1`, `PLT-423`, `OBS-423`, `SCN-423`, `MRO-1`, `UDF-1`, etc.) with assigned roles, titles, and target redirect routes.
- **Scannable QR Badges & Print Layout**: Standalone vector QR code engine renders scannable QR codes pointing to `https://<host>:8743/join/<code>`. One-click "Print Access Badges" stylesheet formatted for lanyard/badge printing.

### 2. Participant Onboarding & QR Authentication
- **Fast Join (`/join/{code}`)**: Mobile cameras scanning QR codes automatically authenticate, receive an HTTP-only `capvsar_session` cookie, and redirect directly into the seat console (`/radio`, `/base`, or `/`).
- **Participant Login Portal (`/login`)**: Mobile-friendly code entry screen with uppercase auto-formatting, error messaging (`invalid_code`, `instructor_required`), and quick-access role test badges.
- **Vendored Offline Compliance**: Implemented a standalone SVG QR generator vendored in `/static/vendor/qrcode.min.js`, maintaining 0 remote dependencies and offline reliability.

### 3. Role-Based Access Control (RBAC) & Session Management
- **SQLite Session & Roster Engine**: Added `roster`, `sessions`, and `exercise_config` tables to `exercise.db` in `services/exercise/app/access.py`. Sessions expire after 24 hours.
- **View Access Control**:
  - `/` and `/setup` require `instructor` role. Unauthorized authenticated sessions redirect with `?error=instructor_required`.
  - `/base` requires `instructor`, `base`, `aircrew`, or `ground_team` role.
  - Unauthenticated browser requests redirect to `/login?next=...` when exercise authentication is active.
- **Mutating Route Protection**: Non-instructor roles cannot stop sorties, reveal beacons, or edit scenarios. MRO/Base roles can submit bearings and mission messages.
- **Truth Containment Preserved**: Aircrew and ground team sessions cannot inspect beacon truth prior to instructor debrief reveal.
- **UI Session Integration**: Added live user role badge (`👤 <Title> (<Callsign>)`) and Logout button to headers on `/`, `/setup`, and `/base`.

### 4. Automated Verification
- Added `tests/test_setup_auth.py` with 23 unit tests covering setup configuration persistence, roster code generation, login/session cookies, `/join/{code}` redirections, RBAC route gating, mutating API role restrictions, and offline vendored asset validation.
- All 34 tests in `tests/test_console.py` pass without regression.
- All 13 tests in `tests/test_radio.py` pass.
- All 6 tests in `tests/test_tdfm.py` pass.
- Lua syntax validation `scripts/luacheck.py` passes cleanly.

## 2026-09-08 — Radio systems specification, feature matrix, and operational use cases publication (DOCX, PDF, Markdown)

**Status: complete. Comprehensive reference manual and automated document generator published.**

Authored and published the complete CAP V-SAR radio ecosystem reference manual across Markdown (`docs/RADIO_FEATURES_AND_USE_CASES.md`), Microsoft Word (`docs/CAP_V-SAR_Radio_Features_and_Use_Cases.docx`), and Adobe PDF (`docs/CAP_V-SAR_Radio_Features_and_Use_Cases.pdf`):

### 1. Equipment Specifications & Operational Feature Matrices
- **Airborne Transceivers & Direction Finders**:
  - **Technisonic TDFM-136B**: P25 digital conventional & analog FM, 200 CAP fleet memory channels with CTCSS subaudible tones and P25 NACs, dual-receiver Guard path (GD1/GD2), 60 s transmitter time-out timer (TOT), and 20-channel carrier-sensing scan engine.
  - **Garmin GMA 1347 Audio Panel**: Three transceiver inputs (COM1, COM2, COM3/TDFM), COM3 MIC transmission interlock, four ICS cockpit isolation modes (`ALL`, `PILOT`, `COPILOT`, `CREW`), Split COM operational separation, 16-block digital clearance recorder (PLAY), and analog fail-safe relay.
  - **Becker SAR-DF 517 & RHOTHETA RT-600**: 121.5 / 243.0 / 406 MHz direction finding, multi-sample circular averaging filter, dynamic inverse signal-to-noise hiss degradation (`elt_noise.wav`), top/bottom antenna installation calibration, and 15-hex COSPAS-SARSAT emergency data frame decoding.
- **Ground & Base Communications**:
  - **Motorola APX 4500**: Fixed base & incident command post multi-channel monitoring, CAP Form 110 radio log synchronization, and cross-band relay.
  - **Mission Base Web Console (`/radio`)**: WebRTC / Web Audio PTT browser radio console, channel selector, headset gain, and direct Mumble voice mesh integration.
  - **Handheld Radios (ICOM IC-A25N & Portable P25)**: Flight line coordination, airfield advisory, and mobile Urban Direction Finding (UDF) ground team bearings.

### 2. Operational Search and Rescue Use Cases
- **Pauma Valley ELT Search**: Step-by-step aircrew DF homing, wing-null banking, cone-of-confusion avoidance, and ground UDF team handoff.
- **Mountain Repeater Net Operations**: Tactical coordination using CA Wing mountain repeaters (Mt. Laguna, Otay Mountain, Santiago Peak) with tone-encoded access.
- **Air-to-Ground SAR Coordination**: Inter-agency communications bridging airborne search assets and ground rescue teams on CALCORD and SAR frequencies.
- **Inadvertent Stuck-MIC Emergency**: Airborne recognition, 60-second automatic timer cutoff, and ground base station diagnostic mitigation.

### 3. Tooling & Automation
- Created `scripts/build_radio_reference_doc.py` using `python-docx` to build the styled 40+ page operational manual with executive layout, styled callouts, comparison tables, and embedded high-resolution equipment graphics.

## 2026-09-08 — Full regression confirmed for L-2/L-3/L-4/F-4; the Python 3.14 TestClient hang does not reproduce

**Status: verification complete. No code changed.**

Closes the one open item from "Planner bounds, database serialization,
authenticated export, and radio recovery (L-3, L-4, L-2, F-4)" below: that
entry shipped all four fixes with targeted tests passing, but left the full
`tests/test_console.py` and `tests/test_radio.py` suites unverified because
this host's Python 3.14 was reported to hang inside pre-existing FastAPI
`TestClient` requests, and running the unchanged suites in ms01's Python 3.12
container was blocked on an SCP-to-ms01 request that was correctly denied —
copying this tree to another host was never authorized.

That local hang does not reproduce. Using the same temporary Python 3.14 venv
(`/tmp/capvsar-test-venv`, FastAPI 0.115.6 / Starlette 0.41.3 / httpx 0.27.2 /
anyio 4.6.2, matching what was already pinned there), each of the following
ran clean, fast, and repeatably — four full runs, no hang, no leftover
process or listening port afterward:

- `pytest tests/test_console.py tests/test_radio.py` — **47 passed**, ~1.1 s,
  twice in a row.
- `python -m unittest discover -s tests` — **71 ran**, only three *pre-existing,
  unrelated* import errors (`test_engine.py` wants a plugin-path argument
  `discover` doesn't give it; `test_faceplate.py` / `test_lcd_text.py` need
  `Pillow`, not installed in this venv). No hang.
- `python -m py_compile services/flightplanner/app.py` and
  `pytest services/flightplanner/tests/test_sar.py` — clean, **19 passed, 6
  subtests passed**.

No ms01 access, SCP, or any change outside `/tmp` was needed. Whatever
produced the earlier hang was specific to that session's process state, not a
standing Python 3.14 incompatibility in this codebase — worth remembering
before requesting cross-host access to work around a local test failure that
hasn't been confirmed to reproduce from a clean process.

## 2026-09-08 — Airborne radio stack fidelity: Guard receiver, scan mode, ICS isolation, digital clearance recorder, and DF SNR degradation (I-12, I-13, I-14, I-15, I-17)

**Status: complete. Instruments, radio service, test harnesses, bug tracker, and contracts updated.**

Building on the 2026-09-08 radio ecosystem audit and the Air Manager Lua test harness
introduced in I-9a, all five Priority 2 tracked defect items (I-12, I-13, I-14, I-15,
and I-17) are implemented and proven across the airborne avionics suite:

### I-12 — TDFM-136B Independent Guard Receiver
The physical Technisonic TDFM-136B features two completely independent receiver modules:
the Main agile transceiver and a dedicated Guard receiver (GD1/GD2). Previously, only a
single operating frequency (`cap_fm_frequency_hz`) was published, meaning Guard was
cosmetic and could not break into Main channel audio.

In `instruments/cap-fm-tdfm-136b/logic.lua`, an independent secondary receive path was
modeled. It continuously monitors the selected Guard channel (GD1 or GD2) and publishes:
- `cap_fm_guard_frequency_hz` (e.g. 168.650 MHz AIRGUARD or 121.500 MHz VHF Guard)
- `cap_fm_guard_channel` (101 for GD1, 102 for GD2)
- `cap_fm_guard_channel_name` (e.g. `AIRGUARD`)
- `cap_fm_guard_ctcss_tone` and `cap_fm_guard_p25_nac`
- `cap_fm_guard_volume` and `cap_fm_main_volume` normalized potentiometer positions [0.0–1.0]

Guard squelch (`cap_fm_guard_rx`) and audio are dual-gated and mixed continuously with Main,
enabling mission base to reach an aircraft regardless of which tactical channel the crew is
monitoring. Proven by `test_guard_receiver_independence` in `tests/test_tdfm.py`.

### I-13 — TDFM-136B Scan Mode Engine
The original `toggle_scan()` function was cosmetic, writing an `'S'` glyph to line 1 of the
display without cycling frequencies. In `instruments/cap-fm-tdfm-136b/logic.lua`, an
operational timer-driven state machine now manages channel scanning:
- A 250 ms dwell timer cycles through programmed scan channels (channels 1..20).
- Carrier detection on `cap_fm_main_rx` immediately halts scanning on that channel.
- Carrier drop arms a 2000 ms hang timer before scanning resumes.
- PTT keying pauses scan to prevent stepping off the frequency while transmitting.
- Toggling scan or powering off the radio cleanly cancels all active timers.

Proven by `test_scan_mode_channel_cycling_and_carrier_halt` in `tests/test_tdfm.py`.

### I-14 — GMA 1347 ICS Isolation and Split COM Integration
The Garmin GMA 1347 audio panel previously published `cap_ics_isolation` and Split COM
de-asserted FM audio/mic flags, but neither was wired into the backend audio service:
every crew member sat in a single Mumble channel, so isolation only changed faceplate lamps.

- In `instruments/mo-audio-panel-gma1347/logic.lua`, published Table 6A.3.2 variables:
  `cap_ics_isolation` (`"ALL"`, `"PILOT"`, `"COPILOT"`, `"CREW"`), `cap_ics_pilot_isolated`,
  `cap_ics_copilot_isolated`, `cap_ics_crew_isolated`, and `cap_split_com_active`.
  Split COM locks the copilot to COM2, isolates the Mission Observer from mission net
  audio and mic, and asserts `cap_split_com_active = true`.
- In `services/exercise/app/radio.py`, added `GET /api/radio/ics` and `POST /api/radio/ics`
  REST endpoints, handled `action: ics` commands in `MumbleRadio.command()`, and applied
  audio isolation filtering in `deliver_audio()` so `pilot_isolated` and `split_com`
  genuinely separate audio streams.

Proven by `test_gma1347_ics_isolation_and_split_com` in `tests/test_am.py` and `tests/test_radio.py`.

### I-15 — GMA 1347 Digital Clearance Recorder
The GMA 1347 PLAY button previously flashed its annunciator for 1200 ms without recording
audio. In `instruments/mo-audio-panel-gma1347/logic.lua`, an authentic clearance recorder
was implemented with a 16-block circular buffer holding up to 2.5 minutes of incoming COM1,
COM2, and COM3 (`cap_fm_main_rx`) audio:
- Pressing PLAY plays back the most recent transmission and illuminates the annunciator.
- Successive presses of PLAY step backward in reverse chronological order through the buffer.
- Pressing any non-PLAY key immediately aborts playback and extinguishes the annunciator.
- Published `cap_recorder_playing`, `cap_recorder_block`, `cap_recorder_count`, and
  `cap_recorder_text`.

Proven by `test_gma1347_clearance_recorder` in `tests/test_am.py`.

### I-17 — DF Audio SNR Degradation
Real DF receivers bury weak sweeps in receiver discriminator hiss at long range or behind
terrain. The simulation previously played fixed-fidelity loops scaled only by receiver volume.
- In `scripts/make_df_audio.py`, synthesized a 2.0-second deterministic band-limited discriminator
  noise asset (`elt_noise.wav`) sampled at 44.1 kHz, placed in both `becker-sar-df-517/resources/`
  and `rhotheta-rt-600/resources/`.
- In shared library `instruments/*/lib/cap_df_audio.lua` (strictly 100% byte-identical),
  loaded `elt_noise.wav` and implemented dynamic inverse noise mixing:
  `signal_vol = gain * signal`, `noise_vol = gain * (1.0 - signal)`.
- Updated both Becker and RT-600 `logic.lua` to sync receiver signal from `df.state.signal / 100`.

Proven by `test_df_audio_snr_degradation` in `tests/test_am.py`, `scripts/make_df_audio.py --check`,
and `tests/test_faceplate.py`.

### Verification, Tooling & Contracts
- **Test Harness (`tests/am.py`):** Added `find_switch_matching` and `click_switch_matching` to
  support toggle switch position and direction interaction in unit tests.
- **Contract (`docs/DATAREF_CONTRACT.md`):** Updated Part 5 to publish all new TDFM Guard,
  GMA 1347 ICS isolation, Split COM, and Clearance Recorder variables.
- **Tracker (`docs/bugs/tracker.json`):** Marked `I-12`, `I-13`, `I-14`, `I-15`, and `I-17` as
  `fixed` and regenerated `docs/BUG_TRACKER.md`.
- **Test Suite Results:**
  - `python3 -m unittest tests.test_am` — 10/10 PASS
  - `python3 -m unittest tests.test_tdfm` — 6/6 PASS
  - `python3 scripts/luacheck.py` — 0 errors / 0 warnings
  - `python3 tests/test_faceplate.py` — 68/68 PASS
  - `python3 scripts/make_df_audio.py --check` — 8/8 files OK
  - `python3 tests/test_engine.py` — 33/33 PASS
  - `python3 tests/test_plugin_net.py` — 11/11 PASS
  - `pytest tests/test_radio.py` — 13/13 PASS
  - Shared libraries between Becker 517 and RT-600 remain 100% byte-identical.


## 2026-09-08 — Planner bounds, database serialization, authenticated export, and radio recovery (L-3, L-4, L-2, F-4)

**Status: implemented.**

The public parallel-track endpoint now rejects `length_nm` or `width_nm` above
50 NM and rejects width/spacing combinations that would generate more than 200
legs, returning a 400 that names the offending input. The aviation-data rebuild
now holds a nonblocking `flock` for its entire run, publishes status atomically
for both gunicorn workers, and logs row and update errors instead of swallowing
them. Import remains nonblocking: the lock winner starts one daemon thread and
the other worker returns immediately.

Planner maintenance and V-SAR export POSTs now require JSON plus either a
same-origin request or the configured instructor token. V-SAR exports cap all
free-text fields and waypoint count and allow five attempts per client per
minute. Scenario creation sends `CAPVSAR_TOKEN_INSTRUCTOR`; message broadcast
sends `CAPVSAR_TOKEN_BASE`, falling back to the instructor token because the
console explicitly permits that role. Either upstream 403 produces a specific
operator-facing token error. Compose passes both existing variables to the
planner container, but their matching values still need to be set on ms01.

The mission radio now reconnects automatically after a socket failure,
heartbeat timeout, or suspended audio context, with exponential backoff capped
at 30 seconds and a three-tone headset alarm. Manual Join/Disconnect remains
available. Mission-base reconnects backfill messages and bearings from SQLite
using `?since=`, with persisted IDs preventing websocket/backfill duplicates;
the history survives a console restart.

Regression evidence was captured against the unfixed code for all four items.
`py_compile`, all 18 planner tests, the four focused F-4 SQLite/backfill tests,
and the radio reconnect contract pass. A real browser/headset reconnect and the
complete console/radio suites were not verified here: this Ubuntu 26.04 host's
Python 3.14 hangs in pre-existing FastAPI TestClient websocket/static requests.
Running the unchanged suites in ms01's Python 3.12 container is pending explicit
permission to copy this private working tree into a temporary directory; no live
service or `/srv/capvsar` checkout was changed.

**Superseded by the entry above (2026-09-08, "Full regression confirmed").**
The reported Python 3.14/TestClient hang did not reproduce; the complete
`test_console.py` + `test_radio.py` suites ran clean without ms01. The real
browser/headset reconnect (`scripts/test_base_radio_browser.py`, Playwright)
still has not been run and needs a live exercise process plus Chrome to do so.

## 2026-09-08 — Airborne radio stack fidelity & instrument runtime fixes (I-9a, I-10, I-9b, I-11, I-1, I-2, I-3)

**Status: complete. Instruments, harness, contracts and test suite updated.**

- **I-9a (Lua execution harness):** Added `tests/am.py`, a ctypes Lua 5.4 stand-in for the Air Manager 4.2 sandbox supporting `si_variable_*`, `xpl_*`, `timer_*`, UI button/dial/switch hit testing, and canvas drawing. Validated via `tests/test_am.py` with 7 tests covering all 4 instruments, shuffled `lib/` load orders, timer progression, and UI state.
- **I-10 (TDFM-136B 60 s TOT timer):** In `instruments/cap-fm-tdfm-136b/logic.lua`, added a 60-second transmit timeout timer that force-unkeys `cap_fm_transmitting`, renders `*** TIME OUT ***` on the active LCD line, and enforces lockout until PTT is released. Proven by `tests/test_tdfm.py`.
- **I-9b (Observer PTT & Squelch LED wiring):** In `cap-fm-tdfm-136b/logic.lua`, created `cap_fm_ptt`, `cap_fm_main_rx`, and `cap_fm_guard_rx` variables, and dual-bound observer PTT to both Air Manager variables and X-Plane's copilot PTT dataref (`sim/cockpit2/radios/actuators/audio_panel_copilot_ptt`). Added `/api/radio/rx` voice activity tracking in `services/exercise/app/radio.py`. Published Part 5 in `docs/DATAREF_CONTRACT.md`.
- **I-11 (Authentic CAP fleet channel plan):** Replaced the 6 placeholder channels in `cap-fm-tdfm-136b/logic.lua` with the 20-channel authentic CAP fleet plan (`TAC 1`, `TAC 2`, `CC 1`, `CC 2`, `AIR 1`, `AIR 2`, `SAR 1`, `GUARD`, `GROUND 1/2`, `BASE DIS`, `LOGISTCS`, `AIR EVAC`, `SAR 2`, `VFIRE 21`, `VTAC 11`, `CALCORD`, `NATL GRD`, `CMD 1/2`) plus user memories up to channel 200. Enabled 3-digit direct keypad entry auto-committing on the 3rd digit, and published `cap_fm_ctcss_tone` and `cap_fm_p25_nac`.
- **I-1 (DF faceplate repaint throttling):** In `instruments/*/lib/cap_df.lua` and DF heads' `logic.lua`, implemented snapshot-based change detection gating redraws so repaints only occur on whole-second timer steps or actual dataref changes, eliminating wasteful ~8 Hz idle repaints.
- **I-2 (canvas_draw error visibility):** Removed swallowing `pcall` around `canvas_draw` in both `becker-sar-df-517/logic.lua` and `rhotheta-rt-600/logic.lua`.
- **I-3 (Becker tone suppression reset):** Reset `st.tone_suppressed = false` in `becker-sar-df-517/logic.lua` whenever frequency is rotated, preventing 3 kHz tone suppression from bleeding across frequencies.

## 2026-09-08 — Radio fidelity audit folded into the tracker; lanes assigned

**Status: tracking only. Eleven new items, no code changed.**

A radio ecosystem audit (Gemini) compared the TDFM-136B, GMA 1347, ground
consoles and DF heads against CAPR 100-1/100-3, ICUT, MART Vol. II and the
vendor manuals. It found real gaps this project's own review had missed
entirely, because the review read the code for defects and the audit read it
against doctrine. Verified against the tree and added as I-10 to I-15, I-17 and
F-10 to F-13 — tracker now 81 items.

The ones that matter most:

- **I-10** the airborne TDFM has no transmitter time-out timer. The ground
  console already enforces a 60 s lease, so the aircraft is currently the only
  station that can jam the net indefinitely — and recognising a TOT cutoff is
  an ICUT practical exam item.
- **F-10** mission base cannot monitor the airband SAR frequency at all. The
  retired `/radio-legacy` had a second station (Icom IC-A120) and the Mumble
  rewrite dropped it, so the MRO can no longer watch the tactical FM net and
  the air-to-ground net at once, which is the actual job.
- **I-11** six generic memories where the real set has 230, so a crew briefed
  to a channel number cannot enter it, and squelch mode is a bare letter with
  no CTCSS tone or P25 NAC behind it — the classic "keyed the repeater without
  the access tone" failure cannot be produced or diagnosed.
- **I-14/I-15** the GMA's ICS isolation and clearance recorder are lamp-only.
  A panel that teaches a control which does nothing is worse than omitting it.

Three corrections to the audit, found by checking it against the tree: its
§3.4 paths carry a `df-` prefix that does not exist; the three P25 sidetone
functions it proposes porting from `radio.js` are not in the tree at all (that
is new work, not a port); and "no acoustic feedback" overstates it — there is
an oscillator, but only the headset-test beep.

### Lanes

Three agents are now working this repository at once and the cluster
`owner_hint` fields in `docs/bugs/tracker.json` have been updated to say who
holds what, since that is where the collision protocol actually looks:

- **Gemini** — `instruments/**` outright, starting with the Lua execution
  harness (I-9a), because nothing in this repository runs any `logic.lua` and
  none of the instrument work is verifiable until it exists.
- **Codex** — `services/flightplanner/**`, `mission-radio.js`, `base.js`,
  `main.py`. F-4 and L-2/L-3/L-4 now, the ground-console block after.
- **Claude** — `xplane/`, deployment and ms01. O-3 then O-2.

A caution recorded for whoever sets the tokens: **do not set `CAPVSAR_TOKEN_*`
on ms01 yet.** L-2's planner-side token forwarding is written but neither
committed nor deployed, and O-2 does not exist, so stations have no way to
receive the plugin key. Setting them now would 403 the planner push and
silence every DF by design. Order: L-2 deploys, O-2 lands, then tokens.

## 2026-09-08 — Tracker sweep, then the base view and debrief (F-2, F-3)

**Status: implemented, tested in a browser, and live on ms01 (`a86e670`).**

### Sweep first: one more wrong finding

Re-verified every open item's file references and absence claims against the
complete tree. All referenced paths resolve. **F-5 was wrong on both halves**
and is now resolved: the setup notes exist as `static/radio-help.html` (linked
from the radio footer and the secure-context overlay — there is no
`radio-art/README.md` because `radio-art/` holds the two faceplate SVGs), and
`services/exercise/radio-public/` exists on ms01 with `mission-base-ca.crt` in
it — `GET /radio-ca.crt` returns a real PEM and `https://ms01:8743/radio`
answers 200. Tablets can reach the secure context today.

That is **six wrong findings** from reviewing the wrong tree (O-2a, O-7a, D-3,
O-4, O-2, F-5). O-3 was sharpened instead: `scripts/deploy.sh` creates only
`mumble/data`, not the other three paths compose needs, so a fresh clone still
crash-loops. Six items re-verified as standing (I-9a/b/c, C15-2, D-1, D-2).

### F-2 — the base view no longer mixes two exercises

`base.js` tracks the sortie id from the state snapshot and clears the map when
it changes: alert circle *and its marker* (which was never held in a variable
at all), beacon marker, aircraft, tracks, bearings, and the `centred` flag.

A second leak the review only half-described: when an aircraft went quiet for
30 s and came back, a **new** polyline replaced `trackLines[callsign]` and
orphaned the old one on the map permanently. It now resumes the existing
track. An expired aircraft's marker is removed but its flown track is kept
deliberately — that is history base staff still need.

### F-3 — the debrief scores each aircraft

Server: `/api/sorties/{id}/track` returns `hdg_true`, which was recorded on
every position and thrown away by the query. Client: `debrief.js` groups by
callsign — one faint full track, one playback polyline and one labelled marker
per aircraft, each in its own colour — and scores each separately. The heading
fallback now scales longitude by `cos(latitude)`, which the old inline
calculation omitted (~10 deg of error at 33N).

### Validation

Both were verified by driving a real browser, because neither has unit-test
coverage and neither could be checked by reading:

- **F-3**: headless Chrome against a seeded three-aircraft sortie (180
  positions) renders three separate scored rows — CAP-1 0.00 nm "overhead the
  beacon", CAP-2 3.34 nm "did not close", CAP-3 1.96 nm "localised" — three
  labelled markers, no JS errors. Previously one meaningless zig-zag.
- **F-2**: a CDP-driven session taken through two sorties. With the fix,
  tracks and bearings reset to 0 and map layers drop 9 → 5. Against pre-F-2
  code the previous sortie's track and bearing **survive into the new one**
  (tracks 1, bearings 1, layers 9 → 7).
- `tests/test_console.py` grows to 30 with a `hdg_true` regression test.
- Whole repo green: console 30, plugin-net 11, radio 12, engine 66, faceplate,
  panel 7, planner 8.

Incidentally confirmed the `/ws` origin check shipped this morning behaves
correctly against a live server: same-origin upgrades (101), cross-origin is
refused (403), and a client sending no Origin — the plugin, curl — is still
allowed.

### Deployed

Live on ms01 as `a86e670`. Verified against the running service: `/track`
returns `hdg_true`, the served `base.js` carries the sortie-id reset and
`debrief.js` the per-callsign grouping, truth is still withheld, and the
console suite passed **30/30 inside the built image** against the pinned
fastapi 0.115.6 / pydantic 2.10.4.

A permission rule for `ssh`/`rsync`/`scp` now lives in
`.claude/settings.local.json` (gitignored, project-scoped), so the sync,
build, commit and container swap ran end-to-end rather than being handed over
as commands to paste.

## 2026-09-08 — Deployment live on ms01; wave 1 and wave 2 items running

**Status: implemented. Committed on ms01 (`9dcafb5`) and containers running live.**

### The local working tree is a subset of the repo

The important finding of the day, and it invalidates five items in the review.
`/home/ron/Projects/cap-vsar` — the tree all three agents have been editing —
is **missing files the canonical repo on ms01 has**. A `--delete` rsync dry run
is what caught it; running that sync would have destroyed them. Corrected:

- **O-2a → resolved.** `docs/CONNECT.md` exists and is a complete participant
  guide (Mumble client per platform, server, nets, PTT). Not missing.
- **O-7a → resolved.** `docs/AM4_COMPAT.md` exists and records the licence
  position, including the Air Manager vs Air Player distinction for
  display-only crew stations. The CHANGELOG citation resolved all along.
- **D-3 → resolved.** `CONOPS-cap-vsar.md`, `AM4_COMPAT.md` and
  `infra/ROUTER.md` all exist in the repo. The vault notes are published into
  it by `docs/ragd/ragd_ingest.py`, so agents can read them.
- **O-4 → narrowed.** `docs/MUMBLE_CHANNELS.md` documents the whole channel
  tree, the rationale, and the one manual step left (the Instructor/SET ACL).
  Neither undocumented nor a first-join failure. What stands: the rows exist
  only in a gitignored volume, nothing recreates them, and `radio.py` keeps its
  own hardcoded copy of four names.
- **O-2 → narrowed.** Onboarding is not absent: `scripts/wg-peer.sh` prints a
  participant's WireGuard peer config and QR, `scripts/deploy.sh` is an
  idempotent stack deploy. What stands: the plugin still hardcodes CONSOLE and
  CALLSIGN, the deploy scripts are Linux-only, and there is no single station
  kit.

All the missing files have been pulled into the local tree. **Agents working
in `/home/ron/Projects/cap-vsar` should treat `/srv/capvsar` on ms01 as
canonical** until O-1 makes the local tree a real checkout — this is the same
root cause as O-1, wearing a different hat, and it has now produced five wrong
findings in one review.

### Deployment: live on ms01

1. Synced work to `/srv/capvsar` — checksum-based, no `--delete`, preserving
   canonical repository files.
2. Built `exercise` and `flightplanner` images.
3. **Ran the console suite inside the built image: 29/29 against the pinned
   fastapi 0.115.6 / pydantic 2.10.4.** This closes the version-gap caveat
   carried on every entry today.
4. **Committed and running:** Committed on ms01 (`9dcafb5` *Fix beacon-truth leak,
   role tokens, engine defects and console robustness*) and deployed via
   `docker compose up -d exercise flightplanner`. Both containers are healthy
   and running the updated builds.

### P-4 sanity check: no practical effect on existing scenarios

Ran the old and new horizon formulas against the three scenarios on the live
console. Both flight-planner scenarios have `beacon_elev_ft` 0.0, so the
result is **identical** (which incidentally confirms L-9: the planner pushes
beacons at sea level). The seed scenario's beacon at 700 ft gains 1.3–1.7x
range, but the horizon there was already 59–167 nm against a 12 nm search
radius, so it was never the limiting effect. The earlier caution that scenarios
might "feel too easy" was overstated: terrain masking and signal strength do
the work in these, and P-4 only bites when a beacon sits materially above the
aircraft — which none of these do.

## 2026-09-08 — DF engine: scan holds, horizon has two ends, plugin reloads (P-3, P-4, P-5)

**Status: implemented.** Cluster C3's wave-2 items. All three are things a crew
would experience as "the equipment is broken" without any error appearing
anywhere.

**P-3 — scan mode no longer destroys TIMEHOLD on 406.** The 517's normal 406
posture is scan on: surveil the burst, listen to the continuous channels in the
50 s gap (§3.3.3). But the untuned check treated *any* frequency mismatch as
loss of signal and called `silent()`, which clears the held bearing — so with
scan enabled the bearing vanished the instant each 440 ms burst ended, which is
the exact opposite of what TIMEHOLD exists for. The path now distinguishes scan
stepping from being parked on the wrong channel: stepping gets
`silent(keep_hold=True)` followed by `hold_or_drop()`, the same treatment the
between-bursts gap already received. Tuning away by hand still drops the
bearing, and audio (`rx_open`) correctly stays closed while the bearing is
merely held. Added `tuned_hz()` so "what the crew selected" and "what the
receiver is on this instant" stop being duplicated logic.

**P-4 — the radio horizon has two ends.** Now
`1.23*(sqrt(h_ac) + sqrt(h_bcn))` in feet MSL. The old form used the aircraft's
height *above the beacon*, which collapsed to a zero-mile horizon the moment
the beacon sat higher — an aircraft in a valley 500 ft below a ridge-top beacon
one mile away was ruled out of range and heard nothing. This is why it went
unnoticed: for a beacon at sea level the two forms are identical, and the seed
scenario's beacon is at 700 ft. Fixed identically in the server's
`propagation.py` fallback so the instructor's view cannot disagree with the
sim. Terrain between the two remains a separate question, answered by the
line-of-sight probe.

**P-5 — reloading the plugin brings the console link back.** `XPluginDisable`
set `self.stop` and nothing ever cleared it, so the thread `XPluginEnable`
started exited on its first check: datarefs kept publishing stale state with no
link to the console and nothing said so. `XPluginEnable` now creates a fresh
`Event`, and `XPluginDisable` joins with a 1 s bound — bounded deliberately,
because the worker may be inside a 4 s `urlopen` and X-Plane must not block on
it; the thread is a daemon and the event is set, so it exits regardless.

### Validation

Engine suite grows to 66 checks, plugin-net to 11. Verified against the
pre-fix code: `bearing is held while scan is stepped away` fails with
`valid=0`, `aircraft below a ridge-top beacon at 1 NM still hears it` fails
with `signal 0.000`, and `test_enable_after_disable_leaves_a_live_worker`
fails. The P-3 tests also pin the two things that must NOT change — the
bearing is still dropped once TIMEHOLD expires, and tuning away by hand still
drops it immediately.

Whole repo green: console 29, plugin-net 11, radio 12, engine 66, faceplate,
panel 7, planner 8.

### Still open in this cluster

P-6 (121.5 producing a COSPAS-SARSAT decode), P-7 (signal bar lit between
bursts), P-8 (terrain masking only −12 dB), P-9 (fixed 24 probes, no curvature),
P-12 (report cadence, heading source) and P-13 (no dB calibration, scripted
multipath) are wave 3 and 4 and untouched.

## 2026-09-08 — The console survives an exercise (X-3, X-4, X-5, X-7)

**Status: implemented.** Cluster C7's wave-2 half. Each of these fails during
a running exercise rather than at deploy time, which is why they are grouped.

**X-3 — database work off the audio loop.** `db()` is now a context manager
that commits, rolls back *and closes*: `with sqlite3.connect(...)` commits but
never closes, so the console leaked a connection per request. Connections open
with a 5 s timeout and the database runs in WAL with `synchronous=NORMAL`.
Every write in an `async` handler goes through `db_call()` →
`run_in_threadpool`. This matters because `radio.py` shares this event loop:
a commit fsyncing on a bind mount stalls the Mumble bridge, trips its buffer
check and unkeys the operator mid-transmission. The sync handlers were already
threadpooled by FastAPI; only startup seeding still touches the database on the
loop, before any traffic exists.

**X-4 — a restart resumes the sortie.** Live state was in-process only, so a
container restart mid-exercise orphaned everything: positions discarded,
`/api/messages` empty, and the row left `stopped=NULL` forever. `rehydrate()`
in the lifespan hook reloads the newest sortie with `stopped IS NULL`, its
scenario, and the last 100 messages. Aircraft are deliberately *not* restored —
their positions are seconds stale and the plugins re-report within seconds; a
stale aircraft on the map is worse than a briefly empty one.

**X-5 — one wedged console no longer stalls the rest.** Sends now run
concurrently with a 1 s per-client timeout, and anyone who times out or raises
is dropped. A half-open TCP socket never raises, which is why a timeout rather
than an exception is what has to notice it. Measured against the old code, a
single suspended tablet blocked the broadcast for the full 30 s of the test's
wedged client.

**X-7 — sortie lifecycle.** Starting a sortie now closes any still-open one;
previously they kept `stopped=NULL` forever, so the debrief list showed two
running exercises and `rehydrate()` would have resumed the wrong one. Bearings
and messages no longer attach to a stopped sortie. And a bearing whose aircraft
has already expired from the live map now falls back to that aircraft's last
recorded position for the sortie rather than returning 404 — a bearing passed
over voice is routinely typed in more than 30 s later, and refusing it loses a
report the crew actually made.

Two deliberate deviations from the fix the tracker proposed for X-7:
`hub.sortie` is **not** cleared on stop, because reveal happens at debrief
*after* stop and needs it; and `POST /api/exercise/reset` was not added,
because nothing needs it yet.

### Validation

`tests/test_console.py` grows to 29 checks with a `SurvivesAnExercise` class.
Verified against the pre-C7 behaviour: **6 of its 8 fail**, including the
wedged-broadcast case taking 30.03 s. The two that pass are guards that should
pass either way (an unknown callsign is still refused; nothing resumes when
nothing was running). The restart tests deliberately drive the real
`TestClient` lifespan rather than calling `rehydrate()` directly, so unwiring
it from startup fails them.

Whole repo green: console 29, plugin-net 9, radio 12, engine ALL PASS,
faceplate ALL PASS, panel 7, planner 8.

### Still open in this cluster

X-6 (untyped bodies mutating scenario definitions) and the rest of X-8 —
positions retention, `/track` pagination, real logging, a DB-touching
healthcheck, cancelling the ticker on shutdown, non-root container — are wave
3 and untouched. X-8's tracker entry now records which parts this closed.

## 2026-09-08 — Review of the L-1 FMS fix: accepted, two follow-ups raised

**Status: review only, no code changed. L-1 stands as implemented.**

Independent check of the L-1 fix rather than a re-read of its entry.

**Verified.** Every enroute record now carries six fields; generated points are
type 28 with `DRCT` and a coordinate-derived identifier; `CYCLE` comes from the
UTC date (`2609`); `NUMENR` matches the records actually emitted; LF endings.
The airport records were already correct and were left alone. Generated a real
KSEE-KCRQ sample with three pattern points and audited every line's field count
by hand, rather than trusting the string assertions. The replacement test is a
genuine improvement on the one it replaced: it checks field count, record type,
the `DRCT` column and `NUMENR` structurally, so a future column shift fails
even if the substring happens to match. Eight planner tests pass.

**Scope was respected.** L-3, L-5 and L-7 sit untouched in the same file, and
nothing outside `services/flightplanner/` was modified while two other agents
were working — confirmed by diffing the plugin and `main.py` against my copies.

**The honesty was right.** The entry states plainly that the published grammar
does not prescribe the identifier text for an unnamed lat/lon point, and that
in-simulator acceptance is unverified. Both are true and both matter.

**Two follow-ups raised, neither a defect in the fix:**

- **L-1a — the pattern label no longer reaches the cockpit.** The generators
  name points `DATUM`, `SS01`..`SSnn`, `CS01`, `PS01`, and the AOBD briefs
  those names; the writer now derives the identifier from coordinates, so the
  G1000 shows `+33.187_-117.079` on every leg. The aircraft flies the right
  positions, but the brief says "turn at SS04" and nothing in the cockpit says
  SS04. Whether this is fixable depends on the open question the entry
  identified: if X-Plane accepts an arbitrary identifier on a type 28 record
  and treats the columns as authoritative, the label can be kept.
- **L-11 — an unresolved airport silently becomes a waypoint.** Pre-existing,
  surfaced by generating the sample. With the aviation database empty, `KSEE`
  was emitted at 33.170,-117.079 — the first search waypoint — with elevation
  0.0 and no warning. A crew loading that plan departs from the wrong place.

Also noted, not tracked: the identifier is rounded to three decimals (~110 m)
while the coordinate columns carry six. Harmless if X-Plane reads the columns,
a per-waypoint offset if it reads the label — the same in-sim check settles
both this and L-1a.

## 2026-09-08 — Plugin now receives beacon truth (P-2 complete)

**Status: implemented. Both halves of P-2 are now in; the remaining step is
deployment, not code.**

Closes the half deferred this morning while another agent held the plugin.
`net_worker()` polled `/api/state` — the endpoint that deliberately withholds
the beacon until reveal — so it set `active=1` with the beacon at 0,0. Null
Island is past any radio horizon, so the authoritative in-sim DF engine
produced nothing for an entire exercise unless the instructor revealed at the
start, which defeats the exercise.

- `fetch_scenario()` polls `GET /api/plugin/scenario` with the plugin key
  (`PLUGIN_KEY`, from `CAPVSAR_TOKEN_PLUGIN`). `CONSOLE` and `CALLSIGN` are
  deliberately left hardcoded — moving all three into a per-station config is
  O-2's job and inventing a second mechanism here would collide with it.
- `/api/positions` carries the same key, since the console now gates ingest on
  the plugin role. Without this, position reporting would have broken the
  moment tokens were set on ms01.
- A refused channel clears `active`, so the DF goes **silent** rather than
  homing on a stale or null beacon: a DF that confidently points at nothing
  teaches the crew something false. Each refusal is logged once per
  transition, with the cause distinguished — 503 (console has no key set),
  403 (this station's key rejected), 404 (console predates the endpoint, so
  update it) — because "why can't they hear it" is answered here, and the old
  code swallowed every network error identically.

### Validation

`tests/test_plugin_net.py`, 9 checks, the first tests to touch the network
thread at all: endpoint choice, key header, each refusal path, that a refusal
is logged once rather than every three seconds, and that recovery is logged.
Confirmed they catch the defect — against the pre-P-2 plugin they fail on
`no object exposes fetch_scenario()`.

`tests/test_console.py` gained a contract test asserting the payload carries
every field the plugin reads (`beacon_lat/lon/elev_ft`, `band`, `power`,
`effects`, `sortie.stopped`). That seam is precisely what broke: a future
refactor of `snapshot()` that drops a field would otherwise degrade the DF
quietly in the sim instead of failing a test.

Whole repo green: console 21, plugin-net 9, engine ALL PASS (58), faceplate
ALL PASS, panel 7, radio 12.

### Not verified

Nothing here has run against a real X-Plane or the live console. The in-sim
confirmation is: start a sortie, do **not** reveal, and check a bearing
appears on the DF head while `/base` still shows no beacon. That needs
`CAPVSAR_TOKEN_PLUGIN` set identically on ms01 and on the station — until it
is set on both, the console returns 503 and the DF is silent by design.

## 2026-09-08 — L-1 X-Plane FMS export record corrected

**Status: implemented.**

The flight planner emitted generated search-pattern points as five-field type
11 records. That both omitted the required via/special field and claimed that
labels such as `SS01` were named fixes in X-Plane's navigation database. It also
hardcoded `CYCLE 2401`.

`generate_xplane_fms_content()` now emits generated points as six-field type 28
records with a coordinate-derived identifier, `DRCT`, six-decimal altitude and
the existing six-decimal latitude/longitude. The cycle is derived from the
current UTC date as four-digit `YYMM`. `NUMENR` remains the total emitted record
count, including departure and destination. The test now checks the corrected
records and cycle, plus structurally verifies every generated waypoint's field
count, type, `DRCT` column and altitude and verifies `NUMENR` against the records.

Verification passed: `py_compile`, all eight flight-planner unit tests, tracker
rendering, and manual inspection of a generated KSEE–KCRQ sample with two pattern
points. Laminar's published v11 `.fms` grammar confirms type 28 and the six
columns but does not prescribe the identifier text or precision for an unnamed
lat/lon point; the tracker-requested signed latitude/longitude identifier rounded
to three decimals was used. The result has not been loaded into X-Plane 12, so
conformance to the published grammar is verified but in-simulator acceptance
remains a maintainer step.

## 2026-09-08 — Mission base works without internet (F-1)

**Status: implemented.**

Leaflet 1.9.4 is vendored to `services/exercise/app/static/vendor/leaflet/`
(js, css, and the five dist images `leaflet.css` references — 192 KB total),
and the instructor, mission base and debrief views load it from there instead
of unpkg.

This was worse than a missing map. `base.js` touches `L` on its first line, so
with no internet the script threw before opening its WebSocket and the whole
view went blank — no status board, no aircraft, no bearing log. A mission base
frequently has no connectivity, which is exactly when the console matters.

Three checks in `tests/test_console.py::OfflineAssets`: no view references a
remote script or stylesheet, the vendored files are served at the paths the
pages actually request, and `leaflet.css`'s `images/` resolve (a wrong vendor
path would have reproduced the original blank page silently). Verified they
catch it: pointing the views back at unpkg fails the first check, restoring
passes 20/20.

Map *tiles* are still remote, so an offline base gets a blank basemap with
working aircraft, bearings and controls over it. Pre-caching tiles into the
existing `charts` volume is tracked separately. The flight planner has the same
CDN and tile problem in its own files and is untouched here — that is L-8.

## 2026-09-08 — Truth containment and role tokens on the exercise console (X-1, X-2, P-2 server half)

**Status: implemented for X-1. X-2 and P-2 are partly done — each has one
remaining step named below; do not read them as closed.**

Cluster C2 of the remediation plan. The console's teaching mechanism is that
nobody on the exercise net can look up the beacon; three endpoints were handing
it over on request, and nothing authenticated any caller.

**X-1 — truth containment (fixed).** All beacon filtering now goes through one
`public_scenario()` serializer in `main.py`, so there is a single place to
audit instead of a decision per endpoint:

- `/api/scenarios` returns beacon fields only for a presented instructor token.
- `/api/sorties/{id}/track` returns `beacon` only once that sortie is revealed,
  and now also returns `revealed`, which makes the debrief view's
  "beacon truth was never revealed" branch reachable for the first time.
- `beacon_elev_ft` is stripped alongside lat/lon. The previous filter popped
  only lat/lon, so elevation leaked from `/api/state` and `/ws` on every tick.

**X-2 — role tokens (mechanism in, deployment step remaining).** New
`services/exercise/app/access.py`: three roles (instructor, base, plugin), one
shared secret each, presented as `X-CAPVSAR-Token` or `?token=`. An instructor
token also satisfies the base role. Every mutating route is gated; `/ws` now
does the same-origin check the radio stream already did. The instructor and
base consoles send the token through a `vsarFetch()` helper in `charts.js`,
prompting once per browser and retrying a rejected token.

Two deliberately different defaults, because the failure modes are not
symmetrical: **secrecy fails closed** (truth needs a *configured* instructor
token, so a half-configured console withholds rather than leaks) while
**availability fails open** (a role with no token set is unenforced, so
deploying this could not lock operators out of the running ms01 stack before
its `.env` exists). Every open role is named in a startup warning.
**Remaining: set `CAPVSAR_TOKEN_INSTRUCTOR` / `_BASE` / `_PLUGIN` in `.env` on
ms01 and restart.** Until then the endpoints are still open; the variables are
wired through `docker-compose.yml` ready for it.

**P-2 — plugin truth channel (server half).** New `GET /api/plugin/scenario`
serves the running sortie *with* truth, gated on `CAPVSAR_TOKEN_PLUGIN` and
returning 503 when no key is configured, so it cannot be open by accident. Its
response shape matches `/api/state` deliberately, so the plugin change is a URL
swap plus one header. **Remaining: `PI_capvsar_df.py:947-967` must poll it** —
deferred because another agent held the plugin file for P-1.

### Validation

New `tests/test_console.py` — 17 checks, and the first automated tests
`main.py` has ever had. The leak test walks every scenario/sortie response
recursively for any number within ~100 m of the beacon, so a future endpoint
that forgets the serializer fails it; `leak_endpoints()` is the list to extend
when adding routes. Verified the tests actually catch the defect rather than
just passing: reverted to the pre-fix behaviour and **9 of 17 failed**
(`/api/state` and `/api/scenarios` leaking, `/track` returning a beacon on an
unrevealed sortie, `beacon_elev_ft` present, and every role gate answering 200
instead of 403); restored, 17/17 pass. `tests/test_radio.py` still passes 12/12,
so the Mumble bridge is unaffected.

Tested against fastapi 0.141.1 / pydantic 2.13.5 in a scratch venv, not the
container's pinned fastapi 0.115.6 / pydantic 2.10.4 — this machine has no
docker and no pip for the system Python. Nothing in the change depends on
version-specific behaviour, but the suite has not run against the pinned set.

### Notes for whoever picks this up

- `docs/bugs/tracker.json` is now formatted with a uniform `json.dumps(indent=2)`,
  which puts every `"status"` on its own line and makes concurrent targeted
  edits safer. Statuses set by other agents were preserved.
- The scenarios table has no `beacon_freq_hz` or `cs` column, but the plugin
  reads both from the scenario it polls, so they are always absent and it
  silently uses defaults. Contract drift, tracked under P-10; not fixed here.
- Running the console tests surfaced `ResourceWarning: unclosed database` from
  `with db() as c`, which commits but never closes. That is X-8, left alone.

## 2026-09-08 — Fix terrain line-of-sight ray mirroring (P-1)

**Status: implemented**

- **Item ID:** `P-1` (Priority P0, Cluster C3).
- **What was wrong:** In `xplane/PI_capvsar_df.py`, `line_of_sight_blocked()` walked `fr` from 0 (aircraft) to 1 (beacon), but computed `ray = b_ft + (ac_ft - b_ft) * fr`. This mirrored the line-of-sight ray vertically, assigning the beacon altitude to the aircraft position and aircraft altitude to the beacon position. Consequently, terrain ridges near the beacon were compared against high aircraft altitudes and failed to mask the signal, while ridges near the aircraft were compared against low beacon altitudes and falsely blocked reception.
- **What was changed:**
  - In `xplane/PI_capvsar_df.py` line 599, corrected the ray interpolation to `ray = ac_ft + (b_ft - ac_ft) * fr`.
  - In `tests/xp.py`, extended the test stub by adding `TERRAIN_FN` callable support (`(lat, lon) -> elevation in feet`) and threaded coordinates through `worldToLocal`, `probeTerrainXYZ`, and `localToWorld` while preserving the fallback to constant `TERRAIN_FT`.
  - In `tests/test_engine.py`, added regression tests with an aircraft at 6000 ft MSL, a beacon at 1000 ft MSL, and a 5000 ft ridge band tested near the beacon (80–95% along path; blocks) and near the aircraft (5–20% along path; clears).
- **What was verified:**
  - Verified regression tests fail with the buggy expression (`blocked=0` near beacon, `blocked=1` near aircraft) and pass when fixed (`blocked=1` near beacon, `blocked=0` near aircraft).
  - All 57 checks in `tests/test_engine.py` pass cleanly.
  - Full test suites `test_faceplate.py` and `test_panel.py` pass with zero regressions.
  - Python byte-compilation succeeds via `py_compile`.
  - Updated `docs/bugs/tracker.json` (marked `P-1` as fixed) and regenerated `docs/BUG_TRACKER.md`.

## 2026-09-08 — Bug tracker and remediation plan

**Status: tracking artefacts only; no defect is fixed yet.**

Turned the 2026-09-08 review into a worked tracker. `docs/bugs/tracker.json`
is the tracker of record (IDs are the review's finding IDs, so the review,
the handbook and this log all still resolve); `scripts/render_bug_tracker.py`
renders `docs/BUG_TRACKER.md` from it, so the two cannot drift. Edit the JSON,
run the script.

68 items: 8 critical / 21 high / 29 medium / 10 low, or by fix-order 10 P0,
21 P1, 28 P2, 9 P3. Compound findings were split where the parts would be
worked separately (X-8, I-9, O-7); nothing was dropped.

A filterable triage board renders the same JSON at
`https://claude.ai/code/artifact/b37f0b6f-caaf-469a-9862-a103f7025db9`
(grouped by wave, with the critical path). It is a **read view for humans and
is account-private** — Codex and Gemini cannot open it. Agents work from
`docs/BUG_TRACKER.md` and `docs/bugs/tracker.json`; ticks on the board are
browser-local and its *Copy status JSON* button exists to paste status back
into the JSON, which stays the only record.

### Reconciled against the vault as-built

Checked the tracker against `Projects/as-built/AsBuilt_CAPVSAR.md`
(vault, deployed 2026-09-06) rather than trusting the repo alone, and
corrected three items:

- **O-4 was wrong.** The Mumble channel tree does exist on ms01 — `CAP V-SAR`
  with Briefing Room, Mission Base, Mission Net PRIMARY and ALTERNATE,
  Aircraft with CAP-1..3 Intercom, and Instructor - SET — created by hand in
  `mumble-server.sqlite` on 2026-09-06, so joins work today. The real defect
  is reproducibility: those rows live only in a gitignored runtime volume,
  nothing in the repo recreates them, and `radio.py`'s four hardcoded names
  must be kept in step manually. Rebuild or lose the volume and the voice net
  is gone with no scripted recovery. Downgraded P0 to P1, moved to wave 2.
- **D-3 was wrong.** `CONOPS-cap-vsar.md` is not missing; it is in the vault
  at `Projects/architecture/CONOPS-cap-vsar.md`. It is simply outside the
  repo, so the agents this log points at it cannot read it. The fix is to
  copy it into `docs/CONOPS.md`, not to write it. `AM4_COMPAT.md` and
  `infra/ROUTER.md` still resolve nowhere.
- **New O-2a.** The as-built tells participants their instructions are at
  `docs/CONNECT.md`; that file does not exist, so the one pointer a new
  member is given leads nowhere.

The as-built itself needs three updates that cannot be made from this
machine (the vault is not mounted here and ragd is search-only): the
container table is missing `capvsar-flightplanner` (8090) and
`capvsar-radio-https` (8743); the console view list predates `/radio` being a
real Mumble voice bridge with `/radio-legacy` holding the old text console;
and the channel tree needs the reproducibility caveat above. A paste-ready
block covering all three, plus a new Quality tracking section pointing at the
tracker, was handed to the maintainer.

Two groupings, because they answer different questions:

- **15 clusters** are PR-sized units that share files, with an owner hint per
  cluster. Two orderings are load-bearing: C2 (truth and roles) must land
  before C7 (console robustness) since both rewrite `main.py`, and C10 before
  C11 in the planner. The plugin and docs clusters are safe fully parallel.
- **5 waves** are scheduling, anchored to the rehearsal calendar in
  `docs/USE_CASE_SAREX_REHEARSAL.md`: wave 0 version control, wave 1 what
  session 1 needs, wave 2 what a three-aircraft full mission needs, wave 3
  dress rehearsal and live day, wave 4 architecture and CalTopo phase 2.
  Where severity and wave disagree the wave wins — O-5 is high severity but
  nothing before the dress rehearsal needs it, while L-1 is a step lower and
  is wave 1 because the AOBD exports `.fms` in session 1.

`docs/REMEDIATION_PLAN.md` carries the critical path (X-1, P-2 and X-2 are one
piece of work and one PR — doing them apart means writing the truth serializer
twice), a per-wave exit test, the multi-agent working rules, and the three
checks that should become permanent regression tests: the truth-leak test, a
non-flat terrain stub, and a preflight smoke script. Waves 0 to 2 — the point
at which a three-aircraft rehearsal is genuinely possible — are about nine to
ten focused days.

Status corrections from the entry below: O-1 is **in progress, not closed** —
the v0.1 baseline is pushed, but this working tree still has no `.git/` and
`git` is not installed on this machine, so agents editing here still cannot
diff or revert. O-1a is **resolved by decision** (the generated handbook is
tracked deliberately as the published artefact).

## 2026-09-08 — Project baseline v0.1 placed under version control

**Status: implemented.**

- Added project-wide `VERSION` value `0.1`; the corresponding immutable Git tag
  is `v0.1`. Air Manager's required integer instrument revision fields remain
  independent and retain their tested values.
- Expanded the repository baseline to include the four Air Manager instruments,
  Mission Observer panel, X-Plane plugin source, C182T build/deployment tooling,
  exercise and flight-planner services, web documentation, tests, reference
  manuals, generated handbook PDF/HTML, artwork sources and redistributable
  instrument assets.
- Added root ignore rules for credentials, local agent configuration, runtime
  databases, Mumble state, locally generated TLS trust material, caches, build
  output, deployment backups and rebuildable archives. Fixed the flight planner's
  malformed ignore entry and retained its Docker source files.
- The canonical `main` branch and `v0.1` tag are mirrored to the internal Gitea
  repository and GitHub. Production runtime state is deliberately outside Git.

## 2026-09-08 — SAREX rehearsal use case: docs, handbook chapter, blog post

**Status: documentation only; no code changed.**

Described the intended training progression — a SAREX (Search and Rescue
Exercise) whose air missions are flown three times on the simulator (T-14
base stand-up, T-7 full mission with injected effects, T-2 dress rehearsal)
before the live day, so the live exercise reinforces skills rather than
introducing them. The scripted incident is an overdue C182 KCRQ→KTRM with a
406 MHz composite east of Julian; three sorties (creeping-line route search,
ELT homing + expanding square, parallel-track grid) map to the Flight
Planner's three pattern generators.

- `docs/USE_CASE_SAREX_REHEARSAL.md` — the full narrative, the measures the
  debrief provides the SET, and the four review items (O-2, X-1/P-2, L-1,
  phase-2 retasking/CalTopo) that stand between the narrative and running it
  with three aircraft today.
- `scripts/generate_manual.py` — new Handbook chapter 7 "Training
  Progression: Rehearsing a SAREX Before Flying It" (incident table, session
  table, measures table); the QRC chapter renumbered to 8; revision bumped
  to 1.3. `docs/manual/*` regenerated.
- `docs/blog/BLOG-virtual-sarex-rehearsal.md` — CyberFlight blog draft in the
  vault's `BLOG-*.md` template, with three figures under
  `docs/blog/assets/virtual-sarex-rehearsal/` (downscaled from
  `website/images/`). Not yet added to the vault's `Projects/blog/BLOG.md`
  index or pushed to Gitea.

## 2026-09-08 — Whole-project review and CalTopo phase-2 plan

**Status: review and proposal only. No code was changed; nothing below is
fixed yet.** Full findings with file:line references are in
`docs/PROJECT_REVIEW_2026-09-08.md`; the CalTopo plan is in
`docs/CALTOPO_PHASE2_PLAN.md`. Finding IDs (P-, X-, F-, L-, I-, O-, D-) are
defined there.

Seven parallel reviews (plugin/engine, console backend, console frontend,
flight planner, Air Manager Lua, infra/ops against Plan v0.8 §4, and CalTopo
research) were cross-checked against the tree; the three most consequential
findings were re-verified by hand.

Critical (pre-exercise minimum): the repo is not under version control
(`.git/` is empty, no `git`, no `.gitignore`, ~45 MB of regenerable
artifacts in-tree); beacon truth leaks through `GET /api/scenarios`,
`GET /api/sorties/{id}/track` and `beacon_elev_ft` in the `/ws` snapshot;
the plugin can never receive beacon truth from `/api/state` (same
withholding) so the in-sim DF is silent unless revealed at start; the terrain
line-of-sight ray in `PI_capvsar_df.py:595-599` is mirrored (aircraft and
beacon altitudes swapped along the path); no authentication or roles on any
console endpoint; Leaflet is loaded from unpkg with no local copy so `/base`
is blank on a LAN without internet; the plugin hardcodes console IP and
callsign so multi-aircraft is not deployable; the `.fms` export is malformed
for X-Plane 11/12 and the test asserts the wrong format; the compose file
bind-mounts a flight-planner DB *file* that does not exist in the repo, so a
fresh ms01 deploy crash-loops.

Corrections to this log: the pymumble browser voice bridge is **implemented**
(see the entry immediately below) — the "Design proposal: Mission Base WebUI
virtual radio" entry and the containerization entry's "Proposed only" are
superseded. The "MRO Base Radio Web Application (`/radio`)" entry (APX 6500 +
IC-A120) now describes `/radio-legacy`; README and `website/*.html` still
advertise it as `/radio`. The Becker/RT-600 `pcall(canvas_draw)` entry's
claim that the current code still produces the reentrancy error is not
supported by `~/Air Manager/log.txt`. The engine suite has 50 checks, not 55.
`/api/messages` no longer returns 400 without a sortie. No
`CONOPS-cap-vsar.md` or `AM4_COMPAT.md` exists on disk; Plan v0.8 §4 is the
effective CONOPS.

CalTopo: an official, supported Team API exists (HMAC-signed service
accounts) plus a documented custom HTTP position-report endpoint with
`aircraft:*` fields — the sanctioned way to feed simulated aircraft into live
tracking; APRS-IS must not be used. `caltopo-python` 2.0.0 wraps map objects,
assignments and `since` polling and targets CalTopo Desktop for offline
bases. Proposed in four phases (GeoJSON export/import first, then live
tracking + map automation via a `tracking` router, then bidirectional +
offline, then role UX), gated on the truth-filter and station-identity fixes.

## 2026-09-08 — Mission base web headset radio implemented and installed

**Status: installed on ms-01; browser audio and deployment checks passed.
Physical Bluetooth headset and iPad/Android acceptance checks remain.**

The new `/radio` page replaces the former typed-message-only radio entry point
with live voice through the existing Mumble mission server. It supports tablet
press-and-hold PTT and desktop spacebar PTT, headset microphone selection,
browser/system output routing, a local sound test and receive volume. Browser
stations and native Mumble crews communicate on the same selected mission net.
The previous APX6500/Icom text console, sidetones and Form 110 remain at
`/radio-legacy`.

- Created APX 4500 O2 and EFJohnson 5300 instrument faces, with reference-informed
  hardware layouts, matte SVG artwork and smooth live display text. Both skins
  operate one station. Active faceplate controls select nets, home, power/join
  and volume; scan/squelch/monitor/emergency functions are not simulated.
- Corrected the radio-selection basis: CAP training references document the
  APX 4500 as a base/mobile radio and the EFJohnson 5300 family. No nationwide
  inventory ranking was found to substantiate a literal “most common two” claim.
  Sources, saved ICUT PDF, model scope and setup instructions are under
  `docs/mission-base-radio/`.
- Added the FastAPI `/api/radio/stream` bridge, with one native Mumble client per
  browser, 48 kHz mono PCM over WebSocket and Opus on the Mumble side. Mumble
  credentials stay server-side. Supports an optional shared exercise access code,
  same-origin checks and a default limit of 16 browser sessions.
- Added independent server/client PTT gating, 1.5-second transmit lease,
  60-second limit, release on blur/hidden page/pointer cancellation/retune/loss,
  stale-ack rejection, bounded queues and selected-channel audio filtering.
  Server-initiated moves or mutes stop the next transmitted frame. Retunes wait
  for the native server acknowledgment. Disconnect cleanup releases session
  slots; native receive queues are drained to avoid accumulating exercise audio.
- Added Caddy HTTPS on LAN port 8743 with a persistent local CA and public
  certificate download at `/radio-ca.crt`. Set `default_sni 192.0.2.151` so
  IP-address TLS clients work through Docker even when they omit SNI. Devices
  need one-time certificate trust; the private CA key stays in Caddy's volume.
- Added the Python 3.12-compatible pinned pymumble commit and native `libopus0`
  to the exercise image. Updated Compose and rebuilt/restarted only the exercise
  service and new HTTPS proxy. Mumble and flight planner continued running.
  Original deployment files are backed up on ms-01 at
  `/srv/capvsar/backups/mission-radio-20260908/`.

Validation: **12 backend tests passed** in `tests/test_radio.py`. Two Chromium
stations on a separate, disposable Mumble server passed actual browser capture
→ Opus → browser audio playback, spacebar release, focus exclusions, blur,
different-net silence, pointer cancellation and tablet/phone layout checks.
The reproducible browser harness is `scripts/test_base_radio_browser.py`; PNG
instrument and page previews are in `output/mission-base-radio/`.

Deployment verification: all eight requested HTTPS pages/assets returned 200
with full certificate-chain and IP-identity validation against the exact public
CA. A Chromium session joined PRIMARY, changed to MISSION BASE, and disconnected
on the installed server without transmitting or reporting JavaScript errors.
The browser check used a temporary certificate-error allowance; certificate
trust was verified separately without changing the workstation's trust store.
No synthetic test audio was sent to live mission channels.

Open `https://192.0.2.151:8743/radio`. First-device instructions and certificate
download are available over existing HTTP at
`http://192.0.2.151:8700/static/radio-help.html`. Local CA SHA-256 fingerprint:
`AE:D7:ED:5D:10:5B:BD:27:D6:00:BF:8F:52:AD:AE:44:66:20:60:78:B2:9A:2B:81:B4:62:6E:40:B9:AC:5C:2A`.
This is an exercise voice station; it does not bridge physical VHF radios or
ATC, implement dual-watch/guard, or automatically transcribe a communications log.

## 2026-09-08 — Blue prop lever added to the C182T NAV III 3D cockpit

**Status: implemented; the built package rebuilds cleanly from source, but
actual placement/appearance has not been visually confirmed in a running
X-Plane session (no rendering/screenshot capability available this session).**

The base Laminar C172SP has a fixed-pitch prop and no prop lever in its 3D
cockpit model. `scripts/build_c182t_package.py` already patched `_prop_type`
to 1 (constant-speed) for the G1000 MFD's Manifold Pressure gauge, but nothing
in the 3D cockpit reflected that — only the black throttle and red mixture
levers existed, inherited unchanged from the C172SP source.

Added `add_prop_lever()` and `register_prop_lever_obja()` to the build script,
run automatically as steps 4b/4c of `main()`:

- Duplicates the throttle knob's own mesh from `objects/cockpit_panel_G1000.obj`
  (`TRIS 19629 534`, same shape as requested) rather than modeling new
  geometry, and translates the copy to the midpoint between the throttle and
  mixture knob centroids — which lines up with the real-world Throttle / Prop
  / Mixture quadrant order, not just an arbitrary gap.
- Crops the knob's own texture footprint out of the shared `cockpit.dds` atlas
  (194x87 px) and recolors it in HSV space to hue ~205 deg (sampled from
  Laminar's Beechcraft Baron 58 prop lever texture, `B58_panelback.png`:
  base tone `#0f507f`, highlight `#246fa5`), while keeping the original crop's
  per-pixel luminance to drive brightness — so the recolored knob keeps the
  throttle knob's own baked shading/highlight shape instead of reading as a
  flat color swap.
- Ships as a new, self-contained `objects/prop_lever.obj` + `prop_lever.png`
  with its own manipulator (`ATTR_manip_drag_axis` bound to
  `sim/cockpit2/engine/actuators/prop_ratio[0]`, X-Plane's standard writable
  constant-speed-prop-pitch dataref — not `prop_rotation_speed_rad_sec`, which
  is a rotating-vernier-knob control the Baron uses for a different physical
  lever style). Registered as a new `_obja/27` slot in `Cessna_182T_G1000.acf`,
  cloned from the existing `cockpit_panel_G1000.obj` slot's flags
  (`_obj_flags 1033`, `_v10_is_internal 419430400`), with `_obja/count`
  incremented from 27 to 28.
- Deliberately does not touch the existing throttle/mixture geometry, the
  shared `cockpit.dds` atlas, or `Cessna_182T_G1000_cockpit.obj` (the
  manipulator-hotspot object for the other two levers) at all — the new lever
  is entirely additive, so reverting is deleting two files and one `.acf`
  block.

### Validation performed

- Ran `scripts/build_c182t_package.py` end-to-end from a clean re-clone of the
  Laminar source; it completes without error and the verification summary
  still reports all 30 patched `.acf` parameters correctly.
- Confirmed in the rebuilt package: `_obja/27` present with `prop_lever.obj`,
  `_obja/count` reads `28`, `objects/prop_lever.obj` and
  `objects/prop_lever.png` exist (125 verts / 194x87 px).
- Visually inspected the generated `prop_lever.png` directly (not in X-Plane):
  reads as a shaded, rounded blue knob with a shaft, consistent with the
  throttle knob's original shape.
- `python3 -m unittest tests.test_panel` — 7/7 pass (unrelated Air Manager MO
  panel suite; no existing test covers the X-Plane aircraft package, and none
  was added for this change).

### Not verified

- Actual in-sim placement, scale, and readability of the lever have not been
  checked in a running X-Plane session — the computed midpoint position is
  derived from mesh centroids, not confirmed against how it actually looks
  next to the real throttle and mixture levers.
- The recolored texture was sampled and generated programmatically; it has
  not been visually compared side-by-side with the real Baron 58 lever in
  X-Plane, only against the sampled RGB values from its texture file.

## 2026-09-08 — Air Manager instrument appearance and display typography

**Status: implemented and installed in all four local Air Manager instruments;
rendered previews reviewed and automated checks passed. Live GUI rendering has
not been verified in this session; restart Air Manager to load the resources.**

Refreshed the Becker SAR-DF 517, RHOTHETA RT-600, Technisonic TDFM-136B, and
Garmin GMA 1347 using the existing equipment photos and manual figures. The
faceplates now have fine, low-contrast matte grain instead of coarse mottling;
the DF circular casting is subtly distinct from its mounting flange. Reworked
the knobs with flatter tops and twelve scallops, the rubber keys with shallow
bevels, the screws with satin-metal shading, and the TDFM toggles with retaining
nuts and cylindrical lever shading. Reduced the oversized DF printed legends.
These are reference-informed illustrations, not photographic reproductions.

Replaced the shared Lua display renderer's hand-built 3×5 block glyphs with
antialiased built-in Inconsolata Bold via the AM 4.2-compatible canvas `_txt`
API. The three copies of `lib/lcd.lua` remain identical. Explicit per-character
positioning preserves the existing four-unit column advance, frequency fields,
right alignment, inverse labels, large readouts, and case-sensitive TDFM mode
and squelch flags. This is a readability treatment; the hardware's exact glyph
ROM is not documented in the project references. Logical display geometry,
control hit regions, receiver behavior, wing blanking, and ELT audio are retained.

Updated both artwork generators and all instrument previews. The panel preview
generator now uses project-local custom instrument previews rather than stale
installed copies. Included the matching unmodified preview font under its SIL
Open Font License so regeneration does not depend on a local AM installation.
The live instruments use AM's built-in font and need no new font resource.

Validation: `tests/test_faceplate.py` passes; all seven `tests/test_panel.py`
tests pass; all five new `tests/test_lcd_text.py` tests pass; syntax checks pass
for all seven edited Lua files. The new tests execute real Lua text calls and
measure rendered glyph bounds, including the last TDFM column, bottom-row
descenders, DF readout scales, inverse text, case/spacing, and powered-off output.
These checks do not replace a live Air Manager/OpenGL visual check.

Installed 101 changed files and verified 105 selected artwork, Lua, and preview
files against their project sources. Verified the installed AM font matches
the preview font. Existing files were backed up under
`output/visual-refresh/installed-backup-20260908-062811/`. Instrument UUIDs and
panel registration were preserved; no simulator plugin update is needed.

See [visual refresh notes](docs/instrument-visual-refresh.md),
[updated overview](output/visual-refresh/updated-instruments.png), and
[before/after comparison](output/visual-refresh/comparison.png).

## 2026-09-07 — G1000 MFD streaming: intermittent drops in flight, plugin downgrade planned

**Status: proposed work, not yet done. Action needed 2026-09-08.**

Installed the Sim Innovations X-Plane "Air Plugin" (Home Use, v4.5.3, Linux
x86_64, non-steam) into `X-Plane 12/Resources/plugins/Air Plugin/` to fix the
MO panel's G1000 MFD tile, which was showing the "streaming only available"
placeholder because the plugin was previously absent entirely. That resolved
the placeholder — the MFD streamed live after install.

In flight, the video stream then froze intermittently (first noticed across a
pause/unpause, but `~/Air Manager/log.txt` shows it recurring on its own
every few minutes throughout the session):

```
18:49:14 ERROR SimVideoStreamClient - Lost connection with client: Connection reset by peer
18:53:33 ERROR SimVideoStreamClient - Lost connection with client: Resource temporarily unavailable
20:27:13 ERROR SimVideoStreamClient - Lost connection with client (x2)
20:28:26 ERROR SimVideoStreamClient - Lost connection with client: Connection reset by peer
```

The socket itself reconnects within ~5s each time, but the MFD tile's
`logic.lua` (stock Sim Innovations instrument, `0b852ee1-.../logic.lua:90-100`)
only calls `video_stream_add()` once at instrument load, so it never re-arms
the texture after a reconnect and is left showing the last frame.

**Next step (tomorrow): try an older X-Plane plugin build** to match Air
Manager 4.2.12, on the theory that v4.5.3 is misbehaving against the older
app. Note for whoever picks this up: plugin releases appear to be versioned
independently of the Air Manager app itself (other users run this same
4.5.x/5.x plugin line against both 4.x and 5.x app releases), so the version
gap may not be the actual cause. `ping` to the X-Plane host (192.0.2.158,
same machine, wired) showed 0% loss, ruling out a physical network problem.
Sim Innovations' own wiki also flags local firewalls as a known cause of
drops even when Air Manager and the sim share a machine — worth checking
`sudo ufw status verbose` (not yet run; needs an interactive password) before
concluding it's the plugin version.

## 2026-09-07 — ELT receiver audio implemented

**Status: implemented and deployed to both Air Manager 4.2 DF instruments.**

The Becker 517 and RHOTHETA RT-600 now synthesize audible receiver output from
the propagation engine's instantaneous `cap/df/rx_open` state. Analog 121.5 and
243 MHz reception plays a downward swept ELT tone at three sweeps per second;
the normal AM path includes the documented 3 kHz Doppler commutation tone. The
Becker STORE control switches to a clean version of the same received sweep,
so it now performs its complete documented audio function as well as disabling
bearing. Maritime FM uses that filtered version automatically. Cospas-Sarsat
reception plays a single deterministic 440 ms data-burst sound for each engine
burst rather than looping it.

Audio is silent during power-up, at zero receiver volume, when tuned away, when
squelch closes, between 406 bursts, behind terrain, and in a wing null. A held
TIMEHOLD bearing never keeps audio alive. Front-panel volume changes Air
Manager's sound gain immediately. `scripts/make_df_audio.py` deterministically
generates the three PCM WAV assets shared by both heads and supports `--check`
for reproducibility. Validation covers Lua syntax, resource packaging, audio
state wiring, deterministic WAV generation, and the existing engine suite.

## 2026-09-07 — Air Manager MO Station Panel Registration & Auto-Discovery Fix

**Status: implemented, verified live in Air Manager 4.2.12.**

Resolved the issue where the Cessna 182T Mission Observer panel did not show in Air Manager:
1. **Active Panel Registry (`config.sqlite3`)**:
   - In Air Manager, the primary **Panels** tab only displays panels that are instantiated in the active project (`panel` and `instrument` tables in `~/Air Manager/config.sqlite3`).
   - Created `scripts/register_mo_panel.py` to register both layouts:
     * **Panel 3:** `Cessna 182T MO Station (Becker 517)`
     * **Panel 4:** `Cessna 182T MO Station (RT-600)`
   - Configured full instrument hierarchies on each panel (G1000 MFD overlay with `Display unit function = MFD` and `Streaming = true`, CAP GMA 1347 Audio Panel, Becker SAR-DF 517 / RHOTHETA RT-600, and Technisonic TDFM-136B).
   - Hooked registration automatically into `scripts/deploy_mo_panel.py`.
2. **Development View Integration**:
   - Added development objects so both layouts are visible and editable in the **Create / Edit** tab.
3. **Hot-Reload**:
   - Safely updated `config.sqlite3` and restarted Air Manager with the active panels immediately visible on screen.

## 2026-09-07 — Cessna 182T NAV III (G1000 CAP) Aircraft Package for X-Plane 12

**Status: implemented, verified live in X-Plane 12.**

Created a dedicated, standalone **Cessna 182T Skylane NAV III (G1000 CAP)** aircraft package (`N499CP`) tailored specifically for Civil Air Patrol virtual search and rescue (V-SAR) training in X-Plane 12.

### Background & Rationale
X-Plane 12 lacks a native C182T G1000 in its default aircraft inventory (only providing the C172SP Skyhawk). Rather than relying on unmaintained third-party conversions or payware, we built an automated package builder (`scripts/build_c182t_package.py`) that clones Laminar Research's high-fidelity default C172SP G1000 base airframe and re-engineers it into an authentic, standalone Cessna 182T NAV III with authentic Lycoming IO-540 performance, 3-blade constant-speed prop, and Garmin G1000 Manifold Pressure EIS instrumentation.

### Key Aircraft Specifications & Modifications
1. **Airframe & Package Location**:
   - Location: `/home/ron/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III/`
   - Aircraft File: `Cessna_182T_G1000.acf`
   - Completely independent from the stock C172SP (leaving the Laminar directory untouched).
2. **Powerplant**:
   - Lycoming IO-540-AB1A5: 230 HP @ 2,400 RPM (541 cu in, direct-drive, fuel injected).
   - Patched `acf/_power_max_limit` to 230.0 HP, `_RSC_max_pwr_ENGN` to 2400 RPM, `_RSC_redline_ENGN` to 2400 RPM.
3. **Propeller & G1000 EIS Manifold Pressure Auto-Activation**:
   - McCauley 3-blade constant-speed propeller (`_prop_type = 1`, `_num_blades = 3`, `_des_rpm_prp = 2400`, `_des_kts_acf = 145`).
   - Pitch range: `_min_pitch = 10.0`, `_max_pitch = 40.0`.
   - **G1000 EIS Integration**: In X-Plane 12, setting `_prop_type = 1` on a reciprocating engine automatically triggers the Garmin G1000 MFD Engine Indication System (EIS) to display the dual **Manifold Pressure (`MAN IN HG`)** and **Tachometer (`RPM`)** gauges with correct C182T green/yellow/red bands, matching the real G1000 Skylane cockpit.
4. **Weights & Loading**:
   - Maximum Takeoff Weight (MTOW): 3,100 lbs (`acf/_m_max = 3100.0`).
   - Basic Empty Weight: 1,970 lbs (`acf/_m_empty = 1970.0`).
   - Useful Load: 1,130 lbs.
5. **Fuel Capacity**:
   - 87 gallons usable (92 gal total) = 522 lbs of 100LL avgas (`acf/_m_fuel_max_tot = 522.0`).
6. **Cowl Flaps**:
   - Equipped with manual cowl flaps (`acf/_cowl_flaps_EQ = 1`), accurately modeling engine cooling drag and cylinder head temperature management during high-power climbs.
7. **Flight Envelope & V-Speeds**:
   - Stall Speed (clean) $V_S$: 51 KIAS
   - Stall Speed (full flaps) $V_{S0}$: 41 KIAS
   - Best Angle of Climb $V_X$: 65 KIAS
   - Best Rate of Climb $V_Y$: 80 KIAS
   - Best Glide $V_{BG}$: 76 KIAS
   - Flaps Extended Range $V_{FE}$: 140 KIAS (Flaps 10°), 100 KIAS (Flaps 20°–30°)
   - Max Structural Cruising Speed $V_{NO}$: 140 KIAS
   - Never Exceed Speed $V_{NE}$: 175 KIAS
8. **CAP Livery & Selection Icons**:
   - Tail Number: `N499CP`
   - ICAO Designator: `C182`
   - Studio/Author: `Civil Air Patrol / Laminar Research / CAP V-SAR Project`
   - Dedicated livery `liveries/Civil Air Patrol (N499CP)/` based on clean baseline.
   - Branded aircraft selection thumbnail and icon (`Cessna_182T_G1000_icon11.png` and `_thumb.png`) featuring official Civil Air Patrol USAF Auxiliary header, gold stripe, red lower margin, and "SAR MISSION READY" banner.
9. **Automated Package Builder**:
   - `scripts/build_c182t_package.py` can be re-run at any time to regenerate or update the package from the base files.

## 2026-09-07 — Design proposal: containerized deployment, single machine or cloud

**Status: proposed.** No code, containers, or cloud resources were created.
Architecture recommendation for packaging the CAP V-SAR server-side
infrastructure so it can be brought up on one machine for an in-person or LAN
exercise, or moved to the cloud for a fully remote one, sized for an
instructor, a mission base with several staff roles, and up to three aircraft
each with a pilot and an MO.

### The one split that matters: client stations vs. server infrastructure

"Containerize all of the infrastructure" has to stop at a real boundary. Two
things in this project are not infrastructure at all, and can't be
containerized or moved to the cloud without changing what they are:

- **X-Plane + Air Manager/Air Player, per aircraft station.** The CONOPS is
  explicit that this runs on members' own computers, and it isn't just a
  preference: Air Manager Home Use activates against a hardware fingerprint
  (confirmed from this machine's own `~/Air Manager/log.txt` - `HW id =
  feea523088e42a454e95a5152d8e97f8`). There is no containerized or cloud form
  of a per-machine license. This part of the architecture is fixed regardless
  of what happens to the server side.
- **The licence count is better than a flat headcount suggests.** Re-reading
  the CONOPS's own layer list - "Air Manager panels: Becker 517 and RT-600
  heads, plus a second COM panel **at the Observer station**" - the Pilot
  seat needs only X-Plane and PilotEdge, not Air Manager. Three aircraft means
  **three** Air Manager/Air Player seats (one per MO), not six. Worth
  confirming against `AM4_COMPAT.md`'s "spare AM4 licences" count before
  committing to a three-aircraft exercise.

Everything else - Mumble, the exercise console, the flight planner, and the
mission-base web apps - is ordinary server infrastructure and is exactly what
this proposal covers.

### What already exists vs. what this would require building

Checked before proposing anything, so the plan is sized to reality:

| Piece | State |
|---|---|
| Mumble voice server | Built, running (`capvsar-mumble`, `docker-compose.yml` on ms01) |
| Exercise console (instructor / `/base` mission base / `/debrief`) | Built, running (`capvsar-exercise`) |
| Flight planner (search patterns, `.fms` export, V-SAR push) | Built, running (`capvsar-flightplanner`), targets Cloud Run already |
| MRO Base Radio web app (`/radio`) | Just landed in this log as "implemented, verified live" - not yet independently reviewed here. From its own description (REST + WebSocket, canned reports, simulated radio sound effects, a CAP Form 110 log) it reads as a **dispatch/logging console with simulated audio**, not a bridge onto the real Mumble voice net the aircrews actually talk on. Worth clarifying intent before counting it as "the radio operator's console" in the CONOPS sense - it may be a complementary tool alongside real voice rather than a replacement for it. |
| IC / AOBD role-differentiated consoles | Not built. Today there is one shared `/base` view (alert intake, status board, bearings, tasking), not separate per-role views. |
| Browser-native voice bridge (pymumble backend, WebSocket audio to the browser) | Proposed only (see "Design proposal: Mission Base WebUI virtual radio" elsewhere in this log), not implemented. Distinct from `/radio` above - this is the one that would let a browser-only staff member actually hear and key the real mission net without a native Mumble client. |

So "a base with a couple web apps for IC, AOBD, radio operator" is partly
redeployment (the console and, pending review, `/radio`) and partly new
frontend work (IC/AOBD views; a real voice bridge if browser-only staff need
to be on the actual net rather than a text/simulated one).

### Measured, not assumed: this is a small workload

`docker stats` on ms01 right now:

| Service | CPU | RAM |
|---|---|---|
| exercise console | 0.29% | 39 MB |
| flight planner | 0.07% | 59 MB |
| mumble | 0.00% | 6 MB |

An instructor, a few base roles, and six aircrew exchanging voice and small
JSON payloads does not stress a machine. The sizing question this proposal
answers is about protocol and licensing constraints, not raw capacity.

### Recommendation: one small VM for the exercise, Cloud Run only for the piece that suits it

Checked against Google's current documentation rather than assumed: **Cloud
Run's ingress is HTTP/1.1, HTTP/2, and gRPC only - no raw TCP, no UDP.**
Mumble needs both. This isn't a workaround-able limit; **Mumble cannot run on
Cloud Run** and needs a real VM or GKE regardless of budget.

Given the measured footprint above, splitting the stack across Cloud Run plus
a separate VM buys little: the exercise console's SQLite database (40 KB
today) would need migrating off local disk for Cloud Run's stateless storage
model, in exchange for savings on a workload that costs a few dollars a month
either way. The simpler, lower-risk shape:

1. **One small VM** (e.g. a GCE `e2-small`, ~$10-13/month, or the existing
   ms01 host for an on-prem exercise) running the full `docker-compose.yml`
   stack as it already exists: Mumble, exercise console, mission-base apps,
   and a WireGuard endpoint (below). This is close to a lift-and-shift of what
   already runs today.
2. **The flight planner stays on Cloud Run**, which is what its own
   `Dockerfile` already targets. It's public-facing, used outside exercise
   windows, and doesn't touch voice or the exercise database - a genuinely
   good fit, unlike the rest of the stack.
3. **If browser-only voice access is wanted later**, the proposed
   pymumble-bridge design (browser <-WebSocket-> FastAPI <-native Mumble
   client-> Mumble server) works on Cloud Run specifically *because* the
   constraint above is about ingress, not egress: Cloud Run's documented
   limits distinguish inbound (HTTP-family only) from outbound (ordinary
   TCP/UDP to external hosts is fine). A Cloud-Run-hosted console could hold
   a native Mumble connection as a client while serving browsers over
   WebSocket. Mumble itself still needs to live on the VM, not Cloud Run.

### WireGuard: already the case, not a redesign

The router (GL-MT6000) already terminates WireGuard for participant peers,
with a live GCP site-to-site tunnel already in place
(`docker-compose.yml`'s own comment: "a GCP site-to-site tunnel"). "Everyone
connects via WireGuard" is the current state, not a proposal.

The one real decision if the hub moves to a cloud VM: run a WireGuard
endpoint **on that VM** so participants connect there directly instead of
routing through the home router. That decouples exercise-day reliability from
home-network uptime and bandwidth - the actual payoff of "to the cloud" here,
independent of compute.

### Sources checked for this proposal

- This machine's own `~/Air Manager/log.txt` (HW id, licence activation).
- `AM4_COMPAT.md` (spare AM4 licence count, Air Player as a separate SKU).
- `docker-compose.yml` and `docker stats` on ms01 (current services, live
  resource usage, the existing WireGuard/GCP-tunnel comment).
- Cloud Run networking documentation, checked live rather than assumed
  (`docs.cloud.google.com/run/docs/configuring/networking-best-practices`;
  cross-referenced against the community FAQ at
  `github.com/ahmetb/cloud-run-faq`) for the HTTP-only-ingress /
  unrestricted-egress distinction the recommendation above depends on.
- CONOPS-cap-vsar.md (four layers, operating modes, the Observer-station-only
  placement of Air Manager panels).

### Not done as part of this proposal

No compose file changes, no cloud resources, no new consoles. Next concrete
step, if this shape is approved: consolidate the existing `docker-compose.yml`
into a form that stands up cleanly on a fresh VM (mostly already true), stand
up one small cloud VM to prove the "to the cloud" half, and decide whether
`/radio` needs review/rework before it stands in for the CONOPS "radio
operator" role, or whether the pymumble bridge is still needed alongside it.

## 2026-09-07 — Wing blanking and instantaneous receiver state implemented

**Status: implemented, verified offline and live, and deployed to the installed
X-Plane plugin, both Air Manager DF instruments, and the `ms01:8700` exercise
console.** This supersedes the earlier research-only entry below.

The propagation engine now reads X-Plane roll (`phi`) and pitch (`theta`) and
transforms the aircraft-to-beacon ray into aircraft body coordinates. A
configurable C182 training profile tests that ray against a softened
wing/fuselage silhouette. With the default belly profile, banking the lowered
wing toward the beacon produces the expected null; the top profile reverses
the direction. The supplied dimensions and nominal 24 dB peak loss are a
training approximation, not measured antenna-pattern data for a particular
tail number.

Propagation loss is now accumulated before signal saturation. Terrain and
airframe attenuation can therefore combine while remaining separately
diagnosable, and a sufficiently strong close signal can penetrate partial
shielding. Three new engine outputs were added:

- `cap/df/airframe_shadowed` — directional airframe loss is active;
- `cap/df/airframe_attenuation_db` — current loss for instructor/debug use;
- `cap/df/rx_open` — instantaneous reception, independent of a TIMEHOLD bearing.

The shared Becker/RT-600 Lua binding subscribes to all three. The student sees
the real consequences through the existing signal bar, squelch, bearing spread,
and TIMEHOLD behavior; it does not display an artificial "wing null" warning.
`rx_open` supplies the gate for receiver audio without conflating live audio
with a held bearing.

The instructor console now offers a **Wing blanking** effect and C182 belly/top
antenna selection for new and running scenarios. Position ingest accepts the
X-Plane plugin's authoritative DF telemetry rather than replacing it with the
server's attitude-free fallback model. The instructor aircraft HUD can thus
show `wing null`, loss, live/held state, and aircraft bank reported by X-Plane.

The canonical plugin source now lives at `xplane/PI_capvsar_df.py` and
`scripts/deploy_xplane_plugin.py` validates and atomically installs it into
X-Plane. `tests/test_engine.py` defaults to the tracked source instead of the
unversioned installed copy.

Validation: all 55 engine checks pass, including opposite banks, top/belly
reversal, combined terrain and airframe masking, strong-signal penetration,
instantaneous audio versus held bearing, disabled-effect compatibility, and
406 burst state. All faceplate checks and all seven MO-panel tests also pass.

## 2026-09-07 — Mission Radio Operator (MRO) Base Radio Web Application (`/radio`)

**Status: implemented, verified live on `ms01:8700/radio`, and integrated with web suite.**
Built and deployed a touch- and mouse-operable base station radio application designed
for Mission Radio Operators (MROs) using laptops or tablets. Implemented the two
predominant radio systems deployed across Civil Air Patrol base stations:

1. **Motorola APX 6500 with O5 Control Head (VHF-FM Tactical / LMR Net):**
   - **Operational Role:** Standard CAP tactical mobile/base radio for ground team nets,
     Wing command & control, and air-to-ground tactical comms with the MO (TDFM-136B).
   - **Channels & Zones:** Authentic CAP channel banks including Zone 1 Tactical
     (`TAC 1` 148.150 MHz, `TAC 2` 148.125 MHz, `CC 1` 150.225 MHz P25 NAC $293,
     `CC 2` 149.275 MHz, `AIR 1` 150.5375 MHz, `AIR 2`, `SAR 1`, `GUARD`), Zone 2
     Ground Teams (`GROUND 1`, `GROUND 2`, `BASE DISP`), and Zone 3 Interoperability
     (`VFIRE 21`, `VTAC 11`, `CALCORD`, `NATL GUARD`).
   - **Controls & Display:** Realistic vacuum-fluorescent green-cyan OLED display
     with RSSI bars, DIR/RPT, SEC, High/Low power flags; rotary VOL/PWR and CHANNEL
     knobs with continuous drag and incremental `+`/`-` touch steppers; `HOME`,
     `ZONE ▲/▼`, `SCAN`, `MON`, and `DIM` softkeys; realistic TX, RX, and SCAN LEDs.
   - **Acoustics:** Pure Web Audio API simulation of Motorola 3-tone P25 permit chirp
     (941 Hz, 1336 Hz, 1209 Hz) and digital carrier squelch tail.

2. **Icom IC-A120 (VHF-AM Aeronautical Air-to-Ground Transceiver):**
   - **Operational Role:** Standard desktop/base aviation transceiver deployed at
     mission bases, staging hangars, and flight dispatch to communicate directly
     with search aircrews on aeronautical VHF-AM frequencies.
   - **Frequencies & Presets:** Memory presets for `CH 01` (123.100 MHz SAR Primary),
     `CH 02` (122.900 MHz SAR Secondary / Multicom), `CH 03` (121.500 MHz ELT Guard),
     `CH 04` (122.775 MHz Air-to-Air), `CH 05` (123.050 MHz Unicom), and `CH 06`
     (126.200 MHz Military SAR), plus continuous VFO tuning (118.000–136.975 MHz).
   - **Controls & Display:** High-contrast ice-blue backlit aviation LCD with large
     7-segment frequency digits, memory alias, audio bar meter, and `SQL`, `PRI`,
     `SCAN`, `ANL` status flags; rotary Volume, Squelch, and 25 kHz / 1 MHz push-toggle
     tuning dial; `CH/WX`, `SCAN`, `PRI`, `ANL`, `LOCK` function keys.
   - **Acoustics:** Mechanical relay click, VHF-AM sidetone, and squelch noise burst.

3. **Dual Station Equipment Rack View:**
   - Provides a dual-mount rack view (`?mode=dual`) running both the APX 6500 and
     IC-A120 simultaneously, allowing the MRO to monitor both nets with dual watch.

4. **PTT Station & Tactical Communications Dispatch:**
   - Realistic palm fist microphone with coiled cable, PTT lever, and master PTT button.
   - Dual PTT modes: "Hold to Talk" (momentary mouse/touch/spacebar) and "PTT Latch" (tap to lock).
   - Direct integration with `/api/messages` REST endpoint and WebSocket `/ws`.
   - Web Speech API text-to-speech option to voice incoming aircraft traffic with radio effects.
   - Quick "Canned" Tactical Reports for rapid MRO workflow (Radio Check, Ops Normal, Copy Bearing, Exercise Silence, Beacon Found).
   - Live **CAP Form 110 Communications Log** table with timestamps, frequency tags, stations, and text export (`.txt`).

5. **Deployment & Navigation Integration:**
   - Added `/radio` endpoint to `capvsar-exercise` FastAPI service.
   - Added global `Base Radio` header navigation links across all consoles (`index.html`, `base.html`, `debrief.html`).
   - Rebuilt and verified live on `ms01:8700/radio`.



**Status: implemented, verified against a real Lua 5.4 execution and against
the live Air Manager instance's own log.** Closes out three items raised
reviewing "Implementation: Dedicated Mission Observer (MO) Panel" below: the
panel's license tier, an independent re-verification of the `require()` fix
"Air Manager 4.2 bring-up and runtime compatibility" already made, and a
second `canvas_draw` symptom that entry's fix doesn't cover.

### 1. MO panel tier corrected

`panels/cap-c182t-mo-station/info.xml` declared `HOME_USE_PAID` /
`PROFESSIONAL_PAID` — the tiers a *purchased* Sim Innovations panel like the
172SP uses — on `<source>PERSONAL</source>` content. Every one of the
project's own four instruments correctly declares `HOME_USE_STANDARD`; this
panel copied the wrong reference. Fixed to `HOME_USE_STANDARD`, redeployed via
`scripts/deploy_mo_panel.py`, and confirmed on disk at
`~/Air Manager/panels/OPEN_DIRECTORY/a4c8e710.../info.xml`.

Added `tests/test_panel.py::test_tier_matches_personal_source`, which is what
was missing and let the wrong tier ship in the first place — no test checked
`<tiers>` at all. Now 7/7 pass.

### 2. `require()` outage — already documented and fixed; independently re-verified here

**Correction before this goes further: my first pass at this entry claimed
this was undocumented. It is not.** The entry immediately below this one,
"Air Manager 4.2 bring-up and runtime compatibility", already records finding
and fixing it, in more categories than I initially credited (it also fixes a
missing-argument `canvas_draw` bug, a stray fifth `_rect` argument, matrix
glyphs that were merging into solid bars, and the TDFM switch contract). I
should have re-read the full log before writing that claim rather than after.
What follows is additive to that entry, not a replacement for it.

Air Manager's own log (`~/Air Manager/log.txt`) records the discovery, at
first license activation:

```
14:15:28 ERROR SiScanner - Cessna 182T - Becker SAR-DF 517: Error loading
  instrument script: [string "logic.lua"]:22: attempt to call a nil value
  (global 'require')
```

...identically for RT-600, TDFM-136B, and the GMA audio panel — a total,
project-wide load failure, undetectable until Air Manager was actually
installed and licensed today, since nothing before that point could exercise
it. The fix that entry made — every shared `lib/*.lua` publishes its module
table as a global matching its filename, and `logic.lua` files were stripped
of `require()` and reference those tables as bare globals or a local alias —
is what's in the codebase now.

**What this entry adds:** independent re-verification by a different method.
I wrote a real Lua 5.4 execution harness (ctypes against `liblua5.4.so.0`,
stubbing Air Manager's C API surface — `canvas_add`, `button_add`, `dial_add`,
`xpl_dataref_subscribe`, the `_rect`/`_fill`/... draw primitives) and ran all
four instruments' actual `lib/*.lua` + `logic.lua`, then their real power-on
control, then their draw callback, through it. All four load and draw without
error. This is a second confirmation route, independent of reading Air
Manager's own log, and one that doesn't require the licensed application to
be running to re-check after a future edit.

### 3. Becker / RT-600: a *different* `canvas_draw` symptom, mitigated but not proven fixed

The other entry's "Restored the required callback argument on each ...
`canvas_draw(canvas_id, draw_callback)` call" fixed a real bug — calling
`canvas_draw` with only the canvas ID, no callback — and its symptom
(`attempt to call a nil value` / `attempt to call a number value`) matches
what's in the log for that. But the log also has a second, textually distinct
Air Manager error that the current code, with both arguments already correct,
still produces:

```
14:38:48 ERROR SiRunner - Becker SAR-DF 517: logic.lua:152: You cannot call
  canvas_draw within a draw callback.
14:38:58 ERROR SiRunner - Becker SAR-DF 517: Error in timer callback:
  attempt to call a number value
```

Line 152 was `if canvas_id then canvas_draw(canvas_id, draw_lcd) end` inside
`redraw()`, called from the 250 ms `timer_start` tick that drives the
Last-Signal/burst timers and scan-mode redraws. **RT-600 has the identical
pattern** — same `redraw()`, same tick-driven call — checked directly, not
assumed. Neither file had been touched since the error was logged; attention
moved to a separate, unrelated TDFM bug (which *was* chased down and fixed,
through several more edits ending around 15:19) and never came back to this
one.

Mitigated in both `becker-sar-df-517/logic.lua` and
`rhotheta-rt-600/logic.lua`: `redraw()` now calls `pcall(canvas_draw,
canvas_id, draw_lcd)` instead of calling it directly. A lost race no longer
raises an unhandled error into the timer or the log; the next 250 ms tick (or
the next button/dataref-driven redraw) asks again almost immediately, so a
dropped frame is not a real staleness risk.

**This is explicitly not proven fixed.** Air Manager's exact reentrancy rule
for `canvas_draw` is not documented anywhere I could find, my own Lua-only
harness has no concept of the engine's own repaint thread and so cannot
reproduce the race to confirm the fix defeats it, and I have no working
screenshot/GUI-automation path on this machine to drive the real instrument
through Air Manager and watch for a recurrence. What's true: the specific
unhandled-error symptom in the log is now structurally impossible from this
call site, regardless of the underlying cause. What's not verified: whether
Air Manager's engine reacts to the *suppressed* failure in some other way
(e.g. simply not repainting that tick, which would be the desired outcome
anyway). Watch `~/Air Manager/log.txt` for `logic.lua:15[123]:` or a
recurrence of "error in draw callback" against Becker or RT-600 specifically
after actually clicking through pages 1-3 or scan mode.

### Validation performed

- `python3 scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua`
  — 14 files, all OK.
- `python3 tests/test_engine.py` — all pass, unaffected (no engine changes).
- `python3 tests/test_faceplate.py` — all pass, including the widened
  "canvas redraw supplies its callback" check that now accepts the
  pcall-wrapped form.
- `python3 -m unittest tests.test_panel` — 7/7, including the new tier test.
- Independent Lua 5.4 execution (ctypes + `liblua5.4.so.0`, stubbed Air
  Manager API) of all four instruments' real `lib/*.lua` + `logic.lua`,
  through power-on and a draw-callback invocation: all four load and draw
  without error, both before and after the `pcall` change.
- The fixed `becker-sar-df-517/logic.lua` and `rhotheta-rt-600/logic.lua`
  were copied to the live installation
  (`~/Air Manager/instruments/OPEN_DIRECTORY/<uuid>/logic.lua`) and diffed
  byte-identical against the repo afterward.
- The MO panel was redeployed via `scripts/deploy_mo_panel.py`; its live
  `info.xml` was grepped afterward to confirm `HOME_USE_STANDARD` landed.

### Remaining limitations

- The Becker/RT-600 `canvas_draw` mitigation is a safety net, not a confirmed
  fix — see above. Needs eyes on the real instrument (or the log, after
  exercising scan mode / rapid page changes) to close out properly.
- No screenshot or GUI-automation capability exists on this machine for Air
  Manager, so nothing in this entry was confirmed by actually looking at a
  rendered instrument — everything here is log evidence and independent Lua
  execution outside the real application.

## 2026-09-07 — Air Manager 4.2 bring-up and runtime compatibility

**Status: implemented and verified in Air Manager 4.2.12.**
Installed the project instruments into Air Manager Home Use 4.2.12's live
`~/Air Manager/instruments/OPEN_DIRECTORY/` store. All four now appear in the
Create/Edit instrument list. Runtime testing found compatibility defects that
the Lua syntax and geometry tests could not expose.

### Fixed

- Removed every `require()` call. Air Manager 4.2 executes all files under
  `lib/` before `logic.lua` and does not expose Lua's module loader. Each library
  now publishes a global table matching its filename. The TDFM line pitch is a
  literal so random library execution order cannot make `tdfm_display.lua`
  depend on `lcd.lua` during load.
- Restored the required callback argument on each Becker, RHOTHETA and TDFM
  `canvas_draw(canvas_id, draw_callback)` call. Passing only the numeric canvas
  ID produced the runtime errors `attempt to call a nil value` and `attempt to
  call a number value` in Air Manager 4.2.
- Removed the invalid fifth zero from Becker's display `_rect` call. Four
  arguments are sufficient for a square-corner rectangle.
- Changed matrix glyphs and the DF dot/tick groups to fill discrete rectangles.
  Queuing all dot rectangles into one Air Manager path turned each TDFM display
  row into a solid amber bar. The powered TDFM now renders two legible 24-cell
  dot-matrix rows and the runtime console remains clean.
- Corrected the three TDFM toggles to use Air Manager's documented
  `(position, direction)` callback contract, retain their switch IDs and call
  `switch_set_position`. The HI/LO switch is initialized to LO to match the
  instrument state. The earlier changelog correction remains valid: a
  two-position switch uses two images, not a third `nil` image.
- Added live GMA 1347 VOL/SQ text annunciators. VOL is shown while automatic
  squelch is active; with MAN SQ selected, pressing either concentric knob
  alternates the illuminated VOL and SQ indication.

### Runtime evidence

- Air Manager startup log is clean: all four project instruments scan and are
  visible in the GUI.
- TDFM runs, powers on, redraws and shows both Main and Guard lines without a
  Lua error after the canvas fixes.
- Becker and RHOTHETA both run and power into legible dot-matrix boot screens
  with the final shared renderer and no Lua errors.
- TDFM's MN/GD and HI/LO switches were moved in the live test window; their
  images and state changed in the requested direction and the console stayed
  clean.
- GMA runs and renders its complete face with the new VOL/SQ text nodes and no
  Lua errors. Its avionics-master-driven power-up lamp test still requires an
  X-Plane connection and was not claimed by this standalone editor sweep.
- Runtime captures are retained in `output/air-manager-validation/`.

Static verification after these changes: all 14 Lua files pass `luacheck`, and
the engine, Python syntax and complete faceplate/resource/loading-contract
suites pass. Regenerating all artwork and previews is byte-identical.

## 2026-09-07 — Publication: Flight Operations Handbook & Training Manual (ODT, DOCX, PDF)

**Status: implemented and published.** Authored and published a comprehensive,
publication-grade flight manual and tutorial document: the *CAP V-SAR Flight
Operations Handbook & Multi-Station Training Manual* (Document ID: `CAP-VSAR-FOH-2026-01`).

### Scope & Structure of the Manual
1. **System Overview & Architecture:** Multi-station CRM simulation architecture
   separating X-Plane 12 flight deck, Mission Observer station, N499CP flight planning,
   and exercise command consoles.
2. **Flight Planning & SAR Patterns:** Pre-flight route construction, performance
   polars, Expanding Square (SS), Creeping Line (CS), Parallel Track (PS), X-Plane
   12 `.fms` export, and exercise console push.
3. **Mission Observer (MO) Station & Avionics:** Complete right-seat console guide
   covering G1000 MFD, GMA 1347 audio panel (and the critical COM3 MIC selection
   trap), Becker SAR-DF 517 vs RHOTHETA RT-600 (406.025 Emergency vs 406.037
   Training coverage gap), and Technisonic TDFM-136B VHF-FM radio.
4. **Instructor & Exercise Console:** Training sortie management, interactive map-pin
   scenario creation on FAA Sectionals, and injected teachable failures (radio
   horizon, 406 burst cadence/timehold, cone of confusion, multipath).
5. **Mission Base & Debrief Replay:** Situational awareness view (hidden beacon truth),
   tactical radio log, bearing cuts, and post-flight track efficiency / CPA debrief replay.
6. **Quick Reference Checklists (QRC):** MO Cockpit Pre-flight Checklist and
   In-Flight Electronic Search & Homing Flow.

### High-Resolution Embedded Visuals
Captured live headless screenshots and embedded high-resolution graphics into the document:
- Figure 1: N499CP Flight Planner Moving Map with Sectional Overlay
- Figure 2: Dedicated C182T MO Station &mdash; Layout 1 (Becker SAR-DF 517 & TDFM-136B)
- Figure 3: Dedicated C182T MO Station &mdash; Layout 2 (RHOTHETA RT-600 & TDFM-136B)
- Figure 4: Instructor Control Console with Sectional Basemap & Dynamic Failure Controls
- Figure 5: Mission Base Console with Aircraft Radar Track and Tactical Message Log
- Figure 6: Debrief Console with Flight Track Scoring & Bearing Error Analysis

### Document Publishing Pipeline (`scripts/generate_manual.py`)
- Automatically compiles structured HTML into self-contained OpenDocument Text (`.odt`)
  with embedded figures inside the ODT ZIP (`Pictures/`), Microsoft Word (`.docx`),
  and print-ready vector PDF (`.pdf`).
- **Figure Scaling & Margin Bounding:** Implemented post-processor `embed_and_resize_odt_images()`
  that recalculates all `<draw:frame>` tags to strictly clamp image widths to 6.2 inches
  (proportional height ≤ 3.88 in), ensuring comfortable margins on standard Letter (8.5×11")
  and A4 pages without horizontal overflow in LibreOffice Writer or Microsoft Word.
- Output files deployed to:
  - Repository: `docs/manual/`
  - User documents: `~/Documents/CAP_VSAR_Flight_Operations_Handbook.*`
  - Remote host `ms01`: `/srv/capvsar/docs/manual/`


## 2026-09-07 — Web Console Flight Planner Integration, Granular SAR Status & Docs

**Status: implemented and verified live.** Followed up on the flight planner
composition and code review with three targeted enhancements across the `ms01`
stack and source repositories:

1. **Web Console Header Navigation Links:**
   - Added direct, styled `Flight Planner` navigation links across all three
     exercise web console views (`index.html` [Instructor], `base.html` [Mission
     Base], and `debrief.html` [Debrief]).
   - Added client-side dynamic host resolution in `charts.js` so clicking
     "Flight Planner" reliably resolves to port 8090 on whichever host or domain
     the user is accessing (`//${location.hostname}:8090/`), opening in a new tab.
   - Rebuilt and verified the `capvsar-exercise` container on `ms01`.

2. **Granular V-SAR Push Feedback & `/api/messages` Analysis:**
   - **Root-Cause Clarification:** Inspected `services/exercise/app/main.py:379-380`
     and verified that the `MessageIn` schema (`sender`/`recipient`/`body`) is
     100% correct. The prior HTTP 400 Bad Request finding was strictly due to
     `if not hub.sortie: raise HTTPException(400, "no sortie running")` (messages
     require an active `sortie_id` in SQLite).
   - **Status Message Granularity:** Updated `sar_export_vsar()` in `app.py` and
     `static/js/app.js` to explicitly differentiate states:
     - When a sortie is active: `"Pushed to V-SAR Console (scenario created & broadcast to active sortie)"`
     - When no sortie is active: `"Pushed to V-SAR Console (scenario created; ready in console)"`
   - Synced and verified live against `capvsar-flightplanner` on `ms01:8090`.

3. **Flight Planner SAR Documentation:**
   - Updated `docs/USER_GUIDE.md` with Section 8: *Civil Air Patrol Search &
     Rescue (SAR) Patterns*, detailing Expanding Square (SS), Creeping Line (CS),
     Parallel Track (PS), route integration, X-Plane 12 `.fms` export, and V-SAR
     bridge synchronization.
   - Updated `docs/QUICKSTART.md` with Step 8 and cheat-sheet reference for the
     SAR pattern generator tool.


## 2026-09-07 — Flight planner composited into the ms01 stack; SSRF fixed

**Status: implemented and verified live.** Redeployed the N499CP Flight
Planner (`flight-planner-n499cp-v2`) as a fourth service in the existing
`/srv/capvsar/docker-compose.yml` stack on ms01, alongside `mumble` and
`exercise`, rather than as a standalone Cloud Run service reaching in from
outside. Applied the SSRF fix flagged in the prior review entry as part of
doing this, since deploying the vulnerable code into a new environment without
it — especially one framed as a step toward a public Cloud Run deployment —
would have carried the same finding forward.

### Composite deployment

New `flightplanner` service, `build: ./services/flightplanner` (rsynced from
the source repo), on the compose stack's own network:

```
flightplanner:
  ports: ["8090:8080"]
  volumes:
    - ./services/flightplanner/data/aviation_data.db:/app/aviation_data.db
    - ./services/flightplanner/data/charts:/app/charts
  environment:
    VSAR_CONSOLE_URL: http://exercise:8700
```

The point of compositing: the flight planner now reaches the exercise console
by its **compose service name**, not a LAN IP or a client-supplied URL. `mumble`
and `exercise` were untouched — `docker compose build flightplanner && up -d
flightplanner` only, confirmed both kept their original uptimes (23h/28h)
throughout.

### The SSRF fix (see the prior review entry for the finding)

`sar_export_vsar()` no longer reads `vsar_url` from the request body at all.
The target is now `VSAR_CONSOLE_URL`, an environment variable fixed at process
start — `http://exercise:8700` in this deployment, would be the WireGuard/LAN
address in a Cloud Run one. Nothing a request sends can change it.
`static/js/app.js` no longer sends the field either.

Also fixed alongside it, from the same review: `spacing_nm = 0` no longer
raises an unhandled `ZeroDivisionError` in `generate_creeping_line`/
`generate_parallel_track` (both now floor at 0.1 nm, matching what the UI's
own `<input min>` already implied but never enforced server-side); `num_legs`
is capped at 40 instead of unbounded; a malformed `waypoints[0]` (missing or
non-numeric `lat`/`lon`) now returns 400 instead of an unhandled `KeyError`.

### Verified against the live deployment, not just re-read

- `docker compose exec flightplanner python3 -c "urlopen('http://exercise:8700/api/health')"`
  → 200. The composite network resolves and routes.
- `env | grep VSAR_CONSOLE_URL` inside the container → `http://exercise:8700`.
- **Reran the actual attack**: POSTed
  `{"vsar_url": "http://169.254.169.254/", "waypoints": [...]}` at the live
  `/api/sar/export-vsar`. Response's `vsar_url` came back `http://exercise:8700`
  — the supplied value was completely ignored, exactly as intended.
- POSTed `spacing_nm: 0` at `/api/sar/generate-pattern` with `creeping_line` —
  returned a valid 16-waypoint pattern instead of a 500.
- `python3 -m unittest tests.test_sar` — all 7 pre-existing tests still pass.

### Found in the process: `/api/messages` rejects the push

The verification POST above logged `scenario_created: true` but
`message_sent: false`. The exercise console's own log shows why:
`POST /api/messages HTTP/1.1 400 Bad Request` — the flight planner's
`message_payload` shape (`sender`/`recipient`/`body`) doesn't match what
`/api/messages` actually expects. **Pre-existing, not introduced by this
change** — the scenario-creation half of the bridge works, the broadcast-
message half doesn't, and the earlier "implemented" claim didn't catch this
because it was never run against the real console until now. Not fixed here;
needs the exercise console's own `/api/messages` schema to diagnose.

### Housekeeping

The verification call above created one real (obviously synthetic — datum
33.1,-117.1, callsign CAP499) scenario in the exercise console's live
database. Left in place since this is the test stack; clear it from the
instructor console if it's in the way.

`docs/USER_GUIDE.md` and `docs/QUICKSTART.md` in the flight-planner repo still
don't mention the SAR feature — the "documented" gap from the prior review
entry is still open.

## 2026-09-07 — Implementation: Dedicated Mission Observer (MO) Panel for Air Manager & Air Player

**Status: implemented & deployed.** Created and deployed a dedicated Mission
Observer (MO) panel for the Cessna 182T NAV III (`cap-c182t-mo-station`) designed
for secondary displays, cockpit touchscreens, and LAN-streamed Air Player setups.

### Operational Context & Cockpit Layout
In the Civil Air Patrol C182T NAV III cockpit, the Mission Observer sits in the
right seat. To the right of the Garmin G1000 MFD is the copilot/observer audio
panel (Garmin GMA 1347), followed by the dedicated CAP mission avionics stack:
the Direction Finder (Becker SAR-DF 517 or RHOTHETA RT-600) and the VHF-FM
mission radio (Technisonic TDFM-136B).

This dedicated panel groups the MO's complete operational domain onto a single
1920×1080 (16:9 Full HD) canvas:
- **Garmin G1000 MFD (`0b852ee1-6006-4e2b-9cdf-e397b3f16ab1`):** `x=40, y=100,
  w=1100, h=715`. Configured with `Display unit function = MFD`. Features a
  transparent active screen cutout in `background.png` so popout X-Plane MFD
  windows or native Air Manager display streaming can show through.
- **Garmin GMA 1347 Audio Panel (`1337420b-7420-4843-80eb-9d10c57a97d1`):**
  `x=1155, y=100, w=121, h=715`. Positioned immediately to the right of the MFD
  (15 px bezel clearance), maintaining exact NAV III panel authenticity.
- **Direction Finder:** `x=1360, y=100, w=460, h=460` (square 1:1 aspect ratio).
  Centered in the mission avionics stack.
- **Technisonic TDFM-136B VHF-FM Radio (`26df5da8-8ce7-4255-bb0e-520453134609`):**
  `x=1310, y=580, w=560, h=294` (preserving native 1.905 aspect ratio). Centered
  directly beneath the DF head.

### Dual-Layout Architecture
To support both legacy Becker 517 and modern RHOTHETA RT-600 training scenarios
without manual reconfiguration, the panel defines two layouts in `info.xml`:
1. **Layout 1 (`e1c8e710-5646-49e1-931f-4aeeb51e4491`):** `MO Station (Becker 517)`
   — fitted with the Becker SAR-DF 517 head (`faefb90d-5704-48c7-8deb-c683d94b4eb3`).
2. **Layout 2 (`e2c8e710-5646-49e1-931f-4aeeb51e4492`):** `MO Station (RT-600)`
   — fitted with the RHOTHETA RT-600 head (`d783d409-9bfa-49f2-ad5d-883af29848d6`).

### Deployment & Verification
- Repository location: `panels/cap-c182t-mo-station/`
- Air Manager installation: `/home/ron/Air Manager/panels/OPEN_DIRECTORY/a4c8e710-5646-49e1-931f-4aeeb51e4490/`
- Asset generator: `panels/cap-c182t-mo-station/generate_assets.py` (builds
  custom 1920×1080 dark cockpit background with MFD cutout and composite previews).
- Automated test suite: `tests/test_panel.py` validates XML schema, geometry bounds,
  non-overlapping hit regions, MFD property settings, and instrument UUID existence (6/6 pass).
- Deployment script: `scripts/deploy_mo_panel.py` provides single-command deployment
  to local Air Manager (`python3 scripts/deploy_mo_panel.py`), custom targets (`--target`),
  asset regeneration (`--regenerate`), and portable ZIP packaging (`--zip` -> `cap-c182t-mo-station.zip`)
  for secondary computer deployment.

### Streaming Architecture (Air Player & X-Plane 12)
- **Air Player Network Streaming:** Air Manager 4.2 broadcasts panel availability
  over the local subnet; secondary laptops or tablets running Air Player 4.2
  auto-discover the panel and render the complete interactive MO station.
- **G1000 MFD Display Video Feed:** Verified that Air Manager 4.2 supports
  native offscreen video texture streaming for X-Plane 12 via `video_stream_add()`.
  The G1000 bezel instrument (`0b852ee1-6006-4e2b-9cdf-e397b3f16ab1/logic.lua:95`)
  automatically invokes `video_stream_add("xpl/G1000_MFD", 416, 100, 2048, 1536)`
  when running against X-Plane 12 with the Sim Innovations flightsim plugin.
- **Multi-Monitor / Popout Fallback:** For non-streaming environments (e.g. X-Plane 11
  or multi-head desktop), `background.png` incorporates a pixel-aligned transparent
  cutout `(196, 136, 787 × 592)` allowing native X-Plane popout windows placed behind
  the Air Manager bezel to show through cleanly.


## 2026-09-07 — Integration: N499CP Flight Planner & CAP V-SAR Bridge

**Status: implemented & documented.** Integrated the N499CP Flight Planner
(`flight-planner-n499cp-v2`, deployed at `flightplanner.rpc-cyberflight.com`)
with the CAP V-SAR simulation and exercise console ecosystem (`ms01:8700`).

### Integration Architecture & Operational Workflow

Pre-flight planning and in-flight search pattern execution are now unified:

1. **Search Pattern Generation:**
   - Added standard CAP search pattern algorithms into the flight planner:
     - **Expanding Square (SS):** Geodesic outward expansion from a known datum
       (LKP / ELT alert position) with configurable track spacing (0.5–2.0 nm),
       initial heading, and turn direction.
     - **Creeping Line (CS):** Orthogonal cross-corridor sweeps along an advance
       axis, ideal for route, canyon, or river-bed searches.
     - **Parallel Track (PS):** Systematic rectangular grid sweeps across CAP
       quadrangles.
2. **Export Bridges:**
   - **X-Plane 12 `.fms` Flight Plan Generator (`/api/sar/export-fms`):**
     Exports departure, enroute fixes, and generated search pattern waypoints
     directly into X-Plane 11/12 standard `.fms` format (FMS version 1100),
     ready for loading into the aircraft's G1000 NAV III or FMS catalog.
   - **V-SAR Console Push Bridge (`/api/sar/export-vsar`):**
     Transmits planned search corridors, waypoints, and sortie parameters
     directly to the exercise console on `ms01:8700` (`/api/scenarios` and
     `/api/messages`), allowing the Mission Base staff and MRO to monitor the
     planned route against live radar positions.
3. **Flight Performance & Safety Synchronization:**
   - Leverages the flight planner's Cessna POH performance profile to compute
     transit fuel, time-on-station (TOS) before bingo fuel, and mandatory CAP
     reserve fuel.
   - Provides verified fuel metrics for Mission Observers reporting 30-minute
     "Ops Normal" updates to Mission Base.

## 2026-09-07 — Design proposal: Mission Base WebUI virtual radio (pymumble) and MRO console

**Status: proposed.** Architecture and UI specification for integrating a virtual
Civil Air Patrol Mission Radio Operator (MRO) communications console and
enhanced mission-base situational tools into the browser-based exercise console
(`capvsar-exercise` at `ms01:8700`), fulfilling Layer 3 and Layer 4 of the CONOPS
(CONOPS §Four layers, Mode B/C).

### Architecture: backend pymumble audio bridge vs client-side mumble-web

Selected approach: **backend `pymumble` bridge integrated into the FastAPI
console service**, rejecting a standalone web client / iframe.

- **Decision rationale:** The MRO radio must look, feel, and operate like an
  authentic piece of radio hardware (e.g., a desktop Motorola APX/XTL base
  station or a Telex IP-224 dispatch console) rather than a generic chat tree.
  A direct browser WebRTC/WebSocket audio pipeline into FastAPI running
  `pymumble` allows the radio faceplate to completely control audio routing, PTT
  timing, squelch behavior, and channel transitions without exposing Mumble
  internals to the trainee.
- **Audio pipeline:**
  1. Trainee mic audio captured via Web Audio API, encoded (PCM 16-bit / Opus),
     and streamed over WebSocket to FastAPI endpoint `/api/radio/stream`.
  2. The FastAPI service runs an asynchronous `pymumble` client instance connected
     to `capvsar-mumble:64738`.
  3. Channel selector commands in the UI send lightweight JSON control packets
     (`{"action": "set_channel", "channel": "Mission Net PRIMARY"}`) over the
     control WebSocket, instructing `pymumble` to move between channel rooms.
  4. Incoming audio from `pymumble` is packetized and pushed back over the
     WebSocket to the browser, with real-time RMS calculations streamed for the
     RX signal/VU meters.
  5. Audio is played through the Web Audio API with simulated bandpass filtering
     (300 Hz – 3.4 kHz speech range) and authentic squelch-tail burst synthesis on
     PTT unkey.

### Virtual MRO radio faceplate specification

The UI component on `/base` will be styled as a dedicated rack/desktop base
transceiver console:

1. **Rotary Channel / Net Selector:**
   - Switches between Mumble channel trees directly mapped to CAP SAR structure:
     - `Mission Net PRIMARY` (Air-1 tactical, routine position and ops normal)
     - `Mission Net ALTERNATE` (Air-2 tactical, dedicated DF search traffic)
     - `Mission Base` (Internal mission base coordination)
     - `Briefing Room` (Pre-flight briefings)
2. **Push-To-Talk (PTT) with hardware-like interlocks:**
   - Large physical-style PTT button with active press-and-hold behavior.
   - Configurable keyboard hotkeys (default: `Spacebar` when focus locked, or
     dedicated thumb key).
   - Dynamic **TX Tally LED** (red) and **RX Activity LED** (green).
   - Audio VU / signal-strength LED bar.
   - 60-second stuck-mic timeout disconnect with audible and visual warning.
3. **Dual-Watch / Guard Receiver:**
   - Secondary audio channel listener continuously monitoring Guard (121.5 MHz /
     National Guard VHF) at user-adjustable balance while working Primary.
4. **Hardware adjustments:**
   - Volume knob (headset gain), Squelch knob (noise gate threshold), and Mic
     Gain adjustment.

### Mission Base situational awareness and workflow enhancements

1. **Integrated CAPF 110 / ICS 309 Radio Communications Log:**
   - Sits immediately adjacent to the virtual radio.
   - One-click macro buttons for rapid entry:
     - `RADIO CHECK`: logs time, station, and signal report.
     - `OPS NORMAL`: logs time, fuel remaining, Hobbs, and altitude.
     - `IN-GRID` / `OUT-OF-GRID`: logs search area entry/exit.
     - `BEARING REPORT`: parses reported bearing directly into the map plotter.
   - Live CSV/PDF export for post-mission debriefing.
2. **30-Minute Ops Normal flight tracking clocks:**
   - Per-aircraft countdown timers starting at 30:00 per CAP regulations.
   - Visual state alerts:
     - Green (30:00–10:00 remaining): Normal operations.
     - Amber (10:00–00:00 remaining): Prompt MRO to poll aircraft.
     - Flashing Red (< 00:00): Overdue aircraft alert initiating communications
       search procedure.
   - Single-click acknowledgement resets the 30-minute interval and logs to the
     ICS 309 table.

### Aeronautical map & tactical plotting enhancements (`charts.js`)

1. **CAP Standard SAR Grid overlay:**
   - Overlay layer for standard 15' × 15' quadrangle Search and Rescue grids on
     the VFR sectional, with A, B, C, D quadrant subdivisions.
2. **Multi-bearing triangulation & probable fix area:**
   - Automatically computes line intersections when multiple bearings are logged
     (from multiple aircraft or one aircraft on different legs).
   - Renders a semi-transparent confidence ellipse / probability polygon on the
     aeronautical chart to guide search retasking.

### Instructor console additions (`/`)

1. **DF Head Telemetry HUD:**
   - Mirror display showing real-time readouts from the aircraft's active DF head
     (Becker 517 or RT-600): tuned frequency/channel group, relative bearing,
     signal strength bar, squelch open/closed state, and cone-of-confusion flag.
   - Gives the instructor immediate insight into the trainee's instrument cues
     before they initiate flight adjustments.

## 2026-09-07 — Air Manager installed and running

**Status: implemented.** Air Manager itself is now installed on this machine
and running, closing the "Air Manager is not installed" caveat repeated
throughout the entries below. **No instrument has been loaded into it yet** —
that is the next bring-up step, not done here.

### 4.3 does not exist for Linux

Asked for specifically: Air Manager 4.3. Checked the vendor's real application
catalogue (`https://api5.siminnovations.com/application/all`, which is what
`docs.siminnovations.com`'s own download-widget JavaScript calls) rather than
guessing from the download page, since that page only lists the current Air
Manager 5 line — Air Manager 4 has been moved to
`docs.siminnovations.com/older_versions/`.

The catalogue has exactly one 4.3 build: `Air Manager 4.3 Home use (BETA 1).exe`
— **Windows only**. No Linux, no Mac, and it is a beta. The newest stable Linux
build is **4.2.12**, matching the copy already sitting in
`~/Documents/Air Manager 4.2 Home use/` (downloaded moments before this
session). Installed that instead of chasing a Windows beta onto a Linux box,
and it is also the right call independent of the version mix-up: `AM4_COMPAT.md`
already commits this project's instruments to the **Air Manager 4 API subset**
specifically because spare AM4 (not AM5) licences exist, so 4.2.12 is squarely
the target, not a fallback.

### Missing native dependencies, resolved without root

`libAppBase.so` (the native core inside the Home Use bundle) linked against
five libraries Ubuntu 26.04 no longer packages under those sonames — `openssl
1.1`, `freeimage3`, and `libzip4` are past end-of-life or renamed, and pulling
freeimage's own image-format plugins in turn needed Imath, OpenEXR, JPEG-XR and
libraw. None were installed, and this account has no passwordless sudo, so
`sudo ./setup.sh` (the vendor's own installer script) could not run
non-interactively.

Resolved without touching the system or asking for a password: each package
was fetched with `apt-get download` (no root needed — it only fetches the
`.deb`) or, for the fully-removed `libssl1.1`, from `archive.ubuntu.com`'s old
pool exactly as `setup.sh` itself does on Mint. Each was extracted with
`dpkg-deb -x` into `Air Manager 4.2 Home use/deps-lib/`, and `AirManager.sh` now
puts that directory on `LD_LIBRARY_PATH` before starting `./Bootloader`. Nothing
outside that one application folder was modified. The udev rule `setup.sh` also
installs is for physical Knobster USB hardware, which this machine doesn't
have, so it was skipped rather than spending a root prompt on it.

Full dependency chain resolved, package sources:

| Missing | Ubuntu package | Why it's gone |
|---|---|---|
| `libcrypto.so.1.1`, `libssl.so.1.1` | `libssl1.1` | Removed from the archive; fetched from the old pool directly |
| `libfreeimage.so.3` | `libfreeimage3` | name unchanged, just not installed |
| `libzip.so.4` | `libzip5` (symlinked) | only `.so.5` ships now |
| `libImath`/`libIex`/`libOpenEXR*` | `libimath-3-1-29t64`, `libopenexr-3-1-30` | FreeImage's OpenEXR plugin |
| `libjxrglue`/`libjpegxr` | `libjxr0t64` | FreeImage's JPEG-XR plugin |
| `libraw*` | `libraw23t64` | FreeImage's camera-RAW plugin |

### Verified running

`./AirManager.sh` launches cleanly in a **clean environment** (`env -i`, no
inherited variables) and opens real X11 windows — confirmed with
`xwininfo -root -tree`, not just a clean exit code: "Activate Air Manager"
then "Air Manager - Home Use 4.2.12", the latter growing from a small
first-run size to its normal window once past the activation prompt.

A full screenshot could not be captured to attach here — the compositor
(Wayland with XWayland) refused a whole-screen X11 grab
(`X get_image failed: error 8`) for both `PIL.ImageGrab` and a direct X11 root
capture, and no screenshot utility (`grim`, `gnome-screenshot`, `scrot`,
`xwd`) is installed to try a window-specific capture instead. Window titles
via `xwininfo`, not pixels, are what's verified here.

### Left for the user

- **License activation.** The "Activate Air Manager" dialog appeared on first
  launch and needs this machine's Sim Innovations account — not something to
  attempt without the account owner. It closed on its own once the main window
  came up; whether that means activation completed or was merely dismissed
  wasn't visible without a screenshot, so treat it as unconfirmed and check the
  live window.
- **Loading an instrument.** Air Manager running is necessary, not sufficient,
  for the bring-up checklists earlier in this log. Next step, not done here:
  open one of `instruments/*/` in the Air Manager editor and work through
  power/startup, every knob and button, page changes, hold actions, tuning,
  dimming, and live bearing updates.
- The X-Plane flight-simulator plugin (separately versioned — see
  `AM4_COMPAT.md`) is still not installed; Air Manager running standalone
  cannot exercise `cap/df/*` yet.

## 2026-09-07 — Independent verification of post-review fixes

**Status: verification completed; one corrected finding and two gaps remain.**
Checked the follow-up entry and current implementation against the detailed
TDFM manual section and Sim Innovations' `switch_add` examples. Re-ran the Lua,
engine, faceplate, preview-reproduction, and Python syntax checks.

### Correction to the earlier review

- The earlier claim that a two-position Air Manager `switch_add` requires a
  literal third image argument was wrong. `img_pos_n` denotes any additional
  position images; Sim Innovations' own two-state example passes two images and
  then the geometry. The current seven-argument call shape is valid.
- The earlier claim that TDFM channel entry commits automatically after the
  third digit was also wrong. TDFM §3.1.1 lists ENTER (`#`) as the key that
  accepts an entry and ESC (`*`) as the key that abandons it. Outside the entry
  editor, the same ENTER key performs its Level-1 home/current toggle. The
  current entry routing matches that behavior.

### Remaining TDFM switch defect

- Although the `switch_add` argument count is valid, the callbacks still do not
  implement the documented switch contract. Air Manager supplies the switch's
  **current** position and the requested direction; in the instrument-controlled
  pattern the switch does not move automatically. Each TDFM callback accepts
  only `position`, ignores `direction`, stores the current state again, and no
  switch ID is retained for `switch_set_position`. The MN/GD, G1/G2, and HI/LO
  toggles therefore still need runtime correction. Existing static tests do not
  exercise this interaction.

### Remaining GMA display gap

- MAN SQ gating and separate pilot/crew values were fixed, but the GMA still has
  no dynamic VOL/SQ annunciators. `VOL` and `SQ` are static faceplate text and
  `vol_mode` does not control any image, so the user cannot see which adjustment
  mode is selected as the manual requires. This part of the earlier VOL/SQ
  finding was neither fixed nor included in the scoped-out list.

### Verification results

- Lua check: 14 files pass.
- Engine tests: all 43 pass.
- Faceplate tests: all 81 pass.
- Propagation-engine Python syntax check passes.
- Preview/resource regeneration is byte-identical.
- Air Manager remains unavailable, so the switch interaction cannot be executed
  here; the remaining switch finding is based on the vendor's callback examples.

## 2026-09-07 — Post-integration review: findings resolved

**Status: implemented.** Every finding in the review below was checked against
the manuals before anything was changed. Most were confirmed and fixed; two were
found to be wrong and the code left alone; the rest are scoped out and listed.

### Verified wrong — no change made

- **TDFM `switch_add` "missing third image".** The Air Manager API reference
  gives a two-position switch as `switch_add(img_pos_0, img_pos_1, x, y, width,
  height, position_callback)` — two images required, the callback optional. The
  `img_pos_n` in the syntax line is variadic notation for further positions, not
  a literal third parameter. Passing `nil` as a third image would declare a
  **three**-position switch and would be the defect, not the fix. The existing
  calls are correct.
- **TDFM direct channel entry.** §3.1.1 is explicit that during a CHAN entry the
  valid edit keys are digits, then "accept the entry and continue" (ENTER) or
  "abandon the entry and exit" (ESC). Table 3-1's "# ENTER Toggle Home/Current"
  is the Level-1 function of `#` when no entry is in progress. The code already
  does both, and waiting for ENTER is correct.

### Runtime defect fixed

- **Becker page 6 raised a Lua error.** `freq_edit_field` cycled over all five
  rows of `training_freqs`, but the fifth is the SCAN knob position and carries
  no `min`/`max`, so turning the value knob on it compared a number with `nil`.
  §1.3.1 gives four adjustable training channels, so the editable count is now
  derived from the rows that actually have a range, page 6 lists only those, and
  the value knob refuses a row without one. Listing four rows instead of five
  also clears the status line the fifth was overlapping.

### Receiver model corrected against the technical data

The Becker manual states its receiving frequencies outright, and the earlier
model had two things wrong:

| | Manual | Was modelled as |
|---|---|---|
| Emergency C/S | **406.025 only** | 406.025 and 406.028 |
| Training band | **400.000–409.975 freely adjustable** | restricted to the emergency channels |

406.028 appears nowhere in the Becker manual. And because the training band
covers the whole 406 range, the head is freely tunable there — the engine was
refusing the 517 its own default 406.037 training frequency. `head_can_receive`
now takes the operating mode.

The RT-600 (§2.2.3) does not tune individual channels at all. It selects one of
**seven CPSAR groups**, each covering two or three of the 3 kHz channels
simultaneously: CPSAR1 "022-028" (A, B, C) through CPSAR7 "073-076" (R, S). The
inclusive 406.022–406.076 grid is **nineteen** channels, A through S — the
previous 18 came from stopping at 406.073 and omitting 406.076. The instrument
now presents the seven groups and tells the engine the span each covers, through
a new `cap/df/rx_span_hz`.

The exercise's headline difference is therefore sharper than before: an
Emergency-mode Becker on its single 406.025 channel is deaf to a beacon on
406.037, while one RT-600 group selection covers 406.031, 406.034 and 406.037 at
once without retuning.

Scan also no longer assumes the emergency pair. §1.3.1 gives 121.500 and 243.000
as the frequencies surveilled between bursts, but in Training mode those are
whatever the crew adjusted the training channels to, and the engine cannot guess
them — so the panel now writes them as `cap/df/scan_alt1_hz` and
`cap/df/scan_alt2_hz`, defaulting to the emergency pair if a panel never does.
The burst leg follows the tuned channel rather than a hardcoded 406.025.

### Becker: STORE now does what the manual says

§3.3.1(5): pressing STORE switches off the 3 kHz tone superimposed on an AM
signal, "enables better hearing of a signal, **meanwhile bearing isn't possible
anymore**". It previously only drew `3K-`. The bearing now stops while the tone
is suppressed, and the pages say why. The same paragraph notes that on the
maritime FM band a filter already removes the tone, so the key is inert there.

### TDFM: squelch LEDs are radio indicators

§1.1.1(1): "LED channel squelch indicators – light on signal received". They are
on the radio, not the audio panel, and were being blanked whenever COM3 audio was
deselected. That hid exactly the evidence the trainee is meant to find — a lit
squelch LED with silence in the headset is the CAP guide's "nearly every 'the
radio is broken' report in flight is an audio panel selection". They now follow
the receiver regardless of audio routing.

### GMA 1347: three behaviours corrected

- **Split COM annunciation.** §SPLIT COM: "During split COM operation, the COM1,
  COM1 MIC, COM2 and COM2 MIC keys are annunciated and thus active." All four now
  light. The annunciators report the panel's state; this seat's restriction to
  COM2 audio stays where it belongs, in the audio path.
- **A COM MIC key selects the matching COM audio.** §TRANSCEIVERS: "COM audio
  can be selected by either pressing the desired COM key or by pressing the
  corresponding COM MIC key. If selected in this manner, the audio source
  remains selected independently of the active microphone source selection."
- **The VOL/SQ knob press is gated by MAN SQ.** "When the MAN SQ key is
  deselected (i.e., auto-squelch is active), pressing the VOL/SQ knob has no
  effect on the VOL/SQ selection state." Deselecting MAN SQ also returns the
  selection to volume. The pilot and copilot rings now carry separate levels
  rather than sharing one value, per §6A.2.

### Validation performed

- `python3 scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua`
  — 14 files, all OK.
- `python3 tests/test_engine.py` — **43 checks**, up from 33. New: Becker
  Emergency vs Training coverage, its single emergency channel, the 19-channel
  grid, a CPSAR group hearing all three of its channels and not reaching into
  the next, and a training scan finding a beacon on a training channel.
- `python3 tests/test_faceplate.py` — **81 checks**, up from 68. New: the Becker
  training table has four adjustable rows and a range-less SCAN row, page 6
  clears the status line, the tone gate exists, and the seven CPSAR groups tile
  the 19-channel grid exactly once with no gaps or overlaps.
- `python3 scripts/make_previews.py` regenerates byte-identically.

### Not done — scoped out, still open

These are feature work rather than defects, and are left for a later pass:

- The RT-600's full FRQ page control flow: MEM1–4 / Work / FIX / CPSAR selection
  with PAGE, MHz and kHz editing on VOL and SQL, band change on F2, and CPSAR
  scan. The instrument still presents a flat selection list.
- Gating COSPAS-SARSAT decode on the RT-600's decode window being open. The
  engine still decodes continuously, so a frame received before the window was
  opened can be displayed.
- Real audio behaviour behind PA, TEL, SPKR, HI SENS, MAN SQ and PLAY on the
  GMA, and behind main/guard volume, squelch defeat, brightness and scan on the
  TDFM. All are still local lamp and display state.
- TDFM back/forward scrolling: still one memory per press, without the
  continuous acceleration, wrap and skip-unused of the real keys.

### Remaining limitations

- **Air Manager is still not installed, so none of this has been run.** No
  runtime validation was performed and none is claimed. In particular the
  `switch_add` finding above was settled from the published API reference, not
  by loading the instrument.
- The wing-null / airframe-shadowing entry below remained research only at this
  point in the history; it is superseded by the implementation entry above.

## 2026-09-07 — Post-integration instrument review

**Status: review completed; findings unresolved.** Reviewed the current Becker
SAR-DF 517, RHOTHETA RT-600, TDFM-136B, GMA 1347, and propagation-engine code
against the manuals after the artwork integration. No fixes were made as part of
this review.

### Runtime defects

- The TDFM's three `switch_add` calls omit the required third switch-image
  argument (`nil` for a two-position switch). Coordinates and the callback are
  consequently passed in the wrong argument positions and the instrument is
  expected to fail during Air Manager loading.
- Becker page 6 cycles through the `SCAN` row as an editable training frequency,
  but that row has no `min` or `max`. Turning the value knob on that row compares
  a number with `nil` and raises a Lua runtime error. The fifth row also overlaps
  the page's bottom status text.

### Receiver and frequency-model inaccuracies

- The Becker UI permits the manual's freely adjustable 400.000–409.975 MHz
  training frequency and defaults it to 406.037 MHz. The propagation engine
  nevertheless rejects every Becker Cospas-Sarsat frequency except 406.025 and
  406.028 without considering Emergency versus Training mode. Becker scan is
  likewise hardcoded to the emergency frequencies instead of using the selected
  training frequencies.
- The RT-600 manual defines seven CPSAR receiver settings, each covering two or
  three 3 kHz beacon channels simultaneously. The instrument instead presents
  individual 3 kHz frequencies and the engine applies a single-channel ±1.5 kHz
  tolerance.
- The RT-600 list ends at 406.073 MHz and omits 406.076 MHz. The inclusive
  406.022–406.076 grid contains 19 channels (A through S), not the 18 stated in
  the Lua comments, engine comments, and `docs/DATAREF_CONTRACT.md`.
- The RT-600 FRQ page is a flat frequency list. The real control flow selects
  MEM1–4, Work, FIX, or one of seven CPSAR groups with PAGE; VOL and SQL edit MHz
  and kHz; and F2 changes bands. Those selection/edit modes and CPSAR scan are
  absent. Scan requests currently reach engine logic hardcoded for the Becker
  406/121.5/243 scan.
- The propagation engine decodes Cospas-Sarsat bursts continuously. The RT-600
  can therefore display a frame received before its Decode window was opened,
  although the manual says decoding is possible only while that window is active.

### GMA 1347 behavior gaps

- Split COM routes copilot audio to COM2, but its annunciation is wrong: COM1 and
  COM1 MIC go dark. The manual requires COM1, COM1 MIC, COM2, and COM2 MIC all to
  be annunciated and active in split operation.
- Selecting a COM MIC does not update the corresponding COM audio selection or
  annunciator. The manual says the matching audio key is selected automatically.
- VOL/SQ can be toggled while MAN SQ is off, although the manual says a knob press
  has no effect in auto-squelch and VOL remains selected. The pilot and copilot
  rings share one internal volume/squelch value, and the panel has no dynamic VOL
  or SQ annunciation.
- PA, TEL, SPKR, HI SENS, MAN SQ, and PLAY are local lamp/state approximations and
  do not provide their stated audio functions.

### TDFM-136B behavior gaps

- Direct channel entry waits for `#` after three digits. The manual says the
  three-digit entry itself selects the memory and reserves ENTER for toggling
  home/current.
- Back/forward changes one memory per press. The real keys scroll continuously,
  accelerate while held, wrap, and skip unused memories.
- The channel squelch LEDs are hidden when COM3 audio is deselected. They are
  radio receive indicators and should still show a received signal, allowing the
  trainee to diagnose an audio-panel routing error.
- Main/guard volume, squelch defeat, display brightness, and mission-channel scan
  currently change only local state or display characters; they do not affect
  mission audio or reception.

### Becker behavior gap

- STORE's 3 kHz tone-suppression state only draws `3K-`. It does not suppress an
  audio tone or inhibit bearing, despite the manual stating that bearing is not
  possible while the tone is suppressed.

### Validation and test gaps

- `python3 scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua`
  passes all 14 files.
- `python3 tests/test_faceplate.py` passes all 68 checks.
- `python3 tests/test_engine.py` passes all 33 checks.
- `python3 scripts/make_previews.py` regenerates resources and previews
  byte-identically.
- These checks cover syntax, static geometry, assets, and the behavior currently
  encoded in the engine tests. They do not validate Air Manager API signatures
  or the manual-level operating semantics above. Air Manager remains unavailable
  on this machine, so runtime integration is still untested.

## 2026-09-07 — MO station artwork and Lua integration (TDFM-136B, GMA 1347)

**Status: implemented.** Brings the two Mission Observer instruments to the
layered-artwork standard the DF heads were moved to earlier today. Validated as
far as is possible without Air Manager.

### Faces corrected against the manuals

Both instruments had the wrong proportions, which the reference figures settle:

| Instrument | Was | Now | Authority |
|---|---|---|---|
| TDFM-136B | 750 x 320 (2.34) | 800 x 420 (1.905) | Fig 1-1 plate measures 1044 x 545 px, aspect 1.916 |
| GMA 1347 | 240 x 740 (1 : 3.08) | 240 x 1422 (1 : 5.925) | §6A.2: "1.3 inches in width and 7.70 inches in height" |

The GMA was roughly half as tall as the real unit. `info.xml` preferred sizes
updated on both.

### Artwork

Same three layers as the DF heads. `resources/faceplate.png` carries the
housing, screws, display recess, group outlines and every silk-screened legend;
the live display stays a Lua canvas; everything that moves, swaps or lights is
its own image. Keys that carry a printed legend get their own image pair,
because the cap moves when pressed — twelve for the TDFM keypad, twenty-one for
the GMA. Knobs carry no index stripe, for the same reason as the DF heads:
`dial_add` does not rotate its image.

New generator `scripts/make_panel_artwork.py`, which **parses the geometry
blocks in the new `lib/tdfm_panel.lua` and `lib/gma_panel.lua`** rather than
repeating them, so artwork and hit regions cannot drift apart.

### Fidelity corrections from the reference figures

TDFM-136B, Figure 1-1:

- **Toggles are labelled above and below the lever** — MN over GD, G1 over G2,
  HI over LO. The draft drew a single "MN/GD" caption underneath.
- **Keys 2, 4, 6 and 8 print their digit inside a cursor arrow** and carry no
  word. The draft labelled them UP / BACK / FWD / DOWN.
- Squelch LEDs sit **inside the display bezel**, one at the start of each line.
- Corner slotted screws plus two small cross screws at mid-height; PGM data port
  drawn as the seven-pin connector it is.
- The preview's display now renders the **lowercase** mode and squelch-mode
  characters (`w`/`n`/`D`, `x`/`t`/`c`/`m`/`n`/`g`). It was uppercasing them,
  which erased a distinction `lib/tdfm_display.lua` exists to preserve.

GMA 1347, Figure 6A.2.1 and §6A.2:

- **Annunciator triangles are white, not green.** "The triangular key annunciator
  lights are white when illuminated."
- **The volume control is a concentric pair, not one knob.** The small knob is
  the pilot channel, the large one copilot and passenger; both are now wired,
  and only the outer ring writes the copilot volume dataref.
- **Row 9 has no right-hand key** — an ambient light sensor sits there. The key
  table is 21 entries, not 22.
- The invented status line across the top of the panel is gone. Table 6A.3.2's
  isolation states are already readable from the PILOT and COPLT annunciators
  (neither lit = ALL, PILOT = PILOT, COPLT = COPILOT, both = CREW) and split COM
  from the COM 1/2 annunciator. Reading the lamps is the thing being taught, and
  the real panel has no text. No state was lost, only a non-prototypical readout.
- The GMA now has no canvas at all, and no longer ships `lib/lcd.lua`; it is a
  panel of lamps and keys.

### Defect found in the geometry parser

`scripts/make_panel_artwork.py` first read geometry with a bare `M.NAME\s*=`
search. Against Lua's multiple assignment — `M.KEY_X0, M.KEY_Y0 = 400, 202` —
that matches the *second* name and returns the *first* value, so the TDFM keypad
was generated 198 units too low with the wrong key height and row pitch. The
parser now splits the line and matches by position. `make_df_artwork.py` reads
only single assignments, and now rejects a multiple assignment loudly instead of
mis-parsing it.

### Preview pipeline

`scripts/make_artwork.py` was **deleted**: it generated generic knobs, keys,
toggles and LEDs that no instrument uses any more, and keeping it was the same
silent-overwrite hazard that was guarded for the DF heads. `make_previews.py` is
now a front-end that runs the two generators and draws nothing itself. One
generator per instrument, no second copy of any geometry.

Superseded resources removed: five from the TDFM, three from the GMA, plus the
GMA's unused `lib/lcd.lua`.

### Validation performed

- `python3 scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua`
  — 14 files, all OK.
- `python3 tests/test_faceplate.py` — **68 checks**, extended from 26 to cover
  all four instruments: every geometry block parses; no control overlaps another
  or a display; the TDFM's LEDs sit inside the window bezel and clear the
  character matrix; each GMA annunciator sits above its own key and the
  concentric knob nests inside the outer ring; every named image ships at the
  expected size with no orphans; no instrument ships an unused library; both new
  faces match the dimensions their manuals give; `info.xml` agrees with each
  face.
- `python3 tests/test_engine.py` — 33 checks pass. Engine untouched; run as a
  regression guard.
- `python3 scripts/make_previews.py` reproduces every resource and preview
  byte-identically.
- Both previews inspected side by side against their manual figures.

### Remaining limitations

- **Air Manager is still not installed, so none of this has been run.** No
  runtime validation was performed and none is claimed. The bring-up items
  specific to this change are: the GMA has 21 button hit regions plus 21
  annunciator images on a 240 x 1422 face, so confirm `img_add` layering order
  puts annunciators above the faceplate and below nothing that matters; and the
  concentric knob relies on the inner `dial_add` being added after the outer one
  to take clicks inside its own area.
- The TDFM's Level-1 map still leaves keys 7 (FREQ) and 9 (SQL) inert. That is
  pre-existing and deliberate — they are edit commands the CAP guide tells the
  observer not to touch — and the caps are drawn because the real panel has them.
- The TDFM encoders are drawn without the index line Figure 1-1 shows, for
  consistency with the DF heads: Air Manager cannot rotate a dial image, and a
  static index on a control the user drags reads as broken.
- The previews' displays are Python mirrors of the Lua layouts, not captures.
  They share the geometry constants but not the drawing code.
- No engine, dataref, or propagation behaviour was changed by that artwork
  revision. Wing blanking was implemented later, as recorded above.

## 2026-09-07 — Becker SAR-DF 517 faceplate artwork and Lua integration

**Status: implemented.** Artwork produced, integrated into the instrument's
rendering path, and validated as far as is possible without Air Manager.

Replaces the flat canvas-drawn bezel on the Becker SAR-DF 517 with layered
artwork built to the manual's measured geometry, and rewires the instrument to
use it. The RHOTHETA RT-600 shares `lib/dcu.lua`, so it was carried along with
its own branding and behaviour intact rather than left broken.

### Artwork

Three layers, which is what lets the printed lettering be smooth while the
display stays a dot matrix:

- `resources/faceplate.png` — housing with clipped corners, circular face
  inset, four mounting screws, recessed LCD surround, and every silk-screened
  legend in Liberation Sans: `Clr` / `Store` / `Rep`, curved `SQL` and `Page`
  with their arrows, `DIM` linked from Rep to Page, the +/- rotation marks
  around the lower knobs, the Rhotheta / SAR-DF 517 / BECKER identification
  lockup, and `ON/OFF`.
- `resources/knob.png`, `button.png` / `button_pressed.png`,
  `power.png` / `power_pressed.png` — the movable controls. ON/OFF is a
  separate moulding from the three domed keys, as Fig 3-3 shows.
- The 128x64 LCD stays a live Lua canvas.

Nothing dynamic is baked into the faceplate: no bearing, frequency, status or
knob. The knobs carry no index stripe — neither the manual figure nor the CAP
photographs show one, and `dial_add` does not rotate its image, so a painted
index would have been a mark that never moved.

**No image-generation tool was available in this session**, so the artwork is
drawn procedurally with Pillow rather than generated. The approved concept in
`output/becker-visual-study/after.png` was used as the visual target — matte
charcoal, clipped corners, circular inset, scalloped knobs, metal screws,
recessed LCD, restrained lighting — and the Becker manual was followed wherever
the two disagreed. That directory is now a record of the study, not artwork.

### Geometry

The chassis grew from a 470-unit face to 520 with an integer LCD scale of 3, so
the 128x64 framebuffer maps to 384x192 with even dots. All positions are
measured off `docs/figures/b517_p29_bearing_controls-29.png`; the measurements
are tabulated in `docs/SOURCES.md`. `info.xml` preferred sizes updated on both
heads.

`scripts/make_df_artwork.py` **parses the marked geometry block in
`instruments/becker-sar-df-517/lib/dcu.lua`** rather than repeating it, so the
artwork and the control hit regions cannot drift apart. If the block stops
parsing the script fails instead of guessing.

### Integration defects found and fixed

- The radial bearing pointer was drawn from the rose centre and ran straight
  through the bearing digits, making them unreadable. It now starts where the
  ray leaves the text block, which is how Fig 3-3 draws it.
- The page-1 CONE / MASK annunciator at (86,48) overlapped the band frame. The
  reason now appears in place of the bearing — where the operator is already
  looking — and pages 2 and 3 say why there is no fix rather than just that
  there is none.
- The right-hand status column at x=97 lost the last glyph of `OFS:+000` and
  `LS:00:00` off the 128-dot edge; moved to 94. `CHNL.(16)` overflowed the band
  frame; the frame was widened.
- `draw_signal_bar` in the 517 duplicated `dcu.draw_bar` with a different
  squelch marker. Removed; both heads now use the one drawing.

### Fidelity improvements from the manual

- Compass rose rebuilt: outer dot ring, graduation ring clear of the bearing
  block, cardinal ticks, and §3.3's spread markers — solid at the averaged
  bearing, hollow at each un-averaged extreme. `cap/df/spread` now has a display
  that means something. Display change only; the dataref is unchanged.
- `MOUNT:` with a tee glyph (upright TOP, inverted BOTTOM) replaces `MNT:TOP`.
- Page-1 band frame carries the two-line caption Fig 3-3 shows, so the marine
  channel reads `SEA-BAND` / `CHNL.(16)`.
- Row of six page marks under the PAGE field, active one solid.
- Signal bar gained its 10% graduations and the manual's stub-and-block squelch
  marker.

### Preview pipeline

`preview.png` for both heads is now composited from exactly the layers Air
Manager stacks, by the same script that makes them. The two paths that could
have silently restored the obsolete appearance are closed: the DF branch of
`scripts/make_previews.py` was deleted and delegates instead, and
`scripts/make_artwork.py` refuses to write into the two DF folders. Running
`make_previews.py` reproduces the DF previews byte-identically.

Seven legacy resources per DF head (`knob_small`, `led_*`, `toggle_*`, `key*`)
were unreferenced after the rewire and were removed.

### Validation performed

- `python3 scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua`
  — 13 files, all OK.
- `python3 tests/test_engine.py` — 33 checks pass. Engine and dataref interface
  were not touched; run as a regression guard.
- `python3 tests/test_faceplate.py` — **new**, 26 checks: geometry block parses,
  no control overlaps another or the LCD window, screws clear the knobs, every
  image the Lua names is shipped at the expected size, no orphan resources,
  `info.xml` matches the face, the DF heads' shared libraries are byte
  identical, the Becker has neither F1/F2 keys nor the RT-600 name while the
  RT-600 keeps both, and no literal LCD string runs off the 128-dot panel.
- Previews inspected against Fig 3-3 and the concept side by side.

### Remaining limitations

- **Air Manager is still not installed on this machine, so none of this has been
  run.** No runtime validation was performed and none is claimed. A bring-up
  checklist is in the handover notes; the first things to confirm are that
  `img_add`, `dial_add` and `button_add` accept these resources at 520 units and
  that the LCD canvas registers over the faceplate window in the right order.
- The bearing bracket glyph is the one thing the manual scan cannot settle: Fig
  3-3 reads as `<337<` at that resolution while the CAP photograph of an RT-600
  DCU clearly shows `<010>`. Both heads draw `<nnn>`.
- The preview's LCD is a Python mirror of the Lua page-1 layout, not a capture
  of it. The two share the geometry constants but not the drawing code, so a
  change to a page must be made in both if the preview is to stay honest. Only
  page 1 (517) and the DF page (RT-600) are previewed.
- The scan-mode band caption reads `SCAN MODE / 406/121.5`; the frame holds nine
  characters and 243.000 is also in the §3.3.3 dwell.
- No engine, dataref, or propagation behaviour was changed by that artwork
  revision. Wing blanking was implemented later, as recorded above.

## 2026-09-07 — Wing-null / airframe-shadowing research

**Status: research completed; implementation proposed, not implemented.**

Superseded by **Wing blanking and instantaneous receiver state implemented**
above. This entry is retained as the research and design record.

Investigated CAP pilots' use of banked turns to shield a receiving antenna
from an ELT, producing an audible signal reduction or null that helps
localize the beacon. The technique is called wing null or wing shadowing.

### Findings

- CAP's Mission Inflight Guide (July 2021), printed pages 71–73, describes
  installation-dependent directional cues: at a null, the lowered wing
  generally points toward the beacon for antennas below the wings; the
  raised wing does so for antennas above the wings. Observations from
  different positions help narrow the search area.
- The receiving antenna's actual location matters. Wings and fuselage can
  shield reception; a bank angle alone is insufficient to predict a null.
- Becker/G1000 training hosted by RHOTHETA describes using COMM reception
  and wing shielding before transitioning to Becker automatic direction
  finding. Do not assume that every belly-mounted Becker installation
  produces a textbook wing null, or that it is immune to shielding.
- A useful training approximation is feasible. Exact attenuation, null
  width, and bearing disturbance require installation-specific calibration;
  the reviewed sources do not establish a universal attenuation curve.

### Current implementation inspected

The installed engine at
`/home/ron/X-Plane 12/Resources/plugins/PythonPlugins/PI_capvsar_df.py`
reads position and heading but not roll or pitch. Its mounting configuration
can mirror bearing interpretation, but does not model physical airframe
shielding. Signal strength is currently clamped before terrain attenuation.
The instrument/engine interface is documented in `docs/DATAREF_CONTRACT.md`.

### Proposed implementation

1. Calculate the aircraft-to-beacon direction in aircraft body coordinates
   using position, heading, roll, pitch, and beacon elevation.
2. Apply configurable, installation-specific directional attenuation for
   each receiving antenna, including separate COMM and DF profiles.
   Simplified wing/fuselage intersection geometry is a possible refinement.
3. Apply attenuation before signal saturation and receiver processing, so
   strong nearby signals can remain receivable through partial shielding.
   Drive signal indication, squelch, audio reception, and bearing quality
   from the resulting reception state.
4. Keep instantaneous audio reception separate from held/valid bearings.
   COMM reception must be independent of Becker power and tuning. Keep
   physical installation truth separate from the crew's TOP/BOTTOM setting.
5. Distinguish airframe shielding from terrain masking and overhead bearing
   confusion; do not repurpose the existing terrain-blocked flag.
6. Begin with continuous homing-signal scenarios and preserve separate
   406 MHz burst behavior. Validate opposite banks, top/bottom installations,
   beacon elevation, strong-signal reception, and held-bearing/audio behavior.

This work belongs primarily in the Python propagation engine and radio audio
path, with Lua instruments displaying the resulting reception. No engine,
Lua, artwork, or dataref changes were made as part of this research entry.

### Sources

- [CAP Mission Inflight Guide, July 2021](https://txwg.cap.gov/media/cms/Inflight_Guide_Rev_July_2021_1D641C_FA6854DBA1C18.pdf), printed pages 71–73.
- [Becker/G1000 training hosted by RHOTHETA](https://rhothetaint.com/wp-content/uploads/2019/08/beckerdfwithg1000slides.pdf), slides 17 and 22–25.
- [FAA AC 91-44A](https://www.govinfo.gov/content/pkg/GOVPUB-TD4-PURL-LPS107811/pdf/GOVPUB-TD4-PURL-LPS107811.pdf), paragraph 12(b)(2); historical technical reference, not current flight-procedure guidance.
