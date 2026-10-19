# CAP-VSAR website — site map and page plans

Static HTML/CSS site. Audience: the owner's squadron and wing first, written so it can go public. Voice: plain CAP
ES training-material English. Every page: the same header/nav, the same footer with the "unofficial" disclaimer
(see STYLE.md), the same dark "ops room at night" theme with light "briefing paper" panels for long reading.

Companion files: `COPY.md` (the words), `ASSETS.md` (screenshots and illustration briefs), `STYLE.md` (tokens and
components), `CLAIMS_AND_RISKS.md` (what we can and cannot say).

## Navigation

| nav label | file | one-line purpose |
|---|---|---|
| Home | `index.html` | Why this exists, what a V-SAREX is, who sits where, the training case |
| Comms | `comms.html` | The simulated radios in the aircraft, on the ground and at base, and how reach is modelled |
| DF & Beacons | `df.html` | The direction finders, how the ELT signal travels, the traps and the techniques |
| ForeFlight | `foreflight.html` | Flying with the real cockpit workflow: the sim feeds ForeFlight its position |
| CalTopo | `caltopo.html` | Roadmap: base staff on the same map tool they use on a real mission |
| AI Pilot | `ai-pilot.html` | The AI Mission Pilot: how it flies, who taught it, what is proven |
| The Airplane | `airplane.html` | Building the CAP 182 and the G1000 additions |
| Flight Planner | `flight-planner.html` | The first AI-built app, now the Air Operations desk: search patterns, the .fms export, the console push |
| Hosting | `hosting.html` | One workstation runs the exercise; everyone else joins over Wi-Fi |
| How It's Built | `how-its-built.html` | Three AI assistants, one commander, one changelog |

Secondary links in the footer: "Read the exercise guide" (the PDF when published), "Source on GitHub"
(`[VERIFY: public URL and whether the sanitized copy is live]`), "Contact your squadron ES officer".

