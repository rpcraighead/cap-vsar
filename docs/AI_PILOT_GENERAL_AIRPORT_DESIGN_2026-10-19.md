# AI pilot: landing at any airport from data, not per-runway code (design review, 2026-10-19)

Status: **design proposal, nothing implemented.** Read-only review of the worktree at
`~/Projects/cap-vsar-c182-ai-pilot` on 2026-10-19 (uncommitted `KCRQ 24` table entry included).
Simulator engineering only: nothing in this document is operating guidance for a real aircraft, and
the FAA data discussed is used only to make a simulated pilot behave plausibly.

Items marked **[unverified]** were not confirmed in files or by running anything; no code was run
(a live trial was in progress on the workstation).

## 1. How the AI pilot works today

**Control boundary.** One X-Plane plugin (`xplane/PI_capvsar_flight_control.py` over
`xplane/capvsar_flight_control_core.py`) is the only writer of native controls. A controller process
sends complete actuator frames over a Unix socket; each frame carries session, generation, increasing
sequence and an expiry no more than 0.20 s ahead (`CANDIDATE_AGE_S`); the runner uses 0.18 s
(`experiment.FRAME_LEASE_S`). An expired frame, a 0.4 s heartbeat gap (`EXECUTIVE_AGE_S`, with three
"stall graces" for callbacks more than 0.2 s apart), an ownership readback change or an envelope
violation calls `_fault`, which pauses the simulator, releases the override and **retires the session
permanently**. Lab modes (`capvsar_qualification.QualificationLab` and its subclasses) pin the aircraft
by path and SHA-256, require an expiring lease (at most 4 h), bound every channel (`AUTHORITY` dicts,
brake capped at 0.35) and run a per-frame envelope check. The GFC 700 can be a second owner
(`gfc_owner.py`, bridge states `WAIT_GFC`/`GFC700`) with an overlapped hand-over, and `terrain_guard.py`
advises both owners from the bridge's terrain scan (`capvsar_terrain.py`, X-Plane terrain probe,
12 NM lookahead).

