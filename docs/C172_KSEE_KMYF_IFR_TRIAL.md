# Stock C172 KSEE–KMYF taxi, departure, and ILS trial

Date: 2026-10-11. Status: an attended simulator sortie reached KMYF 28R,
landed and stopped after one go-around and several paused controller revisions;
an uninterrupted, independently scored qualification remains open. The F-4
program is paused. This scenario uses the stock
X-Plane 12 C172SP G1000 and the user's requested KSEE 27R → Mission Bay Two
departure to 5,000 ft MSL → vectors to BAKEL → KMYF ILS 28R sequence.

## Source and simulator baseline

The current FAA cycle at planning time is 2610 (1–29 October 2026). Use the
[Mission Bay Two obstacle departure](https://aeronav.faa.gov/d-tpp/2610/05402MISSIONBAY.PDF),
its [obstacle continuation](https://aeronav.faa.gov/d-tpp/2610/05402MISSIONBAY_C2.PDF),
the [KSEE airport diagram](https://aeronav.faa.gov/d-tpp/2610/05402AD.PDF),
and the [KMYF ILS or LOC 28R chart](https://aeronav.faa.gov/d-tpp/2610/05401IL28R.PDF)
as chart provenance. Recheck the effective cycle before further trials. The
aircraft-speed source is the bundled
`Aircraft/Laminar Research/Cessna 172 SP/X-Plane_C172_Pilot_Operating_Manual.pdf`:
normal takeoff flaps up, full throttle, rotate 55 KIAS; Vx 62, Vy 74 KIAS.
These numbers describe the simulator aircraft and are not claimed as a real
aircraft's approved POH.

Installed X-Plane `Resources/default data` is cycle **2406**, whereas the FAA
charts above are 2610. It contains MZB 117.8, PGY 116.45, I-MYF 111.95,
and BAKEL/MIBBY/NESTY/PENYY coordinates and an I28R procedure. Before an
instrument trial, compare every fix, course, altitude and missed approach leg
used by the navigator to the current chart. Do not silently treat an old
G1000 procedure load as the current published approach.

## Flight sequence and gates

| Phase | Required behavior | Independent pass evidence |
| --- | --- | --- |
| Park and taxi | Record actual starting spot; use installed KSEE taxi-network nodes and FAA diagram to survey a route to 27R. Obey explicit taxi and crossing authority, stop at hold line. | Surveyed route and runway polygons, stop error, speed and cross-track traces; no unauthorized runway entry. |
| Line-up and takeoff | Verify runway 27R and stock-C172 configuration, receive specific takeoff authority, align to measured runway centerline, use full power, rotate at 55 KIAS. | Correct runway and heading, engine/power readback, centerline error, 55 KIAS rotation, observed liftoff. Rejected takeoff and failed acceleration tested separately. |
| Mission Bay Two | For 27R, charted climbing right turn on heading **062° magnetic** and PGY **R-348**, then MZB **R-076** inbound to MZB. The published runway 27R minimum climb is **500 ft/NM to 2,000 ft MSL**. Hold the assigned route until 5,000 ft MSL. | Flight-path trace compared to mag courses and fixes; rolling climb gradient and altitude gate. If the stock C172 cannot demonstrate the gradient in chosen conditions, record a failed scenario rather than claiming the departure complete. |
| Vectors to BAKEL | At 5,000 ft, switch to an explicit simulated ATC/vector task toward BAKEL. Set the BAKEL entry altitude from the cleared route; use 5,900 ft when joining the charted OGOTE–BAKEL transition. | Separate vector clearance/task, target fix and altitude, positive fix identification, stable approach setup. Do not invent a charted MZB–BAKEL leg. |
| ILS 28R | BAKEL IAF → MIBBY IF → NESTY → PENYY FAF → runway 28R. Charted segments show 4,200 ft after BAKEL toward MIBBY, 3,600 ft toward NESTY, 2,500 ft toward PENYY. Tune/identify I-MYF **111.95**, course **281° magnetic**, then capture the **3°** glideslope. | Frequency/identification, fix sequencing, lateral/vertical errors, configuration/speed, stable approach gate and decision event. KMYF landing controller has attended engineering successes, but not complete-route qualification. |
| Missed approach or landing | If unstable or no valid landing outcome, fly the published miss: climb to 1,100 ft, then climbing left turn to 3,000 ft on heading 270° and MZB R-326 to CARIF/MZB 16.3 DME hold. If landed, stop, clear runway, and taxi to recorded starting spot. | Observed go-around path or independent landing/stop result; correct control release and return taxi. |

The 5,000 ft instruction is the user's **departure milestone**, not an
automatic approach altitude. The chart's 5,900 ft notation applies on the
OGOTE–BAKEL leg; the lower 4,200 ft value applies on the BAKEL–MIBBY leg.
The vector scenario must specify its own entry altitude and terrain/airspace
assumptions. All values in this trial are simulator engineering criteria; no
real-world clearance is implied.

## Implementation order

1. Survey a particular parking spawn, route, hold lines and 27R runway frame
   from the installed apt.dat network against the FAA airport diagram. The
   selected spot is **East Transient Parking 12**. The pinned scenery route is
   `Parking 12–49–55–57–56–58–59–60–175–128–127–126–125–124`, with the
   first 35 m as an apron connector and node 124 as the D8 hold point. The
   surveyed network portion is about 496 m. The controller checks the pinned
   scenery hash and samples every leg against all three KSEE runway footprints.
   The apron connector and physical hold marking still need visual review.
2. Add a bounded ground/takeoff mode to the expiring XPPython3 bridge, with
   independent brake, throttle, flap, heading and runway readback. First run
   attended taxi-only and runway-only trials, each with recorded traces and
   safe pause/override release on fault.
3. Connect the qualified airborne controller to a mag/true-aware Mission Bay
   procedure sequencer. Measure the actual climb gradient under fixed weight,
   pressure, temperature and wind; adjust the scenario or choose another
   departure if the aircraft misses the published minimum.
4. Build vector-to-fix and ILS capture modes with navigation-source checks,
   charted altitude constraints, approach stability checks and a working
   missed-approach controller. Integrate the existing KMYF landing mode only
   after approach-to-landing transitions are tested.
5. Fly the complete sortie repeatedly with independent scoring, including
   rejected takeoff, route uncertainty, ILS failure, unstable approach,
   missed approach and landing-to-taxi recovery. Only measured runs count as
   qualification.

On 11 October 2026, an attended stock-C172 taxi-only diagnostic **passed** from
East Transient Parking 12 to the D8 hold point. The last recorded position was
32.825955° N, 116.964434° W, below 0.5 m/s. The bridge then confirmed pause,
override release and toe-brake release. Earlier runs exposed a parking-brake
reset defect, a brake dataref that did not apply during the roll, and two sharp
corners that needed full nosewheel steering and early turn anticipation. The
passing trace is
`~/.cache/capvsar/ai-pilot/ksee_surface_taxi_20261011_trial8.jsonl`.
This is an engineering diagnostic using explicit **simulated** taxi authority;
it does not represent an ATC clearance or a complete sortie. A subsequent
taxi-plus-takeoff run stopped at D8, entered 27R and lined up near runway
along-track 75 m. It rejected the initial roll at roughly 8 m/s when the
heading drifted about 15° left. Revised steering and initial-climb speed
control then passed both a hold-point diagnostic and a **continuous Parking
12-to-300 ft AGL trial**. The continuous run stopped at D8 at 0.49 m/s,
lined up 75 m along 27R with heading 278.6° true (surveyed 282.1°), crossed
55 KIAS at runway along-track 334 m, became airborne at 71 KIAS near
along-track 509 m, and ended at 300.2 ft AGL and 72.8 KIAS. During the ground
roll the maximum centerline offset was 5.6 m and heading error was 7.0°.
At 0.3 NM airborne, climb from the 388 ft field elevation was about
653 ft/NM. The complete trace is
`~/.cache/capvsar/ai-pilot/ksee_parking_to_takeoff_20261011_trial2.jsonl`
(SHA-256 `dbb6b582cfb321442100013d5e4c2415bdff5f0874792b853d9239c733c27346`).
The bridge confirmed pause and released overrides on completion. The hold-point
checkpoint is marked as an intervention and is not part of this continuous
pass.

## Attended Mission Bay Two and KMYF ILS flight

The aircraft was continued from the paused 300 ft AGL takeoff state without
repositioning. It climbed on runway heading to **790 ft MSL**, turned to
**062° magnetic**, tracked south to PGY10 and west to MZB, and crossed MZB at
**5,002 ft**. The controller flew a simulated vector direct BAKEL at 5,000 ft.
The G1000 flight plan was not loaded; the route was flown with direct surface
control. NAV1 was tuned to I-MYF **111.95** for the ILS.

The cumulative climb from observed liftoff to 2,000 ft was about
**549 ft/NM**, but the lowest sampled half-NM window was **493 ft/NM** near
1,800 ft. Because that is below the chart's **500 ft/NM** minimum, this run
does not qualify the departure climb gradient. The climb controller or loading
must be improved and the segment reflown before claiming chart compliance.

The first approach missed the MIBBY altitude constraint: its sampled low was
about **4,120 ft**, below the charted 4,200 ft segment floor. The subsequent
ILS final was unstable at the 1.2 NM landing handoff (about two glideslope
dots high), so the controller went around. It climbed on runway heading to
**1,100 ft**, then on **270° magnetic**. During the climb, the user directed
a vector to BAKEL near 3,450 ft; the aircraft turned direct and climbed to
5,000 ft. This vector superseded the published CARIF continuation in the
simulated trial, and no live ATC clearance was received.

On the second approach, the sampled segment lows and fix-crossing altitudes
were above the charted floors:

| Fix | Charted floor | Sampled low on leg | Fix crossing |
| --- | ---: | ---: | ---: |
| MIBBY | 4,200 ft | 4,220 ft | 4,309 ft |
| NESTY | 3,600 ft | 3,667 ft | 3,717 ft |
| PENYY | 2,500 ft | 2,558 ft | 2,641 ft |

At the ILS-to-landing handoff, the localizer and glideslope were each near
**0.1 dot** from center, with about **73 KIAS**. The landing controller crossed
the physical threshold about **37 ft AGL** and **64 KIAS**, touched down
**399 m** along runway 28R and **0.1 m** from centerline at about
**−124 ft/min**, then stopped **558 m** along the runway. The simulator was
paused with bridge authority released after the stop.

The bridge's airborne 40 KIAS minimum erroneously remained active after
touchdown. It paused the aircraft on the runway at about 40 KIAS; a bounded
rollout guard was installed and the same paused aircraft continued to a stop.
Raw trace fragments therefore do **not** constitute an uninterrupted landing
qualification replay. The simulator's older navigation data, absence of live
ATC, lack of an audio radio-ident check, and lack of machine-verified runway
visual references at decision altitude also limit what can be claimed. The
independent fragment scorer and hashes are in
[the flight evidence](evidence/ai_pilot_ksee_kmyf_20261011.json).

The next controller interface should accept bounded, authenticated heading,
direct-to and altitude changes during flight. This attended runner still
pauses for route-code changes; live vector reassignment has not yet been
implemented or qualified.
