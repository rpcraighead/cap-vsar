# CalTopo integration plan — 2026-10-11

**Status: plan. No code, accounts or CalTopo maps created.** This supersedes
the phasing and placement sections of
[`CALTOPO_PHASE2_PLAN.md`](CALTOPO_PHASE2_PLAN.md) (2026-09-08); that
document's verified facts about CalTopo (§2), its rate envelope (§6), risks
(§7) and unverified list (§9) still stand and are not repeated here. The
companion user-experience proposal is
[`UX_REVIEW_2026-10-11.md`](UX_REVIEW_2026-10-11.md); this plan assumes its
assignment and event objects (§4.6 there).

## 1. What changed since the phase 2 plan

- The truth boundary is now one serializer with a per-viewer test (D1,
  2026-10-10). The relay can read `hub.snapshot()` without `include_truth`
  and structurally cannot see the beacon; the phase 2 plan's first
  precondition is met.
- Each sortie keeps its own beacon and effects; a relay keyed on the sortie
  id survives console restarts and scenario edits.
- Search-pattern geometry is one tested library shared with the G1000
  (D2), with a fixture; the assignment polygon the relay pushes is the same
  geometry the crew flies.
- Sessions carry a seat, so a staff-drawn feature in CalTopo can be
  attributed to a person when it comes back.

## 2. Division of labour

| Concern | Where it lives | Why |
|---|---|---|
| Beacon truth, effects, scoring, readiness, presence, the record | Exercise console | Must never be on a shared map before reveal; needs the plugin's telemetry; is the exercise's system of record |
| Planning, plotting, assignments as paper, team coordination on the live day | CalTopo | It is what the wing's base staff use on real missions; training the mission means training in it |
| Aircraft tracks, assignments, bearing lines, cuts, alert | Both: console is the source, CalTopo the shared display | Base staff work the map they know; the console keeps the copy it scores against |
| Staff-drawn cuts, clue markers, retask polygons | Both: CalTopo is the source, console the consumer | What the AOBD draws is the training product; the console records it for the debrief and offers it back as an assignment |

The base console does not try to be CalTopo. Its "Mission base" stage keeps
the things CalTopo cannot do: ops-normal clocks, the Form 110, the net, the
readiness board, and the wall board. The map on `/base` stays for bases
without a CalTopo account or connectivity.

## 3. Objects

| Console object | CalTopo object | Direction | When |
|---|---|---|---|
| Exercise (sortie start) | `CollaborativeMap` "EXERCISE {date} {scenario}" in the V-SAR workspace, folders `Alert`, `Assignments`, `Aircraft`, `DF Bearings`, `Cuts & Clues`, `Debrief`; map id stored on the sortie row | → | 2b |
| Alert (IP/LKP, radius, text) | Marker + circle in `Alert` | → | 2b (2a by hand) |
| Assignment (pattern on the sortie) | Area assignment (PS, CS) or line assignment (SS) in `Assignments`, `resourceType` AIR, title `{callsign} {pattern} {spacing} NM`, `primaryFrequency` from the channel plan; status mirrors the console's assigned/active/complete | → | 2a as GeoJSON, 2b live |
| Aircraft position | `position/report` device `VSAREX-{CALLSIGN}` with `aircraft:altitude`, `aircraft:gs`, `aircraft:heading`, `aircraft:track`; 1 report / 5 s / aircraft | → | 2b |
| Reported bearing (base log) | Line, aircraft position → 40 NM, in `DF Bearings`, title `{callsign} {hhmmZ} {bearing}°`; a rejected cut is re-styled grey and suffixed REJECTED | → | 2b |
| Console-computed cut and confidence polygon | Polygon in `Cuts & Clues`, title `CONSOLE CUT {hhmmZ}` | → | 2b |
| Staff-drawn marker/shape in `Cuts & Clues` | Event `caltopo_feature` with the GeoJSON and the drawing user; shown on the instructor map and the wall board as "base estimate"; a polygon can be promoted to an assignment with one click | ← | 2c |
| Retask drawn in CalTopo (polygon titled `TASK {callsign}`) | Assignment on the sortie, pushed to the crew's station page | ← | 2c |
| Reveal | Marker `BEACON (TRUTH)` in `Debrief`; full map GeoJSON archived beside the sortie record; live tracks left to auto-convert | → | 2b |
| Ops-normal calls, messages, readiness | not pushed | — | They are the console's; CalTopo has no object for them |

