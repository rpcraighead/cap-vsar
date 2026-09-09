# CalTopo integration — phase 2 plan

**Status: proposed. No code, accounts, or CalTopo maps have been created.**
Companion to [`PROJECT_REVIEW_2026-09-08.md`](PROJECT_REVIEW_2026-09-08.md);
finding IDs (X-1, O-2, …) refer to that document. Facts about CalTopo below
were verified against caltopo.com, training.caltopo.com, blog.caltopo.com
and the `caltopo_python` repository on 2026-09-08; items that could not be
verified are listed in §9.

## 1. Why CalTopo, and what it must not do

CAP mission bases already run on CalTopo (formerly SARTopo for teams):
Michigan Wing lists it for IMT and field use, Minnesota Wing and Hawaii units
teach classes on it, and there are public "Civil Air SAR Exercise" maps.
A virtual SAREX whose base staff plan, track, and debrief in the same tool
they use on a real mission trains the mission, not just the DF technique.

Two constraints shape everything below:

1. **Beacon truth stays in the exercise console until reveal.** CalTopo is a
   shared, collaborative map; anything pushed to it is visible to every
   staff member. The alert position, assignments, aircraft tracks and
   reported bearings go to CalTopo. The beacon does not, until debrief.
   This depends on fixing X-1/P-2 first — today the console leaks truth
   anyway.
2. **Simulated aircraft must never look like real ones.** No APRS-IS, no
   ADS-B, exercise-prefixed names everywhere, a dedicated workspace.

## 2. What CalTopo provides (verified)

| Capability | State | Source |
|---|---|---|
| Official Team API: HMAC-SHA256-signed requests from service accounts with READ / UPDATE / MANAGE / ADMIN levels | Supported, Team accounts only | training.caltopo.com/all_users/team-accounts/teamapi |
| Documented endpoints: `acct/{team}/since/{ts}`, `CollaborativeMap` create/delete, `map/{id}/since/{ts}`, `map/{id}/Marker`, `map/{id}/Shape`, edit/delete by class + id, media | Supported | same |
| Change detection | `since`-timestamp polling only; no websocket; no published rate limit ("pass a recent timestamp if polling more than once a minute") | same |
| Assignments, OperationalPeriod, Folder CRUD | Work through the same `map/{id}/{Class}` pattern but are **not** in the supported doc — unofficial | `caltopo_python` README |
| **Custom HTTP position endpoint** `GET /api/v1/position/report/{CONNECT_KEY}?id={DEVICE}&lat&lng&alt&speed` — devices auto-register as `{KEY}-{DEVICE}`; aircraft fields `aircraft:altitude` (ft MSL), `aircraft:gs` (kt), `aircraft:heading`, `aircraft:track`, `aircraft:pitch`, `aircraft:roll`, `aircraft:altitude_rate` | Documented (team-tracking page; the `aircraft:*` list was only seen in a search snippet — §9) | training.caltopo.com/all_users/team-accounts/team-tracking |
| Live tracks accrue in a "Live Tracks" folder and become permanent lines after stop, 24 h idle, or 3000 points | Documented | same |
| `caltopo-python` 2.0.0 (PyPI, 2026-01-17, Tom Grundy / NCSSAR): `addMarker/addLine/addPolygon/addFolder/addOperationalPeriod/addLineAssignment/addAreaAssignment/editFeature/delFeature/getFeatures`, background `since` sync thread (10 s default) with new/edit/delete callbacks, non-blocking request queue, `domainAndPort='localhost:8080'` for Desktop | Self-described as wrapping an "unofficial" API that "could change at any time"; no undo — export GeoJSON before use | github.com/ncssar/caltopo_python |
| GeoJSON is the full-fidelity import/export (styles, folders, assignments preserved); KML/GPX lose CalTopo fields | Documented | CalTopo help |
| CalTopo Desktop: local server at `http://localhost:8080` for no-internet bases; Desktop ($100/yr, 50 % first-responder discount) or Team subscription per install; queues edits until connectivity returns | Documented; `caltopo_python` supports it (unsigned http) | training.caltopo.com/all_users/desktop |
| Pricing: First Response Teams from $2,000/yr (≤ 50 personnel, includes Desktop, live tracking, SMS Locators, Flex Workspaces, API); all-volunteer SAR teams "may qualify for a significant discount"; individual Pro $50/yr, Desktop $100/yr | Verified 2026-09 | caltopo.com/about/teams |
| Terms of use (2026-08-11) prohibit automated use imposing disproportionate load and bulk transfer via third-party programs; the Team API and position endpoint are the consent path | Verified | caltopo.com/about/terms-of-use |
| APRS-IS: "Do NOT inject non-amateur radio content falsely identifying it as amateur radio stations"; beacons faster than 1/min prohibited; iGates would leak simulated aircraft onto RF | Verified | aprs-is.net |

