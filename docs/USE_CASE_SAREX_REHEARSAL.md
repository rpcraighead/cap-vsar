# Use case: rehearsing a SAREX before flying it

**Status: use-case description. It is written against the system as it
exists on 2026-09-08; the four gaps that stand between this narrative and
running it exactly as written are listed at the end.**

A Search and Rescue Exercise (SAREX) is Civil Air Patrol's structured
training event: a mission base under an Incident Commander tasks aircrews
and ground teams against a scripted incident. This use case turns the SAREX
into the *second* time a crew flies its missions rather than the first. The
exercise director writes the incident once, and the wing runs it three
times on the simulator before the live day, so the SAREX reinforces skills
learned at home instead of introducing them.

## Setting

- **Live SAREX:** Saturday 17 October 2026, Ramona (KRNM). Three aircraft, a
  mission base with Incident Commander (IC), Air Operations Branch Director
  (AOBD) and Mission Radio Operator (MRO), and a Skills Evaluation Trainer
  (SET) signing off aircrew tasks.
- **Virtual sessions:** three evenings, two weeks out, one week out, and two
  days out. Everyone joins from home over WireGuard. Aircrews fly the
  Cessna 182T NAV III (CAP 487) in X-Plane 12 with the Mission Observer (MO)
  station in Air Manager; base staff use the exercise console and the base
  radio console on tablets; everyone talks on the Mumble mission net.

## The scripted incident

A rented C182 is overdue on a VFR flight from Carlsbad (KCRQ) to Thermal
(KTRM). Its registered 406 MHz ELT has produced a COSPAS-SARSAT composite
position in the mountains east of Julian. Three air tasks fall out of that,
built the way a real IC builds ICS 204s:

| Sortie | Task | Pattern | Purpose |
|---|---|---|---|
| A | Route search | Creeping line along the intended route, Julian to Borrego, 1 nm spacing | Visual search for the aircraft along its planned track |
| B | ELT search | Transit to the composite; home on the 406 burst and the 121.5 signal; expanding square from the point of station passage | A position good enough to hand to a ground team |
| C | Grid search | Parallel track of a 15-minute grid quadrant west of the composite, 1 nm spacing | Cover the case where the ELT position is wrong |

## Session 1 (T-14 days): mission base stands up

The exercise director opens the instructor console, creates the scenario —
beacon on a ridge, 406.025 MHz training frequency, initial effect set
*radio horizon* and *terrain masking* only — and starts the sortie. The
beacon's true position is withheld from every other view.

The AOBD opens the flight planner and builds the three patterns from the
ICS 204s: the creeping line, the expanding square at the composite datum,
and the parallel track filling the grid quadrant. Each exports as an X-Plane
`.fms` the crews load into the G1000, and each is pushed to the exercise
console so the base map shows the assigned areas. The terrain profile on the
route search flags a segment with poor clearance; the leg is re-drawn 500 ft
higher — the correction a real briefing would have to make, made on a
Tuesday night.

The MRO opens the base radio console on a tablet, joins the mission net and
works the channel plan: Mission Net Primary for position reports, Alternate
for DF traffic. The three MOs sit at their MO stations — G1000 MFD, GMA
1347, Becker SAR-DF 517 or RHOTHETA RT-600, TDFM-136B — and drill the parts
that bite people on the real day:

- GMA 1347 COM3 MIC selection (the trap in Handbook §3.2)
- TDFM-136B channel entry and the mission channel plan
- DF head power-up, squelch, scan mode
- Tuning 406.025 MHz (training) rather than 406.037 MHz

The MRO runs radio checks with each aircraft, and the first 30-minute
ops-normal cycle is practised before anyone "leaves the ramp". Nothing is
flown. The point of Session 1 is that the mission base and every seat's
equipment are familiar before the mission starts.

## Session 2 (T-7 days): the full mission

Same crews, same seats, same base staff. The IC briefs on Mumble from the
ICS 204s; the crews already have the `.fms` files loaded.

**Sortie A** flies the creeping line at pattern altitude. The MO calls "in
grid" and each leg turn; the MRO logs each call in the Form 110. The scanner
never finds an aircraft — there isn't one — but the crew learns the rhythm
of leg calls, and the base learns to keep three aircraft's ops-normal clocks
straight.

