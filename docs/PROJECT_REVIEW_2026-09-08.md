# CAP V-SAR project review — 2026-09-08

**Status: review only. Nothing in this document has been fixed yet.** Each
finding was verified against the files named, not against CHANGELOG claims.
The three most consequential items (P-1, X-1, P-2) were re-checked by hand
after the subsystem reviews came back.

Scope: the whole tree — X-Plane plugin, exercise console backend and
frontend (including the new `/radio` Mumble console Codex built for the
Motorola APX 4500 and EFJohnson 5300), flight planner, Air Manager
instruments and MO panel, deployment, docs, and the coordination log.
Companion document: [`CALTOPO_PHASE2_PLAN.md`](CALTOPO_PHASE2_PLAN.md).

Finding IDs: **P** plugin/engine, **X** exercise console backend, **F**
frontend, **L** flight planner, **I** instruments/panel, **O** ops/infra,
**D** docs/process.

---

## 1. Executive summary

Ten things that matter most, in order:

1. **The repo is not under version control.** `.git/` is an empty directory,
   `git` is not installed, there is no `.gitignore`, and ~45 MB of
   regenerable artifacts sit in the tree. Three AI tools and a human are
   editing the same files with no history and no way to diff or revert. (O-1)
2. **Beacon truth leaks.** The design withholds the beacon position from
   base staff until debrief, but `GET /api/scenarios` and
   `GET /api/sorties/{id}/track` return it unconditionally, and the
   `/ws` snapshot leaves `beacon_elev_ft` in. Anyone on the LAN/WireGuard
   can read the answer in one request. (X-1)
3. **The plugin can't get beacon truth either.** The same withholding means
   `/api/state` never gives the X-Plane plugin the beacon position, so the
   authoritative in-sim DF engine is deaf for the whole exercise unless the
   instructor reveals at the start or someone hand-writes datarefs. The
   code comments acknowledge this. (P-2)
4. **The terrain line-of-sight ray is mirrored** — aircraft and beacon
   altitudes are swapped along the path. Ridges near the beacon never
   block; high ground near the aircraft falsely does. The test harness
   stubs terrain to a constant, so no test can catch it. (P-1)
5. **No authentication or roles anywhere.** Any participant can stop,
   reveal, or delete a running exercise, or rewrite its effects. (X-2)
6. **The mission-base pages are dead without internet.** Leaflet is loaded
   from unpkg with no local copy; on a base LAN with no internet `/base`
   throws before the WebSocket connects and the whole view is blank, not
   just the map. Tiles are also remote-only. (F-1, L-8)
7. **Multi-aircraft is not deployable.** The plugin hardcodes the console
   IP and callsign `CAP-1`; three stations means three hand-edited copies.
   There is no station config, no onboarding kit, no Windows deploy path. (O-2)
8. **The `.fms` export is malformed** for X-Plane 11/12 (missing `DRCT`
   column, wrong waypoint type for user lat/lon points) and the test locks
   the wrong format in. The "plan it, load it in the G1000" workflow does
   not work as documented. (L-1)
9. **A fresh ms01 deploy crash-loops.** `docker-compose.yml` bind-mounts a
   database *file* that doesn't exist in the repo; Docker creates a
   directory and the flight planner dies on import. The repo is not the
   deployment — `/srv/capvsar` on ms01 has files this tree lacks. (O-3)
