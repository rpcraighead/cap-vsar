# CAP 487 Flight Planner — User Guide

A route planner, nav-log generator, and performance/W&B calculator built around
**CAP 487** (Cessna 182T NAV III, POH sample planning baseline), CAP San Diego Sr. Sq. 57.

> ⚠️ **SIM USE ONLY.** This tool is for training and planning practice. Weather is
> partly simulated, terrain sampling is approximate, and airport/navaid data comes
> from the public OurAirports dataset. **Always brief with official sources
> (1800wxbrief.com, ForeFlight, current charts, the POH) before any real flight.**

---

## 1. Getting to the app

| Where | URL |
|-------|-----|
| Production (public) | https://flightplanner.rpc-cyberflight.com |
| Cloud Run direct | https://flight-planner-383916130890.us-west1.run.app |
| Local dev server | http://198.51.100.236:5001 (or http://127.0.0.1:5001 on the host) |

The app is a single page — no login. On first load it checks the aviation
database; the status pill in the top-right shows either an airport count
(e.g. `32,553 apts`) or `No data`. If it is empty it downloads automatically;
you can also force a refresh with the **DB ↻** button.

---

## 2. The interface at a glance

The screen has four regions:

1. **Toolbar (top)** — route input, cruise settings, the **Fly** button, and the
   tool buttons (Perf, W&B, Ref, DB ↻).
2. **Map (center)** — the moving-map with chart layers and route editing.
3. **Layer switcher & map controls (over the map)** — chart selection, Plan mode,
   Fit.
4. **Flight Log drawer (bottom)** — slides up to show the nav log, weather,
   airport details, and terrain profile.

---

## 3. Building a route

### 3.1 The route box

Type a route as **space-separated identifiers**, departure first, destination
last. The box auto-uppercases as you type.

```
KSEE JLI TRM KPSP
```

Three kinds of identifiers are accepted:

| Type | Example | Notes |
|------|---------|-------|
| **Airport (ICAO)** | `KSEE`, `KPSP` | US airports from the OurAirports dataset. |
| **Navaid** | `JLI` (Julian VORTAC), `TRM` (Thermal VORTAC) | VORs, VORTACs, NDBs, etc. |
| **User waypoint** | `@33.0450,-116.5880` | A raw `@lat,lon` point. You normally create these by dragging on the map (see §4.3) rather than typing them, but you can type them too. They appear in the log as `USR1`, `USR2`, … |

At least two identifiers are required (a departure and a destination).
Press **Enter** in the box or click **Fly** to calculate.

> **Note:** RNAV named intersections (e.g. KAYOH, LIMBO) are **not** in the
> dataset — use nearby VORs/airports or drop a user waypoint at the fix's
> coordinates instead.

### 3.2 Cruise settings

The route controls drive the 182T standard-temperature performance tables:

- **Altitude** — supported table range 0–10,000 ft. Intermediate values are
  interpolated. Unavailable combinations return an error.
- **RPM** — 2,000–2,400 RPM; default 2,400.
- **Manifold pressure** — inHg; default 20. Power depends on RPM, manifold
  pressure and altitude. Settings above the POH's 80% cruise limit are rejected.
- **Reserve** — minutes of cruise fuel, added to the route requirement and
  subtracted from full-fuel endurance. Default 45 minutes.

Cruise assumes 3,100 lb, standard temperature, recommended lean mixture and
closed cowl flaps. Climb uses the POH maximum-rate, standard-temperature,
zero-wind table. The log shows power setting and full-87-gallon endurance
including climb, with the selected reserve withheld.

### 3.3 Fly

**Fly** calculates the route and:

- draws it on the map with draggable waypoints and rubber-band handles,
- fills the **Log** drawer (nav log + fuel),
- kicks off background loads of **Weather**, **Airports**, and **Terrain**.

---

## 4. The map

### 4.1 Chart layers

The top-left switcher chooses the base layer:

- **VFR Sec** — FAA VFR Sectional (default)
- **IFR Low** — FAA IFR Low Enroute
- **IFR High** — FAA IFR High Enroute
- **Satellite** — Esri World Imagery
- **Street** — OpenStreetMap

**Offline.** The three FAA layers are served by this application from its own
tile cache, so they work at a mission base with no internet for any area that
has been cached. On a cache miss the server fetches that tile once and keeps
it, which means an online planning session quietly populates the cache for the
exercise. An area that was never cached shows blank tiles rather than an error.

This used to read "served from the FAA ArcGIS service (with any locally cached
tiles used first)", which was not true in either half: the browser went
straight to ArcGIS and never asked for a cached tile, and the cache itself only
filled when the app was started with `python app.py` — never in Docker, which
is how it actually runs. Both are fixed (L-8).

