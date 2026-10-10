# CAP V-SAR project review — 2026-10-10

**Status: review only. Nothing in this document has been fixed.** Each
finding names the file and line it was verified against on `main` at
52976b0 (worktree `cap-vsar-integration`). `origin/main` had moved to
62ed4b9 by the time this was written; of its three newer commits, 57663ec
("Fix C182 build safety", 2026-10-10) resolves B2-1, B2-2 and B2-4 below,
and the line numbers in section 8 refer to the older file. Those three rows
are marked **resolved on origin/main**. Findings marked **[hand-checked]** were
re-verified by the reviewing session itself after the subsystem reviews came
back; the rest were verified by the subsystem reviewer by reading the code
path and, where noted, by a reproduction run against a throwaway database or
fake sim.

Scope: everything **except** the two areas under active development:
the AI pilot / autopilot (`services/ai_pilot/`, `xplane/PI_capvsar_flight_control*`,
`scripts/fly_*.py`, flight-test harnesses) and the G1000 enhancement work
(`~/Projects/g1000-sar`). The C182T flight model's aerodynamics were also
skipped (being tuned on `fix/c182-review-20261010`); only the mechanics of the
build pipeline were reviewed.

Companion: [`PROJECT_REVIEW_2026-09-08.md`](PROJECT_REVIEW_2026-09-08.md) and
the tracker [`BUG_TRACKER.md`](BUG_TRACKER.md). Every "fixed" tracker item
touching the reviewed areas was spot-checked; three were found to be fixed in
name only (I-15, L-9, and the X-14 remainder) and are called out below. No
finding here duplicates an open tracker item.

Finding IDs continue the September scheme with a `2` prefix so they can be
added to `docs/bugs/tracker.json` without collision: **X2** console backend,
**F2** console frontend, **L2** flight planner, **P2** DF plugin, **I2**
instruments, **O2** ops/infra, **B2** aircraft build & content pipeline,
**D2** docs/process.

---

## 1. Executive summary

Baseline: `.venv/bin/python -m pytest` on `main` gives **885 passed, 2 failed**
(both in `tests/test_console.py`, see O2-1). The planner's own 106 tests and
the board's 27 are not collected by the default run and the planner's cannot
run in the repo venv at all (O2-2).

The ten things that matter most, in order:

1. **Beacon truth leaks again, through the live telemetry feed.** The plugin
   reports `bearing_true` and `distance_nm` to the beacon with every position;
   the hub stores the whole dictionary on the aircraft record and `/api/state`
   and `/ws` hand it to anyone on the LAN with no login. That is a fix on the
   beacon every second. The September X-1 regression test never posts a
   position, so the leak test walks an empty aircraft list. (X2-1) [hand-checked]
2. **A revealed old sortie reveals the scenario currently being flown.**
   `/track` reads the beacon from the live scenario row keyed by the old
   sortie's `scenario_id`, gated only on the old sortie's `revealed` flag.
   Scenarios are reused, so this is the normal case. (X2-2)
3. **Three Air Manager controls and the whole clearance recorder are dead
   live, while their tests pass.** The GMA recorder subscribes to datarefs
   that do not exist in X-Plane 12 (I-15 is marked fixed but is not), the TDFM
   copilot PTT dataref does not exist, and the TDFM power/squelch-defeat and
   GMA VOL/SQ pushes rely on `dial_add` press callbacks that Air Manager 4.2
   does not offer. The fake harness in `tests/am.py` accepts any dataref name
   and models the press callback, so the suite is green. (I2-1, I2-2, I2-3)
   [hand-checked against `DataRefs.txt` and the AM 4.2 code snippets]
4. **The aircraft builder deleted the installed aircraft before it had built
   anything.** Resolved on `origin/main` by 57663ec the same day (staged
   build, backup to `Output/capvsar-backups`, the N429CP livery now generated
   by the build). Left in the list because the review tree still had it and
   because the backup directory now needs a retention rule. (B2-1)
5. **Flight planner: a mistyped datum silently plans the search 10 NM away.**
   Unknown identifiers fall through to a hard-coded default point and return
   `success: true`. Offline, the terrain profile reports 0 ft terrain and a
   green "ADEQUATE" clearance, and the nav log plans on invented 15–30 kt
   winds with no marker. (L2-1, L2-4, L2-5)
6. **Mission radio: an airband receiver timeout tears down the tactical net**,
   and the Form 110 log, the deliverable of the MRO role, lives only in page
   memory and is lost on any reload or tab eviction. (F2-2, F2-4)
7. **The DF plugin leaks a worker thread on every disable/enable while the
   console is slow, and never resets per-beacon state when the instructor
   starts a new sortie on a different scenario**: the crew keeps the old
   bearing and ident for up to two minutes while distance already reads the
   new beacon. (P2-1, P2-2)
8. **Deployment fails closed in the wrong places.** A blank Mumble password
   produces a password-less voice server on the one internet-forwarded port;
   `CAPVSAR_ENV` is never set so the production guard on `CAPVSAR_DEV_OPEN`
   is inert; the board healthcheck cannot fail; runtime state lives inside
   the git checkout; there is no restore procedure for the backups. (O2-3..O2-7)
9. **Every console's "Flight Planner" link is rewritten to port 8090**, which
   Caddy no longer publishes. One click from any header fails. (F2-1)
