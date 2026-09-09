# N499CP Flight Planner — User Guide

A route planner, nav-log generator, and performance/W&B calculator built around
**N499CP** (2020 Cessna 172S NAV III), CAP San Diego Sr. Sq. 57.

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

Three dropdowns to the right of the route box drive the performance math:

- **Altitude** — grouped by VFR/IFR and cruise direction (hemispheric rule
  labels are a planning aid, not enforced). Pick a preset or **Custom…** to type
  any value (500–17,500 ft).
- **RPM** — engine RPM, tied to the C172S cruise-performance table (2400 RPM ≈
  55% power is the default). **Custom…** allows 1500–2700 in 50-RPM steps.
- **Reserve** — fuel reserve in minutes (30 / 45 / 60 or Custom). This is added to
  the total fuel requirement.

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

FAA chart tiles are served from the FAA ArcGIS service (with any locally cached
tiles used first).

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

Takeoff and landing distances for N499CP from the POH tables. Enter weight
(takeoff), pressure altitude, temperature, and headwind; get **ground roll** and
**distance over a 50 ft obstacle**. The tables use conservative (round-up)
interpolation and a simple headwind credit.

### 6.2 W&B (Weight & Balance)

Enter empty weight/moment and the loading (pilot, front pax, rear pax, baggage,
fuel). The calculator returns total weight, CG, and moment, and checks limits:

- **Forward CG limit varies with weight** — 35.0" at 1950 lb sloping to 41.0" at
  2550 lb (per the POH envelope). Aft limit is 47.3".
- Warns if **fuel > 53 gal usable** or **baggage > 120 lb**.
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

### What you should see (illustrative)

Distances and courses are stable; times/fuel/headings depend on the current
winds aloft (live GFS forecast), so your exact numbers will vary with the weather.

| Leg | Dist (NM) | TC | MH | GS (kt) | Time (min) |
|-----|-----------|----|----|---------|------------|
| KSEE → JLI | ~27 | 046° | ~022° | ~98 | ~17 |
| JLI → TRM | ~36 | 036° | ~014° | ~95 | ~23 |
| TRM → KPSP | ~21 | 305° | ~301° | ~88 | ~14 |
| **Total** | **~85** | — | — | — | **~74** |

Total fuel required ≈ **19 gal** (taxi + climb + cruise + 45-min reserve) — well
within the 53-gal usable, but always confirm with a real W&B and reserve plan.

Note the **magnetic headings run about 11° less than the true courses** — that's
the ~11° E magnetic variation for Southern California being applied correctly.

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
- **Push to V-SAR Console (`ms01:8700`):**
  Transmits the planned search sortie directly into the CAP V-SAR training environment over LAN (`VSAR_CONSOLE_URL`).
  - Automatically creates the scenario in the exercise database with the datum, alert radius, and sortie notes.
  - If an active sortie is currently running, broadcasts an automated mission notification message to Mission Base and connected observer consoles.

---

*Questions or fixes: this app lives at
[github.com/rpcraighead/flight-planner-n499cp-v2](https://github.com/rpcraighead/flight-planner-n499cp-v2)
(and Gitea internally). Fly safe, brief for real.*
