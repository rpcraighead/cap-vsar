**To:** Col Ross Veta; Col Craig Newton; Lt Col David Boehm
**Cc:** [CAWG/DO, CAWG/ESO, Wing Stan/Eval, others as appropriate]
**Subject:** CAP V-SAR — a virtual electronic-search trainer for CA Wing aircrews (concept + draft plan)

Ross, Col Newton, Col Boehm —

I want to put a concept in front of you before I take it any wider, and ask for a slot to present it at the CA Wing conference. Ross, this grew directly out of the sorties you and I have flown together; you'll recognize the Palomar scenario.

**PURPOSE.** Propose CAP V-SAR (Virtual Search and Rescue), a low-cost desktop simulator for training Mission Pilots, Observers, Scanners and mission base staff in electronic search — prosecuting 121.5/243/406 MHz beacons with the Becker SAR-DF 517 and the RHOTHETA RT-600 that is replacing it.

**THE PROBLEM.** Electronic search is a perishable skill that is expensive to practice. A real training sortie needs an aircraft, fuel, a crew, a practice beacon and cooperative weather, and it delivers whatever signal conditions exist that day. Crews too often meet a reciprocal bearing, a terrain-masked signal, or a needle swinging wildly on close approach for the first time on an actual mission — exactly when a trained response matters most.

**THE CONCEPT.** Four layers, all software, all running on members' own PCs:
1. X-Plane 12 flight simulation (Windows, Mac or Linux) hosting a small scripted plugin that synthesizes the beacon signal — bearing, range, radio horizon, terrain masking, the 50-second 406 burst cadence, the 121.5 homer, the cone of confusion, and multipath false bearings, each switchable by an instructor.
2. Air Manager instrument panels replicating the Becker 517 and RT-600 heads, plus a second COM panel at the Observer station, as in the aircraft.
3. Live ATC through PilotEdge (human controllers, ZLA coverage over SoCal, 8am–11pm Pacific) and a separate CAP mission voice net — two radios, two PTTs, as in the aircraft.
4. A mission base web client with live aircraft tracking on a CalTopo training map, and a debrief that replays the recorded track against the true beacon position.

**WHY THIS WORKS.** X-Plane does not simulate distress beacons at all — which is the advantage. Because the whole signal chain is synthesized, an instructor can produce a textbook multipath error or a valley null on demand, repeatably. No real airplane can do that. The debrief — the crew's track replayed against ground truth — is the product; a real sortie gives you that only partially and at far greater cost.

**A SCENARIO YOU'LL RECOGNIZE.** Scenario C-1 is the 121.5 ELT we worked at the ESCON fix on the Palomar ILS, where the plate calls for 3,300 ft. SoCal Approach protected the approach altitude and gave us block altitudes above and below it, so we could search around arriving IFR traffic rather than through it. The training value isn't the beacon — it's that the search cannot be flown at all without continuous negotiation with a live approach controller, on the final approach course, with the ideal altitude occupied by traffic. That's the sortie most likely to defeat a crew that has only searched over open terrain.

**STATUS.** Concept and a 40-page implementation plan (v0.5, attached). Nothing is built yet. The plan has been red-teamed once; the architecture has been checked against the X-Plane, Air Manager, PilotEdge and CalTopo documentation. Estimated effort is 45–73 developer-days plus artwork; a usable single-seat DF trainer falls out at the end of Phase 2 (roughly 20 days), before any of the network layers. Software costs are per-seat and modest (X-Plane ~one-time; Air Manager per seat; PilotEdge ~$36/month for a three-person crew using shared-cockpit tiers). The dominant cost is volunteer time.

**PARTNERS.** I have working relationships with Keith Smith at PilotEdge and Austin Meyer at Laminar Research (X-Plane); both have been receptive before. The plan includes a specific, small dataref request to Laminar that would let the Observer transmit on COM2 while the pilot works COM1 — split COM, as in the GMA 1347.

**WHAT I'M ASKING.**
1. A 20-minute slot at the CA Wing conference to present the concept (deck attached).
2. Your read on the path to training credit. Built as a procedures and decision trainer, it earns nothing unless Stan/Eval and NHQ say it does — I'd rather know the answer early than build for a credit that never comes.
3. Two or three experienced MPs willing to validate the signal-effects model against their own experience before it goes near a trainee.
4. Whether a CalTopo training team (or sub-team) can be provisioned so exercise traffic never touches an operational map.
5. Whether cadets should be in scope — it changes the online-environment design under CPP.

**NEXT STEPS.** With a nod from you, I'll start Phase 0 on my own equipment (sim, Air Manager, and a one-dataref proof that the architecture holds), and bring a working single-seat DF trainer to whoever wants to fly it. The plan is a draft and I'd value hard questions before the conference rather than after.

Respectfully,

Ron
[Rank] Ron Craighead, CAP
[Unit / duty position]
[Phone]

Attachments: CAP_V-SAR_Implementation_Plan_v0.5.docx; CAP_V-SAR_Concept_Brief.pptx