10. **The docs site republishes the manufacturer manuals** that NOTICE and
    D-4 deliberately keep out of git, and the tracked handbook HTML embeds
    absolute `/home/ron/...` image paths so every figure is broken for anyone
    else. (B2-9, B2-7)

Cross-cutting themes, which are where the structural fixes are:

- **Test harnesses that are more permissive than the real thing.** `tests/am.py`
  accepts any dataref and invents an API; `tests/xp.py` ignores dataref types;
  `test_sar.py` carries a dead Flask stub; the truth-leak test never posts a
  position. Four of the top ten findings were invisible to a green suite.
- **No single truth boundary.** `public_scenario()` filters scenarios but
  nothing filters aircraft or sortie payloads. One serializer used by
  `/api/state`, the WS first frame, the ticker and `/track` would have
  prevented X2-1 and X2-2 and makes the invariant testable in one place.
- **Offline honesty.** The mission base is required to work offline, but the
  planner fakes winds and terrain, the frontend falls back to internet tiles,
  and the plugin swallows transport errors silently.
- **Three search-pattern geometries.** The planner, `scripts/fly_search_grid.py`
  and `g1000-sar` disagree on SS waypoint numbering (off by one), PS anchor
  and inset, and CS first-sweep inset. A briefed "turn at SS04" means
  different corners in different tools. (L2-13)
- **Dev environment drift.** The venv is Python 3.14 with FastAPI 0.143
  against a service pinned at 0.115.6 on Python 3.12, with no root
  requirements file. Two tests already fail on it and more are one bump away.

---

## 2. Exercise console backend (X2)

Reviewer repro: TestClient probes against throwaway databases for X2-1, X2-2,
X2-3, X2-6, X2-7.

| ID | Sev | Finding | Where |
|---|---|---|---|
| X2-1 | critical | Live `df` dict with `bearing_true`/`distance_nm` broadcast unfiltered to anonymous `/api/state` and `/ws` every second. X-1's leak test posts no position. **[hand-checked]** | `app/hub.py:56-67`, `routers/telemetry.py:66-78`, `routers/system.py:28-30`, `xplane/PI_capvsar_df.py:1503-1508` |
| X2-2 | high | `/track` of any previously revealed sortie returns the beacon of the scenario now being flown (same `scenario_id`); `/api/sorties` lists ids and `revealed` without auth. | `routers/sorties.py:125-131,156-184` |
| X2-3 | high | `ScenarioIn.effects: dict[str, Any]` accepts `NaN`/unknown keys; one such scenario 500s `/api/scenarios` and `/api/state` for everyone and the ticker emits bare `NaN` that browsers reject. Undoes X-6 on this route. | `app/models.py:28-56`, `app/hub.py:39` |
| X2-4 | high | Radio stream fails open to any claimed callsign whenever `CAPVSAR_TOKEN_BASE` is unset, which is the roster-only production mode. Comment "same condition access.enforce() fails open on" is stale since X-11. This is the open remainder of X-14. | `app/radio.py:467-479`, `pages.py:92-112`, `auth.py:155-157` |
| X2-5 | medium | Blocking SQLite auth lookups called directly from async handlers (event-loop stall carrying 20 ms Mumble frames); X-3 class. | `routers/comms.py:37`, `app/radio.py:471` |
| X2-6 | medium | `init_auth_db()` runs migrations plus a write transaction on every authenticated request; `auth_db()` never sets `synchronous=NORMAL` (FE-9 fixed `store.db()` only). | `app/access.py:71-128,200-229` |
| X2-7 | medium | Shared-radio watchdog belongs to the first face; a full queue on one face marks the whole radio failed, contrary to its own comment. | `app/radio.py:185-201,485-540` |
| X2-8 | medium | Scenario `notes` not truth-filtered; the seed scenario's notes name the beacon location in words and base renders them. | `app/roles.py:17-25`, `app/settings.py:46-49`, `static/base.js:234` |
| X2-9 | low-med | Concurrent `POST /api/sorties` can leave `hub.sortie` on a sortie the DB closed; `stop` is not idempotent and re-stamps `stopped`. | `routers/sorties.py:32-83` |
| X2-10 | low | Role tokens accepted as `?token=` and so land in uvicorn/Caddy access logs, including the plugin key on the one route that serves truth. | `app/access.py:175-178` |
| X2-11 | low | `DELETE /api/scenarios/{id}` with a running sortie strands it; `rehydrate()` returns early and the sortie never closes. | `routers/scenarios.py:63-67`, `main.py:48-55` |
| X2-12 | low | `/api/setup` accepts untyped aircraft/staff dicts: non-string callsign 500s; `staff[].role` unchecked, so a roster row with role `plugin` can be minted. | `app/models.py:166-172`, `app/access.py:313-339` |

Cleared after checking: pymumble `SoundOutput` locking, `geo.py` bearing
intersection and antipodal rejection, `prune_positions` window, migration
idempotence, WS origin check behind Caddy, CSRF posture (`SameSite=Lax`, all
mutations POST/DELETE).