**How a landing is set up and flown.** `xplane/capvsar_landing.py` is the landing lab. Its
`RUNWAYS` table is hand-entered: for each runway a *physical* end (lat, lon), the far end, the
*airport* elevation, a displaced-threshold distance in metres and the width, all transcribed from the
installed apt.dat by a person. `RunwayGeometry` derives length, true heading and an along/cross frame.
The aim point is `aimpoint_m = displaced_threshold_m + 25 ft`. Four entries exist: `KMYF 28R`
(366 m displaced), `KSAN 27` (552 m, from the custom KSAN v3.0 scenery), `KSEE 27R` (215 m) and, added
today, `KCRQ 24` (no displaced threshold; a human chose 305 m "to give about 50 ft threshold crossing
height"). `LandingLab.reset` places the aircraft **1.2 NM before the physical end on a 3° line to the
aim point, at 70 KIAS, flaps one stage, throttle 0.24, ISA, calm** (optional wind up to 15 kt within
±120° of runway heading, lateral/altitude/speed offsets up to 25 m/40 ft/3 kt), engine quick-started,
paused; `check_flight` holds the aircraft inside ±180 m cross-track, −2450 m to length+80 m along, 250 m
AGL, 110 KIAS, 240 s.

`services/ai_pilot/landing_trial.py::LandingController` then flies final: pitch for speed, power for
the 3° path to the aim point (target altitude = **airport** elevation + geometry), profile flap gates,
a wing-low crosswind law, flare from `profile.flare_start_agl_ft`, rollout with ramped braking to
0.32. `LandingObserver` scores independently from telemetry: threshold crossing 20–85 ft AGL at a
profile speed window, all three flap stages seen, touchdown between the aim point and aim point+400 ft,
|cross| ≤ 4 m, pitch in the profile window, sink > −600 fpm, full stop before `length − 100 m`,
moderate symmetric braking, crosswind alignment demonstrated. `scripts/ai_pilot_landing.py` runs one
trial per process (reset, start, exchange loop, fault-pause at the end, independent replay of the
JSONL trace). There is **no go-around branch** in `LandingController`; the only missed-approach logic
is in `ksee_kmyf_mission.py` and acts before the 1.2 NM hand-off.

**Why the table exists.** The lab needed an exact, pinned runway frame for a scored trial, the
observer needed a touchdown window relative to the usable runway (the KMYF displaced-threshold catch in
`docs/AI_PILOT_LANDING_VIDEO_NOTES.md`), and transcribing one runway was faster than parsing a
380 MB apt.dat inside a plugin. It was the right first step; it does not scale.

**Navigation, patterns, missions.** `ksee_kmyf_mission.py::MissionController` is a stage machine with
hard-coded fixes (PGY10, MZB, BAKEL, MIBBY, NESTY, PENYY, CARIF), the KMYF ILS frequency, charted
altitudes with hand margins and a missed-approach sequence; it hands to `LandingController("KMYF 28R")`
at 1.2 NM once the ILS is within one dot. `search_patterns.py` generates CAP patterns and flies them
with `CruiseLaw` (measured-table throttle feed-forward, climb capped by the profile).
`xplane/capvsar_mission.py::MissionLab` is the bridge envelope for sorties: fixed lat/lon geofence
boxes, a KMYF rollout box and a KSEE surface box, 6,500 ft ceiling, NAV1 forced to 111.95. Ground work
(`taxi.py`, `ground_guidance.py`, `runway_entry.py`, `takeoff_guidance.py`, `capvsar_surface.py`) uses
surveyed KSEE points (parking 12, D8 hold) given as literals or as constructor arguments.
`flight_executive.py` defines typed `APPROACH`/`LAND`/`GO_AROUND` tasks and runway corridors
(`phase_profiles.RunwayCorridor`), but the attended runners drive the controllers directly; the
executive is still the offline boundary **[unverified that any live runner uses it]**.
`flight_controller.py` is the retired KSEE→KRNM prototype with its own literals (magnetic variation
11.5°, KRNM 27 threshold) and is still imported by `web_server.py`/`agent_bridge.py` for display.

**Where the profile design generalizes and where it does not.** Everything that differs between the
C172SP and C182T *by handbook* is in `services/ai_pilot/profiles/*.toml` (speeds, Vfe, flap gates,
observer windows, flare onset, base throttles, prop, measured performance table), loaded strictly. That
part works: the pattern and owner-transfer trials flew both aircraft on the same code. What is **not**
in the profile but is aircraft-flavoured in `landing_trial.py`: the crosswind bank gains (1.05 left /
0.85 right, "the stock C172 needs less right bank"), the rollout aileron schedule (0.04→0.30), the
brake ramp (0.32, comment references C182T toe-brake readback), the flare law constants
(5.5° + 4.5° late-flare, 4.5 s blend, −120 fpm floor), pitch/trim gains and rates. Nothing in the
profile describes required landing distance, demonstrated crosswind, pattern speed/bank or turn
radius, so nothing can yet decide whether a runway is *acceptable* for the aircraft.

## 2. Methodology weaknesses and risks (ranked)

1. **Runway geometry and the aim point are hand-entered and hand-chosen.** Four airports took four
   transcriptions, each with a human-picked number, and the two conventions already disagree:
   KMYF/KSAN/KSEE aim 25 ft past the displaced threshold (an unflared 3° line that crosses the
   threshold at about zero height; the flare carries the airplane), while KCRQ aims 1,000 ft down
   the runway for a 50 ft crossing. Published threshold crossing heights are 41 ft (MYF 28R),
   45 ft (SEE 27R), 54 ft (CRQ 24) [NASR `THR_CROSSING_HGT`, see §3.1]. The observer's touchdown
   window therefore means different things per runway, and a pass at one is not comparable to a
   pass at another.
2. **The path is a fixed 3° to the airport elevation, not the threshold elevation on the published
   angle.** Threshold elevations differ from the field elevation (KCRQ 24: 326 ft vs 331; KRNM 09/27:
   1386/1395 ft vs 1395; KSEE 27R displaced threshold 381.8 vs 388), so the same code is a few feet
   high or low depending on the runway and cannot represent a sloped runway at all (KSEE 0.5% up
   east, KMYF 0.3% up east per the Chart Supplement; about 25 ft over KSEE 27R's length). Published
   visual glide paths are not 3° everywhere: KSEE 27R PAPI is **4.5°** (obstacle-driven: NASR lists a
   road 37 ft high 585 ft from the threshold on a 10:1 slope), KCRQ 24 is 3.2°, KMYF 10L 3.4°, KRNM
   3.5°. A fixed 3° line at KSEE 27R passes under the PAPI path with little obstacle margin
   **[rough estimate, unverified against the obstacle position convention]**.
3. **No pattern, no runway choice, no go-around.** The lab starts on a configured 1.2 NM final in
   the right flap stage; the only sortie approach is the KMYF ILS. The aircraft never chooses a
   runway from wind, never flies downwind/base, and `LandingController` has no balked-landing path:
   an unstabilized final either lands or trips the bridge envelope. The development plan's
   milestone 3 ("recovery and go-around") is open.
4. **Single point of failure on the frame lease, and a restart-the-sim recovery.** A 0.18 s lease,
   0.2 s acceptance window, 0.4 s heartbeat and three grace ticks mean one simulator hitch (scenery
   paging, autosave, GC in XPPython3, a slow host) ends a trial with a fault-pause and a *retired*
   session; the runner then needs a new `lab_reset`, and in practice the owner restarted the
   simulator (`docs/evidence/ai_pilot_ksan_restart_20261010.json`: "Restart the landings after the
   simulator had shut down"; the crosswind sequence's seventh run "interrupted by the simulator
   bridge before touchdown"). Interrupted runs are excluded from scoring, which is honest but hides
   the hitch rate. Nobody has measured tick-gap statistics per phase or per airport (scenery-heavy
   airports will be worse). The right answer is probably *not* to lengthen the lease but to measure,
   budget and checkpoint (see §3.6).
5. **Calm-air, ISA, fixed-loading laboratory.** Every landing is flown at 170 kg payload, 100 kg
   fuel, 15 °C, 29.92, no turbulence, no shear, no gust, wind set relative to the runway and read back
   from truth datarefs; the controller's "crosswind" decision uses `wind_mps`/`wind_from_true_deg`
   truth, not anything a pilot would see. X-Plane attenuates wind near the ground (12 kt set, ~8 kt
   measured at contact), so the "15 kt crosswind" claim is really ~10 kt. Nothing covers density
   altitude (KRNM at 1,395 ft is the first chance), weight at the aft limit, or gusts.
6. **Aircraft-specific behaviour still in shared code** (listed in §1). The C182T profile carries
   `tuning_validated = false`; the flare law and crosswind gains were tuned on the C172 and simply
   inherited. A third aircraft would inherit them too, silently.
7. **Observer criteria are literals that do not scale.** Threshold 20–85 ft AGL, +400 ft touchdown
   window, stop before `length − 100 m`, ±4 m cross-track: reasonable at KMYF (4,598 ft), meaningless
   at a 2,100 ft strip (the stop margin should be a fraction of LDA, the window a fraction of the
   available distance; the threshold-height window should follow the TCH).
8. **Envelopes and geofences are hard-coded in the bridge.** `MissionLab.AIRBORNE_BOXES`, the KMYF
   rollout box, the KSEE surface box, the qualification reset position, `SurfaceLab.PARKING/HOLD` and
   `LandingLab`'s "scenery loaded" check (±0.15°) are literals in the plugin. Moving to a new airport
   today means editing and re-staging the plugin, which also changes the hashes recorded in evidence.
9. **Installed-data consistency is assumed, not checked.** `scenery_packs.ini` lets custom packs
   (KSAN v3.0, "KSEE Gillespie Field") override Global Airports; the KSEE custom file and the Global
   one differ by ~3.7 m at the 27R end and by VGSI types (`~/Projects/ksee-gillespie/data/faa/report.md`).
   The table uses the Global KSEE row while the custom pack is loaded **[which one X-Plane uses at
   run time: unverified]**. X-Plane's nav data is cycle 2406 (Navigraph build 2025-10-02); the NASR
   extract is 2610; the Chart Supplement is the 2026-09-03 edition; apt.dat is a May 2026 WED build.
   Nothing records which was used for a trial. apt.dat's `1101` rows are also incomplete at the home
   field: NASR and the Chart Supplement both say KMYF 28R and 10R are right traffic; apt.dat lists
   only `05 left`.
10. **Two architectures coexist.** The typed executive (`flight_executive.py`, phase profiles,
    runway corridors) and the attended runners that call controllers directly. The general-airport
    work should land in one of them, and the corridors should be derived from the same airport record.
11. **Magnetic/true handling is fine but implicit**: apt.dat and NASR headings are true; the
    controllers fly true heading and measure variation from telemetry; the legacy prototype hard-codes
    11.5°. The planner must state its frame everywhere (runway *numbers* are magnetic).

## 3. Proposed architecture

### 3.1 What is available offline on this workstation (verified 2026-10-19)

| Source | Where | What it carries that we need | Gaps |
|---|---|---|---|
| X-Plane Global Airports `apt.dat` (380 MB, spec 1200, WED 2.7.2) | `~/X-Plane 12/Global Scenery/Global Airports/Earth nav data/apt.dat` | Row `1` airport + elevation; `1302` metadata (`icao_code`, `datum_lat/lon`, `transition_alt`, `allows_circuits` at KMYF); `100` runway rows: width, surface, both ends' lat/lon, **displaced threshold (m)**, blast pad, markings, approach-light code, TDZ, REIL; `21` VGSI rows with **glide angle** (KCRQ 24: PAPI 3.20°, KSEE 27R: 4.50°); `1050–1056` frequencies (kHz); **traffic flows `1000/1001/1002/1003` with `1101` VFR pattern direction and `1110` runway-in-use** (KCRQ: "24 right" under westerly and calm flows, "06 left" easterly; KSAN: flows; KMYF: only "05 left"); `1201/1202` taxi network; `1300` ramp starts; `19` windsocks | No per-end elevation, no TPA, no obstacles, no TCH; `1101` incomplete (KMYF lacks 28R, Global KSEE has no flows); custom scenery packs override whole airports |
| Custom scenery `apt.dat` | `~/X-Plane 12/Custom Scenery/<pack>/Earth nav data/apt.dat`, order from `Custom Scenery/scenery_packs.ini` | Same rows; KSAN v3.0 and KSEE packs installed | Must be merged by precedence |
| `earth_nav.dat` (cycle 2406) | `~/X-Plane 12/Resources/default data/` | ILS/LOC/GS with **glide-slope angle** (KCRQ 24 GS 3.20°, KMYF 28R 3.00°), LPV final paths with angle and TCH-like height | FAA cycle lag |
| `CIFP/<ICAO>.dat` (15,911 airports) | same dir | `RWY:` records: **threshold elevation per end, displaced-threshold length (ft), localizer ident** (KMYF RW28R 422 ft, 1199 ft displaced; KSEE RW27R 376 ft, 706 ft); `APPCH/SID/STAR` legs with fixes, altitudes, course | Procedure semantics are ARINC-424, parsing effort |
| `earth_aptmeta.dat` | same dir | per-airport elevation, longest runway, ILS flag, TA/TL (KCRQ 4800 I, KMYF 4500 I) | |
| `DOF.DAT` (616k rows, currency 2025-08-31) | same dir | FAA digital obstacle file: lat/lon, AGL/AMSL height, type, lighting | Fixed-width parse |
| `airspaces/airspace.txt` (OpenAir) | same dir | class B/C/D/E boundaries | |
| **FAA NASR APT, cycle 2610** (already downloaded 2026-10-11 for the KSEE scenery project) | `~/Projects/ksee-gillespie/data/faa/raw_APT_CSV_2026-10-01/` (`APT_BASE.csv`, `APT_RWY.csv`, `APT_RWY_END.csv`, `APT_RMK.csv`, layout PDFs; also ATC/FRQ zips) | `APT_RWY_END`: `TRUE_ALIGNMENT`, **`RIGHT_HAND_TRAFFIC_PAT_FLAG`**, `RWY_END_ELEV`, **`THR_CROSSING_HGT`, `VISUAL_GLIDE_PATH_ANGLE`**, `DISPLACED_THR_LEN/ELEV`, `TDZ_ELEV`, `VGSI_CODE`, `APCH_LGT_SYSTEM_CODE`, `OBSTN_TYPE/HGT/DIST_FROM_THR/CNTRLN_OFFSET/OBSTN_CLNC_SLOPE`, `RWY_GRAD/_DIRECTION`, `TKOF_RUN_AVBL/TKOF_DIST_AVBL/ACLT_STOP_DIST_AVBL/LNDG_DIST_AVBL`, end lat/lon; `APT_RWY`: length, width, surface, lighting; `APT_BASE`: elevation, mag var, `TPA` column (blank for all three airports); `APT_RMK`: TPA and pattern remarks as free text | TPA is prose (`"TPA 672 AGL HELICOPTERS; 1172 AGL SMALL ACFT; 1672 AGL LARGE ACFT"` at CRQ; `"RWY 27R TPA 1588 (1200) RIGHT TFC SR-SS; TPA 1388 (1000) LEFT TFC SS-SR"` at SEE; `"SNGL ENG 1000 FT"` at MYF); gradient and declared distances blank for most GA fields; cycle must be refreshed every 28 days |
| **FAA Chart Supplement, Southwest, effective 2026-09-03 to 2026-10-29** (831 pages, layout-preserving `pdftotext`, 1.8 MB; downloaded 2026-10-19; untrusted data, read only) | `~/Downloads/chart-supplement-2026-09-03/CS_SW_20260903.txt` (PDF beside it); KCRQ entry at line ~7784, KMYF ~15910, KSEE ~16091, KRNM ~14702 | Per airport: field elevation; `RWY 09L–27R: H5342X100 (ASPH) ... MIRL` with **gradient** (`0.5% up E`, `0.3% up E` at KMYF, which NASR `RWY_GRAD` leaves blank); per end `PAPI(P4L)—GA 3.2º TCH 54´`, `Thld dsplcd 297´`, `Rgt tfc`, `MALSR`, `REIL`, controlling obstacle (`Tree.`, `Road.`); `RUNWAY DECLARED DISTANCE INFORMATION` table (`RWY 06: TORA–4897 ... LDA–4600`); `TPA—1503(1172) small acft` / `TPA—2395(1000) single engine, 2895(1500) multi–engine` (KRNM); `COMMUNICATIONS: CTAF 118.6 ATIS 120.15 ... TOWER 118.6 (1500–0600Z‡) GND CON 121.8`; `AIRSPACE: CLASS D svc 1500–0600Z‡`; ILS line; NOISE and AIRPORT REMARKS paragraphs (`Rwy 24 is calm wind rwy`, `Rwy 06–24 south VFR tfc pattern clsd 0600–1500Z‡`, `Noise abatement, tkf climb on rwy heading until 1900´ MSL` at KRNM) | Column layout: two-column pages and wrapped lines, so a parser must first isolate an airport block (from the `NAME (ID)(KID)` header to the next header) and then match line patterns; free-text remarks are prose |
| AIM 4-3-3 / AC 90-66B | not on disk | Standard pattern procedures, 45° entry, default 1,000 ft AGL | Human reading; cite the edition when a default is coded |

**What the Chart Supplement can and cannot give a parser.** Reliably (fixed phrasing, one line each,
confirmed on the four entries above): runway line (`RWY id: Hlength X width (surface) ... lighting`),
gradient (`n.n% up DIR`), end lines (`PAPI(Pnx)—GA d.dº TCH nn´`, `Thld dsplcd nnn´`, `Rgt tfc`,
`MALSR`/`REIL`, single-word obstacle), the declared-distance table, `TPA—msl(agl) class[, msl(agl)
class]`, the `COMMUNICATIONS` line (CTAF, ATIS, UNICOM, APP/DEP, TOWER with hours, GND, CLNC DEL), the
`AIRSPACE: CLASS D svc hhhh–hhhhZ‡` line and the ILS line. Not reliably: everything inside `NOISE:`
and `AIRPORT REMARKS:` (calm-wind runway, pattern-side closures by time, noise-abatement climb
instructions, "TPA—See Remarks" cross-references in KSEE's wrapped multi-runway TPA sentence, PPR
rules). Those are prose; the builder should copy them verbatim into the record under `remarks[]`,
flag the airport AMBER whenever a remark contains `tfc pattern`, `TPA`, `calm wind`, `noise` or
`clsd`, and let the owner (or a model with the owner's review) turn specific sentences into typed
rules, each rule carrying the quoted sentence as its source. The supplement is also the tie-breaker
when apt.dat and NASR disagree: it confirms `Rgt tfc` for KMYF 28R and 10R, KSEE 27R and KCRQ 24.

Two facts from those files that change the design: pattern direction and TPA are **time- and
class-dependent** (KSEE 27R: right traffic 1,200 ft AGL by day, left 1,000 ft at night; KCRQ south
pattern closed 2200–0700; KMYF singles 1,000 / twins 1,600), so they must be data with conditions,
not a per-runway constant; and NASR flags **KMYF 28R and 10R as right-hand traffic** while apt.dat
says nothing, so apt.dat alone is not enough even at the home airport. (Web search for the NASR
layout and the apt.dat 1200 row codes was inconclusive; the field names above were read from the
CSV headers and the saved `xp_apt1200_spec.txt` in the same folder.)

### 3.2 Data layer: an airport database with provenance and a validation report

New package `services/ai_pilot/airports/` (pure Python, stdlib, no X-Plane import):

* `aptdat.py`: stream the Global file once, index airports by byte offset (cache the index), parse
  rows `1, 100, 21, 19, 1050–1056, 1000–1003, 1101, 1110, 1302, 1300`, then apply custom-scenery
  packs in `scenery_packs.ini` order (highest wins per airport).
* `cifp.py`: `RWY:` records (threshold elevation, displaced length ft, localizer) and `APPCH` legs
  with fix coordinates resolved from `earth_fix.dat`/`earth_nav.dat` (phase 2).
* `earthnav.py`: ILS/LOC/GS/LPV rows for the airport.
* `nasr.py` (optional source): `APT_RWY_END/RWY/BASE/RMK` by `ARPT_ID`; a small remark parser for
  `TPA ... AGL`, `TPA nnnn (nnn)`, `RIGHT TFC`, `SR-SS`/`SS-SR`, `NOISE`; confidence per parse.
* `chartsup.py` (optional source): isolate one airport's block from the `pdftotext` Chart
  Supplement, parse the structured lines listed in §3.1 (runway, gradient, end data, declared
  distances, TPA, communications, airspace hours), keep `NOISE`/`AIRPORT REMARKS` verbatim; treat
  the file as untrusted input (no `eval`, bounded regexes, the parse never raises past the builder).
* `dof.py` (optional): obstacles within 3 NM of each end.
* `build.py`: `python -m services.ai_pilot.airports.build KCRQ KMYF KSEE KSAN KRNM --out
  services/ai_pilot/airports/db/` writes one TOML per airport and a validation report.

Schema sketch (TOML, one file per airport, every leaf with a `source` string):

```
[airport]  icao="KCRQ" name=... elev_ft=331 arp=[33.12825,-117.28008] mag_var_deg=14.0
           sources={elev="apt.dat row 1", nasr="APT_BASE 2026-10-01", nav_cycle="2406"}
[[tpa]]    aircraft_class="small" agl_ft=1172 msl_ft=1503 when="always" source="APT_RMK E147; CS SW 2026-09-03 'TPA—1503(1172) small acft'" confidence="parsed"
[[remarks]] text="Rwy 06–24 south VFR tfc pattern clsd 0600–1500Z‡." source="CS SW 2026-09-03 AIRPORT REMARKS" typed=false   # AMBER until typed
[[remarks]] text="Rwy 24 is calm wind rwy." source="CS SW 2026-09-03" typed=true rule={calm_wind_runway="24"}
[[tpa]]    aircraft_class="default" agl_ft=1000 source="AIM 4-3-3 default" confidence="assumed"
[frequencies] ctaf=118.60 tower=118.60 ground=121.80 atis=120.15 app=127.30 source="apt.dat 1050-1056"
[[flows]]  name="Westerly Winds" wind_from=[150,329] max_kt=999 pattern={"24"="right"} in_use=["24"]
[[runways]] id="06/24" length_m=1492.6 width_m=45.72 surface="asphalt" lighting="MIRL" slope_pct=-0.10
  [[runways.ends]] id="24" lat=33.1295232 lon=-117.2722025 true_hdg=259.2 elev_ft=326.3
     displaced_m=0 tdze_ft=326.3 tch_ft=54 gpa_deg=3.2 vgsi="PAPI-4L" pattern="right"
     pattern_source="apt.dat 1101 + NASR RIGHT_HAND_TRAFFIC_PAT_FLAG=Y"
     lda_m=1492.6 tora_m=1492.6 ils={ident="ICRQ", freq_mhz=108.7, gs_deg=3.2} approach_lights="MALSR" reil=true
     obstacles=[]            # from NASR controlling obstacle + DOF within the approach fan
[validation] status="GREEN" checks=[...]
```

Validation report per airport (machine-readable, printed): end positions apt.dat vs NASR (< 5 m
GREEN, < 15 m AMBER), displaced-threshold m vs ft (< 3 m), VGSI angle vs NASR `VISUAL_GLIDE_PATH_ANGLE`,
`1101` vs `RIGHT_HAND_TRAFFIC_PAT_FLAG`, TPA parse confidence, custom-scenery override present,
nav-cycle dates, threshold elevation available (CIFP or NASR) or **probed** (see below). GREEN is usable
unattended inside the existing envelope; AMBER requires the owner to acknowledge the listed items (the
acknowledgement is recorded in the file); RED is refused by the lab. The four flown runways become
the regression fixture: a test asserts that the database-derived `RunwayGeometry` matches the pinned
`RUNWAYS` entries within 1 m / 0.1°.

**Threshold elevation and slope from the simulator itself.** The wheels touch X-Plane's mesh, not the
NGS survey. The bridge already has a terrain probe; add a `probe_runway` lab request that returns
mesh elevation at both ends and the displaced threshold while paused. The planner uses the probed
threshold elevation as the path reference, and the validation report compares it with NASR
`RWY_END_ELEV` (a mismatch > 15 ft is AMBER: scenery and survey disagree, which the owner should know).

**Runtime access.** `RunwayGeometry` gains a classmethod `from_record(airport, end_id)` (threshold =
physical end, displaced from the record, elevation = probed or CIFP threshold elevation, plus
`tch_ft`, `gpa_deg`, `lda_m`, `pattern`, `slope`). The lab config pins `{"airport": "KCRQ", "runway":
"24", "db_sha256": ...}` instead of a table key, and the staged plugin receives the one-airport TOML
alongside its config so the plugin never parses apt.dat.

### 3.3 Aim point, path and flare from runway data

Replace the two ad-hoc conventions with one rule, every term sourced:

* `gpa_deg` = NASR `VISUAL_GLIDE_PATH_ANGLE` or apt.dat row-21 angle or ILS GS angle, else 3.0
  (`source="default"`); the controller's `tan(3°)` becomes `tan(gpa)`.
* `tch_ft` = NASR `THR_CROSSING_HGT`, else implied from the VGSI position (distance past threshold ×
  tan gpa, which the KSEE report shows agrees within ~5 ft), else 40 ft default.
* `aimpoint_m` = `displaced_m + tch_ft / tan(gpa)` measured from the physical end. (KMYF 28R: 366 m +
  238 m; KCRQ 24: 294 m, close to the 305 m chosen by hand; KSEE 27R at 4.5°: 215 + 174 m.)
* Path reference = threshold elevation (probed) plus `slope × along` beyond the threshold, so the
  flare height and the observer's AGL windows are measured against the pavement actually under the
  aircraft (the bridge already supplies `agl_m`).
* Touchdown window = `[aimpoint − 0.25·tch/tan(gpa), aimpoint + max(400 ft, 0.10·lda)]`; threshold
  crossing window = `tch ± 25 ft`; stop criterion = `along ≤ lda − max(100 m, 0.1·lda)`; all three
  recorded in the manifest as now.
* Runway acceptability (new profile fields, handbook-sourced): `landing_distance_50ft_m` at sea
  level ISA with the POH's altitude/temperature corrections applied, × 1.3 (a training safety factor,
  configurable) ≤ `lda_m`; `max_demonstrated_crosswind_kt` (C182T POH 15 kt, C172 15 kt
  **[cite when added]**); if either fails the runway is rejected at planning time, not discovered on
  rollout.
* Flare onset stays a profile value but is expressed as height above the *threshold* path.

The old 25 ft convention is kept as `aimpoint_rule = "legacy_displaced_plus_25ft"` so archived
traces replay to the same score (§4, stage 1).

### 3.4 Pattern planner

`services/ai_pilot/pattern_planner.py`, pure, profile-scaled, outputs a list of typed legs that the
existing waypoint tracker can fly:

1. **Inputs**: aircraft state (lat, lon, true heading, altitude), wind at pattern altitude (lab: the
   configured wind; sortie: `sim/weather/region` wind read through the bridge as the ATIS proxy, with
   the measured value logged beside the assumed value), the airport record, the aircraft profile, time
   of day (for `SR-SS` rules), an optional ATC-assigned runway.
2. **Runway choice** (all candidates scored, the decision and its reasons logged): reject if
   `lda < required`, crosswind > demonstrated, tailwind > 5 kt, surface not in the profile's list,
   or flow rules exclude it; prefer the apt.dat flow in use for the wind (KCRQ westerly → 24), then,
   below 5 kt, the typed calm-wind runway from the Chart Supplement (KCRQ 24, KRNM 27), then the
   highest headwind, then the longer runway; parallel runways: prefer the one whose `1110` rule
   lists `props`, and never plan a pattern that crosses the parallel's pattern side (KMYF 28R right /
   28L left both keep traffic outside the parallel, which the data expresses).
3. **Pattern geometry** in the runway frame (along/cross, metres): TPA from the record for the
   aircraft class and time, default 1,000 ft AGL above the *airport* elevation (AIM 4-3-3,
   AC 90-66B); direction from the record, default left (14 CFR 91.126(b)); downwind offset
   `d = 2·r + 300 m` where `r = V²/(g·tan 30°)` at the profile's pattern speed (C172 90 KIAS → r≈370 m
   → d≈1.0 km, about 0.55 NM; C182T 100 KIAS → d≈1.2 km) **[check against AC 90-66B's ½–1 mile]**;
   abeam-threshold point; base turn when 45° behind the threshold; final length ≥ 1.2 NM so the
   existing `LandingController` regime (flap gates at 1 NM and 0.5 NM, 70 KIAS target) is reached
   unchanged; final-intercept altitude = path altitude at that distance (≈ 380 ft above threshold at
   1.2 NM for 3°).
4. **Entry selection** from position and heading: if the aircraft is on the pattern side, a 45°
   entry to the midpoint of downwind at TPA (AC 90-66B preferred entry); if on the opposite side,
   cross midfield 500 ft above TPA and descend on the outside to a teardrop 45° entry, or, when the
   record says `allows_circuits=0` or a noise remark exists, overfly to the upwind side (AMBER
   acknowledgement); straight-in only when the aircraft is already within ±10° of final and ≥ 3 NM.
   Each entry is a leg list with altitude, speed and flap targets taken from the profile
   (`approach_clean_kias` downwind, `ils_final_kias` base with stage 1, `final_approach_kias` final).
5. **Who flies it**: a new `PatternController` stage machine modelled on `MissionController`,
   using `CruiseLaw` for downwind/base (it already holds altitude, speed and cross-track) and
   handing to `LandingController` at the final-intercept gate with a fresh instance; descent on
   downwind to base uses the measured table's −400 fpm column. Terrain guard stays active until
   the hand-off (its 1,000 ft trigger would fire on short final, so it is muted below TPA inside the
   pattern box, which must be recorded as a conscious exception).

### 3.5 Stabilization gates and go-around

Gates evaluated by both the controller and, independently, the observer:

* **1,000 ft above threshold** (end of base/start of final): configured for landing (stage ≥ 2),
  speed within −5/+10 of target, on centerline within 0.3 NM at 1.2 NM, within ±1° of path.
* **500 ft** (VFR stabilized-approach gate): centerline ±(0.1·distance), path ±0.5°, speed −5/+10,
  sink ≤ 1,000 fpm, full flaps, trimmed (trim rate small). Not met → **go-around**.
* **200 ft and below**: sink > 1,200 fpm, bank > 15°, speed below `threshold_kias[0] − 3`, or
  predicted touchdown beyond the window (ground speed × remaining flare time) → go-around.
* **On the runway**: bounce above 3 ft after contact or touchdown beyond `aimpoint + window` while
  `along < lda − landing roll` → go-around (balked landing); beyond that, maximum braking and the
  observer marks `LONG_LANDING`.

`GoAroundLaw` (new, small): full throttle and prop full forward (`prop_law.FULL`), pitch for
`missed_kias`, flaps to `missed_flap_ratio` once positive climb, then clean per the profile's
retract rule, wings level on runway heading to 400 ft above the threshold (the bridge's existing
`check_flight` box of 250 m AGL must be raised to TPA + 500 ft for pattern trials), then rejoin
crosswind at TPA. The executive's `GO_AROUND` task already exists; wire it so the runner's
`FlightTask(LAND, on_timeout="go_around")` is honoured. The observer reports `GO_AROUND_CORRECT` /
`GO_AROUND_MISSED` / `GO_AROUND_SPURIOUS` as outcomes distinct from `PASS`/`FAIL`, and a deliberately
unstable entry is a scored go-around test, not a failed landing.

### 3.6 Fitting the existing pieces without rewriting them

* `LandingController`/`LandingObserver`: change only what they read: `runway.aimpoint_m`,
  `runway.gpa_deg`, `runway.threshold_elev_ft` (+ slope), `runway.lda_m`, `runway.tch_ft` through
  `RunwayGeometry`; move the crosswind bank gains, rollout aileron schedule, flare constants and
  brake ramp into `[landing]` of the profile (with the C172 values as defaults so flown behaviour is
  byte-identical, exactly as the C182T port did for speeds).
* `AircraftProfile`: add `pattern_kias`, `pattern_bank_deg`, `landing_distance_50ft_m`,
  `max_demonstrated_crosswind_kt`, `min_runway_width_m`, `surfaces`, and the landing tuning block;
  the loader refuses missing keys as today.
* Bridge: `LandingLab` and `MissionLab` take their geometry and envelope boxes from the one-airport
  TOML in the staged config (box = runway frame ± 4 NM along, ± 2 NM cross, TPA + 1,000 ft), and the
  "scenery loaded" check becomes a probe at the threshold. The `RUNWAYS` dict stays as the pinned
  regression set until stage 1 passes.
* Frame lease: keep the fault-pause (it is the safety culture's strength) but (a) record the
  bridge tick-gap histogram per trial in the trace end record, (b) run a 60 s paused-then-running
  "hitch budget" probe at each new airport before the first trial and refuse to start unattended
  runs above a threshold, (c) make an interrupted landing re-flyable from its last checkpoint
  (`lab_reset` to the planner's final-intercept state) with the interruption counted in the campaign
  ledger rather than dropped. Lengthening the lease is a last resort and should be decided from (a).

## 4. Staged validation plan

Stage 0, offline (no simulator): copy the apt.dat blocks, CIFP `RWY:` lines, earth_nav rows and NASR
rows for KMYF, KSAN, KSEE, KCRQ, KRNM and the stage-3 airports into
`services/ai_pilot/tests/data/airports/` with provenance headers (as was done for the search-pattern
fixture). Tests: parser round-trips; precedence of custom scenery; database output pinned by hash;
`from_record` equals the four `RUNWAYS` entries within 1 m / 0.1°; aim-point rule reproduces the TCH
identity (`height at threshold == tch_ft`); planner mirror symmetry (left pattern at KCRQ 06 mirrors
right at 24); wind → runway choice table (headwind, tailwind limit, crosswind limit, parallels);
go-around triggers on synthetic snapshots; point-mass fly-through of the whole pattern as in
`test_search_patterns.py`. Pass: all green, no simulator.

Stage 1, replay: run `LandingObserver` with database-derived geometry over every archived landing
trace under `~/.cache/capvsar/ai-pilot/` for KMYF 28R, KSAN 27, KSEE 27R and KCRQ 24 (trial numbers in
`docs/evidence/`). Pass: identical outcome and identical touchdown/stop numbers under
`legacy_displaced_plus_25ft`; under the TCH rule the touchdown window moves and the report must list
which archived passes would now be short of the window (expected at KMYF: touchdowns ~40 m past the
displaced threshold). That list is a decision for the owner, not a failure.

Stage 2, attended sim, C172SP then C182T, calm first, then 8 kt crosswind each side, then entries from
four quadrants, three repetitions each, pass = all repetitions scored PASS or correct go-around:

| Character | Candidate | Why |
|---|---|---|
| Sloped, higher elevation, terrain | KRNM 27 (PAPI 3.5°, 1,386→1,395 ft, 0.5% gradient; CIFP present) | already the sortie destination; density altitude |
| Displaced both ends, obstacle-driven VGSI | KSEE 17/35 (450 / 685 ft displaced, PAPI 3.7°/3.5°) and 27R at 4.5° | tests the TCH/angle rule against the fixed 3° habit |
| Right traffic, ILS, flow rules | KCRQ 24 | `1101` and NASR agree; night rule in remarks |
| Parallel runways, one short and narrow | KMYF 28L (3,401 × 60 ft) beside 28R | runway choice and pattern side; width limit |
| Short runway | KOKB Oceanside (CIFP file present) **[runway data unverified]** or KSDM Brown | landing-distance rejection and acceptance |
| Non-towered, CTAF only | L18 Fallbrook or KOKB **[unverified: check `1054` absent, `1051` present]** | pattern entry without a flow in use; CTAF in the record |

Go-around tests at each: an entry 150 ft high and 10 kt fast at the 500 ft gate must produce a
go-around, climb at `missed_kias ± 5`, altitude loss below 50 ft, rejoin at TPA ± 100 ft.

Stage 3, the existing campaign discipline: freeze the tune, ten baseline and ten disturbed landings
per airport from the pattern (not from 1.2 NM), independent replay, interruption ledger, tick-gap
histogram in every trace. Only after stage 3 does an airport's record move from AMBER to GREEN for
unattended use.

## 5. Prioritised backlog

| P | Item | Size | Files likely touched | Delegate to |
|---|---|---|---|---|
| P0 | Airport database builder: apt.dat (Global + custom precedence), CIFP `RWY:`, earth_nav ILS/GS, earth_aptmeta; one-airport TOML with provenance; validation report; fixtures for the 6 stage-2 airports | L | new `services/ai_pilot/airports/{aptdat,cifp,earthnav,build}.py`, `tests/data/airports/`, `tests/test_airports.py` | Codex (long, well-specified parsing; CPU-light) |
| P0 | `RunwayGeometry.from_record` + aim-point/TCH/slope rule with `legacy` flag; `LandingController`/`Observer` read `gpa`, threshold elevation, `lda` from the geometry; stage-1 replay script | M | `xplane/capvsar_landing.py`, `services/ai_pilot/landing_trial.py`, `scripts/ai_pilot_landing.py` (score), `tests/test_landing_trial.py` | Codex; second-opinion review of the aim-point rule by a different model |
| P0 | Move landing tuning (crosswind gains, rollout aileron, flare constants, brake ramp) into the profile `[landing]` block with C172 defaults; golden test that flown behaviour is unchanged | S | `profiles/*.toml`, `profile_loader.py`, `aircraft_profiles.py`, `landing_trial.py`, `tests/golden_profiles.py` | Codex |
| P0 | Bridge tick-gap histogram in the trace end record + hitch-budget probe | S | `xplane/capvsar_flight_control_core.py` (status fields only), `PI_capvsar_flight_control.py`, `scripts/ai_pilot_landing.py` | Codex; owner installs |
| P1 | NASR reader (`APT_RWY_END/RWY/BASE/RMK`), TPA/pattern remark parser with confidence, cross-checks in the validation report | M | `services/ai_pilot/airports/nasr.py`, fixtures from `~/Projects/ksee-gillespie/data/faa/see_csv/` style extracts | Codex; owner confirms parse of the three remarks |
| P1 | Chart Supplement block parser (structured lines only; remarks verbatim; AMBER flags) with the KCRQ/KMYF/KSEE/KRNM blocks as fixtures; gradient and `Rgt tfc` feed the validation report | M | `services/ai_pilot/airports/chartsup.py`, `tests/data/airports/cs_*.txt` | Codex; owner types the remark rules |
| P1 | Pattern planner (runway choice, TPA/direction, entry, legs) + point-mass tests | M | new `services/ai_pilot/pattern_planner.py`, `tests/test_pattern_planner.py` | Codex; review of the geometry and AC 90-66B reading by a different model |
| P1 | `PatternController` (CruiseLaw downwind/base → LandingController) and `GoAroundLaw`; executive `GO_AROUND` wired; observer outcomes for go-arounds; `LandingLab` envelope raised to TPA for pattern trials | L | new `pattern_controller.py`, `go_around.py`, `flight_executive.py`, `xplane/capvsar_landing.py`, runner `scripts/ai_pilot_pattern_landing.py` | Codex implementation; attended trials by the owner |
| P1 | Lab geometry and envelope boxes from the staged one-airport TOML; threshold probe request; `RUNWAYS` kept as regression | M | `xplane/capvsar_landing.py`, `capvsar_mission.py`, `capvsar_surface.py`, `scripts/ai_pilot_experiment.py` (staging) | Codex; bridge changes reviewed by a different model before staging |
| P1 | Profile fields: pattern speed/bank, landing distance, demonstrated crosswind, surfaces | S | `profiles/*.toml`, `profile_loader.py`, `profiles/README.md` | Codex; owner sources the POH lines |
| P2 | CIFP `APPCH` legs → fly a published RNAV/ILS final from the FAF (replaces hand-typed fixes in `ksee_kmyf_mission.py`) | L | `airports/cifp.py`, `ksee_kmyf_mission.py` successor | Codex later |
| P2 | DOF obstacles in the approach fan; obstacle-clearance check of the planned path | M | `airports/dof.py`, planner | Codex |
| P2 | Interrupted-landing checkpoint resume and interruption ledger | M | `scripts/ai_pilot_landing_campaign.py`, lab reset | Codex |
| P2 | Retire `flight_controller.py` literals from `web_server.py`/`agent_bridge.py` | S | those files | Codex |

## 6. Open questions for the owner

1. Aim-point convention: adopt the published TCH rule (touchdowns move ~200 m further down the runway
   at KMYF than the flown passes) or keep "25 ft past the displaced threshold" as the CAP training
   target with the TCH rule only for runways without a displaced threshold?
2. When apt.dat and NASR disagree (KMYF 28R right traffic in NASR, absent in apt.dat; KSEE custom
   scenery 3.7 m off the survey), which is authoritative for the simulator: the installed scenery
   (what the wheels touch) with NASR as a warning, or NASR with the scenery flagged for repair?
3. Is the FAA NASR extract under `~/Projects/ksee-gillespie` the copy this project should depend on,
   and who refreshes it every 28 days? (A stale cycle is acceptable for a simulator if recorded.)
4. Wind source for runway choice in sorties: the region wind datarefs (truth), or an ATIS text
   generated by the exercise console so the AI pilot sees what the trainee sees?
5. Is a go-around a PASS-class outcome for the campaign gates, and how many deliberate go-arounds per
   airport count as evidence?
6. Should the bridge's 0.18 s lease be reconsidered at all, or is the tick-gap measurement the only
   change you want before the pattern work (the author's recommendation)?
7. Which of the stage-2 airports do you want first, and is KRNM (terrain, slope, the existing
   sortie destination) acceptable as the first "unfamiliar" field?
8. Time-of-day rules (KSEE 27R right by day, left at night; KCRQ south pattern closed at night): honour
   them from the simulator clock, or pin "day" for all trials and record it?
