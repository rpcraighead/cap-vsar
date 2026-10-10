# Design decisions — 2026-10-10

Decided by Claude (Fable) for the four items in
[`PROJECT_REVIEW_2026-10-10.md`](PROJECT_REVIEW_2026-10-10.md) that need a
judgment before anyone writes code. Ron can overturn any of them. Each is a
decision with its reason and the shape of the change, written so a cheaper
model can implement it from the review's file:line list without re-deciding.
Same format as `g1000-sar/docs/DESIGN_NOTES.md`.

Scope of each: **D1** truth boundary in the exercise console (X2-1, X2-2,
X2-8, X2-4); **D2** search-pattern conventions across the planner,
`fly_search_grid.py` and `g1000-sar` (L2-13, L2-6, L2-7); **D3** the Air
Manager test harness (I2-1..I2-4); **D4** the aircraft builder's install
step (B2-1, now mostly resolved on `origin/main`).

---

## D1. One truth boundary, keyed by who is asking

### The decision

1. **Truth is snapshotted into the sortie row at start.** `start_sortie`
   copies `beacon_lat`, `beacon_lon`, `beacon_elev_ft`, `band`, `freq_hz`
   and `cs` into new `sorties` columns (migration guarded by
   `PRAGMA table_info`, as `effects` was for X-6). Everything that answers
   "where was the beacon for sortie N" (`/track`, reveal, the debrief, the
   plugin's `/api/plugin/scenario` while that sortie runs) reads the sortie's
   copy, never the live scenario row. Editing or reusing a scenario can then
   never change what an old sortie reveals, which closes X2-2 by
   construction rather than by a check.
2. **One serializer owns the browser-facing state.** `roles.public_state(
   snapshot, viewer_role, revealed)` replaces the ad hoc filtering in
   `hub.snapshot()`, `/api/state`, the `/ws` first frame and the ticker. It
   applies three rules: scenario truth fields are stripped unless the viewer
   is `instructor` or the sortie is revealed (as today); each aircraft's `df`
   dictionary is stripped to `{valid, head_type, power, tuned_to}` unless the
   viewer is `instructor` or the sortie is revealed; scenario `notes` is
   instructor-only, base and aircrew see `alert_text` and the `alert_*`
   fields only. The instructor keeps the full `df` because the instructor
   console renders it ("why can't they hear it" is answered there) and the
   instructor already holds truth.
3. **Every browser-facing read requires a session.** `/api/state`, `/ws`,
   `/api/sorties`, `/api/sorties/{id}/track`, `/api/messages`,
   `/api/bearings` and `/api/radio/config` take a new `any_role` dependency:
   any valid roster session or configured token, or `dev_open()`. The
   WebSocket resolves the session from the handshake cookie (same origin, so
   the browser sends it) and the hub stores `clients: dict[WebSocket, str]`
   mapping each socket to its role. `broadcast()` serializes once per
   distinct role present, not once per client. `/api/plugin/*` is unchanged.
4. **Debrief of a revealed sortie is for base, aircrew and instructor**, which
   is what `access.py`'s role table already says. `/track` of an
   *unrevealed* sortie that is not the running one returns positions only
   (no `df`, no beacon), same as today.
5. **The radio stream's fail-open goes.** `radio.py` admits a socket without
   a session only when `dev_open()` is true. The comment about "the same
   condition `access.enforce()` fails open on" is deleted with it; that
   condition no longer exists since X-11. Same change for the three page
   routes that still serve `/instructor`, `/base`, `/setup` HTML to anonymous
   callers: redirect to `/login`.
6. **Reusing a revealed scenario is allowed but warned.** `start_sortie`
   returns `"warning": "scenario revealed in sortie <id> on <date>"` when an
   earlier sortie on the same scenario was revealed, and the instructor
   console shows it. The console cannot know whether the same crews are in
   the room; the instructor can.

### Why

- The leak in X2-1 exists because filtering was added per endpoint as each
  leak was found (X-1 scenarios, V2-5 `/track`). A third endpoint leaked the
  same fact in a different shape. The only durable fix is one function that
  every browser-facing payload passes through, with a test that posts a
  position, runs two sorties on one scenario, and walks every endpoint as
  every role.
- Snapshotting truth into the sortie follows the pattern X-6 set for
  effects: the sortie flies with a copy. It also makes the record honest: the
  debrief replays the beacon that was actually modelled, even if the
  instructor edited the scenario afterwards.
- Requiring a session for reads costs nothing now that X-2 made roster
  codes universal; the base tablet and the debrief laptop already log in.
  It is what makes "the instructor sees `df`, base does not" enforceable on a
  WebSocket, which has no per-message auth otherwise.
- Keeping `{valid, head_type, power, tuned_to}` for base lets the base
  console still show "N429CP has the DF on 121.5, squelch open" without any
  geometry. `bearing_rel` is deliberately withheld too: with the aircraft's
  heading in the same frame it is `bearing_true` under another name.

### Not decided here

- Whether aircrew should see other aircraft's positions on `/base`. Today
  they do (role `aircrew` is served the page). Leave as is.
- Rate limiting of login codes. Separate item.

### Tests that pin it

- `leak_endpoints()` in `tests/test_console.py` gains: a posted position with
  a full `df`, a second sortie on the same scenario, and a walk as each of
  `instructor`, `base`, `aircrew`, anonymous. Anonymous gets 401/403 on every
  read; base and aircrew never see `beacon_*`, `bearing_true`, `bearing_rel`,
  `distance_nm`, or `notes` before reveal; instructor sees all of it.
- `test_radio.py:133` flips from asserting the fail-open to asserting a
  403 when a roster exists and no session is presented.

## D2. Search-pattern conventions: the G1000 library is the reference, the planner is a front end

### The decision

1. **Waypoint naming for the expanding square is `DATUM`, then `SSnn` where
   `nn` is the leg whose end the point marks.** `SS01` is the end of leg 1
   (length S), `SS02` the end of leg 2 (S), `SS03` the end of leg 3 (2S).
   This is the planner's current convention; `g1000-sar`'s `names()` changes
   for the expanding square only. `PSnn` and `CSnn` already agree (`PS01` and
   `CS01` are the first lane start) and stay.
2. **The library's datum is where the aircraft starts the pattern, with no
   inset.** Parallel track: datum is the first lane's start; lanes lie on
   the `turn` side. Creeping line: datum is the centre of the first sweep;
   sweeps are `width_nm` wide and the axis advances `spacing_nm` per sweep.
   Expanding square: datum is the centre. This is `g1000-sar`'s current
   geometry and matches Garmin's own SAR feature, whose waypoint anchors a
   corner for parallel and the centre for the square.
3. **The half-spacing inset is a planner front-end rule, not geometry.** The
   planner keeps its box-by-corners and start/end-point inputs because that
   is how an AOBD thinks, and converts them before calling the library:
   parallel datum = corner moved `spacing/2` across the box and lanes =
   `ceil(width/spacing)`; creeping datum = start moved `min(spacing,
   distance)/2` along the axis and sweeps = `ceil(distance/spacing)`. The
   conversion is one pure function with its own test; the geometry is shared.
4. **Default turn is right; both tools accept left for every pattern.** The
   planner's parallel track grows a `turn` field so a left-handed box can be
   briefed; the planner's creeping line maps its "first sweep flies right" to
   the library's `first_turn: right`.
5. **The contract between repos is a fixture file, not a shared package,
   for now.** `g1000-sar` generates `tests/data/search_pattern_fixtures.json`
   (datum, parameters, expected names and lat/lon for each pattern, including
   a west-longitude and a southern-hemisphere case and a left turn). The
   file is copied verbatim into `cap-vsar/tests/fixtures/` and both planner
   geometry tests and `scripts/fly_search_grid.py`'s test assert against it
   to 25 m. Vendoring `g1000_sar/mission.py` into the planner is the next
   step once the planner's `app.py` is split (review L2 improvement 2); the
   fixture makes that swap safe.
6. **`scripts/fly_search_grid.py` loses its own geometry.** Its datum-centred,
   odd-leg-count box becomes a front-end conversion like the planner's
   (centre to first-lane start), calling the shared geometry, and the odd-leg
   restriction goes.
7. **The console push sends `pattern.datum` and `pattern.type`**, and the
   console anchors the alert circle on the datum the library defines (L2-6).
   For a parallel track that is the first lane's start, which is on the box
   edge; the planner therefore also sends the box centre as `search_centre`
   and the console uses that for the alert circle and the beacon offset when
   present. The beacon offset is measured from the search centre, never from
   a corner.
8. **"Apply to Route" keeps `DATUM`** so the nav log carries the leg that
   defines the square and labels match the FMS export (L2-7).

### Why

- The crew reads waypoint names off the G1000 flight-plan page and calls
  legs by the handbook's numbering (leg 1 is S, leg 3 is 2S). With `SSnn` =
  end of leg `nn`, the name on the display is the leg the crew just flew.
  `SS01` as the datum breaks that by one, and `DATUM` says what the point is.
- Garmin anchors on the start point with no inset. The G1000 editor in
  `g1000-sar` follows Garmin's names and ranges (D6 there); putting an inset
  into the geometry would make the G1000 page disagree with the real
  instrument it imitates. The inset exists to centre lanes in a box, which
  only the box-based planner input knows about.
- A fixture file costs nothing to keep in sync and catches the SS
  off-by-one mechanically. A shared package across two repos edited by three
  agents would be fought over.

### What changes where

- `g1000-sar/g1000_sar/mission.py:190` `names()` for `expanding_square`;
  `docs/DESIGN_NOTES.md` D1 and "Planner differences" item 2 updated; new
  fixture generator and file.
- `cap-vsar/services/flightplanner/app.py:836-936` the three generators
  become front-end conversions over one geometry (shared file or vendored
  copy); `app.py:2100-2131` push payload; `static/js/app.js:1145-1147`
  keep DATUM, `:1213-1225` send datum and centre.
- `cap-vsar/scripts/fly_search_grid.py:85-117` and `tests/test_search_grid.py`.
- New `docs/SEARCH_PATTERN_CONVENTIONS.md` holding the review's table with
  the "Agree?" column all "yes".

## D3. The Air Manager harness must refuse what Air Manager refuses

### The decision

1. **The stub API is generated from one signature table.** `tests/am_api.py`
   lists every Air Manager 4.2 function the instruments may call with its
   exact positional signature, taken from the AM 4.2 code snippets and the
   stock G1000 instrument (`dial_add(img, x, y, w, h, [step], turn_cb)`;
   `button_add(up, down, x, y, w, h, press_cb, [release_cb])`; and so on).
   The Lua preamble in `tests/am.py` is built from that table and each stub
   raises a Lua error on an extra positional argument or a wrong type. A
   function not in the table is undefined, as it is in Air Manager.
2. **Dataref and command names are validated against an allowlist that is
   itself validated against X-Plane.** `tests/fixtures/xplane_names.json`
   holds the `sim/...` datarefs and commands the instruments use, with their
   types. `scripts/check_xplane_names.py` regenerates it by scanning the Lua
   and checking each name against `X-Plane 12/Resources/plugins/DataRefs.txt`
   and `Commands.txt` on the workstation; it exits non-zero on an unknown
   name. The harness rejects any `xpl_dataref_subscribe`, `xpl_dataref_write`
   or `xpl_command` whose name is not in the fixture or in the `cap/df/*`
   list scraped from `xplane/PI_capvsar_df.py` at test time. Laminar's file
   is not committed; only the names this project uses are.
3. **Multi-dataref subscriptions are modelled.** The stub parses
   `(name, type, name, type, ..., callback)`, keeps one subscriber record per
   name, and invokes the callback with every current value on any change,
   matching AM. Tests drive the DF heads through
   `am.write_dataref("cap/df/bearing_rel", "FLOAT", 47.0)` and stop mutating
   `cap_df.state` directly (the I-1 redraw gating is then under test).
4. **Knob pushes are `button_add` regions.** A `knob_push(spec, press,
   release)` helper in `_shared/lib` adds a transparent button over the knob
   centre, as the stock G1000 does; the TDFM main and guard encoders and the
   GMA ring use it. `am.press_dial*` helpers are deleted; tests press the
   button at the knob's coordinates.
5. **Sounds model restart semantics.** `sound_loop` on an already-looping
   sound increments a `restarts` counter the tests can assert is zero across
   a burst of updates (I2-4).
6. **`si_variable_subscribe` with no producer loaded stays nil-callback**,
   as AM behaves, and a new test loads the master switch, the CB panel and
   one consumer into one state to cover the producer-present path (I2-7).

### Why

- Four of the review's instrument bugs are invisible because the harness
  accepts what Air Manager does not: unknown datarefs, an invented press
  callback, any command name. A harness that is stricter than the target in
  exactly these places turns "passes offline, dead live" into "fails
  offline". The signature table is the cheapest way to keep it strict as
  new instruments arrive.
- Committing only the names used, not Laminar's whole list, keeps the
  release boundary (`test_release_boundary.py`) intact and keeps the fixture
  reviewable; the generator is where the ground truth is consulted.
- Driving tests through datarefs instead of state pokes is what makes the
  contract in `DATAREF_CONTRACT.md` executable.

### Order

Do (1) and (2) first, run the suite, and fix every instrument failure they
surface (I2-1, I2-2, I2-3 will fail immediately). Then (3) and (4) together,
because the TDFM tests need the knob-push buttons before they can power the
radio. (5) and (6) last; they are additive.

## D4. The aircraft builder: resolved, with two residuals

Ron's 57663ec (on `origin/main`, 2026-10-10) builds into a staging sibling,
renames the old install to `Output/capvsar-backups/<name>-<id>`, and
generates the N429CP livery from the approved artwork, so B2-1 no longer
applies. Two decisions remain:

1. **Backups are kept, not pruned, until there are five.** `publish_staged_package`
   deletes the oldest backups beyond the five most recent. The directory
   already held 319 MB before this change (`REPO_STATE_2026-10-09.md`), and
   every build adds ~590 MB. Five builds is enough to recover from a bad
   week; the number is a constant at the top of the script.
2. **Liveries are build outputs.** Anything under `liveries/` that the build
   did not generate is not preserved across builds; the backup is the
   recovery path. This is stated in the script's docstring and in
   `FLIGHTGEAR_C182_GPL_PLAN.md`, so nobody hand-edits a livery in the
   install again expecting it to survive. If a hand-made livery is ever
   wanted, it goes into `scripts/adapt_cap_livery.py`'s inputs, not the
   install.

Still open from the review and not needing a decision: B2-3 (`&bull;`
literal), B2-5 (hard-coded TRIS offsets; locate the `TRIS` after the
`throttle_ratio[0]` ANIM line and assert the count), B2-6 (flap 38 vs 40),
B2-7..B2-10.