Two controls, if you need them:

| Environment variable | Effect |
|---|---|
| `CAPVSAR_TILES_OFFLINE=1` | Never reach for the network. Serve only what is cached. Set this at a base you know is isolated, so the server does not spend a timeout on each missing tile. |
| `CAPVSAR_PRECACHE_CHARTS=0` | Do not pre-download charts at startup. |

**Satellite** and **Street** are not cached and come straight from Esri and
OpenStreetMap, so they need internet and will be blank without it. The FAA
layers are the ones to brief from.

### 4.2 Plan mode (click-to-add)

Click **✈ Plan** (top-right of the map) to arm planning mode; the cursor becomes a
crosshair. Click anywhere on the map and the app finds the nearest fixes within
20 NM and offers **Dep / Wpt / Dest** buttons to insert that fix into the route
box in the chosen role. Click **✈ Planning** again to disarm.

**⊙ Fit** re-centers and zooms the map to frame the whole active route.

### 4.3 Rubber-band route editing ⭐

This is the fastest way to shape a route directly on the map.

**Midpoint handles** — every route segment has a small white dot at its midpoint.
Drag one to bend the route:

- While dragging you see a **dashed gold preview** of the new leg and a small
  tooltip showing the nearest snap candidate (e.g. `⌖ JLI · 4.3 NM`).
- On release, a popup lists the **top three snap candidates** (weighted to favor
  VORs/VORTACs and real airports over private strips) plus a **📍 User waypoint
  here** option that drops a raw `@lat,lon` point.
- **Shortcut:** hold **Shift** while you release to drop the `@lat,lon` user
  waypoint **immediately**, skipping the menu.
- Release without choosing (click elsewhere) and the edit is cancelled.

**Existing waypoint markers** are also draggable:

- Drag a waypoint and you get the same snap-candidate / user-waypoint popup to
  redefine it. Shift-drop again drops a user waypoint in place (intermediate
  points only).
- **Departure and destination** can only be moved to real fixes (airports/navaids)
  — the weather, terrain, and climb math need real airport data at the ends.
- **Click** an intermediate waypoint marker to get a **✕ Remove waypoint** option.

The green dot is the departure, the red dot is the destination, blue dots are
intermediate waypoints.

---

## 5. The Flight Log drawer

Click the **▲ Flight Log** tab at the bottom (or it opens automatically after
**Fly**). Four tabs:

### 5.1 Log

- **Summary strip** — total distance (NM), time en route (MIN), total fuel (GAL),
  and the winds used (`dir°/spd kt`).
- **Nav log table**, one row per leg:

  | Column | Meaning |
  |--------|---------|
  | FROM / TO | Leg endpoints |
  | DIST | Leg distance (NM, great-circle) |
  | TC | True course |
  | WCA | Wind correction angle |
  | MH | **Magnetic heading** — TC + WCA − magnetic variation. Variation now comes from the World Magnetic Model at each leg's midpoint (≈ 11° E in SoCal). |
  | GS | Ground speed (kt) |
  | TIME | Leg time (min) |
  | FUEL | Leg fuel (gal) |

- **Fuel breakdown** — taxi & takeoff, climb, cruise, reserve, and total required.

### 5.2 Weather

Loads automatically after a route calc. Shows **METARs**, **TAFs**, **winds
aloft**, and **NOTAM placeholders** for each airport on the route.

> METARs/TAFs are fetched live from aviationweather.gov when reachable; anything
> tagged **(sim)** is simulated. **Winds aloft are real** — GFS forecast winds
> from Open-Meteo at the route midpoint, interpolated to the standard altitudes
> (tagged with the source; they fall back to a deterministic estimate only if the
> service is unreachable). NOTAMs are still placeholders pointing you to
> notams.faa.gov. Always confirm with an official briefing.

### 5.3 Airports

Per-airport cards for the airports on your route: name/city/state, elevation,
lat/lon, current flight category, raw METAR, and a runway table
(runway, length, surface).

### 5.4 Terrain

An elevation profile sampled along the route (USGS elevation data):

