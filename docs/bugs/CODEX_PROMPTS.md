# Codex work prompts — open tracker items in Codex's lanes

> **Post-reboot handoff:** paste
> [`CODEX_RESUME_AI_PILOT.md`](CODEX_RESUME_AI_PILOT.md) into the next Codex
> session to continue the supervised CAP 487 live Gate A acceptance (AI-2).

Generated 2026-09-10 from `docs/bugs/tracker.json`. Each numbered prompt is a
PR-sized unit: paste one whole prompt into Codex, let it finish, then move to
the next. They are ordered so that prompts touching the same file run in
sequence, never in parallel.

Claude is working `xplane/PI_capvsar_df.py` (cluster C3) at the same time; that
file and `tests/test_engine.py` are off limits in every prompt below.

## Standing rules — prepend to any prompt in this file

> **2026-09-10 — the simulated aircraft is now `CAP 487`, not `N499CP`.**
> N499CP is a real Cessna 172S; the simulated 182T should never have carried
> it. The rename has landed across `scripts/`, `services/exercise/`, `docs/`,
> `website/`, `docker-compose.yml` and `tests/test_setup_auth.py`. The flight
> planner is the one place still saying N499CP, deliberately — see prompt 1.
> If you touch an aircraft identity anywhere, it is CAP 487.
>
> This repository is shared by three agents working concurrently (Claude,
> Codex, Gemini) with no branch isolation. Before you start, read the head of
> `CHANGELOG.md` to see what has landed since this prompt was written, and
> verify every claim in the prompt against the current tree rather than
> assuming it still holds — if the code no longer matches the description, say
> so and stop rather than fixing something else.
>
> Stay inside the files the prompt names. Do not touch `xplane/`,
> `instruments/`, `tests/test_engine.py`, `tests/test_faceplate.py` or
> `tests/test_panel.py` — those are other agents' lanes and they have
> uncommitted work in them.
>
> When you are done:
> 1. Run the relevant suites and paste the real output:
>    `pytest tests/test_console.py tests/test_radio.py` and, for planner work,
>    `pytest services/flightplanner/tests/test_sar.py`.
> 2. Set each item you actually fixed to `"status": "fixed"` in
>    `docs/bugs/tracker.json`, then regenerate the board with
>    `python3 scripts/render_bug_tracker.py`. Re-read the JSON immediately
>    before editing it — another agent may have changed statuses meanwhile.
> 3. Add a dated entry at the TOP of `CHANGELOG.md` saying what changed, what
>    you verified, and anything you found but did not fix.
>
> If a fix turns out to be wrong or bigger than described, report that instead
> of forcing it through. New problems you find go in the changelog entry as
> findings, and into `docs/bugs/tracker.json` as new items — do not silently
> expand scope.

---

## Prompt 1 — L-7, L-11, L-1a: the flight planner's data is not the aircraft's

`services/flightplanner/app.py`, `services/flightplanner/README.md`,
`services/flightplanner/docs/USER_GUIDE.md`

Three related truth problems in the planner's data and export path. All three
hand a crew a plausible-looking document that is wrong.

**L-7 (P2) — REWRITTEN 2026-09-10.** You stopped on the previous wording and you
were right to: it claimed the profile carried 172S figures "under a 182T label",
and it does not. `app.py:80` says `N499CP - Cessna 172S NAV III`, and the
planner README and USER_GUIDE agree. That part was stale and is fixed.

The actual defect is an identity collision, and half of it has since been
fixed outside your lane. **N499CP is a real Cessna 172S on the squadron line.**
The simulated aircraft was wearing that same registration while being a 182T,
which is why the two descriptions disagreed. As of 2026-09-10 the simulated
aircraft is **CAP 487** everywhere — `build_c182t_package.py`, the exercise
console's aircraft defaults, the handbook, the website — with one deliberate
exception: this planner, which still describes the real N499CP 172S, correctly.

What is left is the gap the item was always really about. **The exercise flies
CAP 487, a 3100 lb / 87 gal / 230 HP IO-540 182T, and the planner computes
fuel, endurance and weight-and-balance for a 2550 lb / 53 gal 172S.** Every
sortie is planned on the wrong airframe, and now the crew cannot even notice
via a shared registration.

