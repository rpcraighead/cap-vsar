# CAP-VSAR website — copy deck

Final copy for every page. Headlines in sentence case unless shown otherwise. `[VERIFY: …]` marks a claim the
repository does not prove; the builder must not remove the marker, only the owner can (see CLAIMS_AND_RISKS.md).
Button labels in **bold**. Captions start with a bold lead.

Every page footer carries the disclaimer in STYLE.md verbatim.

---

## Home

### 1. Hero
**Eyebrow:** VIRTUAL SEARCH AND RESCUE · FOR CIVIL AIR PATROL CREWS AND STAFF

**Headline:** Fly the SAREX before you fly the SAREX.

**Sub-headline:** CAP-VSAR runs a complete search and rescue exercise, a V-SAREX, on the simulator: a mission base with a staff,
a working radio net, aircraft with faithful replicas of the direction-finding gear, ground teams, and a practice beacon that misbehaves the way the real one does. Same seats, same incident, same mistakes — made on a Tuesday night instead of on the day. (T11: on phones the list between the colon and the full stop is hidden so the buttons stay above the fold.)

**Buttons:** **See a V-SAREX** · **How the training works**

**Under the buttons (T11):** Unofficial training tool built by CAP members. Not a CAP program.

**Mono caption (bottom-right of hero):** ESCON · 121.5 MHz · SIMULATED · NOT A REAL DISTRESS · NOT A NAVIGATION CHART

**Hero reel (T22, 2026-10-18):** slide 1 stays the animated map; slide 2 is the Mission Observer station panel (the `hero-panel` clip, pending from Codex; until it lands the slide shows the station still `df-becker-517.webp`, copied to `assets/video/hero-panel-poster.webp`, kept in the reel by `data-allow-still`); the existing clips follow in their existing order. Caption: **The Mission Observer’s station.** A training replica of the Becker SAR-DF 517 direction-finder head, the tactical radio, the audio panel and the display with the search pattern, as simulated. (While the clip is missing the reel appends "Still frame; the moving clip is not yet available." and shows its STILL FRAME badge; both disappear by themselves when the clip files exist.) Layout: the slide letterboxes like the other UI clips, with its bands in the panel's own background; on phones (≤ 600 px) the panel is pinned to the top 62 % of the slide box and the caption (0.85 rem) sits at the foot of the box, so at 390 px the caption clears the panel; at 360 px and narrower its first lines overlap the panel's bottom edge under the gradient until the still note goes.

### 2. The mission in one breath
**Eyebrow:** THE MISSION

**H2:** A whole SAR event, not a flight sim with a map.

**Lede:** An exercise director writes the incident once. Then the wing runs it: command, communications, air and
ground, each person in the seat they will hold on the real day.

Tiles (title — one sentence):
* **Mission base** — An Incident Commander, an Air Operations Branch Director and a Mission Staff Assistant work a
  live map with aircraft tracks, plotted bearings and tasking.
* **Communications** — A Mission Radio Operator runs the tactical net on a base radio with a real push-to-talk,
  a time-out timer and a CAP Form 110 log that fills itself in.
* **Aircraft** — Crews fly a Cessna 182T with the G1000, a Garmin audio panel, a Technisonic tactical radio and a
  Becker or RHOTHETA direction finder on a Mission Observer station.
* **Ground teams** — An Urban Direction Finding (UDF) team joins the net from a phone, takes the bearing cut from base, and homes on the beacon.
* **The beacon** — A simulated ELT on 121.5, 243 or 406 MHz that hides behind ridges, drops out in a bank and
  swings the needle as you pass overhead.
* **AI Mission Pilot** — When no pilot can sit at the console, the airplane still flies the pattern, so the observer, the base and the ground team can still train.

### 3. A V-SAREX, seat by seat
**Eyebrow:** INCIDENT COMMAND, SIMULATED

**H2:** Every seat on the org chart has a screen.

**Lede:** The exercise follows the incident structure CAP staff already know. A base-staff tabletop is a good
drill; a base-staff tabletop with live tracks, a working net and bearings that are wrong in realistic ways is a
rehearsal.

Node "what they do" sentences (one per box; the builder uses these in the chart):
* **Incident Commander (IC):** Runs the base from the Mission Base screen: reads the alert, tasks sorties, watches
  the cuts come in, and sends the ground team to the intersection.
