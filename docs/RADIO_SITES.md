# Fixed radio sites: base antenna and repeater (T31)

**Status (2026-10-18, T33):** data model, reach function and a read-only endpoint (T31) plus the link-quality
model applied on the live voice path (T33, §8): a listener's relayed audio picks up static and dropouts according
to its link to the speaker. §6 records the user's decisions and what is still open.

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

## 6. Decisions (user, 2026-10-18) and what is still open

**Decided**

1. **Antenna heights:** base antenna 30 ft AGL at KSEE, confirmed. The repeater stays at 40 ft AGL: a VORTAC site
   carries its own counterpoise and tower, and 40 ft is a conservative figure for a CAP repeater antenna on such a
   site; a better basis would be the real R-site survey, which the wing holds. Geometry only; no ERP or feedline.
2. **Out of range never hard-blocks.** A transmission degrades gradually: static and dropouts that get worse with
   distance, terrain obstruction and how close the station is to the radio horizon (the signal margin, §8), and
   becomes unusable only far beyond the horizon or deep in a terrain shadow.
3. **Ground teams talk to aircraft directly.** Air-to-ground is a direct line-of-sight link with the same
   degradation; the repeater is for the aircraft/ground-to-base path. Ground teams report no position today, so
   their links are nominal (good) until they do.
4. **Repeaters have nothing to do with DF.** The direction finder listens to the beacon band; the propagation
   engine (`PI_capvsar_df.py`) and the console's DF stub never see the sites or the link model
   (`tests/test_radio_link.py::DirectionFindingIsSeparate` pins that).

**Still open**

5. **Second repeater / talk-around:** both pairs (Palomar on the secondary pair) and the simplex talk-around
   channel the TDFM-136B feature list mentions.
6. **Symmetry:** base-to-aircraft uses the same path and margin as aircraft-to-base; the base's higher power is
   not modelled.
7. **Ground-team positions:** a way for a team to report where it is (phone GPS on the radio page, or a typed
   grid), which would make the air-ground and ground-base links real rather than nominal.
8. **Screens:** the `link` message is sent to each listening face but the pages do not show it yet (UI work).

## 8. Link quality: static and dropouts by signal margin (T33)

`services/exercise/app/radio_link.py`, applied in `radio.py` `MumbleRadio.deliver_audio` to the tactical-net
(`main`) face only, per listener and per speaker, behind the sortie effect `radio_reach` (default on in
`DEFAULT_EFFECTS`; set it false with the other injected effects to turn the model off) and the 0..1 hook
`radio_conditions` (weather or atmospherics; 1.0 is a clear day; no weather physics is modelled).

* **Signal margin 0..1 per path** = horizon score × terrain score × conditions. Horizon: 1 inside 60 % of the
  two-ended radio-horizon distance, falling smoothly to 0 at 115 % of it. Terrain: the engine's diffraction-loss
  shape (0 dB above a 1,000 ft Fresnel-ish graze zone, 20 dB grazing, 40 dB at 500 ft of obstruction) mapped to
  1 − loss/40 dB; unchecked terrain (the console has none) counts as clear. For a station-to-base link the path is
  the better of direct and via a repeater (the repeater path's margin is the weaker of its two legs); air-to-air
  and air-to-ground are direct.
* **Impairment, monotonic and gradual in the margin m:** static level (1−m)^1.5; speech level 0.35 + 0.65 m;
  dropped fraction 0.9·((0.7−m)/0.7)^1.5 (none above m = 0.7); mean dropout length 0.06 + 0.54 (1−m) s; usable
  above m = 0.05. A seeded `DropoutGate` turns the rate into a reproducible on/off sequence per 20 ms frame.
* **Where it is applied:** the voice travels browser → websocket → console → Mumble, and back the same way as
  20 ms PCM frames relayed per listening face. `deliver_audio` looks up the listener (its roster role: base staff
  sit at the base antenna; aircraft come from `/api/positions` telemetry matched by callsign; ground teams and
  anything without a position are nominal) and the speaker (another browser radio's role and callsign, or the
  Mumble user name), computes the link every 2 s, and processes each relayed frame: a dropped frame becomes
  silence, the others get seeded static mixed in at the computed level with the speech lowered. A clear link
  passes frames untouched at no cost. The face is sent one `{"type": "link", speaker, path, via, margin,
  quality, heard}` message when its link to a speaker changes, for the radio page to show.
* **Not modelled:** the airband face (a local base radio), the base's own transmit power, ground-team positions,
  weather (only the hook), and the DF.

## 7. Tests

`tests/test_radio_link.py` (margin and impairment boundaries and monotonicity, seeded dropouts, frame processing,
routing including the gradual fall with distance and altitude, the DF separation) and `tests/test_radio_reach.py`
(the live path: a far, low aircraft heard at base with static and dropouts; an aircraft in the search block heard
clear; the effect switch and a missing scenario pass audio through; conditions degrade a clear link; ground teams
nominal). `tests/test_radio_sites.py`: pinned coordinates and sources, pair convention, site validation, JSON override,
the horizon rule equal to the engine's, an aircraft at 4,500 ft near Julian reaching the repeater while a low
aircraft behind a synthetic 7,000 ft ridge east of JLI does not, the repeater's fixed link to KSEE, routing
direct -> via repeater -> none, and the read-only route.