Add a **CAP 487** profile with real 182T POH data, matching the `.acf` that
`scripts/build_c182t_package.py` produces, and make it the default for an
exercise. Cite the source for every figure in a comment. Keep the real N499CP
172S profile alongside it if you like — it is accurate for that aircraft — but
it must not be what a V-SAR sortie plans with.

**Do not simply relabel the existing 172S table as CAP 487.** That recreates
exactly the mislabel this item began as, and it would be worse than what is
there now, because the current profile is at least internally honest.
*Verify: planning a sortie in the exercise aircraft uses 87 gal and 3100 lb,
and planned endurance matches the 182T handbook. If you cannot source a 182T
POH figure, say which one and stop rather than guessing — a plausible wrong
fuel number is the failure mode here.*

**L-11 (P2)** — `app.py:626-628` and `639-641`: when `get_airport()` misses (an
unknown identifier, or the aviation database still downloading), the FMS export
falls back to the first/last waypoint's coordinates with elevation 0.0 and
emits them under the requested airport code. An observed sample put KSEE at
33.170,-117.079 — a search waypoint, not Gillespie Field — with no warning
anywhere. Return a 400 naming the identifier that could not be resolved, or
emit the record only on a successful lookup. Never substitute an unrelated
position under an airport code.
*Verify: exporting with an unknown ADEP returns an error, not a plausible file.*

**L-1a (P2)** — `app.py:635` (and the generators at `517-554`): the pattern
generators label points DATUM, SS01..SSnn, CS01, PS01 and the AOBD briefs the
crew on those names, but the FMS writer derives the identifier purely from
coordinates, so the G1000 shows `+33.187_-117.079` for every leg. The brief
says "turn at SS04" and nothing in the cockpit says SS04. First establish
whether X-Plane 12 accepts an arbitrary identifier on a type 28 record while
treating the lat/lon columns as authoritative — check the actual X-Plane 12
FMS format documentation, do not assume. If it does, emit the generator's label
sanitised to the FMS character set and keep the coordinates in their columns.
If it does not, document that in `docs/USER_GUIDE.md` so the AOBD briefs
coordinates instead, and close the item as documented-not-fixable.
*Verify: load an exported pattern in X-Plane 12 and read the leg names on the
G1000 flight plan page. If you cannot run X-Plane, say so and state what you
verified against instead.*

---

## Prompt 2 — L-5, L-6: search coverage and performance maths

`services/flightplanner/app.py`

**L-5 (P2)** — `app.py:591-595,543,532,554`. Parallel track places
`int(width/spacing)` tracks starting on the box edge, so a 4 NM box at 1 NM
spacing leaves the last mile unsearched and wastes half the first track. CAP
practice puts tracks at S/2, 3S/2, 5S/2 — half-spacing in from the edge — and
the count should be `ceil`, not `int`. Creeping line silently truncates at
`max_legs` with no indication that coverage is incomplete: return an explicit
`coverage_truncated` flag the UI can show. `heading_mag` is emitted for
expanding square but not for the other two patterns; emit it consistently.
*Verify: generated coverage matches the requested box within one track spacing.
Add a test to `services/flightplanner/tests/test_sar.py` that asserts the 4 NM
/ 1 NM case covers the full box.*

**L-6 (P2)** — `app.py:711,736-740,665,937`. `get_cruise` is
nearest-neighbour where it should interpolate between table rows.
Takeoff/landing clamp to the last table row, understating distance above
6000 ft or 30 °C — refuse or flag beyond-table inputs rather than silently
extrapolating. Negative headwind (i.e. a tailwind) is ignored, so a tailwind
leg is planned as still air. Worst of the four: when wind ≥ TAS, ground speed
clamps to zero and the leg then reports zero time and zero fuel, so a leg that
cannot be flown looks like the cheapest one on the plan. Error on GS ≤ 0.
*Verify: a leg with a 100 kt headwind reports an error, not zero fuel.*

---

## Prompt 3 — L-9, L-12: API error honesty and the database mount