Improvements: one `public_state()` serializer (above); move `init_auth_db()`
to startup and make per-request auth a single indexed `SELECT`; gate the
read surface (`/api/state`, `/ws`, `/api/sorties*`, `/api/messages`,
`/api/bearings`) on any valid session now that roster auth is universal;
key `ICS_STATE` by aircraft id instead of one global dict with a `'MO' in
name` substring test; cap `PositionIn.df` size and whitelist keys; `ruff F401`
pass over the routers (every router copies a 12-line import block).

Version-skew notes beyond O2-1: `tests/test_radio.py:114,579` pass
`cookies=` per request, which Starlette 1.x deprecates; the httpx-backed
`TestClient` is itself deprecated in Starlette 1.7.

## 3. Exercise console frontend and static sites (F2)

Truth-leak check of page templating: clean. `/instructor`, `/base`,
`/debrief`, `/radio` serve static files; truth only arrives via the API (see
X2-1 for the API).

| ID | Sev | Finding | Where |
|---|---|---|---|
| F2-1 | high | `charts.js` rewrites every `a.nav-planner` href to `//host:8090/`, a port Caddy no longer publishes; the HTML hrefs (`/planner/`) are already right. | `static/charts.js:88-93` |
| F2-2 | high | Airband join timeout and airband pong timeout call `connectionLost()` and drop the tactical net; F-10's own `airbandLost()` is used on the close/error paths only. Reconnect loop with alarm for the 17th Mumble session. | `static/mission-radio.js:570,775` |
| F2-3 | medium | Form 110 table rebuilt from scratch on every transmission, kicking the MRO out of the cell they are typing in. | `static/mission-radio.js:129-150,697-707` |
| F2-4 | medium | Form 110 log held only in page memory; reload, back-swipe or iOS tab eviction discards a multi-hour log. | `static/mission-radio.js:112-113,769` |
| F2-5 | medium | Shared role token stored in `localStorage` for the browser-profile lifetime and solicited via `prompt()` on any 403, including from roster users who merely lack the role (aircrew on `/base`). Logout clears the cookie only. Obsolete since X-12/X-13; should redirect to `/login`. | `static/charts.js:102-128`, `app.js:290-297`, `base.js:368-375` |
| F2-6 | low-med | Open redirect: `next` from the query string assigned verbatim to `location.href` after login. | `static/login.js:11,64-65` |
| F2-7 | medium | Debrief: selecting a sortie with no positions leaves stale callsigns in `order`; the next seek throws on every 250 ms tick. No `.ok`/catch on `loadList()`/`load()`. | `static/debrief.js:56-72,133-137` |
| F2-8 | low | Hard-coded `https://192.0.2.151/radio` on the headset help page offline tablets are told to read. | `static/radio-help.html:19`, `docs/mission-base-radio/README.md:3-12` |
| F2-9 | low | Every bearing-log failure (403 expired session, 503, 422) shows "That callsign is not reporting a position yet"; `loadScenarios()` has no `.ok` check; Stop/Reveal ignore the response. | `static/base.js:342`, `app.js:139,157-158` |
| F2-10 | low | Setup page "Target Exercise Scenario" control is never sent; `SetupPayload` has no field for it. | `static/setup.html:40-45`, `setup.js:262-267`, `app/models.py:166-170` |
| F2-11 | low | One malformed control frame calls `disconnect()` (clears `wantOnline`) so FE-5 never retries. | `static/mission-radio.js:667` |
| F2-12 | low | Legacy console: spacebar PTT excludes only `INPUT`; a message is logged as sent even when `POST /api/messages` failed. | `static/radio.js:445-468,835-849` |

Improvements: move the verbatim-duplicated `esc`/`planeIcon`/`fmtDur`/WS
`connect()`/auth badge/Zulu clock into `charts.js`; ship the F-8 geodesy block
as one shared file so the instructor's bearing ray stops using the flat-earth
approximation `base.js` abandoned; reuse `mission-radio.js`'s exponential
backoff in `app.js`/`base.js`/`radio.js` and add F-4-style backfill to the
instructor view; a dark theme for the Leaflet consoles (the radio page already
has one); autosave the Form 110 to `sessionStorage` and optionally POST
entries for debrief; remove the hard-coded shortcut codes from
`login.html` rather than regex-stripping them (the raw file is still served by
the static mount); update `docs/mission-base-radio/README.md` and
`radio-help.html` for F-9/F-10 (dual receiver, 8 dual-radio desks);
`OfflineAssets` test should hit `/instructor`, not the inline-only portal.

Questions: `pagehide` → `disconnect()` on iOS Safari backgrounding;
`secure=True` login cookie makes any plain-HTTP dev console a login loop
unless `CAPVSAR_DEV_OPEN=1`; 500 ms keepalive per socket, two sockets per
desk.

## 4. Flight planner (L2)

The planner suite (106 tests) passes under a scratch venv with Flask 3.0;
it is not collected by `pytest.ini` and cannot run in `.venv` (no Flask; the
stub in `test_sar.py:19-35` predates the `Response`/`ProxyFix` imports). It
also cannot share a pytest process with `tests/test_geodesy.py` because both
put a top-level `app` on `sys.path`.