Top-right nav extra: a small cyan pill "Get started" that scrolls to Home §7. (T11: it was "V-SAREX" → org chart, which duplicated the hero's primary button; the term V-SAREX is now defined in the hero sub-headline.)

---

## Home (`index.html`)

### 1. Hero (full viewport)
* **Purpose:** make a CAP member stop and think "we could run our SAREX on that".
* **Visual:** the animated DF convergence (illustration H1, below). Behind the copy, a stylised sectional-style map
  of the Oceanside–Escondido–Julian corridor: muted sectional green/yellow landforms, a few chart-style labels
  (ESCON, KCRQ, JLI VOR, KSEE), range rings from the base antenna at Gillespie Field. Two aircraft symbols fly short
  legs of an expanding square; from each, a thin cyan bearing line sweeps and settles toward a safety-orange ELT dot
  near ESCON that pulses every 50 s (slow) with a brief brighter blink; where the two lines cross, a faint orange
  confidence ellipse fades in. A ground-team symbol creeps along the highway toward it. Loop ~24 s. Reduced motion:
  the final frame (lines converged, ellipse drawn), no pulse.
* **Copy:** headline, sub-headline, two buttons (COPY.md §Home 1).
* **CTA:** primary "See a V-SAREX" (scrolls to §3); secondary "How the training works" (scrolls to §5).
* **Logo:** the CAP-VSAR mark top-left (ASSETS.md L1), wordmark next to it.

### 2. The mission in one breath
* **Purpose:** state what the system is: a complete SAR event, staff, comms, aircraft, ground teams, simulated ELT,
  radios, DF, AI pilots when real pilots cannot sit at the console.
* **Layout:** six icon tiles in a row (base, comms, aircraft, ground team, ELT/DF, AI pilot), one sentence each.
* **Screenshots:** none; icons from the illustration set (I3).

### 3. A V-SAREX, seat by seat (the ICS org chart)
* **Purpose:** show that the exercise mirrors the real incident structure, and that a base-staff tabletop gets real
  context: live tracks, real radio traffic, bearings that are wrong in realistic ways.
* **Visual:** org chart (illustration H2). Boxes derived from the console's seat model
  (`services/exercise/app/access.py` SEATS and the roster the Setup page builds) and the guide §3:

  | box | seat id (role) | screen | what the simulated person does |
  |---|---|---|---|
  | Incident Commander (IC) | `ic` (base) | Mission Base `/base` (IC mode) | Runs the base: alert, tasking, the picture on the map; vectors the ground team to the LOP intersection |
  | Air Operations Branch Director (AOBD) | `aobd` (base) | Flight Planner `/planner/` then `/base` | Builds the search patterns from the ICS 204, exports them to the G1000, watches tracks and cuts |
  | Mission Radio Operator (MRO 1, MRO 2) | `mro` (base) | Base Radio `/radio` (and `/base`) | Net control on the tactical VHF-FM net, CAP Form 110 log, 30-minute ops-normal clock; MRO 2 watches airband |
  | Mission Staff Assistant | `base` (base) | `/base`, `/ready` | Status board, who has joined, bearing intersections |
  | Aircrew: Mission Pilot (MP) | `pilot` (aircrew) | X-Plane 12 cockpit, `/ready` | Flies the pattern or supervises the AI Mission Pilot and the GFC 700 |
  | Aircrew: Mission Observer (MO) | `observer` (aircrew) | Air Manager MO station (G1000 MFD, GMA 1347, Becker 517 / RT-600, TDFM-136B) | Works the audio panel, the DF head and the tactical radio; reports bearings and ops-normal |
  | Aircrew: Mission Scanner (MS) | `scanner` (aircrew) | second screen / tablet | Visual lookout, chart orientation, cross-checks the bearing geometry |
  | Ground Team / UDF (GTL + members) | `udf` (ground_team) | Base Radio `/radio` on a phone or tablet | Takes the LOP intersection from base, drives to it, homes with the handheld DF, reports the find |
  | Exercise Director (ED) | `director` (instructor) | Setup `/setup`, Exercise Console `/instructor` | Writes the scenario, places the beacon, injects signal effects, reveals truth at debrief |
  | Skills Evaluation Trainer (SET) / evaluator | `evaluator` (evaluator) | Debrief `/debrief` | Watches, then scores: CPA, bearing error, log discipline, SQTR tasks |
  | Simulator station | `station` (plugin) | the X-Plane plugin | Not a person: the aircraft's position and DF state feeding the base |

  Chart layout: IC on top; three branches below (Air Operations → aircraft cards with MP/MO/MS; Communications →
  MRO 1/2; Ground → UDF team); ED and SET in a dashed "exercise control" box to the right, connected to everything
  with a thin dotted line. Each box shows the seat's screen as a small chip ("/base", "Air Manager", "X-Plane").
  Hover/tap opens the "what they do" sentence.
* **Copy:** COPY.md §Home 3.
* **CTA:** "Who needs what hardware" → `how-its-built.html#stations` (or a small table here: base staff a laptop
  or tablet; MO a second screen; MP the sim).

### 4. What the seats look like (seats gallery; T19/T21, 2026-10-18, was "See it in action")
* **Purpose:** proof it is real: the pages crews and staff actually use, in the order they use them, directly under the
  org chart (T21: nothing between the diagram and this section; the chart's hardware note and "Who needs what hardware"
  button now close this section). Eyebrow WHAT CREWS SEE, H2 "What the seats look like.", one intro line that says the
  data is sample exercise data, then a 3 / 2 / 1-column grid: the Mission Observer's station panel (Becker SAR-DF 517)
  as a featured tile two columns wide on desktop, then seven tiles (screenshot with the lightbox, bold title, one
  sentence on who uses it and what it does). Section id `#screens`.
* **Screenshots (ASSETS.md):** S-PANEL-517 (featured; its G1000 display now carries a simulator capture), S-GUIDE-18
  (Flight Planner), S-GUIDE-10 → G1 (Home portal), S-GUIDE-11 (Ready Room), S-GUIDE-13 (Mission Base with two lines of
  position), S-GUIDE-14 (Base Radio), S-GUIDE-12 (Exercise Console), S-GUIDE-15 (Debrief). Sign-in and boarding pass
  withheld (owner decision). Copy: COPY.md §Home 4.

### 5. Why train this way (the training benefit)
* **Purpose:** the owner's argument: the gap between familiarization and preparation and the real flight; the cockpit is a poor
  classroom for pilots and for Mission Observers; recurrent refresher when weather, staff, money or airplanes are
  short.
* **Layout:** two short paragraphs, then four "learning law" cards (Readiness, Primacy, Exercise, Intensity), each
  with a concrete ES example from the exercise (COPY.md §Home 5). Light "briefing paper" panel.
* **Illustration:** I4 "from the classroom to the cockpit" strip (three panels: classroom slide → V-SAREX desk →
  real cockpit), muted, no text in the art.

### 6. What it is not (honesty box)
* **Purpose:** keep the trust of ES people: not an official CAP product, training only, not for real navigation or
  real DF; what is proven vs under development (one line each, link to AI Pilot page).
* **Copy:** COPY.md §Home 6.

### 7. Get started / contact
* **CTA:** "Ask about running a V-SAREX" (mailto to a role address, `[VERIFY: which address]`), "Read the exercise
  guide", "Source on GitHub". T11: until the address, the guide and the public source URL exist, the section carries a
  plain "a contact address will be added" sentence and two real buttons ("What each seat needs" → How It's Built
  §stations; "See the radios and the net" → Comms). The chain's last page (How It's Built) now ends here too.