`services/flightplanner/app.py`, `docker-compose.yml:121`

**L-9 (P2)** — `app.py:894-897,1001-1008,1397,1438,1463`. Unguarded
`int()`/`float()` on client JSON returns a Werkzeug HTML 500 that the frontend
JS then fails to parse, so a bad field shows up as a silent dead UI. Guard the
parsing and return JSON errors. The "no sortie running" branch is dead code
because the console no longer 400s, so the UI always claims the scenario was
broadcast to an active sortie even when nothing was persisted — report
persisted and broadcast status separately and honestly. The push also sets
`beacon_elev_ft` to 0.0: the DF propagation model in `xplane/PI_capvsar_df.py`
uses that elevation for both the radio horizon and the terrain line-of-sight
ray, so a beacon at sea level in mountainous terrain models nothing real. Carry
a real elevation. Finally, the push places the beacon exactly on the planned
search datum, which hands the trainee the answer — offset it by a configurable
distance so the crew has to actually search.
*Verify: bad input returns a JSON 400; a pushed scenario does not sit on the
planned datum.*

**L-12 (P2)** — `docker-compose.yml:121` mounts `aviation_data.db` as a single
FILE at `/app/aviation_data.db`. SQLite writes its rollback journal beside the
database, so `-journal` and `-wal` files land in the container's own writable
layer instead of on the host: a crash mid-write leaves the journal on a
discarded layer and the database with no way to roll back. O-3 works around the
symptom by pre-creating the file; this is the underlying shape. Mount the
DIRECTORY (`./services/flightplanner/data:/app/data`) and point `DATABASE_PATH`
(`app.py:25`) at `/app/data/aviation_data.db`. The host file does not move, so
there is no migration — but confirm that, do not assume it.
*Verify: a write leaves its journal on the host volume, not inside the
container.*

---

## Prompt 4 — L-8 — **DONE 2026-09-10 by Claude, do not re-run**

Landed at Ron's request while Codex was between prompts: Leaflet and the fonts
vendored, tiles routed through `/tiles/` cache-first, the pre-cache made to run
under gunicorn, and the user guide corrected. 13 new tests in
`services/flightplanner/tests/test_offline_map.py`. See the 2026-09-10
changelog entry. **Skip to prompt 3, then 5.**

Note while you are in `app.py`: `chart_type` is now whitelisted via
`TILE_CACHE`, which covers the `serve_tile` bullet in prompt 11 (L-10).

<details><summary>Original prompt 4, for reference</summary>

### L-8: the planner has no offline map path

`services/flightplanner/templates/index.html:8,447`,
`services/flightplanner/static/js/app.js:83-97`,
`services/flightplanner/app.py:1490`,
`services/flightplanner/docs/USER_GUIDE.md`

The mission base is assumed to run with no internet (this is why F-1 vendored
Leaflet into the exercise console — follow what that fix did, in
`services/exercise/app/static/`). In the planner, Leaflet and Google Fonts
still load from CDNs and tiles come straight from ArcGIS. Worse, the
server-side tile cache at `app.py:1490` only runs under `__main__` and never
under gunicorn, and the frontend never requests `/tiles/` at all — so the
charts volume is dead weight and `USER_GUIDE.md`'s claim that cached tiles are
used first is simply false. Vendor Leaflet and the fonts locally, wire the
frontend to `/tiles/`, make the cache work under gunicorn, and pre-cache the
exercise area into the existing volume. Correct the user guide to match what
the code now actually does.
*Verify: plan a route with outbound internet blocked (`scripts/firewall.sh` or
an equivalent) and confirm the map renders and tiles resolve.*

</details>

---

## Prompt 5 — X-6: untyped request bodies mutate scenario definitions

`services/exercise/app/main.py:235,277-283,143,219`

`start_sortie` and `set_effects` take raw dicts, bypassing Pydantic entirely.
The consequence is not cosmetic: `set_effects` merges arbitrary keys straight
into the **scenario** row, so an instructor changing an effect mid-exercise
permanently rewrites the scenario definition for every future sortie that uses
it. Effects belong on the sortie, not the scenario. Also: no lat/lon range
checks anywhere on the way in, and the positional `INSERT ... VALUES (?×15)`
will break silently on the next schema change — use named columns.