| ID | Sev | Finding | Where |
|---|---|---|---|
| L2-1 | high | Unresolvable datum (typo, out of range, DB still downloading) falls through to `(33.17, -117.0792)` and returns `success: true`; the UI never sends `datum_lat/lon`. Same shape as fixed L-11. | `app.py:1936-1947`, `static/js/app.js:1028-1031` |
| L2-2 | med-high | No waypoint cap on FMS export: 200 legs → 201 waypoints, `export-fms` accepts any list (verified `NUMENR 301`); X-Plane's FMS holds ~100, the G1000 99. Confirm the XP12 figure, then cap and say so. | `app.py:97,938-977,2016-2032` |
| L2-3 | medium | L-9 is marked fixed but five endpoints still return Werkzeug HTML 500 on bad numbers (`calc_route`, `wb`, `sar_export_fms`, `sar_generate`, `terrain_profile`); the JS shows "Unexpected token '<'". | `app.py:843,940,962,1483-1485,1617-1619,1763,1936,2022` |
| L2-4 | med-high | Terrain profile returns `(idx, 0)` on any USGS failure, so offline every route shows 0 ft terrain and a green ADEQUATE badge. | `app.py:1817-1829`, `app.js:776-781` |
| L2-5 | medium | Offline, `simulate_winds` invents 15–30 kt from a lat/lon hash; the nav log prints them with no "(sim)" marker (the weather brief does mark it). | `app.py:697-707,1538-1540`, `app.js:516-520` |
| L2-6 | medium | Console push uses `waypoints[0]` as the datum: correct for SS (`DATUM`), wrong for PS (`PS01`, a corner + S/2) and CS (left end of the first sweep). The alert circle and the 2.5 NM beacon offset anchor on a box edge; the beacon can land outside the briefed area. `pattern.datum` is available in the JS and not sent. | `app.py:2100-2131`, `app.js:1213-1225` |
| L2-7 | low-med | "Apply to Route" drops `DATUM`, so the nav log omits the leg that defines the square while the FMS export keeps it; pattern labels become `USR1..n` in the nav log. | `app.js:1145-1147`, `app.py:1495-1497` |
| L2-8 | low | `CS01` carries a fictitious 1.5 NM leg and heading nobody flies. | `app.py:875`, `app.js:1105` |
| L2-9 | low | d-TPP cycle computed from calendar month; FAA cycles are 13/year, so diagrams vanish for much of the year. | `app.py:1661-1667` |
| L2-10 | low | Live ArcGIS/OSM fallbacks in `app.js` bypass the L-8 tile cache when `/api/tile-sources` fails; the offline test scans templates only. | `app.js:30-32,94-100` |
| L2-11 | low | `get_climb` snaps both ends to the nearest 2000 ft row (L-6 fixed cruise interpolation only). | `app.py:1084-1091` |
| L2-12 | note | `_allow_vsar_export` rate limit is per-process memory; with 2 workers the limit is 10/min. | `app.py:1194-1204` |

**L2-13 — Pattern geometry conventions the G1000 work must agree on.** Read
against `~/Projects/g1000-sar/g1000_sar/mission.py:150-180`:

| Convention | Planner | g1000-sar | Agree? |
|---|---|---|---|
| Heading input | true | true | yes |
| SS leg lengths / default turn | S,S,2S,2S…, right | same | yes |
| **SS naming** | `DATUM`, `SS01` = end of leg 1 | `SS01` = the datum, `SS02` = end of leg 1 | **no, off by one** |
| SS leg count | API 1..40, UI 4..16 | 1..60 | range mismatch |
| **PS anchor** | datum = box corner, first lane S/2 inside, lanes right of axis | datum = first lane start, no inset, lanes on `turn` side | **no** |
| PS lane count | `ceil(width/spacing)` (last lane may lie outside the box) | `legs` given | different |
| PS naming | `PS01` first lane start, 2·lanes points | same | yes |
| **CS** | axis advanced S/2 before first sweep | first sweep at offset 0 | **no** |
| CS first sweep side | left end → right | `first_turn: right` | yes |

A third convention lives in `scripts/fly_search_grid.py:85-117` (datum-centred
box, odd leg count forced) and `tests/test_search_grid.py` pins that one.
Nothing asserts any two of the three agree. Recommended: write the table into
`docs/SEARCH_PATTERN_CONVENTIONS.md`, decide the SS numbering and the
half-spacing inset once (D1–D5 in `g1000-sar/docs/DESIGN_NOTES.md` already
records the G1000 side), and have both repos assert against one fixture JSON.

Improvements: add Flask/Werkzeug/pygeomag to dev requirements and the planner
tests to `pytest.ini` (needs the `app` module-name collision solved, e.g. a
`conftest.py` importing under a unique name as `tests/test_search_grid.py`
already does); split `app.py` (2294 lines) into geodesy / patterns / fms /
performance / weather / tiles / routes; one `_num()` validation helper plus a
JSON `errorhandler(Exception)`; an `offline` flag that disables USGS /
Open-Meteo / aviationweather / d-TPP and returns `unavailable` instead of 0 or
simulated; env-var the KSEE default point and the "ms01" status string.

Still unverified per `USER_GUIDE.md:366-370`: the G1000's display of the
exported `.fms`. The g1000-sar harness can now load a flight plan into a
running sim (`xp.loadFMSFlightPlan`), so this is cheap to close.

## 5. DF propagation plugin (P2)