* **Air Operations Branch Director (AOBD):** Builds the search patterns from the Incident Command System (ICS) 204 assignment in the Flight Planner,
  exports them to the G1000, then watches tracks and bearing cuts on the base map.
* **Mission Radio Operator (MRO 1 and 2):** Net control on the tactical VHF-FM net; radio checks, 30-minute
  ops-normal calls, bearing reports, all logged on the CAP Form 110. MRO 2 keeps the airband watch.
* **Mission Staff Assistant (MSA):** Keeps the status board honest: who has joined, who is on the net, where the
  cuts cross.
* **Mission Pilot (MP):** Flies the pattern in the Cessna 182T, works a role-played SoCal Approach for the altitude block, or
  supervises the AI Mission Pilot and the GFC 700.
* **Mission Observer (MO):** Runs the right seat: the audio panel, the tactical radio and the direction finder.
  Calls the bearings, recognises the cone of confusion, reports ops-normal.
* **Mission Scanner (MS):** Eyes outside, chart in hand, a second opinion on the bearing geometry.
* **Ground Team / UDF:** Joins the net from the truck, copies the intersection from base, drives the corridor and
  homes with the handheld DF to the find.
* **Exercise Director (ED):** Writes the scenario, places the beacon, injects the signal effects mid-sortie, and
  reveals the truth at debrief.
* **Skills Evaluator (SET-qualified):** Watches, then uses the Debrief screen's scores (closest approach, bearing error, first good cut, track efficiency) to sign off log discipline and Specialty Qualification Training Record (SQTR) tasks by hand.

**Caption under the chart (T21: moved to close §4, directly under the chart):** Seats come from the exercise roster. Base staff need a laptop or tablet; the Mission
Observer needs a second screen; the Mission Pilot needs the simulator. Everyone needs a headset.

**Button:** **Who needs what hardware**

### 4. What the seats look like (T19/T21, 2026-10-18; was "See it in action")
Sits directly under the org chart (T21): nothing between the diagram and this section; the org chart's hardware note and
"Who needs what hardware" button now close this section instead.

**Eyebrow:** WHAT CREWS SEE

**H2:** What the seats look like.

**Intro:** The Mission Observer's instrument panel and seven pages from the exercise system, as crews see them in the
simulator, with sample exercise data: a practice scenario at the ESCON fix, the practice callsigns CAP 423 and CAP 415, and
seats filled by roles rather than people.

Tiles (a 3 / 2 / 1-column grid; each a click-to-zoom picture, a bold title, one sentence). The featured tile comes first and
is two columns wide on desktop (its picture box 40:19, the panel cropped at its own blank lower strip), full width below 900 px; the seven pages follow in the order people use them:
0. `df-becker-517.webp` (featured, T21) — **The Mission Observer's direction finder.** A training replica of the Becker
   SAR-DF 517 head, drawn from the manual, on the Mission Observer's station beside the audio panel, the tactical radio and
   the G1000 display: the needle points toward the practice beacon, the signal bar climbs as the aircraft closes, and the
   observer calls the bearing to base. *The panel is the project's own artwork; the map display is a simulator screen.*
1. `planner-escon-square.webp` — **Flight Planner, search pattern.** The Air Operations Branch Director builds the sortie
   here: the route, the expanding-square search pattern and the navigation log on the sectional chart, for the simulator only.
2. `exercise-portal.webp` — **Home portal after sign-in.** Everyone lands here after signing in; the role on the badge
   decides which stations are listed, and the Exercise Director sees all six.
3. `exercise-ready-room.webp` — **Ready Room station check.** Before launch, staff see who has joined, who is on the net,
   and whose headset and direction-finder head are checked, seat by seat.
4. `mission-base-lops.webp` — **Mission Base plot.** Base staff log each bearing the crews report; the plot draws the
   line of position from where the aircraft was when it called, and the true beacon stays hidden until debrief.
5. `comms-mission-radio.webp` — **Base Radio station.** The Mission Radio Operator's station: choose the radio, pick the
   net, check the headset and join; the push-to-talk and the Form 110 log sit below the fold.
6. `exercise-console.webp` — **Exercise Director's console.** The Exercise Director runs the scenario, switches signal
   effects on and off mid-sortie, and sees what each cockpit's needle is seeing, which nobody else sees until debrief.
7. `debrief-scoring.webp` — **Debrief scoring cards.** After the sortie, each aircraft is scored on closest approach,
   logged bearing error, first good cut and track efficiency, here from sample exercise data.