Add Pydantic models for both endpoints, move effects onto the sortie row
(with a migration for existing rows), range-check coordinates, and name the
INSERT columns.
*Verify: changing effects mid-sortie leaves the scenario row untouched — add a
test to `tests/test_console.py` that asserts exactly that.*

---

## Prompt 6 — X-8: console operational hygiene

`services/exercise/app/main.py:300-302,442-444,149`,
`services/exercise/Dockerfile`

Partly addressed on 2026-09-08 (connections now close, X-3 added WAL). What is
still open, all of it:

- `positions` has no retention policy and `/track` is unpaginated, so a long
  exercise grows both without bound and the endpoint gets slower all day.
- `main.py` has no logging at all beyond two `print()` calls. Add structured
  logging, and make sure sortie lifecycle events (start, stop, reveal, effect
  change) are in it — that is the record an after-action review reads.
- The healthcheck never touches the database, so the container reports healthy
  with a broken or missing DB.
- The ticker task is not cancelled in the lifespan shutdown.
- The container runs as root.

*Verify: a long exercise does not grow `/track` unboundedly; logs show the
sortie lifecycle; the healthcheck fails when the database is unavailable.*

---

## Prompt 7 — F-9 + F-7: Form 110 on the new console, then retire the legacy one

`services/exercise/app/static/mission-radio.html`,
`services/exercise/app/static/mission-radio.js`,
`services/exercise/app/static/radio.js:471-495,530,535-559`

**F-9 (P2)** — the CAPF-110 communications log exists only in `/radio-legacy`,
the console nobody is supposed to use any more. The MRO role in the CONOPS
depends on that log, so right now the primary console cannot do the job. Port
the logger onto the Mumble console, and fix the three bugs in the export while
you do: it has no date column; `padEnd` does not truncate, so any long field
misaligns every row after it; and the blob URL is never revoked.

**F-7 (P2)** — in the same legacy file, `radio.js:530`:
`a && b || c.startsWith()` throws when `sender` is undefined (masked today only
by a server-side default), and at `535-559` incoming traffic resumes the
AudioContext and speaks outside a user gesture, so iPad Safari stays silent
until something is tapped. Fix the precedence and require a gesture to arm
audio, as the new console already correctly does.

If F-9 lands and `/radio-legacy` is genuinely retired — route removed, nothing
linking to it — then F-7 closes with it and you can say so instead of fixing
the legacy file. Make that call explicitly, do not leave it ambiguous.
*Verify: an exercise produces a Form 110 export from `/radio` with correctly
aligned, dated rows; an iPad hears the first incoming call after joining.*

---

## Prompt 8 — X-9 then F-10: Mumble sessions and the second receive channel

`services/exercise/app/radio.py:141`,
`services/exercise/app/static/mission-radio.js`

These two are one problem seen from both ends and must be done together, X-9
first.

**X-9 (P2)** — every browser socket spawns its own pymumble thread at a 10 ms
loop rate, against a 16-session server cap. A base desk running two radio faces
burns two of the sixteen and shows up as two separate users on the net, which
is wrong operationally as well as expensive. Share one Mumble client per
operator across their radio faces. If you conclude that sharing is not
workable, the alternative is to raise the cap and document it — but only with
measured CPU at the new number, not an estimate.

**F-10 (P2, effort L)** — the MRO must monitor the VHF-FM tactical net and the
VHF-AM aeronautical SAR frequency simultaneously; the console joins one Mumble
channel at a time. The retired `/radio-legacy` console had a second airband
station (Icom IC-A120) and the rewrite dropped it, so the base can no longer
hear aircraft calling air-to-ground while working the tactical net. Add a
second simultaneous receive channel with independent volume and its own log
identity (it needs to land in the Form 110 from prompt 7 distinguishably).
Two channels per operator doubles the session count — which is exactly why X-9
comes first.
*Verify: a dual-radio desk appears once on the net; one operator hears both
nets at once and can key the correct one.*

---

## Prompt 9 — F-11, F-12, F-13: radio console realism