Assignment properties as of `caltopo_python` 2.0: `number`, `letter`,
`operationalPeriodId`, `resourceType`, `teamSize`, `priority`,
`responsivePOD/unresponsivePOD/cluePOD`, `previousEfforts`,
`transportation`, `timeAllocated`, `primaryFrequency`, `secondaryFrequency`,
`preparedBy`, `status`. CalTopo's 2026-03-04 update merged letter/number
into a single Title in the UI; whether the properties changed is unverified.

## 3. Design

### 3.1 Placement

`services/tracking/` (created empty today) becomes the **CalTopo relay**: a
router in the exercise app (per review §5.1) plus one background task. It
is the only component that holds CalTopo credentials, and it sees the
console's data through the same truth-filtering serializer base staff get
— so it structurally cannot push the beacon before reveal.

```
X-Plane plugin ──POST /api/positions──► exercise console ──┐
                                        (tracking router)  │  1. position/report (5 s per aircraft)
flight planner ──POST /api/sar/export-vsar──► scenario ────┤  2. map + folders + assignments  (caltopo_python)
base staff ──log bearing──► bearings table ────────────────┤  3. bearing lines → "DF Bearings" folder
                                                           │
                          console ◄── since/{ts} poll ◄────┘  4. staff-drawn cuts/markers back to instructor view
instructor ──reveal──► truth marker + debrief GeoJSON export ─► exercise archive
```

### 3.2 Objects

| Console object | CalTopo object | Direction | Notes |
|---|---|---|---|
| Exercise (sortie start) | `CollaborativeMap` named `EXERCISE {date} {scenario}` in the exercise workspace; folders `Alert`, `Assignments`, `Aircraft`, `DF Bearings`, `Cuts & Clues`, `Debrief` | console → CalTopo | Created once per sortie; map id stored on the sortie row |
| Alert position (IP/LKP, search radius) | Marker + circle Shape in `Alert` | console → CalTopo | From the scenario's `alert_*` fields; never `beacon_*` |
| Search pattern from the flight planner | Area assignment (`addAreaAssignment`, `resourceType` = `AIR`) or line assignment for creeping line, `primaryFrequency` from the TDFM channel | console → CalTopo | Planner already posts the waypoint list; the relay turns it into the assignment polygon |
| Aircraft position (each 2–3 s report) | `position/report` device `{KEY}-{CALLSIGN}` with `aircraft:altitude`, `aircraft:gs`, `aircraft:heading`, `aircraft:track` | console → CalTopo | Throttled to one report per 5 s per aircraft (§6) |
| Reported DF bearing | Line Shape (aircraft position → 40 NM ray) in `DF Bearings`, title `{callsign} {hhmmZ} {bearing}°` | console → CalTopo | Base staff draw cuts in CalTopo with its own tools |
| Staff-drawn markers/shapes in `Cuts & Clues` | Read via `since` poll | CalTopo → console | Shown on the instructor map as "base staff estimate"; feeds debrief scoring (estimate vs truth) |
| Reveal | Marker `BEACON (TRUTH)` in `Debrief`; live tracks left to auto-convert; full map GeoJSON exported to `exercise.db`/archive | console → CalTopo | Only after `revealed` |

