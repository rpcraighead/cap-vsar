# Exercise Console

Instructor-facing web app that runs a sortie: pick a scenario, watch aircraft
on a live map, toggle signal effects mid-flight, log the bearings the crew
reports, and reveal beacon truth for the debrief.

**http://192.0.2.151:8700** - LAN and WireGuard only. Not forwarded at the
router, and it should stay that way.

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
| GET | `/api/sorties/{id}/track` | recorded track, bearings, beacon - for replay |
| POST | `/api/positions` | **sim bridge ingest** |
| POST | `/api/bearings` | log a bearing the crew reported |
| GET | `/api/state` | current snapshot |
| WS | `/ws` | live push to consoles |

## Beacon truth is withheld

`/api/state` omits `beacon_lat` and `beacon_lon` until someone calls
`/api/sorties/reveal`. A trainee who opens the console mid-sortie cannot read
the answer out of it. The truth lives only in the database on the server.

## Try it without a simulator

```bash
cd /srv/capvsar/services/exercise
python3 mock_bridge.py --url http://192.0.2.151:8700 --callsign CAP-1 --alt 5500
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