Contract consistency plugin ↔ `cap_df.lua` ↔ both faceplates checked and
found clean (names, INT/FLOAT/BYTE types, 0..1→0..100 signal rescale in one
place, `-1` error sentinel, squelch percentage, `rx_open` audio gating,
`panel_seen` flip on power-up). Reviewer repro for P2-1 and P2-2 with the
fake sim.

| ID | Sev | Finding | Where |
|---|---|---|---|
| P2-1 | medium | Disable/Enable while the worker is inside a 4 s `urlopen`: join times out, `self.stop` is rebound to a fresh Event, the old worker loops on the attribute and never exits. Every reload with a slow console leaks another reporting thread (duplicate position reports). `DisableEnableCycle` only tests an instantly-failing `urlopen`. | `PI_capvsar_df.py:788-803,1413` |
| P2-2 | medium | New sortie on a different scenario (console swaps `hub.scenario` in one step, `running` stays true): plugin rebinds `self.scn` but never clears `held`, `samples`, `scan_hold_hz` or the decode. Old bearing for TIMEHOLD, old hex15 ident for up to 120 s, while `distance_nm` already reads the new beacon. | `:1278,1321,1423-1474` |
| P2-3 | med-low | No-ini default console URL is `http://192.0.2.151:8700`, a port O-8 made unreachable, and `note_poll_failure` swallows `URLError`/`OSError` silently; a mis-provisioned or TLS-untrusted station is deaf with no log line. | `:97,1482-1485` |
| P2-4 | low | `compute()` takes `s = self.scn` but `beacon_hz()`, `published_band()`, `load_decode()` re-read `self.scn`, so the EN-4 one-scenario-per-tick guarantee does not hold. | `:909,962,1058,1332` |
| P2-5 | low | Radio horizon uses MSL heights at both ends, so a beacon on 9000 ft ground is treated as on a 9000 ft tower; the term almost never bites in mountains. Use probed terrain as the reference. | `:1094` |
| P2-6 | low | Wall clock everywhere; no `sim/time/paused` read. A pause-to-brief expires held bearings and the decode hold. Use `time.monotonic()` and freeze on pause. | `:920,1278` |
| P2-7 | trivial | `fetch_scenario` comment promises a 404 fallback that is not implemented (behaviour is fine, comment wrong). | `:~1377` |
| P2-8 | trivial | `self.net` not initialised in `__init__`; Disable after a failed Enable raises inside the XPLM callback. | `:800` |

Improvements: snap `beacon_elev_ft` to probed terrain when the scenario gives
0 (today the beacon is modelled underground and every LOS ray fails); factor
the 240-line `compute()` into geometry → gating → link budget → bearing with
one publish step; convert the ~1000-line import-time script
`tests/test_engine.py` into pytest functions; make `tests/xp.py` record dataref
types and assert the read callback returns a matching Python type; mark
`docs/PHASE0_DF_PLUGIN.md` historical (it still says "edit CONSOLE and
CALLSIGN at the top of the plugin"); fix the `spread` self-contradiction in
`DATAREF_CONTRACT.md`; short exponential backoff on consecutive console
failures so REPORT_S stays honest.

Questions: whether XPPython3's bundled Python sees the OS certificate store
where ms01's CA is installed (check `ssl.get_default_verify_paths()` under
that interpreter once); `cap/scenario/beacon_*` and `distance_nm` are plain
readable datarefs on the aircraft PC (P-2 accepted this; `distance_nm` is
published even while the receiver is silent, which is a stronger hint than
the DF ever gives).

## 6. Air Manager instruments (I2)

Evidence beyond the repo: `X-Plane 12/Resources/plugins/DataRefs.txt` (5647
entries), `Commands.txt`, the AM 4.2 code snippets in
`~/Documents/Air Manager 4.2 Home use/code_snippets/`, the stock G1000
instrument's Lua, and `~/Air Manager/log.txt`.

| ID | Sev | Finding | Where |
|---|---|---|---|
| I2-1 | P2 | GMA clearance recorder subscribes `sim/cockpit2/radios/indicators/com1_receiving`/`com2_receiving`, which do not exist; the real ones are `sim/atc/com1_rx`/`com2_rx`. COM1/COM2 traffic is never recorded. **I-15 is marked fixed on the strength of a test that passes because `tests/am.py` auto-creates any dataref name.** **[hand-checked]** | `mo-audio-panel-gma1347/logic.lua:532,543` |
| I2-2 | P2 | TDFM subscribes `sim/cockpit2/radios/actuators/audio_panel_copilot_ptt`; no dataref containing "ptt" exists. Contract line 335 ("PTT also synchronised from X-Plane") is not met. **[hand-checked]** | `cap-fm-tdfm-136b/logic.lua:736`, `DATAREF_CONTRACT.md:335` |
| I2-3 | P2 | `dial_add` is called with press/release callbacks (TDFM main encoder power on/hold-off, guard encoder squelch defeat, GMA VOL/SQ swap). AM 4.2's `dial_add` takes one turn callback; the stock G1000 overlays `button_add(nil, nil, ...)` for every knob push. Lua ignores extra args, so no log error. The harness models the press callback and every TDFM test powers the radio through it. Live check: hold the TDFM main encoder 2 s with the bus up. **[hand-checked against the AM snippet]** | `cap-fm-tdfm-136b/logic.lua:521-561`, `mo-audio-panel-gma1347/logic.lua:448-455`, `tests/am.py:194-202` |
| I2-4 | P2/P3 | DF audio re-issues `sound_loop(noise)` on every `update()` (several per second on a weak signal); if AM restarts an already-playing loop, the hiss stutters exactly in the weak-signal case I-17 was for. | `_shared/lib/cap_df_audio.lua:83-84` |
| I2-5 | P3 | `LS` and `BURST` timers read `00:00` before any signal was ever received (`last_signal`/`burst_age` initialised to 0, not nil). | `_shared/lib/cap_df.lua:60-61,258,318` |
| I2-6 | P3 | Becker STORE tone-suppression survives a power cycle; the real head powers up clean. | `becker-sar-df-517/logic.lua:593-600,673` |
| I2-7 | P3 | Master switch and CB panel only publish from the button callback; a reload desynchronises the drawn state from `cap_mission_*`. Publish once at load as the TDFM does. | `cap-mission-master-switch/logic.lua:31,98`, `cap-mission-cb-panel/logic.lua:43,191` |
| I2-8 | P3 | G1000 watchdog adds a new 2048×1536 `video_stream_add` node on every re-arm, never removing the old one; the stale banner and manual re-arm hotspot are covered after the first re-arm. Not deployed and not in the panel, so O-7b (open) is not yet addressed in the deployed panel either. | `g1000-mfd-watchdog/logic.lua:279-360` |