### 3.3 Accounts and naming

- One CalTopo **Team** (First Response tier is the only one with the
  supported API and Desktop). Confirm whether the wing already has one
  (Michigan Wing's GIS page implies unit-level accounts exist) before
  buying; the all-volunteer SAR discount applies.
- A **dedicated workspace / sub-team** for V-SAR, so exercise maps never sit
  beside real incidents.
- Service account with **UPDATE** permission (create/edit), not MANAGE —
  the relay should not be able to delete maps. Credentials in `.env`
  (`CALTOPO_TEAM`, `CALTOPO_SA_ID`, `CALTOPO_SA_SECRET`,
  `CALTOPO_CONNECT_KEY`), never in the repo (O-1's `.gitignore`).
- Every map, device and folder name carries the `EXERCISE` prefix; the
  connect key itself should read as exercise traffic (e.g. `VSAREX`), so a
  device shows as `VSAREX-CAP499`.

### 3.4 Offline base

Run **CalTopo Desktop** on the mission-base laptop (or on ms01) and point
the relay at `localhost:8080` via `CALTOPO_BASE_URL`. `caltopo_python`
handles the unsigned-http case. Whether `position/report` works against
Desktop is unverified (§9); the fallback is `editFeature` on one marker per
aircraft at 0.2 Hz, which is within a defensible rate and is what the relay
should implement first anyway, since it needs it for Desktop.

## 4. Phasing

| Phase | Deliverable | Depends on | Size |
|---|---|---|---|
| **2a Export / import, no API** | Flight planner exports the pattern as CalTopo-schema GeoJSON (assignment polygon + waypoint markers); debrief exports per-aircraft tracks, bearings and truth as GeoJSON; staff import/export by hand | WP7 (per-aircraft tracks), F-3 | 1–2 days. Zero API risk, works on Desktop, proves the schema. |
| **2b Live tracking + map automation** | `tracking` router; map/folders/assignment created at sortie start; `position/report` at 5 s per aircraft; bearings pushed as lines; sortie row stores map id | WP1 (truth filter, role tokens), O-2 (callsign identity), WP10 `tracking` router | 3 days + a Team account |
| **2c Bidirectional + offline** | `since` poll of `Cuts & Clues` into the instructor view and debrief scoring; Desktop support via `CALTOPO_BASE_URL`; marker-update fallback for tracking | 2b | 2 days |
| **2d Role UX** | IC/AOBD work in CalTopo; the console's `/base` becomes the MRO/Form-110 station + Ops Normal clocks; instructor keeps the console; a "CalTopo map" link in every console header | 2b, WP5 | 1–2 days |

2a is worth doing now regardless of the account decision.

## 5. Acceptance

- Start a sortie: a map appears in the workspace within 10 s with the six
  folders, the alert circle and the planner's assignment; **no** feature
  contains `beacon_*` values (test: dump map GeoJSON, assert no coordinate
  within 100 m of truth before reveal).
- Three aircraft (`CAP499`, `CAP501`, `CAP503`) report from three plugin
  stations; three live tracks update at ≤ 5 s cadence for 60 min without
  a dropped device; total request rate ≤ 1 request/s.
- A bearing logged in `/base` appears as a line in `DF Bearings` within 15 s;
  a marker drawn by staff in `Cuts & Clues` appears on the instructor map
  within 15 s (10 s poll + latency).
- Console restart mid-sortie (X-4 fixed) resumes reporting to the *same*
  map, not a new one.
- Reveal: truth marker appears; map GeoJSON is archived alongside
  `exercise.db`; debrief page shows staff estimate vs truth distance.
- Pull the base's internet: the relay switches to Desktop within one poll
  cycle and resumes on the cloud map when connectivity returns, with no
  duplicate maps.

## 6. Rate and policy envelope

- Positions: 1 report / 5 s / aircraft → 0.6 req/s for three aircraft.
  `caltopo_python`'s queue for everything else. Never edit markers at the
  plugin's 2–3 s cadence.
- `since` poll at 10 s (library default) with a recent timestamp, as the
  API doc asks.
- No APRS-IS, no ADS-B, no `MANAGE` permission, no real-incident workspace.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Unofficial-API breakage (assignments, folders, `since` shapes) | Pin `caltopo-python`; phase 2a's GeoJSON path is the fallback for everything but live tracking; export GeoJSON before every automated edit (no undo) |
| Truth leak through CalTopo | Relay reads only through the filtered serializer; acceptance test above; X-1/P-2 fixed first |
| Cost / account availability | Ask the wing; 2a needs no account |
| Rate limits (unpublished) | Envelope above; back off on 429/5xx; log request rate |
| Desktop `position/report` unsupported | Marker fallback |
| Naming confusion with real ops | `EXERCISE` prefix, dedicated workspace, `VSAREX` connect key |

## 8. Code sketch (2b)

```python
# services/exercise/app/routers/tracking.py (sketch, not implemented)
from caltopo_python import CaltopoSession

class CalTopoRelay:
    def __init__(self, cfg, store):
        self.s = CaltopoSession(domainAndPort=cfg.base, accountId=cfg.sa_id,
                                key=cfg.sa_secret, sync=False)
        self.cfg, self.store = cfg, store
        self.map_id, self.folders, self.last_report = None, {}, {}

    async def on_sortie_start(self, sortie, scenario_public):
        # scenario_public comes from the truth-filtering serializer
        self.map_id = self.s.createMap(f"EXERCISE {sortie['date']} {scenario_public['name']}")
        for name in ("Alert", "Assignments", "Aircraft", "DF Bearings", "Cuts & Clues", "Debrief"):
            self.folders[name] = self.s.addFolder(name)
        self.s.addMarker(*scenario_public["alert_latlon"], title="ALERT / LKP",
                         folderId=self.folders["Alert"])
        self.store.set_map_id(sortie["id"], self.map_id)

    async def on_position(self, p):
        if time.time() - self.last_report.get(p["callsign"], 0) < 5:
            return
        self.last_report[p["callsign"]] = time.time()
        await http_get(f"{self.cfg.base}/api/v1/position/report/{self.cfg.connect_key}",
                       id=p["callsign"], lat=p["lat"], lng=p["lon"],
                       **{"aircraft:altitude": p["alt_ft"], "aircraft:gs": p["gs_kt"],
                          "aircraft:heading": p["hdg_true"], "aircraft:track": p["trk_true"]})

    async def on_bearing(self, b):
        end = geodesy.destination(b["lat"], b["lon"], b["bearing_true"], 40.0)
        self.s.addLine([[b["lon"], b["lat"]], [end.lon, end.lat]],
                       title=f"{b['callsign']} {zulu(b['t'])} {b['bearing_true']:03.0f}°",
                       folderId=self.folders["DF Bearings"])

    async def on_reveal(self, truth):
        self.s.addMarker(truth["lat"], truth["lon"], title="BEACON (TRUTH)",
                         folderId=self.folders["Debrief"], color="#FF0000")
        self.store.archive(self.map_id, self.s.getFeatures())
```

## 9. Unverified — confirm before 2b

- The exact `aircraft:*` parameter list for `position/report` (seen only in
  a search snippet of a help-center post that returned 403).
- Rate limits on `position/report` and the map API.
- Whether `position/report` works against CalTopo Desktop.
- Post-2026-03-04 assignment property names (letter/number vs title).
- Whether the wing already holds a Team account and what tier.
- Whether individual-account API credentials are a legitimate path
  (`caltopo_python` obtains them by sniffing a browser request — treat as
  unofficial; use a Team service account).
