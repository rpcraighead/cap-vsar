# CAP 487 Flight Planner

**SIMULATOR USE ONLY. NOT FOR REAL WORLD NAVIGATION.**

Flight planning application for CAP 487 (Cessna 182T NAV III, POH sample baseline), built for Civil Air Patrol San Diego Senior Squadron 57.

**Live:** [flightplanner.rpc-cyberflight.com](https://flightplanner.rpc-cyberflight.com)

## Features

- **Route Planning** - Enter departure, destination, and waypoints. Calculates fuel burn, time enroute, headings, and wind corrections using real performance data from the C182T POH.
- **VFR/IFR Charts** - FAA sectional and IFR enroute charts with route overlay, served from a local tile cache so the map works at a base with no internet (L-8).
- **Vertical Terrain Profile** - Terrain elevation along the route using USGS Elevation API, with climb/descent gradients based on aircraft performance data.
- **Airport Data** - Airport info, runway diagrams (FAA d-TPP), current METAR, and runway lengths for all route airports.
- **Weather Briefing** - Live METAR, TAF, and winds aloft from aviationweather.gov.
- **Performance** - Takeoff and landing distance calculations adjusted for altitude, temperature, and wind.
- **Weight & Balance** - CG envelope verification with graphical output.
- **Reference** - V-speeds, limitations, and fuel data for the aircraft.

## Tech Stack

- **Backend:** Python / Flask
- **Frontend:** Vanilla JavaScript, Leaflet.js, HTML5 Canvas
- **Data:** SQLite (OurAirports data), FAA d-TPP diagrams, USGS elevation API, aviationweather.gov
- **Hosting:** Docker container in the CAP V-SAR lab stack (`docker-compose.yml`), mounted by Caddy at `https://192.0.2.151/planner/`. Port 8080 is private to the Compose network. It was originally a Google Cloud Run service; that is no longer how it runs.

## Running Locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000. Click "Update Database" on first run to download airport/navaid data.

## Deploying

The planner runs as one service in the lab stack, alongside the exercise
console and the Mumble server:

```bash
docker compose up -d flightplanner
```

It listens on 8080 in the container and is reachable by participants only
through the shared Caddy HTTPS front door at `/planner/`. The exercise console
and planner therefore receive the same host-only session cookie. Neither 8080
nor the historical host port 8090 is published.

The earlier Google Cloud Run deployment is retired. It is kept in mind only
because the cost work in `docs/CLOUD_RUN_COST_ESTIMATE.md` still informs the
hosting question, which is open — see `docs/LAB_HOSTED_DEPLOYMENT_PLAN.md`.

## Built With

The CAP 487 profile is for simulation. Its POH sample baseline has not been flight-tested against the modified X-Plane aircraft.


## Aircraft baseline

CAP 487 is the default: 3,100 lb maximum takeoff weight, 2,950 lb maximum
landing weight, 87 gal usable fuel and the 230 HP IO-540 182T tables.
The user-selected POH sample empty weight/moment is **1,924 lb / 70.9 thousand
lb-in**, not the builder's 1,970 lb empty weight. Match the simulator setting
before comparing loading results; this application does not change the builder.

Cruise uses altitude, RPM and manifold pressure, with standard temperature
and recommended lean mixture. See the [user guide](docs/USER_GUIDE.md#cap-487-poh-baseline-and-sources)
for sources, imported ranges, endurance conditions and the unverified simulator
CG-datum mapping. The N499CP 172S profile has been removed from this exercise planner.

### Console authentication (L-15)

`POST /api/update-database` and `POST /api/sar/export-vsar` require an
instructor identity verified by the configured console's `/api/auth/me`.
They fail closed if authentication is missing, expired, rejected, or unavailable.
The planner forwards the caller's `capvsar_session` cookie, `Authorization`
header, and/or `X-CAPVSAR-Token` header to that console only. It never reads
`CAPVSAR_TOKEN_INSTRUCTOR` or `CAPVSAR_TOKEN_BASE` from its environment.
Console writes independently enforce the caller's permissions; authentication
and write requests do not follow redirects.

Browser deployments must expose the planner and console under the same origin
so the console session cookie reaches the planner. Cookie-authenticated writes
require a matching Origin (scheme and authority) and JSON. Non-browser clients
can present their own Bearer session or console token without Origin. Origin
alone never authenticates a caller. Database refresh and scenario export require
instructor access; calculation and download endpoints remain available without
sign-in. A console denial during export returns 401/403 and preserves any
partial-success information rather than substituting a more privileged token.