`services/exercise/app/static/mission-radio.js:251`,
`services/exercise/app/radio.py:29-34`

All three came from the 2026-09-08 radio ecosystem audit and were re-verified
against the tree.

**F-11 (P3)** — the only oscillator on the console is the 660 Hz headset-test
beep. There is no talk-permit chirp on channel grant and no squelch tail, so an
operator gets no acoustic confirmation that the radio actually keyed. Note: the
audit proposed porting `playP25Chirp`/`playP25Tail`/`playAmSquelchBurst` from
`radio.js`. **Correction, 2026-09-10: they DO exist** — as methods of the
`audio` class in `radio.js` (roughly lines 29, 60 and 102), which is why an
earlier grep for standalone functions missed them. This is a port, and those
implementations are the reference for what the tones should sound like.
*Verify: keying produces an audible grant tone before speech is passed.*

**F-12 (P3)** — SCAN, MON, SQL and EMER appear on the APX/EFJ SVG faceplates
but have no hit regions in the JS at all (grep finds none of those names).
Start with MON: opening the squelch is what an operator actually reaches for to
pull a marginal signal from an aircraft low in terrain, and it is a real
trained skill.
*Verify: MON opens the squelch and marginal traffic becomes audible.*

**F-13 (P3)** — channels read PRIMARY / ALTERNATE / MISSION BASE / BRIEFING.
Real control heads show zone and channel tags from the fleet plan, and reading
them correctly is part of the operator's job. The cockpit half of this (tracker
item I-11) is **already done**: the CAP channel card lives in
`instruments/cap-fm-tdfm-136b/logic.lua:42` onward — TAC 1, TAC 2, CC 1 and the
rest, with frequencies, tones and NACs. Read those names out of that table and
match them; do not invent your own set and do not edit that file (it is
Gemini's lane). The point is that a channel briefed by name is the same channel
on both ends.
*Verify: a channel briefed by name is identifiable on both the aircraft radio
and the base console.*

---

## Prompt 10 — F-6, F-8: escaping, and the intersection maths the README promises

`services/exercise/app/static/base.js:99-102,114`,
`services/exercise/app/static/debrief.js:105`,
`services/exercise/app/static/app.js:80`,
`services/exercise/app/static/radio.js:453`, `README.md`

**F-6 (P2)** — message bodies, senders and channel names are interpolated into
`innerHTML` unescaped in four separate views, and any client on the LAN can
POST `/api/messages` with markup. `radio.js:467` already escapes correctly —
use that as the pattern and apply it in all four places.
*Verify: a message containing a script tag renders as visible text.*

**F-8 (P2)** — bearings are drawn as flat-earth 40 NM rays (fine at that
scale), but nothing computes intersections or a confidence area, even though
`README.md` advertises "bearing logging & intersection cuts". Base staff are
currently eyeballing the crossing. Compute pairwise intersections and a simple
confidence polygon. Bearing entry also requires typing the callsign; make it a
dropdown of the aircraft currently reporting. Either implement what the README
claims or correct the README — do not leave them disagreeing.
*Verify: three bearings produce a plotted cut area matching a hand plot.*

---

## Prompt 11 — L-10: planner dependency and container hygiene

`services/flightplanner/requirements.txt`, `services/flightplanner/Dockerfile`,
`services/flightplanner/app.py:807`

Run this last: it touches the same files as prompts 1-4 and is the lowest
priority (P3, wave 4).

- `requests==2.31.0` carries CVE-2024-35195 and CVE-2024-47081. Bump it.
- gunicorn and Werkzeug are unpinned — pin them.
- The container runs as root.
- The healthcheck hits `/` rather than anything that proves the database is
  there. Add `/api/health` that verifies the DB.
- `serve_tile` accepts `..` in `chart_type`. Not currently exploitable given
  the surrounding code, but whitelist the value anyway.
- `_winds_cache` grows unbounded — bound it.
- The aviation database is OurAirports, not FAA NASR, and no cycle date is
  shown anywhere. Display the data cycle so a planner knows how stale it is.

*Verify: `pip-audit` clean; the health endpoint fails when the DB is missing.*