**Sortie B** climbs toward the composite. On the DF head the 406 burst shows
as a bearing that appears every 50 s and holds between bursts. The MO
reports "CAP 501, bearing 085 true from present position"; the MRO relays it
to the AOBD, who plots it on the base map. Twenty minutes in, the director
injects *cone of confusion*: the bearing swings wildly as the aircraft
passes near the beacon. The MO first reports the swinging bearing as real,
then recognises the symptom, calls "passing overhead", and starts an
expanding square from that point. The director adds *multipath*: a false
reciprocal off a ridge. The MO takes one bad bearing; the AOBD's plotted cut
disagrees with the previous three; the base — not the cockpit — catches it
and asks the crew to re-fly the leg. That exchange, base staff
cross-checking the aircraft's bearings, is what a SAREX is for, and it has
now happened once before the live day.

**Sortie C** flies the parallel track. The director injects *wing blanking*
when the aircraft banks toward the beacon on a turn: the signal drops out
on one wing, and the crew learns that a null in a turn is not a lost signal.

When Sortie A's route search comes up empty, the IC retasks it onto a second
grid through the MRO, with the new assignment pushed from the flight planner
mid-flight.

**Debrief.** The director stops the sortie and reveals the beacon. The
debrief console shows each aircraft's track against truth: closest point of
approach, track efficiency, and every reported bearing with its error in
degrees. Sortie B's multipath bearing stands out at 140° off; the two good
ones were within 8°. The SET identifies which SQTR tasks were demonstrated
and which need another look.

## Session 3 (T-2 days): dress rehearsal

Nothing about the incident changes except that everything is now exactly
as it will be on Saturday: the real callsigns, the frequencies from the
real communications plan, the real grid numbers, the timing from the real
ICS 204s, the same base staff in the same roles, and the composite position
moved to where the practice beacon will actually be. Crews fly it cold; the
director injects the effects that gave trouble in Session 2. Sortie B finds
the beacon on the first expanding square. The base's bearing plot has no
rejected cuts. Ops-normal reports are on time for all three aircraft for
the whole period.

## The live SAREX

On Saturday the crews brief, launch and fly the same three assignments
against a real practice beacon on 121.775 MHz, with real terrain, weather,
radios and a ground team. Every procedure — panel setup, leg calls, bearing
reports, cone-of-confusion recognition, retasking, the ops-normal cadence,
the Form 110 — has been performed at least twice. The live day adds the
airplane, the weather and the pressure. The debrief compares the live
bearing plot against the Session 3 numbers, and the SET signs off tasks that
were demonstrated on both.

## What the system records across the three sessions

| Measure | Source | What it tells the SET |
|---|---|---|
| Bearing error per report (degrees) | Debrief console | DF technique; multipath/cone recognition |
| Closest point of approach and time to first good cut | Debrief console | Homing effectiveness |
| Track efficiency vs assigned pattern | Debrief console | Pattern discipline |
| Ops-normal report timing per aircraft | Form 110 / message log | Communications discipline at base and in the cockpit |
| Rejected or corrected cuts | Base bearing log | Whether base staff cross-check the cockpit |
| Session-to-session change in all of the above | Three debriefs | Whether the rehearsal worked |

## What this needs from the system

Available today: scenarios with hidden truth and live-injected effects
(radio horizon, terrain masking, 406 burst cadence, cone of confusion,
multipath, wing blanking), the four instruments and the MO panel, the
pattern generator and `.fms` export, the Mumble net and the base radio
console, bearing logging, and the debrief scoring.

Four items from the 2026-09-08 review stand between this narrative and
running it exactly as written (IDs refer to
[`PROJECT_REVIEW_2026-09-08.md`](PROJECT_REVIEW_2026-09-08.md)):

1. **Three aircraft need per-station identity** (O-2): the plugin hardcodes
   the console address and callsign `CAP-1`.
2. **The hidden beacon has to stay hidden, and the plugin has to receive
   it** (X-1, P-2): today both are broken.
3. **The `.fms` export must load in X-Plane 12** (L-1): the format is
   currently malformed.
4. **Mid-flight retasking and assignment maps** are phase 2
   ([`CALTOPO_PHASE2_PLAN.md`](CALTOPO_PHASE2_PLAN.md)); today the AOBD's
   assignment view is the base map with pushed patterns, and cuts are
   plotted by hand.