Harness permissiveness, root cause of I2-1..I2-4: `xpl_dataref_subscribe`
accepts any name/type and registers only the first name of a multi-dataref
call with a one-argument callback (so `cap_df.subscribe()`'s 8/9-argument
callbacks are never exercised; tests poke `cap_df.state` directly, bypassing
the I-1 redraw gating); `dial_add` takes press/release; `xpl_command` and
`xpl_dataref_write` accept any name; `sound_*` record a string.

Improvements: validate names in the harness against `DataRefs.txt` /
`Commands.txt` (path from env, skip if absent) plus the `cap/df/*` list
scraped from the plugin, which enforces `DATAREF_CONTRACT.md` mechanically;
model multi-dataref subscriptions; one `_shared/lib/cap_power.lua` replacing
the four copy-pasted bus-power blocks (~80 lines); a `knob_push()` helper that
adds the `button_add` hit region; `reset_volatile()` from `power_off()` in both
DF heads; clear `active_rx` on GMA power loss; document that consumers must
gate on `cap_fm_power_on` because `publish()` on power-off leaves frequency
and channel at their last values.

Questions: COM3 MIC deliberately sends no `xpl_command`, so a PTT device also
mapped to an X-Plane PTT transmits on COM1/2 at the same time (intended?);
`_fill("rgba(...)")` CSS form in the watchdog is not used by any bundled
instrument; what AM does asking for 15 bytes of a 0-length `Type_Data`
accessor; the Becker `redraw()` comment still describes a `pcall` I-2 removed.

## 7. Deployment, infrastructure, repo hygiene (O2)

| ID | Sev | Finding | Where |
|---|---|---|---|
| O2-1 | high (dev) | Two `test_console.py` tests fail on `main` because the venv's FastAPI 0.143 adds lazy `_IncludedRouter` entries without `.path` and the tests iterate `app.routes` flat. Routes are served. Fix the test to walk recursively or use the OpenAPI schema, and pin the dev env. **[hand-checked]** | `tests/test_console.py:871,920` |
| O2-2 | high (dev) | No reproducible test environment: no root `requirements*`/`pyproject`/lock; `.venv` is ad hoc Python 3.14.4 with fastapi 0.143 / starlette 1.7 / pydantic 2.14 / pytest 9.1 against services pinned 0.115.6 / 2.10.4 on Python 3.12 images. The only instruction is one line in `docs/mission-base-radio/README.md:139`. `pytest.ini` skips the board (27) and planner (106) suites, which also cannot be collected with the root suite in one process (`app` package collision). `scripts/ci_local.sh` exists, handles this, and is mentioned in no doc; there is no CI. | `pytest.ini:6`, `scripts/ci_local.sh:166-171` |
| O2-3 | high | Blank `MUMBLE_SERVER_PASSWORD`/`MUMBLE_SUPERUSER_PASSWORD` deploy a password-less voice server on 64738, the one port the router forwards to the WAN; compose has no `:?`, `.env.example` ships both blank, `deploy.sh` checks only that `.env` exists. | `docker-compose.yml:26-27`, `.env.example:8-9`, `scripts/deploy.sh:8`, `infra/ROUTER.md:22-27` |
| O2-4 | high | `CAPVSAR_ENV` is set nowhere (compose, `.env.example`, `deploy.sh`), so the X-11 production refusal of `CAPVSAR_DEV_OPEN` is inert; safe today only because compose does not forward the flag. Hardcode `CAPVSAR_ENV: production` in the exercise block. Compose and `.env.example` still describe the pre-X-11 "unset means open" behaviour. | `app/access.py:163-165`, `docker-compose.yml:78-82`, `.env.example:19-25` |
| O2-5 | medium | `deploy.sh` does not know the board service: no host paths, not in the build list. A fresh host creates `id_ed25519` and `known_hosts` as directories, and the README's `ssh-keygen` then fails. | `docker-compose.yml:196-198`, `scripts/deploy.sh:24-50`, `services/board/README.md:62` |
| O2-6 | medium | Board healthcheck cannot fail: HTTP 200 `status: ok` with `board_present`/`git_sync`/`writes_enabled` all false; `GitSync.pull` is a silent no-op on a non-repo. The exercise service does this right. | `services/board/app/main.py:109-116`, `docker-compose.yml:213-215` |
| O2-7 | medium | All runtime state (`exercise.db`, Mumble DB with channel tree and SuperUser hash, published CA, planner data, board repo) is bind-mounted from gitignored paths inside the checkout; one `git clean -fdx` or re-clone on ms01 loses it. Only `exercise.db` has a backup. | `docker-compose.yml:20,69,70,162,196` |
| O2-8 | medium | Backups are write-only: no restore mode, no doc, no test that a backup opens against the current schema; the deployment plan itself requires "test a full restore". | `scripts/backup_exercise_db.py`, `docs/LAB_HOSTED_DEPLOYMENT_PLAN.md:128` |
| O2-9 | low-med | `pymumble` pinned to a GitHub tarball by commit SHA with no `--hash`; GitHub tarballs are not content-addressed. This component holds the Mumble password. | `services/exercise/requirements.txt:6` |
| O2-10 | low | `preflight.py` probes planner port 8090; the planner has exposed 8080 since L-12/O-8. `deploy.sh`, `ROUTER.md`, `WEB_HOSTING_AND_IDENTITY_PLAN.md` say 8090 too. | `scripts/preflight.py:80`, `scripts/deploy.sh:104` |
| O2-11 | low | `.ci-out/` (logs, a downloaded `.deb`, a sitecustomize shim) is not gitignored. | `scripts/ci_local.sh:118-121`, `.gitignore` |
| O2-12 | low | `scripts/wg-peer.sh` drives a WireGuard container the repo says was removed and must not be recreated; tracker O-2 still cites it as the onboarding tool. | `scripts/wg-peer.sh:220-229`, `docker-compose.yml:221-225`, `infra/ROUTER.md:5-20` |