- **Max Terrain** and **Min Clearance** (ft AGL) stats, plus a status badge:
  **ADEQUATE** (≥ 2000'), **MIN VFR CLR** (≥ 1000'), or **INSUFFICIENT** (< 1000').
- A cross-section chart: green terrain fill, the red planned flight path (with
  climb and descent ramps), a dashed cruise reference line, and gold waypoint
  markers.
- **Hover** the chart to read distance, altitude, terrain height, and clearance at
  any point.

---

## 6. Tools (toolbar buttons)

### 6.1 Perf

Takeoff and landing distances for CAP 487 from the POH tables. Enter weight
(takeoff), pressure altitude, temperature, and headwind; get **ground roll** and
**distance over a 50 ft obstacle**. The imported runway subset covers 0–6,000 ft and 0–40 °C; values between
rows use the next higher row. Takeoff uses the 3,100 lb short-field table
(flaps 20°); landing uses the 2,950 lb table (full flaps). Both assume paved,
level, dry surface. Wind corrections follow the POH chart notes: 10% decrease
per 9 kt headwind, or 10% increase per 2 kt tailwind through 10 kt. Outside-table
inputs return an error.

### 6.2 W&B (Weight & Balance)

Enter empty weight/moment and the loading (pilot, front pax, rear pax, baggage,
fuel). The calculator returns total weight, CG, and moment, and checks limits:

- **Forward CG limit varies with weight** — 33.0" at/below 2,250 lb, 35.5" at
  2,700 lb and 40.9" at 3,100 lb, linearly between points. Aft limit is 46.0".
- Warns if **fuel > 87 gal usable** or **baggage A > 120 lb** (the form does not model baggage B/C).
- The status line spells out exactly what's out of limits (overweight amount, or
  CG forward/aft of the weight-specific limit).

### 6.3 Ref

A quick-reference card: V-speeds, weights, fuel, CG limits, and station arms.

