# Exercise Console

Instructor-facing web app that runs a sortie: pick a scenario, watch aircraft
on a live map, toggle signal effects mid-flight, log the bearings the crew
reports, and reveal beacon truth for the debrief.

Participant applications share one HTTPS origin. Sign in at the home page and
open the views listed for your assigned role:

| View | URL | Audience |
|---|---|---|
| Participant home | `https://192.0.2.151/` | Role-aware application launcher |
| Instructor console | `https://192.0.2.151/instructor` | Runs the scenario: effects, reveal, control |
| Mission base | `https://192.0.2.151/base` | IC / AOBD / MRO: alert, board, bearings, tasking |
| Flight planner | `https://192.0.2.151/planner/` | Routes, performance, loading, and SAR patterns |

LAN and WireGuard only. Caddy on port 443 is the sole participant listener;
the exercise backend on 8700 is private to the Compose network.

## The two views differ on purpose

Mission base has **no scenario picker, no effect toggles and no reveal button**,
and never receives the beacon position until the instructor reveals it. It is
the same WebSocket and the same state endpoint - the server withholds truth, so
opening dev tools on the mission base page gains a trainee nothing.

What mission base has that the console does not:

- **Alert intake.** The tasking as it actually arrives - kind, narrative, and a
  reported area with an uncertainty radius, drawn on the map as a dashed circle.
  This is deliberately *not* the beacon position. For scenario C-1 the alert is
  a 121.5 pilot report with no position at all, because 121.5 has not been
  satellite-monitored since 2009.
- **Sortie status board** - aircraft, altitude, heading, position, time airborne,
  and whether their reports have gone stale.
- **Tasking messages** - retasking text that supplements the voice net and leaves
  a record for debrief.

## What exists and what does not

There is no simulator yet. Phase 0 of the implementation plan has not started,
so nothing is producing real aircraft positions.

What this console gives you now:

- the scenario model and the instructor controls, working
- a live map, aircraft tracks, and a bearing log, working
- **the position-ingest API the real sim bridge will use**, fixed and testable
- a mock aircraft so the whole thing is demonstrable today

## The Phase 4 contract

The sim bridge POSTs this, at whatever rate you choose (2-5 s is realistic):

```
POST /api/positions
{"callsign": "CAP-1", "lat": 33.13, "lon": -117.28, "alt_ft": 4500, "hdg_true": 65}
```

The response carries what the direction finder would show:

```json
{"ok": true, "df": {"valid": true, "bearing_rel": 12.5, "bearing_true": 77.5,
                    "signal": 0.29, "distance_nm": 9.2, "in_cone": false, "note": ""}}
```

That return value is a convenience for bridges without their own engine. Once
the XPPython3 plugin exists it computes bearing and signal itself - with real
terrain masking, which this server cannot do - and this response is ignored.

**Keep the request shape stable.** Everything downstream depends on it.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/scenarios` | list scenarios |
| POST | `/api/scenarios` | create one |
| DELETE | `/api/scenarios/{id}` | remove one |
| POST | `/api/sorties` | start a sortie (`{"scenario_id": "..."}`) |
| POST | `/api/sorties/stop` | stop the running sortie |
| POST | `/api/sorties/reveal` | expose beacon truth for debrief |
| POST | `/api/sorties/effects` | toggle effects mid-sortie |
| GET | `/api/sorties/{id}/track` | recorded track, bearings, messages, beacon - for replay |
| POST | `/api/positions` | **sim bridge ingest** |
| POST | `/api/bearings` | log a bearing the crew reported |
| POST | `/api/messages` | send a tasking / retasking message |
| GET | `/api/messages` | recent messages |
| GET | `/api/state` | current snapshot |
| WS | `/ws` | live push to consoles |

## Beacon truth is withheld

`/api/state` omits `beacon_lat` and `beacon_lon` until someone calls
`/api/sorties/reveal`. A trainee who opens the console mid-sortie cannot read
the answer out of it. The truth lives only in the database on the server.

## Try it without a simulator

```bash
cd /srv/capvsar/services/exercise
python3 mock_bridge.py --url https://192.0.2.151 --callsign CAP-1 --alt 5500
```

Flies a box pattern from KCRQ and prints the DF result each report. Start a
sortie in the console first, or the aircraft appears on the map with no DF.

## The propagation model here is a stand-in

`app/propagation.py` models range falloff, radio horizon
(1.23 x sqrt of height above the beacon), the 406 burst cadence, the cone of
confusion, and an optional multipath offset.

It does **not** model terrain masking, because that needs a terrain probe that
only the simulator has. Per the implementation plan the authoritative engine
belongs in the XPPython3 plugin. This module exists so the console could be
built and validated first, and so the mock bridge has something to fly against.

Do not let it drift into being the real engine.