Repo hygiene checked and fine: the 3 MB zip, `build/`, `output/`, `logs/` are
untracked and ignored; no keys, certs or sqlite files tracked; no literal
secrets in tracked files. `CHANGELOG.md` (436 KB) is hand-written prose, the
project's engineering journal; consider splitting by month. ~2.5 MB of figure
PNGs are duplicated under `docs/figures/manual/` and `website/images/`.

Improvements: `requirements-dev.txt` that `-r`s the three service pins plus
pytest/httpx/Flask/pygeomag, used by `ci_local.sh`; a Gitea Actions workflow
running `ci_local.sh --no-shim` on Python 3.12; `${VAR:?}` for every secret
and drop the dead `CAPVSAR_MUMBLE_*` lines from `.env.example`; pin
`python:3.12-slim` by digest as O-5 did for Mumble and Caddy; `.dockerignore`
for exercise and board; stop `deploy.sh` sourcing `.env` as shell (quoting
differs from compose's parser); `provision_mumble.py --check` so redeploys stop
blipping the voice net.

Questions: does the pinned Caddy image contain `curl` for its healthcheck
(official Alpine image ships busybox `wget`); mumble-docker behaviour on an
empty superuser password; read-only WAL backup as a non-root operator when
`-shm` is absent; the board pushing to `main` directly while everyone else
works on branches.

## 8. Aircraft build pipeline and content generators (B2)

Tests pass (86). Not a bug, recorded so nobody re-chases it:
`DELIBERATELY_EXCLUDED` applies only to the `lights` bucket, but every
excluded object in the pinned donor is untextured, so nothing leaks today
(listed as improvement 1).

| ID | Sev | Finding | Where |
|---|---|---|---|
| B2-1 | **resolved on origin/main** (57663ec) | `shutil.rmtree(target_dir)` runs before conversion and the `.acf` patch; a mid-build failure leaves no aircraft, and the installed `liveries/Civil Air Patrol (N429CP - C172 Adapted)/`, which the script does not create, is destroyed on the next run. Build into a sibling and rename; preserve liveries the source did not supply. | `scripts/build_c182t_package.py:479-481,525,540-552` |
| B2-2 | **resolved on origin/main** (57663ec: `DEFAULT_DONOR` imported from the fetcher) | Builder default donor path `~/.cache/cap-vsar/flightgear-c182-<commit>` ≠ fetcher default `~/.cache/capvsar/capvsar-flightgear-c182-pinned`; the README recipe cannot run and re-downloads 120 MB into a second cache. | `build_c182t_package.py:39-44`, `fetch_flightgear_c182.py:27-28`, `README.md:258` |
| B2-3 | low | Selection icon renders the literal text `&bull;` (`ImageDraw.text` does not decode entities); verified on the installed icon, which also still says N499CP. | `build_c182t_package.py:219-222` |
| B2-4 | **resolved on origin/main** (57663ec: `patch_acf_lines` raises unless each field occurs exactly once) | "Applied N of 50" patches is printed and never enforced; a typo in a new `ACF_PATCHES` key or a Laminar field rename silently ships the C172 value. `PatchHygieneTests` checks anchoring and uniqueness, not that each matches a line. | `build_c182t_package.py:540-554` |
| B2-5 | medium | Prop-lever extraction hard-codes TRIS index offsets (19629/534, 19179/450) into Laminar's cockpit OBJ with no validation; any X-Plane re-export builds the lever from arbitrary geometry and prints success. | `build_c182t_package.py:276-277,355-356` |
| B2-6 | low | Flap animation maps 0→38° over `flap1_deg` 0→40 while the `.acf` patch sets flap travel 38, so the visual flap stops at 36.1°; `ElevatorTrim` is driven by `elevator1_deg` not trim. | `convert_flightgear_c182.py:299-335` |
| B2-7 | medium | `generate_manual.py` hard-codes `/home/ron/Projects/cap-vsar/docs/...` (a *different* checkout) and embeds `src="/home/ron/..."` into the **tracked** handbook HTML; 8 figures broken for anyone else, inherited by `build_docs_site.py`. `build_radio_reference_doc.py:842` bakes the same path into a tracked `.md`. | `scripts/generate_manual.py:17-18,533,968` |
| B2-8 | low | `build_radio_reference_doc.py` (python-docx) and `build_docs_site.py` (markdown) cannot run in `.venv` or system Python; dependencies declared nowhere. `make_df_artwork.py` hard-codes Debian font paths. | `build_radio_reference_doc.py:11-17`, `build_docs_site.py:209`, `make_df_artwork.py:46-47` |
| B2-9 | medium | `build_docs_site.py` copies the Becker, RT-600, TDFM and GMA manufacturer manuals into `build/docs-site/files/` for a site intended to be served to participants; NOTICE and D-4 keep these out of git for this reason. Not in D-5's file list. | `scripts/build_docs_site.py:109-117,312-323` |
| B2-10 | low | Tracked `fig_c182t_aircraft.png` (docs and website) is a render of Laminar's C172SP mesh in an N429CP livery: same category of question as D-5's stock-MFD tile, not covered by `test_release_boundary.py`, and no longer depicts the aircraft the package ships. | `docs/figures/manual/`, `website/images/`, `website/index.html:161` |
| B2-11 | note | `c182t_corrections.py` edits geometry in memory only, never the `.acf`; mechanics are sound. One weakness: the radial-scale branch ignores the JSON `axis_from` and always scales about `PROP_ROTATION`. | `scripts/c182t_corrections.py:281-288,357-358` |

Improvements: apply the exclusion lists to every bucket and reject AC3D line
and two-sided surfaces explicitly; assert every emitted surface's object has a
texture (materials are discarded); per-position smoothing honouring `crease`;
staged build with atomic swap and stop copying `full_white` DDS textures for
objects no longer attached; a 1-triangle hidden object instead of
`POINT_COUNTS 0 0 0 0` so `validate_obj8` covers it; end-to-end converter
test on a synthetic donor, `add_prop_lever` test, `validate_obj8` checking
`IDX < vertex_count`; `--force` hint and `urlretrieve` timeout in the
fetcher; generate the icon from a render of the package itself.

Questions: `ATTR_no_cull`/`BLEND_GLASS` before `POINT_COUNTS` loads in
X-Plane but may not in XPlane2Blender/ObjView; the GPL plan should say in one
sentence that hinge coordinates and landmark numbers copied from the donor
XML are considered acceptable facts; `test_flightgear_c182.py` has
`unittest.main()` before `class LiveryTests` (harmless under pytest).

---

## 9. Suggested order of work

**Implementation status (branch `impl-wave-a-2026-10-10`):** wave A is done:
X2-1, X2-2, X2-4, X2-8 (D1), O2-1, O2-3, O2-4, F2-1, L2-1, L2-4, L2-5, L2-6,
P2-2, each with a test that fails without the fix. Full suite 912 passed, 0
failed (baseline 885 passed, 2 failed). Not yet done from wave A's neighbours:
the instructor console still talks to `/ws` by cookie only, so an instructor
who authenticates with a pasted token (not a login) sees the redacted live
feed; F2-5 removes that path.

Wave A, before the next exercise with participants (truth and safety):
X2-1, X2-2, X2-8 (one `public_state()` serializer plus a leak test that posts
a position and runs two sorties on one scenario); X2-4; O2-3, O2-4; F2-1;
L2-1, L2-4, L2-5, L2-6; P2-2.

Wave B, before the next sim session (things a crew will hit): I2-1, I2-2,
I2-3 with the harness name validation so they stay fixed; I2-4; F2-2, F2-3,
F2-4; P2-1, P2-3; B2-5.

Wave C, hygiene that makes A and B stick: O2-1, O2-2 (dev requirements,
planner and board suites in the default run, CI on 3.12); L2-3 with the
`_num()` helper; O2-5..O2-8; B2-7, B2-9.

Wave D, when the G1000 pattern work lands: L2-13 conventions document and
cross-repo fixture; L2-2 after an FMS load test; close the `USER_GUIDE`
"not yet checked in X-Plane" item with the g1000-sar harness.

Design decisions for the four items that need one are in
[`DECISIONS_2026-10-10.md`](DECISIONS_2026-10-10.md).

Everything here can be added to `docs/bugs/tracker.json` under the `2`-prefixed
IDs; that step was deliberately left for the maintainer so wave dates can be
re-anchored to the real exercise calendar.