Closing the section (moved from the org chart, T21): **Seats come from the exercise roster.** Base staff need a laptop or
tablet; the Mission Observer needs a second screen; the Mission Pilot needs the simulator. Everyone needs a headset. Button:
"Who needs what hardware" → `how-its-built.html#stations`.

Dropped from the old strip: the older dual-radio Base Radio capture (superseded by the current page, tile 5; it stays
on the Comms page). The Becker 517 station panel, dropped in T19, is back as the featured tile (T21, owner request).
The sign-in and boarding-pass screens are not shown: owner decision (CLAIMS_AND_RISKS.md §3 item 5).

### 5. Why train this way
**Eyebrow:** THE TRAINING CASE

**H2:** The cockpit is a poor classroom.

**Body (two paragraphs):**
There is a gap between familiarization and preparation and the real flight, and crews fall into it. The first time a new Mission
Observer sees the needle swing through a cone of confusion should not be at 1,000 feet over real terrain with a
pilot waiting for a heading. The same is true for the pilot learning to fly a pattern while the observer works the
radio, and for the base learning to keep three ops-normal clocks straight.

CAP-VSAR puts that first time on a desk, with the same gear and the same net, where a mistake costs nothing and
can be repeated until it is gone. It is also the refresher that actually happens: when weather, staff, money or an
airplane are short, the exercise still runs.

**Pictures (T14, 2026-10-18; replaces the inline three-icon diagram):** three 16:9 pictures in stage order, three across on
desktop and stacked on phones, each with a caption, inside the paper panel:
1. `assets/svg/training-classroom.svg` — **1 · Familiarization and preparation.** Crews learn the roles, the radios and the charts in the classroom. *Illustration.*
2. `assets/svg/training-sim-room.svg` — **2 · V-SAREX.** The same crews work an incident from simulator seats, laptops and tablets, with the exercise console on the big screen. *Illustration.*
3. `assets/img/training-flight.webp` — **3 · Flight.** A Civil Air Patrol Cessna 182T flying in the simulator. *Simulator frame.*

Under the three: **From the classroom to the flight.** Pictures 1 and 2 are illustrations of the kind of room and activity, not
photographs of real crews or a real event; picture 3 is a frame from the simulator, not real-world footage. (Real photos of
identifiable people would need consent and CAP public-affairs approval.) Alt text describes what each picture shows and says
"Not a photograph" for the two illustrations. "V-SAREX" is not expanded anywhere in the plan; the hero sub-headline defines it
by apposition ("a complete search and rescue exercise, a V-SAREX"), so the caption keeps the term as is.

**H3 over the cards:** Four laws of learning, one exercise.