10. **The new `/radio` console is the right foundation and is further along
    than the log says** — real browser→pymumble→Mumble voice, half-duplex
    PTT lease, descriptor-driven radio models — but the CA-cert directory
    the compose file mounts doesn't exist, Mumble channels are never
    provisioned, and two older CHANGELOG entries still describe the bridge
    as "proposed only" (Codex's own entry for it landed this morning). (O-5, D-1)

Nothing here is beyond a few focused days of work. Items 1, 2, 3, 4 and 9
are each under a day and should go first.

---

## 2. Critical findings

| ID | Where | Finding | Fix |
|---|---|---|---|
| **O-1** | repo root | `.git/` empty, no `git` binary, no `.gitignore`. `output/` (14 MB, includes a snapshot of the installed Air Manager tree), `docs/manual/*.odt\|docx` (24 MB), `cap-c182t-mo-station.zip` (3.5 MB) and `__pycache__` are all regenerable and untracked. | Install git, `git init`, add `.gitignore` (`output/`, `*.zip`, `__pycache__/`, `.pytest_cache/`, `docs/manual/*.odt`, `docs/manual/*.docx`, `services/*/data/`, `.env`), push to the Gitea remote, make ms01 pull from it. |
| **X-1** | `services/exercise/app/main.py:116-131, 208-212, 297-316` | `Hub.snapshot()` is the only place truth is filtered, and only `/api/state` and `/ws` use it. `/api/scenarios` returns every `beacon_lat/lon`; `/track` returns `beacon` for an unrevealed running sortie; `snapshot()` pops lat/lon but not `beacon_elev_ft`. `debrief.js:80`'s "never revealed" branch can never trigger. | One truth-filtering serializer applied to every scenario/sortie response; `/track` returns `beacon` only when `revealed`; pop `beacon_elev_ft` too. |
| **P-2** | `xplane/PI_capvsar_df.py:947-967`; `main.py:406-408` | Plugin polls `/api/state`, which withholds truth; plugin sets `active=1` with lat/lon at 0/0 (or the previous exercise's beacon). Distance to Null Island exceeds the radio horizon → DF silent. | A plugin-only truth channel: `GET /api/plugin/scenario` gated by a shared secret header (`CAPVSAR_PLUGIN_KEY` in `.env`, same value in the station config). The pilot's machine must hold truth — the instruments need it — so the secret protects the *endpoint*, not the pilot. |
| **P-1** | `xplane/PI_capvsar_df.py:595-599` | `interp()` walks aircraft→beacon with `fr`, but `ray = b_ft + (ac_ft - b_ft) * fr` puts the beacon's altitude at the aircraft end. | `ray = ac_ft + (b_ft - ac_ft) * fr`. Add a test with a non-flat terrain stub (ridge at 30 %, 60 %, 90 % of path) — `tests/xp.py` currently returns one constant height. |
| **X-2** | `main.py` (all routes); `docker-compose.yml:73` | No auth on any endpoint. Only the radio stream has an access code, empty by default. `/ws` has no origin check (the radio socket does). | Per-role bearer tokens from `.env` (`instructor`, `base`, `plugin`); instructor-only on scenario CRUD, start/stop/reveal/effects; base token on `/base`, `/ws`, bearings, messages. Origin check on `/ws`. |
| **F-1** | `index.html:5,109`, `base.html:5,62`, `debrief.html:5,54` | Leaflet 1.9.4 from `unpkg.com`, no local copy. `base.js:4` throws when `L` is undefined → no WS, no status board, no bearing log. | Vendor `leaflet.js`/`.css` under `static/vendor/`. Same for the flight planner (`index.html:447`, Google Fonts at `:8`). |
| **O-3** | `docker-compose.yml:120`; `services/flightplanner/app.py:113` | Bind-mount of `./services/flightplanner/data/aviation_data.db`; the directory doesn't exist in the repo (`*.db` is gitignored there). Docker creates a directory, `sqlite3.connect` fails at import, gunicorn crash-loops. | Mount the `data/` directory, and make `init_database()` create the file. Add a `make bootstrap` that creates every host path compose expects (`mumble/data`, `services/exercise/data`, `radio-public/`, `flightplanner/data/`). |
| **O-2** | `xplane/PI_capvsar_df.py:86-87`; `scripts/deploy_*.py` | `CONSOLE = "http://192.0.2.151:8700"`, `CALLSIGN = "CAP-1"`; no env/config override. Deploy scripts are Linux `Path.home()` only; `build_c182t_package.py` hardcodes `/home/ron`. No installer, no checklist, no WireGuard peer doc (`infra/ROUTER.md` referenced, absent). | `capvsar_station.ini` beside the plugin (console URL, callsign, plugin key). A per-station kit zip: plugin + station.ini + four instruments + MO panel + C182T package + CA cert + WireGuard peer + one-page checklist. Windows paths in the deploy scripts. |

---

## 3. High findings

### Plugin / propagation engine

| ID | Where | Finding | Fix |
|---|---|---|---|
| **P-3** | `PI_capvsar_df.py:645-652, 755-759, 693` | Scan mode steps the receiver to alt1/alt2 between 406 bursts; the next tick finds it untuned and calls `silent()`, which clears `held`. With `scan_enable=1` (the 517's normal 406 posture) the bearing vanishes the instant each 440 ms burst ends instead of TIMEHOLD-ing. Untested (scan tests use 121.5). | Don't clear `held` when the miss is due to scan stepping; add a scan+406 timehold test. |
| **P-4** | `PI_capvsar_df.py:738`; `services/exercise/app/propagation.py:37-40` | Radio horizon uses `sqrt(max(alt - beacon_elev, 0))` — one-sided, zero when the aircraft is below the beacon. An aircraft in a valley 500 ft below a ridge-top beacon 1 NM away hears nothing. | Standard form `1.23·(√h_ac + √h_bcn)` NM with heights above intervening terrain / MSL as appropriate. |
| **P-5** | `PI_capvsar_df.py:555-560, 945` | `XPluginDisable` sets `self.stop` and never clears it; the net thread started by `XPluginEnable` exits immediately on re-enable. Datarefs keep publishing stale state with no console link. | Recreate the `Event` in `XPluginEnable`; join the thread on disable. |

### Exercise console backend

| ID | Where | Finding | Fix |
|---|---|---|---|
| **X-3** | `main.py:26-29, 237, 257, 269, 281, 353, 369, 391`; `radio.py:223-243` | SQLite writes run synchronously inside `async def` handlers on the same event loop that carries 20 ms PCM frames for the Mumble bridge. Every commit fsyncs on a bind mount. A stalled commit trips the audio buffer check and unkeys the operator ("Audio connection is delayed"). No WAL, no `timeout=`, connections never closed. | Sync handlers or `run_in_threadpool`; `PRAGMA journal_mode=WAL`; close connections; consider moving the radio bridge to its own process (see §5). |
| **X-4** | `main.py:98-104, 137-150, 334, 401-403` | Live state (`hub.sortie/scenario/aircraft/messages`) is in-process only and never rehydrated from SQLite on startup. A container restart mid-exercise orphans the sortie: positions discarded, `/api/messages` empty, DB row `stopped=NULL` forever. `--workers>1` would silently split state. | Rehydrate the running sortie and last N messages in `lifespan`; document the single-worker constraint in the Dockerfile. |
| **X-5** | `main.py:106-114` | `Hub.broadcast` awaits `send_text` sequentially with no timeout. One wedged tablet blocks the 1 Hz ticker and every HTTP handler that broadcasts. Half-open sockets are never dropped. | `asyncio.wait_for(send, 1.0)` per client, drop on timeout, `gather` them. |

### Frontend

| ID | Where | Finding | Fix |
|---|---|---|---|
| **F-2** | `base.js:43, 83-85`; `app.js:144-145` | `alertCircle` is created once and never updated; `trackLines`/`bearingLayer` never cleared on a new sortie. Start a second sortie and base staff see the previous scenario's search circle and marker; expired aircraft leak their track entries. | Reset layers on a `sortie` change in the snapshot, as `app.js` already does. |
| **F-3** | `debrief.js:45, 68-72, 90-98`; `main.py:301` | Debrief treats all positions as one track. With three aircraft the polyline zigzags between them, "track flown" sums inter-aircraft jumps, CPA is meaningless. Heading derived via `atan2(dlon, dlat)` without `cos(lat)` (~10° bias at 33° N) although `hdg_true` is stored but not returned. | Group by callsign; return `hdg_true` from `/track`. |
| **F-4** | `mission-radio.js:184`; `base.js:19-30`; `radio.js:501-526` | The new radio console deliberately does not auto-reconnect — a Wi-Fi blip drops the base station off the voice net with only a text notice. Base/legacy reconnect but lose bearings/messages broadcast during the outage (no list endpoint for bearings; messages fetched only at load). | Rejoin with backoff and an audible alarm on the radio; `GET /api/bearings?since=` and `?since=` on messages; refetch on reconnect. |
| **F-5** | `services/exercise/radio-public/` (missing); `docker-compose.yml:67`; `mission-radio.html:52,54` | The CA cert directory Caddy serves at `/radio-ca.crt` doesn't exist, so tablets can't get the secure context `getUserMedia` requires and the console blocks at `mission-radio.js:148`. `radio-art/README.md` (linked as the setup notes) doesn't exist. | Part of the bootstrap script (O-3). Write the setup note. |

### Flight planner

| ID | Where | Finding | Fix |
|---|---|---|---|
| **L-1** | `app.py:620, 636`; `tests/test_sar.py:115` | FMS v1100 waypoint line is `type ident airway\|DRCT altitude lat lon`; code emits `11 SS01 5500.0 lat lon` (no `DRCT`, so `5500.0` is parsed as the airway). Type `11` means "named fix in navdata"; `SS01`/`DATUM` don't exist. User points should be type `28`. `CYCLE 2401` hardcoded. | Emit `28 +33.187_-117.079 DRCT 5500.000000 33.187 -117.079` for user points; fix the test to assert the real format; derive `CYCLE` from the date. Verify by loading in X-Plane 12. |
| **L-2** | `app.py:1406`; `main.py:386-398` | `/api/sar/export-vsar` has no auth or rate limit; free-text `callsign`/`pattern_type`/`departure` flow unbounded into scenario `name`/`notes`/`alert_text` and a broadcast. `/api/update-database` (`:816`) takes no body, so a cross-site form POST triggers a DB wipe/reload. The README still advertises Cloud Run `--allow-unauthenticated`. | Require the base token (X-2) on the push; CSRF-safe JSON-only on `update-database`; length caps. |
| **L-3** | `app.py:591, 1360-1361` | `length_nm`/`width_nm` unbounded; `width_nm=1e7, spacing=0.1` → 10⁸ sweeps in `generate_parallel_track`. `num_legs` cap does not cover it. | Cap width/length (≤ 60 NM) and total legs. |
| **L-4** | `app.py:357`; `Dockerfile` (`--workers 2`) | Both gunicorn workers run `auto_update_if_empty()` at import; concurrent `DELETE`/`INSERT` on the same SQLite file with lock errors swallowed by bare `except: pass` (`:300, 317, 334`). `update_status` is per-process, so `/api/update-status` is inconsistent. | Run the update in one place (a `flask db-update` command or a lock file); log exceptions. |

### Instruments

| ID | Where | Finding | Fix |
|---|---|---|---|
| **I-1** | `becker-sar-df-517/logic.lua:755-758`; `rhotheta-rt-600/logic.lua:574-577`; `lib/cap_df.lua:95`; `lib/lcd.lua:131` | The 250 ms tick repaints unconditionally, and `df.on_change` fires `redraw()` from all three subscription groups every engine tick — ~8 Hz of ~100 `_txt` calls each rebuilding a style string, whether or not anything changed. | Redraw only when the whole-second `last_signal`/`burst_age` or the state snapshot changes. This also shrinks the reentrancy window I-2 was meant to cover. |
| **I-2** | `becker/logic.lua:163`; `rt-600/logic.lua:141`; `~/Air Manager/log.txt` | `pcall(canvas_draw, …)` was added for a "cannot call canvas_draw within a draw callback" error. The log shows that error exactly twice, each immediately followed by the missing-callback signature, and zero Becker/RT-600 errors after the callback fix landed. The `pcall` now swallows every synchronous failure silently. | Drop it or log the error. Correct CHANGELOG §"Becker / RT-600: a different canvas_draw symptom". |

### Ops / infra

| ID | Where | Finding | Fix |
|---|---|---|---|
| **O-4** | `radio.py:29-34, 181`; `docker-compose.yml` | Four Mumble channel names are hardcoded and `find_by_tree()`'d; nothing creates them. First exercise-day join fails with "voice server did not confirm the selected net". | `scripts/provision_mumble.py` (Ice/`murmur` config or a one-shot pymumble client with SuperUser) that creates the channel tree and ACLs; run it from bootstrap. |
| **O-5** | `docker-compose.yml` (mumble service) | `CERTREQUIRED=false`, `ALLOWHTML=true`, shared server password only, no per-user certs or channel ACLs, `USERS=100`; images `mumble-server:latest` and `caddy:2` unpinned. Callsign on the radio console is free-form (`radio.py:307`) so a student can present as "MISSION BASE". | Pin images; per-role channel ACLs; derive the radio callsign from the role token. |
| **O-6** | ms01, GL-MT6000 | Single points of failure on exercise day: ms01 (all services + SQLite + the voice bridge), the router (WireGuard for everyone), home ISP. No backup of `exercise.db`, no monitoring, `radio-https` has no healthcheck. | Nightly `exercise.db` copy; `radio-https` healthcheck; a pre-exercise smoke script (`/api/health`, Mumble channels present, tiles reachable, CA cert served). The CHANGELOG's one-VM-plus-WireGuard proposal is sound. |
| **O-7** | Air Manager licensing | Plan v0.8 §9.4 assumes one seat per MO station; the containerization entry says "confirm against `AM4_COMPAT.md`", which does not exist. Three MO seats are unconfirmed. The G1000 MFD streaming drops ("action needed 2026-09-08") are unresolved and will hit every MO station. | Confirm seat count in writing; resolve the streaming issue (the stock MFD instrument calls `video_stream_add()` once and never re-arms after reconnect — a wrapper instrument that re-arms on `SimVideoStreamClient` reconnect is the likely fix). |

---

## 4. Medium and low findings

### Plugin
- **P-6** `:824` — 121.5 beacons produce a COSPAS-SARSAT decode inside the cone (`decode_tick` not gated on `on_406`). Analog beacon shows SYNC OK + hex ident.
- **P-7** `:783, 805` — `cap/df/signal` stays lit between 406 bursts (published before the burst gate); squelch evaluates the continuous value.
- **P-8** `:772` — terrain "blocking" is only −12 dB (`*0.06`); a fully masked beacon at 2 NM still yields a valid bearing. Real knife-edge loss is 20–40 dB.
- **P-9** `:94, 593` — fixed 24 probes (1.25 NM spacing at 30 NM); no earth-curvature bulge.
- **P-10** `docs/DATAREF_CONTRACT.md` mismatches: L67-74 says `cap/scenario/*` is writable for offline testing but `active` is read-only and only the net thread sets it (so offline hand-written beacons are ignored); L107 draws extremes at `bearing ± spread/2` but `:858` publishes one-sided max deviation; L43 "slant range" is great-circle ground range; L59 `BYTE[15]` returns length 0 when undecoded; effects `radio_horizon`, `terrain_masking`, `cone_of_confusion`, `burst_cadence`, `multipath(_offset_deg)` undocumented.
- **P-11** `propagation.py:68-71` vs plugin — server fallback uses a 1.5 s burst window vs 0.44 s, never invalidates between bursts, matches band as string `"406"`, and has no squelch/averaging/timehold/tuning/terrain/airframe. It runs whenever the plugin omits `df` (until `panel_seen`), so a sim without Air Manager shows the instructor a different DF than the sim computes.
- **P-12** `:86-87, 962, 471, 972, 1018` — nulls in JSON would throw in the dataref accessor; `REPORT_S=2` but the loop sleeps 3 s; first report is (0,0,0); `psi` is OpenGL-frame heading (`true_psi` is correct).
- Realism: no dB calibration (`25/d²` saturates at 5 NM for all bands; 121.5 at ~0.1 W and 406 at 5 W differ only in cadence/decode). Multipath is a deterministic 40° step for 12 of every 36 s independent of terrain. Airframe shadowing is the strongest piece.

### Exercise console
- **X-6** `main.py:235, 277-283` — `start_sortie`/`set_effects` take raw `dict`s; `set_effects` merges arbitrary keys into the *scenario* row, permanently mutating the definition. No lat/lon range checks. Positional `INSERT … VALUES (?×15)` breaks on the next `ALTER`.
- **X-7** `main.py:234-250, 364, 390, 158-160` — starting a sortie while one runs leaves the old row un-stopped; after `/stop`, `hub.sortie` persists so bearings/messages keep attaching; `log_bearing` 404s for aircraft older than 30 s.
- **X-8** — `positions` has no retention; `/track` unpaginated; no export beyond `/track`; no logging in `main.py`; health check doesn't touch the DB; ticker never cancelled on shutdown; container runs as root.
- **X-9** `radio.py:141` — one pymumble thread per browser socket at `set_loop_rate(.01)`, 16 max; two radios on one desk = two Mumble users.

### Frontend
- **F-6** `base.js:114`, `debrief.js:105`, `app.js:80`, `radio.js:453` — server strings interpolated unescaped (HTML injection via `/api/messages`).
- **F-7** `radio.js:530` — `a && b || c.startsWith()` precedence bug; `:535-559` legacy autoplay/TTS outside a user gesture (silent on iPad until a click). The new console does this correctly.
- **F-8** `base.js:99-102` — bearing lines are flat-earth 40 NM rays (fine at that scale); no intersection/"cut" math exists anywhere despite README claims. Bearing entry requires typing the callsign.
- **F-9** — Form 110 export (`radio.js:471-495`): no date column, `padEnd` doesn't truncate, blob URL never revoked. The new Mumble console has no Form 110 log at all.

### Flight planner
- **L-5** `app.py:591-595, 543, 532/554` — parallel track starts on the box edge (`int(width/spacing)` tracks at 0,1,2,3 → last NM unsearched); creeping line truncates silently at `max_legs`; `heading_mag` omitted for two of three patterns.
- **L-6** `app.py:711, 736-740, 665, 937` — `get_cruise` is nearest-neighbour; takeoff/landing clamp to the last row (understates above the table); tailwind ignored; wind ≥ TAS yields *less* fuel.
- **L-7** `app.py:64-102`, `README.md` — performance data is 172S (2550 lb, 53 gal) under a 182T label.
- **L-8** `index.html:447, :8`; `app.js:83-97`; `app.py:1490` — Leaflet/Google Fonts remote; tiles direct from ArcGIS; the server tile cache only runs under `__main__`, never under gunicorn, and the frontend never requests `/tiles/`; the `charts` volume is dead; `USER_GUIDE.md:102` is false.
- **L-9** `app.py:894-897, 1001-1008, 1397, 1463` — unguarded `int()/float()` on client JSON → Werkzeug HTML 500s; the 'no sortie running' branch is dead (the console never 400s any more) but the UI always says "broadcast to active sortie" even when nothing was persisted; `beacon_elev_ft: 0.0` puts the beacon at sea level; the beacon is placed exactly on the planned datum, handing the trainee the answer.
- **L-10** — `requests==2.31.0` (CVE-2024-35195/47081); gunicorn/Werkzeug unpinned; root container; healthcheck hits `/`; `serve_tile` accepts `..` in `chart_type`; `_winds_cache` unbounded; DB is OurAirports (community), not FAA NASR, with no cycle shown; Cloud Run re-downloads the DB on every cold start.

### Instruments / panel
- **I-3** `becker/logic.lua:712-717, 615` — `tone_suppressed` clears only when STORE is pressed on FM; suppress on 121.5, turn to CH16 and the rose shows "3K-" with no bearing.
- **I-4** `becker/logic.lua:378, 392, 402` — `msg and msg.has_pos or s.cs_has_pos` falls through to live data for a STORED frame with no position.
- **I-5** `rt-600/logic.lua:479-481, 386` — long-press timers survive power-off; `f1_long` → `clear_average()` fires after shutdown.
- **I-6** DF heads (`:588`) and TDFM (`:353-358`) power up with battery/avionics master off; only the GMA follows `avionics_power_on` and ignores `bus_volts`.
- **I-7** — `lib/cap_df.lua`, `cap_df_audio.lua`, `dcu.lua`, `lcd.lua` and the three WAVs are byte-identical across Becker and RT-600 (and `lcd.lua` in the TDFM); `test_faceplate.py:126-129` enforces the DF pair but not the TDFM copy. Suggested: `instruments/_shared/`, copied in by the deploy scripts, with a test asserting the installed copies match.
- **I-8** `register_mo_panel.py:107-168, 171-172, 50, 97-100, 182` — hardcodes 26 `panel` columns and magic values; `sqlite_sequence` synced for two of four tables; `pkill`s Air Manager without confirmation; relaunches from a hardcoded path; never updates an existing layout; positions triplicated across `info.xml`, the registrar, and `generate_assets.py`. `Streaming=true` is set only via the SQLite path, so the `--zip` route ships a dead MFD.
- **I-9** — the ctypes Lua 5.4 execution harness the CHANGELOG describes is not in the repo; `luacheck.py` is syntax-only; nothing executes any `logic.lua`. `cap_fm_ptt`, `cap_fm_main_rx`, `cap_fm_guard_rx` have no producer and no contract. `info.xml` claims FSX/P3D/FS2020 support; TDFM/GMA have no deploy script; `deploy_df_instruments.py` deploys two of four instruments although `deployment.html` says four.

---

## 5. Architectural problems

1. **One process does everything.** `main.py` (504 lines) holds scenario truth, telemetry ingest, the WebSocket hub, SQLite, and — via `radio.py` — the real-time voice bridge, all on one asyncio loop. X-3 is the symptom. The empty `services/missionbase/` and `services/tracking/` directories created today are the right instinct. Recommended shape, still one container and one SQLite file for now:
   - `services/exercise/app/store.py` — SQLite access, WAL, rehydration, the truth-filtering serializer.
   - routers: `exercise` (scenarios, sorties, effects, reveal — instructor token), `tracking` (ingest, tracks, replay, and later the CalTopo relay — plugin/base tokens), `missionbase` (base view, bearings, messages, Form 110/ICS-214 log, Ops Normal clocks — base token), `radio` (already its own module).
   - The Mumble bridge in its own process (or at least its own event loop/thread) so SQLite fsyncs can never unkey a radio.
2. **Truth handling is by page, not by role.** Fix X-1/X-2 together: a role token per view, and a single serializer that knows what each role may see.
3. **Five geodesy implementations** (`flightplanner/app.py`, `exercise/app/propagation.py`, `exercise/mock_bridge.py`, `static/debrief.js`, `xplane/PI_capvsar_df.py`) and **two propagation models**. Policy already says the plugin is authoritative; shrink `propagation.py` to the mock-bridge stub and share one Python `geodesy.py` between the two services (the plugin must stay standalone — it ships alone to member PCs — so it keeps its own copy, tested against the shared one).
4. **The plugin has no identity or configuration** (O-2). Everything that must vary per station is a constant in source.
5. **Two radio consoles, one advertised.** `/radio` (Mumble, APX 4500/EFJ 5300) and `/radio-legacy` (simulated audio, APX 6500/IC-A120, Form 110). README, all `website/*.html`, and the CHANGELOG describe the legacy one. Retire `/radio-legacy` after porting its Form 110 logger onto the Mumble console (F-9).
6. **The build isn't the deployment** (O-3). `/srv/capvsar` on ms01 carries state and files this tree doesn't. A `bootstrap` target plus git pull on ms01 closes it.

---

## 6. Operational improvement opportunities (against Plan v0.8 §4 CONOPS)

There is no `CONOPS-cap-vsar.md` anywhere on disk; the CHANGELOG cites it seven times. Plan v0.8 §4 (in `~/Documents`) is the effective CONOPS and should be copied into `docs/` so the coordination log's source of truth is in the repo.

| Need | Today | Gap |
|---|---|---|
| Up to three aircraft, each pilot + MO | Server keys aircraft by callsign (works); plugin hardcodes `CAP-1` | O-2 station config + kit |
| Role-separated IC / AOBD / MRO | One shared `/base`; no auth | X-2; a role token selects the view; IC/AOBD views are new frontend work (assignments board, Ops Normal 30-min clocks per aircraft, overdue alert) |
| Base staff "with a radio in front of them" | `/radio` Mumble console works end-to-end | O-4 channel provisioning, F-5 CA cert, F-4 rejoin, O-5 ACLs, F-9 Form 110 on the new console, a TDFM-channel ↔ Mumble-channel map so cockpit and base "tune" the same net |
| Exercise start/stop/reset | start/stop/reveal exist; no reset, no clock | X-7 lifecycle; a `POST /api/exercise/reset` that clears aircraft/messages; exercise clock in the header; `TZ` respected in displays (all Zulu today, which is correct, but say so) |
| Withheld truth until debrief | Filtered on `/ws` only | X-1, P-2 |
| Debrief exports | `/track` JSON only | CSV/GeoJSON/PDF export; per-aircraft tracks (F-3); bearing-error scoring is present, keep it |
| ICS-214 / CAPF-110 | Legacy `.txt` Form 110 | Port to the Mumble console; add ICS-214 from the messages table |
| Offline base | Remote Leaflet + tiles | F-1/L-8; a tile pre-cache for the exercise area (the `charts` volume already exists, just unused) |
| Participant onboarding | Nothing | O-2 station kit + checklist + WireGuard peer doc |
| Voice recording (Plan §6.3.2) | Absent | Mumble server-side recording, or record at the bridge |
| Air Manager seats (3 MO) | Unconfirmed | O-7 |

---

## 7. Improvement program (ordered)

Work packages sized honestly; each is independently shippable.

| WP | Scope | Findings | Size |
|---|---|---|---|
| **WP0 Version control** | git init, `.gitignore`, Gitea remote, ms01 pulls from it, CHANGELOG entry per merge | O-1 | ½ day |
| **WP1 Truth & roles** | Truth-filtering serializer; role tokens; plugin truth endpoint; `/ws` origin check | X-1, X-2, P-2 | 1 day |
| **WP2 Engine fixes** | Terrain ray; radio horizon; scan+406 timehold; disable/enable; 121.5 decode gate; signal between bursts; deeper terrain loss; non-flat terrain test stub | P-1, P-3–P-9 | 1–2 days |
| **WP3 Offline mission base** | Vendor Leaflet/fonts; tile pre-cache into the `charts` volume; planner uses `/tiles/` | F-1, L-8 | 1 day |
| **WP4 Station kit & multi-aircraft** | `capvsar_station.ini`; kit zip builder; Windows deploy paths; checklist; WireGuard peer doc | O-2 | 2 days |
| **WP5 Radio console hardening** | Bootstrap paths + CA cert; Mumble channel/ACL provisioning; rejoin + alarm; role-derived callsign; Form 110 on the new console; retire `/radio-legacy`; bridge off the main loop | O-3, O-4, O-5, F-4, F-5, F-9, X-3, X-9 | 2–3 days |
| **WP6 Console robustness** | WAL + threadpool; rehydrate on start; broadcast timeouts; lifecycle/reset; validation; bearing/message `since` endpoints; escape HTML; logging; DB-touching healthcheck | X-3–X-8, F-2, F-6, F-7 | 2 days |
| **WP7 Debrief & exports** | Per-aircraft tracks; `hdg_true`; CSV/GeoJSON export; ICS-214 | F-3, X-8 | 1 day |
| **WP8 Flight planner** | FMS format + test; input caps; single DB updater; pin deps; 182T data; coverage math; JSON errors; auth on push | L-1–L-10 | 2 days |
| **WP9 Instruments** | Conditional redraw; drop/log `pcall`; band reset; STORED fallthrough; timers on power-off; electrical bus; `_shared/` lib; commit the Lua execution harness | I-1–I-9 | 2 days |
| **WP10 Service boundaries** | `store.py`, routers, role middleware; shared `geodesy.py`; shrink `propagation.py` | §5.1–5.3 | 2 days, after WP1/WP6 |
| **WP11 Docs & record** | Copy Plan §4 into `docs/`; fix README/website (APX 4500, Flask not Node, no `docker-compose.prod.yml`, ports 49000/49001, cloud claims); CHANGELOG corrections below; `AM4_COMPAT.md`/`infra/ROUTER.md` or remove the references | D-1–D-4 | 1 day |

WP0, WP1, WP2 (P-1 only) and the O-3 bootstrap are the pre-exercise minimum. CalTopo (phase 2) depends on WP1, WP4 and the `tracking` router from WP10 — see the companion plan.

---

## 8. Corrections to the record

The CHANGELOG is the coordination protocol between three tools; these entries are now wrong and will mislead the next reader.

- **D-1** "Design proposal: Mission Base WebUI virtual radio (pymumble)" is marked *proposed*, and the containerization entry's table says the browser voice bridge is "Proposed only". It is implemented (`radio.py`, `radio-worklet.js`, `mission-radio.js`, 15 tests, Caddy TLS, `libopus0` in the Dockerfile); Codex's entry "Mission base web headset radio implemented and installed" (2026-09-08) now documents it, and notes that ms01 holds backups under `/srv/capvsar/backups/` and that `radio-public/` was created there — both consistent with O-3 (the repo is not the deployment). Add a one-line "superseded by …" note to the two older entries.
- **D-2** The "MRO Base Radio Web Application (`/radio`)" entry (APX 6500 + IC-A120) now describes `/radio-legacy`. README line 25 and `website/operations.html` still advertise it as `/radio`. `main.py:493` spells it `APX6500`; `mission-radio.html` says APX 4500.
- **D-3** "Becker / RT-600: a different `canvas_draw` symptom, mitigated but not proven fixed" — the log does not support the claim that the current code still produces the error (I-2).
- **D-4** "all 55 engine checks pass" — the file has 50. "`/api/messages` rejects the push (400)" — no longer true (`main.py:386-398` never raises). The 2026-09-07 MO-panel review entry has no heading and reads as part of the `/radio` entry.
- `website/technical.html:441` calls the flight planner "Node.js / Vite" (it is Flask/gunicorn); `deployment.html:295-298` cites a `docker-compose.prod.yml` that doesn't exist; its port matrix lists 49000/49001 which nothing uses; `index.html:67-72` carries unsourced ROI figures; `technical.html:453` claims "sub-20 ms" voice with nothing measuring it. `services/flightplanner/README.md` still says Cloud Run is the hosting target.
- No `LICENSE` file, although `build_c182t_package.py` derives from Laminar's shipped C172SP.

---

## 9. Method

Seven parallel reviews (plugin/engine, console backend, console frontend, flight planner, Air Manager Lua, infra/ops/CONOPS, CalTopo research), each reading whole files and cross-checking the CHANGELOG against the tree; findings above were spot-verified by hand where they were critical or where reviewers disagreed. The Air Manager log (`~/Air Manager/log.txt`) and Plan v0.8 were read directly. Nothing was executed against X-Plane or Air Manager in this session.