Everything the relay sends is built from `public_state()` output and from
the `events` stream, never from the scenario row.

## 4. Phases

| Phase | Deliverable | Depends on | Size |
|---|---|---|---|
| **2a Files, no API** | Planner exports an assignment as CalTopo-schema GeoJSON (polygon + waypoint markers, folder, title); debrief exports tracks, bearings, cuts, assignments and (after reveal) truth as GeoJSON; both import into CalTopo or Desktop by hand. A `tests/` fixture round-trips the schema. | assignments on the sortie (UX phase 1) | 1–2 days |
| **2b Live relay** | `app/relay/caltopo.py`: map and folders at sortie start, alert marker, assignment push, `position/report` at 5 s, bearing lines, cut polygon, reveal marker and archive. Configured by `CALTOPO_TEAM`, `CALTOPO_SA_ID`, `CALTOPO_SA_SECRET`, `CALTOPO_CONNECT_KEY`, `CALTOPO_BASE_URL`; absent means off. The relay consumes the `events` stream and `public_state()`. Status (map link, last push, queue depth, errors) shown in the Ready room and the base header. | 2a, events table, a Team account | 3 days |
| **2c Bidirectional and offline** | `since` poll of `Cuts & Clues` and `TASK` polygons into events; promote-to-assignment; CalTopo Desktop via `CALTOPO_BASE_URL`; marker-edit fallback for tracking where `position/report` is unsupported; reconnect to the same map after restart | 2b | 2 days |
| **2d Seat UX** | IC and AOBD work in CalTopo with the console's base page open beside it; "Open CalTopo map" in the shell header; the wall board can show the CalTopo share link; the debrief imports the final map to score staff estimates against truth | 2b, UX phase 2 | 1–2 days |

2a needs no account and should be built with UX phase 1, because the
assignment object is the same work.

## 5. Truth guard

- The relay reads only `hub.snapshot()` (no truth) and events whose type is
  on an allowlist; scenario rows and the sortie's `truth` column are never
  passed to it.
- `tests/test_caltopo_relay.py` runs the relay against a fake CalTopo, posts
  a position with a full DF dictionary, logs a bearing, and dumps every
  request body: no coordinate within 100 m of the beacon and no
  `bearing_true`, `distance_nm` or `beacon_*` key before reveal; the truth
  marker appears only after reveal. This is the same shape as
  `TruthBoundaryByViewer`.
- Device, map and folder names carry `EXERCISE` / `VSAREX`; the workspace is
  dedicated; the service account has UPDATE, not MANAGE.

## 6. Acceptance (adds to the phase 2 plan's §5)

- A pattern built in the planner for CAP 487 appears in CalTopo as an
  assignment within 10 s of being attached to the sortie, and on the crew's
  station page at the same time.
- Marking a bearing rejected in the base console re-styles its line in
  CalTopo within 15 s.
- A polygon titled `TASK CAP 423` drawn in CalTopo becomes a pending
  assignment on the base page within 15 s and reaches the crew when the IC
  confirms it.
- The debrief shows the distance from the base's final estimate marker to
  truth, and that marker was drawn in CalTopo.
- The relay reports its own health in the Ready room; with
  `CALTOPO_BASE_URL` pointed at Desktop and the internet pulled, tracks keep
  updating locally.

## 7. Still to verify before 2b

The phase 2 plan's §9 list, plus:

- Whether the wing holds a Team account and at what tier (First Response is
  the only tier with the supported API and Desktop); the all-volunteer
  discount.
- Whether a CalTopo map can be embedded in the base page or wall board (an
  iframe or the share link's embed mode), or only linked.
- Post-2026-03 assignment property names (title vs letter/number) against the
  current `caltopo-python` release.
- `position/report` against Desktop.

## 8. Decisions taken here

- The console remains the system of record; CalTopo is the shared display and
  the staff's drawing surface. No scoring reads CalTopo as truth.
- Assignments are console objects first and CalTopo objects second, so a base
  without CalTopo loses nothing except the shared map.
- 2a ships with UX phase 1; 2b waits for the account decision; nothing
  else in the UX proposal depends on CalTopo.
