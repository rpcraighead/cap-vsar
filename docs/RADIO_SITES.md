# Fixed radio sites: base antenna and repeater (T31)

**Status (2026-10-18):** data model, reach function and a read-only endpoint are in; nothing in the live radio
path uses them yet, because the voice net does not gate delivery on position at all (see §1). This document is
the design the next step should follow, and the questions the user has to answer first (§6).

User request: "Placement of base staff antennas and repeaters (static) is important. There's a repeater on
Palomar mountain for example. For this exercise, let's assume that the antenna for base is at KSEE, and that the
repeater is at the same location as JLI VOR."

## 1. What exists today

* **No base position.** The scenario seed (`services/exercise/app/settings.py` `SEED`) carries the beacon and the
  alert area; nothing records where Mission Base is. The flight planner's "base station" is a comment about the
  tile cache, not a location. The guide describes Mission Base as a screen (`/base`) and a command post, never a
  place.
* **No repeater.** `docs/CA_WING_REPEATERS.md` is reference material (the national 143.550/148.125 and
  143.700/148.150 pairs, the CA Wing site table incl. R20 Mt. Palomar) and says it is not wired into anything.
* **Radio reach is not modelled.** `services/exercise/app/radio.py` is the Mumble voice net bridge: channels,
  PTT, sessions, the ICS state. It never looks at a position; everyone on a channel hears everyone. The TDFM-136B
  instrument has a talk-around mode "bypassing mountain repeaters" in its feature list, but no site behind it.
* **Reach *is* modelled for the beacon.** The propagation engine `xplane/PI_capvsar_df.py` decides what a
  direction finder hears: a two-ended VHF radio horizon (`1.23 (sqrt h1 + sqrt h2)` NM, heights in feet) and a
  terrain line-of-sight probe along the path (`terrain_clearance`: samples every 0.25 NM, 24-96 probes, the ray
  lowered by the earth's bulge at 4/3 effective radius, blocked when the ground comes within 50 ft of the ray,
  then a diffraction loss from the worst clearance). The console-side `propagation.py` is explicitly a mock-bridge
  stub that repeats only the horizon rule.
* **Positions.** Aircraft positions reach the console through `/api/positions` (lat, lon, alt_ft). Ground teams
  report nothing positional today.

## 2. Site data

`settings.RADIO_SITES` (default for this exercise) or a JSON file named by `CAPVSAR_RADIO_SITES`
(`{"sites": [...], "repeater_pair": "primary"}`) — so another exercise can put the base at Palomar airport and
the repeater on Mt. Palomar without a code change. Each site:

| field | meaning |
|---|---|
| `id` | short unique label (`BASE-KSEE`, `RPT-JLI`) |
| `role` | `base_antenna` (exactly one) or `repeater` (any number) |
| `lat`, `lon` | WGS-84 degrees |
| `ground_elev_ft` | ground at the site, ft MSL |
| `antenna_agl_ft` | antenna height above ground, 0-500 ft |
| `name` | optional, used in the "heard via ..." phrase |

Default sites and their sources (also in comments next to the data):

| site | position | ground | source |
|---|---|---|---|
| `BASE-KSEE` Mission Base, Gillespie Field | 32.826199 N, 116.972000 W | 388 ft | OurAirports `airports.csv` (2026-10-12) as loaded in the planner's `aviation_data.db`, row KSEE; the repo's KSEE 27R survey gives the same 388 ft |
| `RPT-JLI` Julian repeater | 33.140458 N, 116.585936 W | 5,560 ft | X-Plane 12 `Resources/default data/earth_nav.dat` line 22664, `JLI ENRT K2 JULIAN VORTAC`, 114.00 MHz |

Antenna heights (30 ft at the base, 40 ft at the repeater) are placeholders. The repeater pair is a scenario
field (`REPEATER_PAIR`, `primary` = TX 148.125 / RX 143.550, `secondary` = TX 148.150 / RX 143.700).

## 3. Reach model (reused, not invented)

`services/exercise/app/radio_sites.py`:

* `path(lat, lon, alt_ft, site, terrain_ft=None)` — can a station reach the site's antenna? Two tests, both
  taken from the existing engine: the **two-ended radio horizon** (`propagation.radio_horizon_nm`, the same form
  `PI_capvsar_df.py` uses) and the **terrain line of sight** (`terrain_clearance`, the engine's rule with the
  engine's constants: 0.25 NM spacing, 24-96 samples, 4/3-earth bulge, 50 ft margin). The console has no terrain
  of its own, so the caller passes a `terrain_ft(lat, lon)` sampler: the simulator's probe when the result is
  computed sim-side, a DEM if one is ever added to the console, or a synthetic ridge in tests. With no sampler the
  result says `terrain_checked: false` and only the horizon applies.
* `site_link(repeater, base)` — the fixed antenna-to-antenna link, computed the same way.
* `route(lat, lon, alt_ft, sites)` — `direct` when the base antenna is reachable; else `repeater` via the first
  repeater that is reachable **and** whose fixed link reaches the base; else `none`. It returns the phrase for
  the radio log: "heard direct at Mission Base, Gillespie Field (KSEE)", "heard via Julian (JLI VORTAC)
  repeater", "out of range of base and repeater".

Where it should run: the engine already probes terrain between the aircraft and the beacon every cycle; the same
probe between the aircraft and each site is the honest source. Computing it in the plugin and publishing
`cap/radio/route` (direct / repeater id / none) in the telemetry would give the console truth it cannot compute
itself. The console-side function is for the base's own view (which repeater *should* hear this position,
horizon only) and for ground teams and planning.

## 4. Routing a transmission (next step, not implemented)

1. **Aircraft -> base, simplex:** aircraft reaches `BASE-KSEE` (horizon + terrain) -> heard direct.
2. **Aircraft -> repeater -> base:** aircraft reaches `RPT-JLI` on the input (143.550) and the fixed link
   `RPT-JLI -> BASE-KSEE` is clear -> heard via the repeater on the output (148.125). Both legs must hold.
3. **Base -> aircraft** is the reverse of the same paths (the model is symmetric; power differences are an open
   question, §6).
4. **Ground team <-> base:** the same rule with the team's position and a hand-held antenna height (open
   question). A team in a canyon with no path to either site is out of range; a team that reaches the repeater
   is heard via the repeater.
5. **Neither path:** the transmission is not delivered. For training value the radio log should record the
   attempt with the reason ("out of range of base and repeater") so the debrief can show it.

Where to hook it: `MumbleRadio` keys a radio by callsign and knows the channel; the position for an aircraft
callsign is in the hub's latest `/api/positions` entry. Gating a PTT on `route(...)["path"] != "none"` and
tagging the log line with the `heard` phrase is the smallest change; muting *reception* per listener is the
larger one (the voice server mixes per channel, not per pair of stations) and is what §6's questions decide.

## 5. What the screens should show

* Base Radio (`/radio`): next to the station chip, "heard direct" / "via JLI repeater" / "out of range"; the log
  line carries the phrase.
* Mission Base map (`/base`): the two sites as fixed markers (antenna and repeater symbols) from
  `GET /api/radio/sites`; optionally the repeater's fixed link drawn to the base.
* Ready room briefing pack: "Mission Base antenna: Gillespie Field. Repeater: Julian (JLI) on the primary pair."

## 6. Open questions for the user

1. **Antenna heights:** base mast height at KSEE (30 ft assumed) and the repeater's antenna above the VORTAC
   site (40 ft assumed)? Real sites also have feedline loss and ERP; the model uses geometry only.
2. **Do ground teams use the repeater?** If yes, what antenna height and power for a hand-held (5 W at 6 ft) and
   a vehicle radio (50 W at 8 ft)? Geometry alone treats them like a very low aircraft.
3. **Does the aircraft's DF hear the repeater?** The DF is tuned to the beacon band; the repeater is on the
   tactical net. The engine should keep them separate unless the exercise wants a "repeater as training beacon"
   case.
4. **Delivery policy:** block a transmission that has no path, or deliver it degraded (hiss, dropouts) the way
   the DF audio degrades with signal? Blocking is simple and teaches siting; degradation is more realistic.
5. **Second repeater / talk-around:** should the exercise carry both pairs (e.g. Palomar on the secondary pair)
   and the simplex talk-around channel the TDFM-136B feature list mentions?
6. **Symmetry:** base-to-aircraft on the same path, or model the base's higher power?

## 7. Tests

`tests/test_radio_sites.py`: pinned coordinates and sources, pair convention, site validation, JSON override,
the horizon rule equal to the engine's, an aircraft at 4,500 ft near Julian reaching the repeater while a low
aircraft behind a synthetic 7,000 ft ridge east of JLI does not, the repeater's fixed link to KSEE, routing
direct -> via repeater -> none, and the read-only route.