Cards (the FAA Aviation Instructor's Handbook lists them; these are the four this program leans on):
* **Readiness** — People learn best when they are ready to learn. A crew that has just been assigned to next
  month's SAREX wants to practise now. The V-SAREX gives them their actual sorties two weeks out, not a generic
  lesson.
* **Primacy** — What is learned first is learned best, right or wrong. A new observer's first cone of confusion
  happens on the simulator, where the first impression can be the correct one: "that swing means I am overhead",
  not "the DF is broken".
* **Exercise** — Skills that are repeated are retained. Three evenings before the live day, the crews drill the
  parts that bite: COM3 MIC on the audio panel, 406.025 not 406.037 on the DF head, the 30-minute ops-normal
  call, the bearing report in the right words.
* **Intensity** — A vivid, realistic experience teaches more than a routine one. A bearing that lies because of a
  ridge, a signal that drops out in a bank, a base that catches the bad cut before the crew does: that is a lesson
  nobody forgets, and nobody had to launch an airplane to learn it.

### 6. What it is not
**Callout title:** Straight talk.

CAP-VSAR is an unofficial project built by CAP members for training. It is not a CAP program and nothing here is
endorsed by Civil Air Patrol. It is a simulator: the propagation, the beacon decodes and the performance tables are
tuned to be instructive, not to plan or run a real search. The AI Mission Pilot flies a simulated airplane and has
never flown a real one. What is proven and what is still being tested is listed on the AI Pilot page.

### 7. Get started
**H2:** Run one.

**Body:** If your squadron or wing wants to rehearse an exercise on CAP-VSAR, start with the exercise guide, then
talk to us about a date.

**Buttons:** **Read the exercise guide** · **Ask about a V-SAREX** `[VERIFY: contact address]` · **Source on
GitHub** `[VERIFY: public URL]`

T11 (until those exist): **What each seat needs** (→ How It's Built §stations) · **See the radios and the net** (→ Comms), with the sentence "A contact address for the project will be added here before the site goes public."

---

## Comms

**Eyebrow:** COMMUNICATIONS

**H1:** Radios that behave like radios.

**Lede:** Exercises fall apart on the radio: the wrong mic selected, a repeater nobody can hit, a report in the
wrong words. The simulator gives every seat a radio in front of them and a net that behaves like a net.

### In the aircraft
On the Mission Observer station sit a Technisonic TDFM-136B tactical radio and a Garmin GMA 1347 audio panel,
drawn from the manufacturers' manuals and wired to the simulator.

The audio panel carries the trap every new observer falls into: pressing the top **COM3** button lets you hear
Mission Base; to talk you must press **COM3 MIC**. Most "the FM radio isn't transmitting" calls we have heard in training come down to this. The panel also has the intercom isolation the pilot uses while working SoCal Approach on COM1, and the
clearance recorder that replays the last call you missed.

The TDFM-136B covers 136–174 MHz in analog FM and P25, with CAP channels programmed and a guard receiver that keeps
listening to AIRGUARD in the background while you work the main channel.

**Captions:** **TDFM-136B.** Channel 1 on the command net, guard on the second line, the keypad and toggles where
the real ones are. · **GMA 1347.** COM1, COM2, COM3 and the MIC row; pressing the wrong one is the lesson.

### At Mission Base
The Base Radio page is the MRO's station: a Motorola APX-style VHF-FM control head on the tactical net, an
Icom-style airband face beside it, push-to-talk on the touchscreen or the spacebar, a monitor button for weak
signals, and a 60-second time-out that unkeys a stuck mic to protect the net.

Below it the CAP Form 110 fills itself in: Zulu time, station, channel, message. Quick reports for radio checks and
ops-normal, and an export for the Incident Commander.

### Ground teams
An Urban Direction Finding (UDF) team joins the same net from a phone in the truck. Air-to-ground is direct, line of sight. On the model the team reaches base direct to the Gillespie Field antenna or through the repeater, like the aircraft; because the phone does not yet report its position, the console treats a ground team's link as good.

### How reach is simulated
Where the fixed equipment stands decides who can hear whom. For the sample exercise the Mission Base antenna is placed at Gillespie Field, 30 feet up on the valley floor, and a repeater is placed on the Julian VORTAC site at 5,560 feet, on the wing's assigned repeater pair (the frequencies are not published; the console carries them). Those are exercise choices, not a survey of real CAP sites; other exercises can put them elsewhere, Palomar for example.

A station reaches a site when it is inside the radio horizon for both antenna heights and the terrain between them
does not block the path. The simulator does not cut you off when you drift out of range. It gets worse the way a
real net does: the further you are from the base antenna, the lower you are, or the more terrain is in the way,
the more static and dropouts you hear, until the net is unusable. An aircraft at 4,500 feet near Julian is heard
clearly through the repeater; a low aircraft in the canyons east of Julian may reach neither.

The Exercise Director can switch the effect off, or dial in a worse day.

**Caption (C1):** **Three paths.** Direct to the base antenna, via the mountain-top repeater, or blocked by the ridge. (Diagram label: "REPEATER PAIR · NOT PUBLISHED"; never print the frequencies.)

### The voice net
One mission net, several channels: a briefing room, Mission Base, Mission Net PRIMARY and ALTERNATE, an intercom
per aircraft, and an Instructor–SET channel (SET: Skills Evaluator Training, the evaluators' qualification) for the evaluators to talk without being heard.

### Honest limits
The base's transmit power is not modelled (the same path works both ways). Ground teams do not yet report where
they are, so their links are assumed good. On the live voice net the reach is computed from the radio horizon
today; the terrain check is in the model and the tests, but the console does not yet have terrain data of its own
to apply it as you talk. The airband face is a local radio with no propagation model of its own.

**Button:** **DF & Beacons →**

---

## DF & Beacons

**Eyebrow:** DIRECTION FINDING

**H1:** The beacon lies to you a little, all the time.

**Lede:** A ridge between you and the ELT, the wrong wing down in a turn, a signal that exists for less than half a
second every fifty seconds. Teaching a Mission Observer to read through that is most of the job, so the simulated
receiver had to be wrong in the same ways the real one is wrong.

### The two heads
CAP 423 carries a Becker SAR-DF 517; CAP 415 carries the RHOTHETA RT-600, the newer of the two heads. Both are drawn
from the manufacturers' manuals, button for button, and both read the same simulated signal.

| | Becker SAR-DF 517 | RHOTHETA RT-600 |
|---|---|---|
| 121.5 / 243.0 homing | Bearing pointer and signal strength, 3 kHz DF tone | Bearing on a compass rose, dual-watch scan |
| 406 MHz | Emergency mode: one channel, 406.025. Training mode: tunable 400–410 | All 19 COSPAS-SARSAT channels in selectable groups |
| After a turn | CLR clears the bearing averaging | CLR resets the filter; a spread bar shows quality |
| Overhead | STORE silences the DF tone so you hear the raw warble peak and null; TIMEHOLD (edit menu) holds the last bearing between 406 bursts | Holds the decoded 406 bearing between bursts |
| Antenna | TOP / BOTTOM must match the airframe; wrong setting mirrors left and right | Wing blanking in a bank is an exercise effect applied to both heads; see "How the signal travels" |

**Captions:** **Becker SAR-DF 517.** The older of the two heads: a bearing pointer and a signal bar. · **RHOTHETA RT-600.** The one that
decodes the 406 burst.

### How the signal travels
The propagation model lives inside X-Plane, because that is the only place the real terrain is. Each update the
program running inside X-Plane samples the straight path between the aircraft and the beacon, probes the simulator's own terrain at each
point, and asks whether the ground pokes above the ray. Then it adds up what a real receiver would lose:

* the radio horizon, from both the aircraft's height and the beacon's;
* free-space loss for the band, with a calibrated link budget;
* terrain: 20 dB when the path grazes a ridge, up to 40 dB in deep shadow;
* the airframe: in a bank toward the beacon, the lowered wing on the beacon's side sits between a belly antenna and the signal and can shade it by up to 24 dB — the wing null CAP crews are taught to fly;
* the 406 beacon's burst: 440 milliseconds every 50 seconds, and nothing in between;
* the cone of confusion directly above the beacon, where the needle has nothing to point at;
* multipath: an intermittent false bearing the director can switch on, offset a fixed amount (40° by default) to stand in for a reflection off a ridge.

What is left decides the needle, the signal bar and the audio the observer hears.

**Caption (D1):** **Asking the sim what is in the way.** The ridge that shadows the beacon is the one you are
flying next to.

### Techniques and traps
* **Fly the null.** Bank toward the suspected side. With a belly antenna the lowered wing now sits between the antenna and the beacon, the signal drops, and the drop tells you which side the beacon is on.
* **Passing overhead.** Inside the cone the needle swings and reverses. That is not a failure. Press STORE, listen
  for the warble peak and null, call "overhead the beacon", and start the expanding square from that point.
* **Reflections.** A bearing 40° off the others is the exercise's stand-in for a reflection off the Ramona ridge. The cockpit rarely sees it; the
  base does, because the plotted cut disagrees with the three before it. The base asks the crew to re-fly the leg.
* **TOP or BOTTOM.** Set the antenna mounting to match the airframe or every left and right will be mirrored.
* **406.025, not 406.037.** The Becker in emergency mode listens to one channel. Tune the exercise channel in
  training mode, or let the RT-600 scan.

**Caption (D2):** **Wing null, cone of confusion, reflection.** Three ways a correct receiver gives a wrong
answer.

### Exercise control
The Exercise Director places the beacon on the chart, picks the band, writes the alert the base will get, and can
switch each effect on or off mid-sortie: radio horizon, 406 burst cadence, cone of confusion, multipath, wing
blanking. The console shows the director what each cockpit's needle is seeing. Nobody else sees the true position
until the director reveals it for debrief.

**Captions:** **Exercise Console.** Scenario, effects, truth. · **Debrief.** The needle's error over time, with
every logged bearing marked against the 10° good-cut band.

### What the DF does not see
The direction finder listens to the beacon band. The tactical net, its repeater and the radio-reach model are a
separate thing; repeaters have nothing to do with DF, in the simulator or in the airplane.

**Buttons:** **Comms →** · **AI Pilot →**

---

## ForeFlight

**Eyebrow:** ELECTRONIC FLIGHT BAG

**H1:** The same tablet, the same taps.

**Lede:** A crew that briefs, files and flies with ForeFlight should rehearse with ForeFlight. Connected to the
squadron's private link, the simulator feeds its position to the iPad, and the electronic flight bag shows the
simulated airplane where the simulator has it.

### How it connects
Crews join the exercise over the squadron's WireGuard link. With the iPad on that link, the simulator's position
output reaches ForeFlight the way a portable GPS would, and the ownship symbol flies the pattern on the chart in
the crew's hands. `[VERIFY: no code or configuration in the repository implements or documents the simulator →
ForeFlight position feed; WireGuard is on the router (infra/ROUTER.md). Prove the feed on the LAN and over the
link, then write the steps.]`

### Why it matters
Consistency is the training. The pattern the Air Operations Branch Director (AOBD) built in the Flight Planner, the one on the G1000, and the one
on the iPad are the same assignment; the crew's hands do what they do in the real airplane.

### Setting it up
`[VERIFY: steps depend on the proven feed]` 1. Put the iPad on the squadron link. 2. Point the simulator's
position output at the iPad. 3. In ForeFlight, add the device and confirm the ownship moves.

**Callout:** The Flight Planner's own airport data is not FAA data and is not for real navigation. Brief every
real flight with official sources.

**Caption (F1):** **Sim to tablet.** The position goes out; the chart comes along for the ride.

---

## CalTopo (roadmap)

**Eyebrow:** ROADMAP

**H1:** Base staff on the map they already use.

**Lede:** Some wings work real searches on CalTopo. The plan is for the exercise to meet them there: assignments
pushed from the exercise, live aircraft tracks on the CalTopo map, crew marks coming back.

### What is designed
(H2, T11: "Staff work the exercise on their own map; the beacon stays hidden.")

The integration plan draws one hard line: the relay that talks to CalTopo can never see the hidden beacon. Each
sortie gets its own relay, the pattern polygon pushed to CalTopo is the same geometry the crew flies, and a
feature drawn by staff in CalTopo comes back attributed to the seat that drew it.

### Where it stands
(H2, T11: "Nothing is built yet." The chip in the title block already says "Roadmap · plan only".)

No code, accounts or CalTopo maps exist yet. It waits on a wing that uses CalTopo for exercises and
wants to help test it.

**Button:** **Tell us your wing uses CalTopo** `[VERIFY: contact]`

---

## AI Pilot

**Eyebrow:** THE AI MISSION PILOT

**H1:** When no pilot can sit at the console, the airplane still flies.

**Lede:** An observer wants to practise the DF on a weeknight. A base wants to run the whole exercise with every
aircraft airborne. The AI Mission Pilot flies the search pattern, hands the airplane to the autopilot for the
cruise, and takes it back for the approach, so the rest of the crew can train.

### How it works, in plain terms
Three layers, kept deliberately apart.

* **Judgment.** Tasks are chosen and results read above the control loop — "fly the ESCON square at 4,500", "that landing was long of the aim point" — today by the test team and its AI coding assistants working offline, by design never by a model inside the loop. The flights on this page were started by scripts that name the task; a language model is not in the airplane.
* **Stick and rudder.** A small, predictable controller does the flying: same inputs, same outputs, every time. It talks to the simulator through a
  bounded bridge, frame by frame fifty times a second, on a control lease that expires in under a fifth of a
  second, and the simulator pauses the moment the controller goes quiet. An independent observer scores every trial from the recorded trace, not from the controller's own
  opinion.
* **Workload and safety.** The Garmin GFC 700 flies the cruise and climb legs the way a human crew would use it,
  with a hand-over in both directions (flown in vertical-speed mode; the flight level change (FLC) procedure crews brief is not yet validated) and a terrain guard that climbs away from the Ramona ridge before the airplane gets there.

**Caption (A1):** **No model in the loop.** Judgment above, a controller in the middle, the autopilot below.

### Taught by a flight instructor
The controller was corrected the way a certificated flight instructor (CFI) corrects a student, by one sitting at the simulator and watching it fly. Pitch controls airspeed, power controls the glidepath; if you are low and slow, lower the nose
*and* add power. Make the flare gradual and keep raising the nose in the last two seconds. In a crosswind, aileron
into the wind and rudder to keep the nose straight, through touchdown and into the rollout. And look at the
*usable* runway: the instructor caught a scorer that called a landing good when the wheels touched before the
displaced threshold, and the acceptance test changed. `[VERIFY: the owner's name and credentials are to be
confirmed before publishing "flight instructor and squadron commander"]`

### Operational concepts
The AI is written to hand-fly the parts that need hands: taxi and line-up, the takeoff roll and initial climb, pattern entry, the search pattern itself, and the approach and landing. Of these, the search pattern, the autopilot hand-over and the approach and landing have been flown and scored (table below). The GFC 700 takes the rest. Every aircraft is a data profile, not a code branch: the C172SP and the C182T fly the same program with their own speeds and flap gates, and the C182T carries a measured performance table flown with the aircraft's own autopilot.

### Repeatable, flown, and still being tested
Legend above the table: *Repeatable*: flown and independently scored more than once. *Flown*: done at least once and scored. *Not yet*: owed. Nothing here is a validated tuning; both profiles carry `tuning_validated = false`.
| | Status |
|---|---|
| Cessna 172SP: repeated flight cycles, independent scoring, terminal pause every time | Repeatable · ten-and-ten campaign; tuning not yet validated |
| 172SP crosswind landings at Montgomery, 12–15 kt | Flown · scored; the formal 10/10 gate was not completed |
| 172SP full sortie Gillespie → Mission Bay departure → vectors → Montgomery ILS 28R | Flown · attended |
| ESCON expanding square, 9 waypoints, altitude within 25 ft | Repeatable · on both aircraft |
| AI → GFC 700 → AI hand-over with the terrain guard at the Ramona ridge | Flown · PASS on both aircraft in vertical-speed mode; the FLC hand-over crews brief is not yet validated, and the guard's turn-back has not been flown |
| Cessna 182T takeoff and landing | Flown · the landing passed its scorer but touched down 63 m past the aim point, still long |
| Tuning validated end to end | **not yet** for either aircraft: a full scored validation sortie is still owed |
| A real airplane | Never · not the goal |

### The F-4 and the carrier
`[VERIFY: the owner says the same approach flew carrier operations in an F-4 Phantom. The repository holds an
"F4 Test Pilot Development" aircraft and a note that the F-4 program is paused, but no trace, log, video or report
of a carrier launch or arrested landing. Do not publish this section without a clip or a scored trace.]`

Published copy (T7, 2026-10-18; evidence in `~/Documents/Codex/f4-phantom`, see CLAIMS_AND_RISKS.md claim 22): heading "Arrestments from a Case I-style arrival, on the simulator." Alongside the Cessna work, the same ideas were pointed at something harder. A separate F-4 test program, built on the same principles — bounded, leased control; every flight's telemetry recorded and scored afterwards by an independent check — flies the Laminar F-4 Phantom II in X-Plane 12.4.3 through a Case I-style overhead arrival; the project calls the card experimental and the pattern timing does not yet match the briefed procedure. After some fifty development attempts, the last three control-law versions came aboard on 12 of 15 completed approaches, flown on a development copy with the tail hook extended to 50° (stock 40°); on the unmodified aircraft, one series of five gave 3 in 5. "Completed" excludes engage-ring waveoffs (12 in 22 and 3 in 6 counting them); earlier versions did much worse. It is not a CAP mission. It is evidence that the ideas carry to a harder airplane, and no more than that. The F-4 row sits in its own one-row table, not in the AI Mission Pilot table. Never write "Before the Cessna", "unchanged", "full Case I" or "proof".

**Buttons:** **Read the engineering notes** · **Watch the landing** `[VERIFY: video exists]`

---

## The Airplane

**Eyebrow:** CAP 487

**H1:** Building a Cessna 182T that barely existed.

**Lede:** CAP flies 182Ts. X-Plane 12 ships a Cessna 172SP with the G1000 and no 182T at all. So CAP 487 was
built.

### The recipe
The cockpit and systems come from the simulator's own C172SP G1000, read from the operator's licensed copy at
build time and never redistributed. The exterior is a pinned, GPL-licensed FlightGear C182 converted to X-Plane format. A build script supplies what makes it a 182T: the IO-540 at 230 horsepower, a three-blade constant-speed
propeller and a prop lever in the 3D cockpit, 87 gallons usable, the 182T's speeds, weights and limits, with
dimensions from the handbook and the type certificate. Every value in the aircraft file cites where it came from,
and a test pins it there.

**Caption (P1):** **Cockpit from one source, skin from another, numbers from the book.**

### The G1000 additions
The stock G1000 showed a 172's engine page: a tachometer and no manifold pressure, because the 172 has a
fixed-pitch prop. The 182's constant-speed prop needs manifold pressure (MP) and RPM, so the build selects them and the gauge appears.

The stock G1000 also had no idea what a search pattern was. An independent extension adds search and rescue pages to the G1000's multifunction display (MFD):
parallel track, creeping line, expanding square and grid, named waypoints, range rings, a DF bearing overlay,
export to the flight plan, and a guarded ACTIVATE that loads the pattern into the flight management system (FMS) only when pressed twice and
only when no AI pilot has control.

**Figure (T16, 2026-10-18):** the MFD search and rescue pages as simulator screens inside a generic drawn bezel, with view
links "Plan", "Pattern editor", "Fly view", "Native map with route" (ASSETS.md M1). Caption: **The search and rescue pages on
the multifunction display (MFD), as shown in the simulator.** The pattern is an illustrative demonstration. These are simulator
screens, taken with the airplane parked on the ramp (0 knots, no time-to-go), so the pattern sits next to the airport; the search
page is the extension's own pane beside the simulator's native map, and "Native map with route" shows that map after the pattern
was activated into the flight plan. The frame around the screen is a drawing, not any manufacturer's product. Alt text begins
"Simulator screen:" and describes what is visible. Footer trademark line extended for Garmin/Laminar.

### Measured, not assumed
The performance table in CAP 487's profile was flown, not copied: 35 throttle-and-climb points held by the
aircraft's own autopilot, checked against the handbook's cruise figures (214 hp at full throttle at the test
altitude against a rated 230). Handling cards and flight-test cards record the rest.

**Callout:** The built aircraft is for the operator's own use. The repository holds the recipe and nothing from
the simulator's or the donor's files.

---

## How It's Built

**Eyebrow:** HOW IT'S BUILT

**H1:** One instructor, three assistants, one changelog.

**Lede:** CAP-VSAR was built by three AI coding assistants working the same code, directed by a flight instructor and an AI orchestrator. `[OWNER DECISION: credentials/billet wording; "squadron commander" removed from the site in T7 until decided]` The interesting part is not the models. It is how they keep each
other honest.

### Three models, one truth
Claude Code and OpenAI Codex work inside the editor next to the project files; Gemini works in Google's
Antigravity. They cannot see inside each other, and left alone they would drift into three versions of the truth.
So none of them works from private notes. Every session reads the project changelog before touching anything and
corrects it in place before finishing, and every assistant quotes from one shared knowledge base instead of its
own memory.

The orchestrator is a small tool called AgentDeck: one planning session with a live task board, delegating work to
three worker terminals, each in its own copy of the repository. The human plans, approves, flies the simulator and
listens for the DF null on the correct wing.

**Caption (W1):** **The loop is the force multiplier.** Three workers that read each other's homework, and a
human who checks them against the real airplane.

### Dev, QA and test
Work moves in a rhythm. A read-only review first, with findings and evidence. Then fixes, each with a test that
fails before and passes after. Then a second model reviews the first model's work against the real runtime: that
is how a licensing mismatch and a crash-on-redraw in the Mission Observer panel were caught, by one assistant
checking another's. The full test suite runs on the project's own continuous-integration (CI) server on every push, and a script strips private material to build a public copy when one is published. `[VERIFY: current test totals at build;
whether the GitHub copy is live]`

### Working to their strengths
From the record: Gemini built the first Mission Observer panel; Claude reviewed it and fixed the defects it found,
and later wrote the exercise guide and the sign-in; Codex worked the DF propagation and flew the C182 on the
simulator. The instructor flew the airplane and said what was wrong.

### Stations and hardware
| Seat | Needs |
|---|---|
| Base staff: Incident Commander (IC), Air Operations Branch Director (AOBD), Mission Radio Operator (MRO), Mission Staff Assistant (MSA) | A laptop or tablet with a browser and a headset |
| Mission Observer | A second screen or tablet for the MO station (Air Manager) and a headset |
| Mission Pilot | X-Plane 12, a yoke and pedals, a headset; the CAP 487 package built locally |
| Ground team | A phone with a browser and a headset |
| Exercise Director (ED) / Skills Evaluator (SET) | A laptop with a browser |

**Button:** **Source on GitHub** `[VERIFY: URL]`