---

## Comms (`comms.html`)

1. **Intro:** radios are where exercises fall apart; the sim gives everyone a radio in front of them, and a net that
   behaves like a net. Screenshot S-RADIO-DUAL.
2. **In the aircraft:** the Technisonic TDFM-136B tactical radio and the Garmin GMA 1347 audio panel on the Mission
   Observer station; the COM3 vs COM3 MIC trap; guard dual-watch; the clearance recorder. Screenshots
   S-PREVIEW-TDFM, S-PREVIEW-GMA (side by side), S-AM-PANEL (the whole Air Manager MO station).
3. **At Mission Base:** the APX 6500 / EFJohnson 5300 VHF-FM control heads and the Icom IC-A120 airband face on the
   Base Radio page; PTT on a tablet or the spacebar; the 60-second time-out; the CAP Form 110 log with quick
   reports and export. Screenshots S-RADIO-APX, S-RADIO-ICOM, S-RADIO-CONSOLE (log).
4. **Ground teams:** the same page on a phone; direct to aircraft, and to base direct or through the repeater.
5. **How reach is simulated:** the fixed sites (base antenna at Gillespie Field 30 ft AGL; repeater on the Julian VORTAC site, on the wing's repeater pair (frequencies never printed)); radio horizon from both antenna heights; terrain
   line-of-sight; signal margin → static and dropouts that get worse with distance, low altitude and terrain, never a
   hard cut-off; the Exercise Director can turn it off or dial in "conditions". Illustration C1 (signal paths:
   aircraft → base direct, aircraft → repeater → base, low aircraft blocked by the ridge east of Julian).
6. **The voice net:** one mission net with Briefing Room, Mission Base, Mission Net PRIMARY/ALTERNATE, aircraft
   intercoms and an Instructor–SET channel; a table of channels (from `services/exercise/app/mumble_channels.py`).
7. **Honest limits:** [VERIFY items from CLAIMS]: no base transmit-power model, ground teams report no position yet,
   the airband face is a local radio. CTA: "DF & Beacons →".

## DF & Beacons (`df.html`)

1. **Intro:** the beacon lies to you a little, all the time, in physically real ways; training the MO to read
   through it is the job. Screenshot S-PANEL-517 and S-PANEL-RT600.
2. **The two heads:** Becker SAR-DF 517 (CAP 423) and RHOTHETA RT-600 (CAP 415): what each shows, 121.5/243/406,
   the 19-channel COSPAS-SARSAT grid vs the 517's single emergency channel, STORE/CLR/TIMEHOLD. Spec table.
3. **How the signal travels:** the propagation engine lives inside X-Plane because that is the only place the real
   terrain is; it probes the scenery along the path (24–96 samples), applies the radio horizon, a per-band link
   budget, terrain diffraction loss (20 dB grazing to 40 dB in shadow), airframe shadowing by roll and pitch (up to
   24 dB wing null), the 406 burst (440 ms every 50 s), the cone of confusion above the beacon, and multipath off
   ridges. Illustration D1 (cutaway: aircraft, ridge, beacon, ray, the sampled points).
4. **Techniques and traps:** wing null; cone of confusion (passing overhead); reflections off the Ramona ridge and
   why base, not the cockpit, catches a bad cut; antenna TOP/BOTTOM mirror trap; 406.025 vs 406.037.
   Illustration D2 (three small diagrams: wing null, cone, reflection).
5. **Exercise control:** the Exercise Director's console: scenario, beacon placement, the five injected effects,
   live truth of what each DF head sees; reveal at debrief. Screenshot S-GUIDE-12 and S-GUIDE-15.
6. **What the DF does NOT see:** the tactical net and its repeater; the DF listens to the beacon only.
   CTA: "Comms →" and "AI Pilot →".

## ForeFlight (`foreflight.html`)

1. **Intro:** keep the cockpit workflow consistent: brief, file, fly the plan in ForeFlight while the sim flies.
2. **How it connects:** over the squadron's WireGuard link, the simulator feeds its GPS position to ForeFlight on the
   crew's iPad; the EFB shows the simulated aircraft where the sim has it. `[VERIFY: no code or config in this
   repository implements the X-Plane → ForeFlight position feed; the router hosts WireGuard (infra/ROUTER.md). Write
   the page as "how to set it up" only once the feed is proven on the LAN and over WireGuard.]`
3. **Why it matters for training:** same tablet, same taps, same chart; the Flight Planner's pattern export, the
   G1000 SAR pages and ForeFlight all showing the same assignment.
4. **Setup steps (short):** iPad on the WireGuard profile; X-Plane network output; ForeFlight Devices.
   Illustration F1 (iPad + sim + WireGuard tunnel diagram, no logos).
5. **Caution box:** the planner's own data is not FAA NASR; brief with official sources before any real flight.

## CalTopo (`caltopo.html`) — roadmap page, say so at the top

1. **The idea:** base staff work the search on the same CalTopo map they use on a real mission: assignments pushed
   from the exercise, live aircraft tracks, crew marks coming back.
2. **What is designed:** the integration plan (`docs/CALTOPO_INTEGRATION_PLAN.md`, 2026-10-11): one truth boundary
   so the relay can never see the beacon; per-sortie relay; the same pattern geometry the crew flies; attribution of
   staff-drawn features to a seat.
3. **Status:** plan only; no code, accounts or maps created. What it takes and what would unblock it.
4. **CTA:** "Tell us if your wing uses CalTopo" (contact).

## AI Pilot (`ai-pilot.html`)

1. **The idea:** a Mission Observer can train when no pilot can sit at the console; a base can run a full exercise
   with every aircraft flown. Screenshot S-GUIDE-18 (ESCON pattern) and a trace plot if available (ASSETS A-TRACE).
2. **How it works, in plain terms:** three layers. Judgement: a language model picks tasks and reads results, off the
   control loop. Stick and rudder: a small deterministic controller flies through a time-limited, bounded bridge
   (20 ms frames, an independent observer scoring every trial). Workload and safety: the GFC 700 flies the cruise
   and climb legs, with a clean hand-over both ways and a terrain guard. Illustration A1 (three-layer diagram).
3. **Taught by a flight instructor:** the owner sat as the instructor and corrected it the way a CFI corrects a
   student: pitch for airspeed, power for glidepath; a gradual flare; aileron into the wind through touchdown; the
   displaced-threshold catch that changed the acceptance test (from `docs/AI_PILOT_LANDING_VIDEO_NOTES.md`).
4. **Operational concepts:** AI hand-flying for taxi, takeoff, pattern entry, the search pattern and the landing;
   GFC 700 the rest of the time; the Ramona ridge terrain guard; fails-to-intent as the design direction.
5. **What is proven, what is not (the honesty table):** C172SP: ten-and-ten frozen campaign, crosswind landings,
   KSEE→KMYF sortie, ESCON pattern, owner hand-over; C182T: pattern, hand-over, takeoff and landing trials flown,
   toe-brake path live-confirmed; `tuning_validated` false for both until a full scored validation sortie; no real
   aircraft, ever.
6. **The F-4 Phantom and the carrier:** the owner's claim that the same approach flew carrier operations in an F-4.
   `[VERIFY: an "F4 Test Pilot Development" aircraft is installed and the IFR trial doc says "the F-4 program is
   paused", but no trace, log, video or document in the repository records a carrier launch or trap. Publish this
   section only with a clip or a scored trace; see CLAIMS_AND_RISKS.md.]` Illustration A2 (F-4 on final to a
   carrier, stylised, no markings) held until verified.
7. **CTA:** "Read the engineering notes" (docs links) and "Watch the landing" (`[VERIFY: video exists?]`).

## The Airplane (`airplane.html`)

1. **Why a 182:** CAP flies 182Ts; X-Plane 12 ships a C172SP G1000 and no 182T.
2. **How CAP 487 was built:** the Laminar C172SP G1000 cockpit and systems, a pinned GPL FlightGear C182 exterior
   converted to X-Plane, and a build script that supplies the IO-540 (230 hp), a three-blade constant-speed prop,
   87 gal usable, C182T limits and a prop lever in the 3D cockpit; dimensions from the POH and type certificate;
   every ACF value cites its source. Illustration P1 (exploded "recipe" diagram; no Laminar art).
3. **The G1000 additions:** the stock G1000 had no manifold-pressure gauge because the 172 has a fixed-pitch prop,
   and no SAR capability; the build selects MP/RPM engine indications, and an independent extension (`g1000-sar`)
   adds SAR mission pages: PS/CS/SS/GS patterns, named waypoints, range rings, a DF bearing overlay, FMS export and a
   guarded ACTIVATE. Screenshot: `[VERIFY: a G1000 SAR page screenshot shows Laminar's G1000 artwork; see
   CLAIMS_AND_RISKS.md before publishing one]`.
4. **Measured, not assumed:** the performance table flown with the aircraft's own autopilot (35 throttle/climb
   points), the calibration against POH figures, the handling cards. Small spec table.
5. **Licensing box:** the built aircraft is for the operator's own use and is never redistributed; the repository
   holds the recipe only.

## How It's Built (`how-its-built.html`)

1. **One commander, three assistants:** Claude Code, OpenAI Codex and Gemini in Antigravity, working the same
   tree, directed by a flight instructor and squadron commander and an AI orchestrator (AgentDeck: an orchestrator
   session with a task board delegating to three worker CLIs, each in its own git worktree).
2. **Keeping each other honest:** nobody works from private notes: one changelog every session reads first and
   corrects in place, one knowledge base (`ragd`) every assistant quotes from; one model reviews another's work
   against the real runtime (the Air Manager licence-tier and reentrancy catch); the human flies the sim and
   listens for the null on the correct wing. Illustration W1 (workflow diagram).
3. **Dev, QA and test:** read-only reviews before fixes; fixes with a test that fails first; per-commit test runs;
   the full suite in Gitea CI on every push; a sanitize script builds the public GitHub copy (history purge,
   address scrub, no third-party material). Numbers: `[VERIFY at build time: run_tests totals]`.
4. **Working to their strengths:** which model did what, from the record (panel build, DF propagation, console
   security, the guide) — only claims the changelog supports.
5. **Stations and hardware (#stations):** what each seat needs. CTA: "Source on GitHub".

---

## Illustration briefs (summary; full briefs with file names and tokens in ASSETS.md)

| id | where | subject |
|---|---|---|
| H1 | Home hero | animated DF convergence over a stylised sectional (SVG/CSS, built by the site builder) |
| H2 | Home §3 | ICS org chart (SVG from the table above) |
| I3 | Home §2 | six mission icons |
| I4 | Home §5 | classroom → V-SAREX desk → cockpit strip |
| C1 | Comms §5 | signal paths with base, repeater, ridge |
| D1 | DF §3 | propagation cutaway |
| D2 | DF §4 | wing null / cone / reflection trio |
| F1 | ForeFlight §4 | iPad, sim, tunnel |
| A1 | AI Pilot §2 | three-layer architecture |
| A2 | AI Pilot §6 | F-4 on final to the carrier (held) |
| P1 | Airplane §2 | C182 build recipe |
| W1 | How It's Built §2 | three assistants, one changelog |
| L1 | header | CAP-VSAR logo (GPT Sol) |