> **Known discrepancy:** the Ref card currently lists the *old* fixed forward CG
> limit (35.0") and a front-seat arm of 40.0". The **W&B calculator** uses the
> corrected sloped envelope and a 37.0" front-seat arm. When in doubt, trust the
> W&B calculator (and the POH). This card is slated to be updated.

### 6.4 DB ↻

Re-downloads the airport/runway/navaid database from OurAirports. Runs in the
background with a progress modal; the app stays usable meanwhile.

---

## 7. Worked example — KSEE → JLI → TRM → KPSP

A short cross-country from **Gillespie Field (KSEE)** in El Cajon, over the
**Julian VORTAC (JLI)**, across to the **Thermal VORTAC (TRM)** in the Coachella
Valley, and into **Palm Springs (KPSP)** — a nice mountains-to-desert VFR hop.

### Step by step

1. **Open the app** and confirm the DB pill shows an airport count (not
   "No data").
2. In the route box, type:

   ```
   KSEE JLI TRM KPSP
   ```

3. Set **Altitude** to **9,500 ft** (good terrain clearance over the Peninsular
   Ranges / San Jacinto area), leave **RPM** at **2400 (55%)** and **Reserve** at
   **45 min**.
4. Press **Fly**.
5. The route draws KSEE → JLI → TRM → KPSP and the **Log** drawer opens.

### What you should see

Times, fuel and headings depend on the selected RPM/manifold pressure and
winds. The former 172S numerical example no longer applies. Read the calculated
log and fuel summary for CAP 487's 87-gallon profile.


### Explore the rest

- **Terrain tab** — the profile will show the high ground east of San Diego and
  around San Jacinto; check the Min Clearance badge against your 9,500 ft cruise.
- **Weather tab** — METARs for KSEE and KPSP (live if reachable), plus live GFS
  winds aloft.
- **Airports tab** — runway lengths/surfaces for KSEE and KPSP.
- **Edit it on the map** — drag the midpoint of the JLI→TRM leg northward and
  snap to another fix, or **Shift-drop** to place a user waypoint, to see the
  route and nav log recompute instantly.
- **W&B** — open the modal, enter your actual loading, and confirm you're inside
  the (now weight-dependent) CG envelope.

---

## 8. Civil Air Patrol Search & Rescue (SAR) Patterns

The flight planner incorporates specialized search pattern generators used in Civil Air Patrol aerial search missions, coupled with export options for flight simulators and the CAP V-SAR exercise console.

### 8.1 Accessing the SAR Tool
Click the **SAR** button in the main toolbar. This opens the SAR Pattern Generator dialog and enables interactive datum selection on the map.

### 8.2 Supported Search Patterns

1. **Expanding Square (SS):**
   - Used when searching a concentrated area around a known datum (e.g., last known position or initial ELT alert location).
   - Parameters: Datum coordinates (lat/lon), track spacing (0.5–2.0 NM), number of legs, initial heading, and turn direction (Right or Left).
   - Generates sequential expansion legs (1×S, 1×S, 2×S, 2×S, 3×S, 3×S...) with calculated magnetic courses and leg distances.

2. **Creeping Line (CS):**
   - Used when searching a route corridor, valley floor, or canyon where the target is likely located along a specific track.
   - Parameters: Start point, end point, sweep width (NM), track spacing (NM), and maximum legs.
   - Generates alternating orthogonal cross-track sweeps advancing along the route axis.

3. **Parallel Track (PS):**
   - Used for systematic grid searches covering large rectangular areas or CAP quadrangles.
   - Parameters: Corner coordinate, search box length (NM), search box width (NM), axis heading, and track spacing (NM).
   - Generates parallel search tracks stepped across the search area.

### 8.3 Route Integration & Search Sortie Metrics
Clicking **Apply to Route** integrates the generated search waypoints (`SS01`, `CS01`, `PS01`...) into the active flight plan:
- The route box is automatically populated with geodesic user coordinates (`@lat,lon`).
- The nav-log drawer recomputes fuel burn, time-on-station, and terrain clearances for the search pattern using the aircraft POH performance polar.
- The map visualizes the search grid overlaid against FAA VFR Sectionals and IFR enroute charts.

### 8.4 Exporting & Simulator Integration

- **Export X-Plane 12 `.fms`:**
  Downloads a standard FMS format file (version 1100) compatible with X-Plane 11 and 12 G1000 / FMS navigation systems. Save directly to your simulator's `Output/FMS plans/` folder.
- **Push to V-SAR Console (shared `https://ms01/` origin):**
  Transmits the planned search sortie directly into the CAP V-SAR training environment over LAN (`VSAR_CONSOLE_URL`).
  - Automatically creates the scenario in the exercise database with the datum, alert radius, and sortie notes.
  - If an active sortie is currently running, broadcasts an automated mission notification message to Mission Base and connected observer consoles.

---

*Questions or fixes: this app lives at
[github.com/rpcraighead/flight-planner-n499cp-v2](https://github.com/rpcraighead/flight-planner-n499cp-v2)
(and Gitea internally). Fly safe, brief for real.*


## SAR flight-plan export to X-Plane 12

The FMS export requires both airport identifiers to resolve in the local
aviation database. An unresolved departure or destination returns an error
naming the identifier. Correct it or update the database before exporting;
search waypoints are never substituted for airport positions.

SAR waypoints retain DATUM, SS01, CS01 and PS01-style identifiers. Export
normalizes labels to uppercase ASCII letters, digits and underscores, while
latitude and longitude remain in their own columns. Unlabelled points retain
coordinate-derived identifiers. This follows Laminar's
[v11 FMS format used by X-Plane 12](https://developer.x-plane.com/article/flightplan-files-v11-fms-file-format/).

Validation covers file structure, identifiers and coordinates against that
specification. The G1000 display has not yet been checked in a running
X-Plane 12 session. Before the exercise, load the file and compare the flight
plan's names and coordinates with the brief; brief both until that check passes.


## CAP 487 POH baseline and sources

The profile uses Cessna 182T NAV III GFC 700 information manual
[182TIMBUS-01, revision 1, 20 December 2007](https://www.aeroelectric.com/Reference_Docs/Cessna/cessna-poh/C182T_2007_NavIII-G1000%2BGFC700_POH-PIM_fromCessna.pdf):
Section 2-8 for limits, Figure 5-6 for takeoff, 5-8 for climb/start allowance,
5-9 for cruise, 5-12 for landing, and Figures 6-3/6-5 for sample loading/arms.

As selected for this simulation, empty weight is **1,924 lb** and empty
moment/1000 is **70.9**, the POH sample pair. These are not measurements of
CAP 487. The aircraft builder currently uses **1,970 lb**, so its empty-weight
setting must be changed to 1,924 lb to match this planning baseline. The
planner does not modify the installed simulator aircraft. CG arms are measured
from the POH firewall datum; the simulator's datum mapping is not verified.

The POH maximum takeoff weight is 3,100 lb, maximum landing weight 2,950 lb,
and usable fuel 87 US gal. The W&B result shows required fuel burn before
landing when the calculated weight exceeds 2,950 lb. Passenger arms assume
average seat positions; this form supports only baggage area A.

At 6,000 ft, 2,400 RPM and 20 inHg, Figure 5-9 gives **65% power, 130 KTAS
and 11.4 gal/h**. With 87 gal, the Figure 5-8 maximum-rate climb from sea level,
1.7 gal start/taxi/takeoff allowance and 45 minutes reserve, the planner gives
approximately **6.66 hours** including climb. This supports the project
handbook's **5.5+ hours** at 65% power; endurance is not a fixed 5.5-hour value.
The POH endurance chart uses a different (normal-climb) assumption, so this
calculation is explicitly based on the imported maximum-rate climb table.
