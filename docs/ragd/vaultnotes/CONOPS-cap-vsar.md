# CAP V-SAR — Concept of Operations

**Project:** CAP V-SAR (Civil Air Patrol Virtual Search and Rescue)
**Started:** 2026-09-05
**Status:** Infrastructure and exercise console deployed. Phase 0/1 of the sim
side partially complete. Not an approved CAP program.

## What it is

A low-cost desktop simulator for training Civil Air Patrol Mission Pilots,
Mission Observers, Mission Scanners and mission base staff in **electronic
search** — locating 121.5, 243 and 406 MHz distress beacons with the Becker
SAR-DF 517 and the RHOTHETA RT-600 that is replacing it in the CAP fleet.

Runs on members' own computers. Combines X-Plane 12, custom Air Manager
instrument panels replicating the DF heads, live human ATC via PilotEdge, a CAP
mission voice net, and a mission base map that staff join from a browser.

## The central idea

X-Plane does not simulate distress beacons at all. That is the advantage rather
than the obstacle. Because the whole signal chain must be synthesized, the
instructor controls every effect that makes electronic search hard — terrain
masking, radio horizon, the 50-second 406 burst cadence, the cone of confusion,
multipath false bearings — individually, repeatably, on demand. No real
aircraft can be told to produce a textbook multipath error.

The recorded track replayed against beacon truth in debrief is the product.

## Four layers

1. **Simulation** — X-Plane 12 hosting an XPPython3 plugin that synthesizes the
   beacon signal and probes real terrain for line of sight.
2. **Instruments** — Air Manager panels: Becker 517 and RT-600 heads, plus a
   second COM panel at the Observer station as in the real aircraft.
3. **Radios** — PilotEdge for live ATC, a self-hosted Mumble server for the CAP
   mission net. Two radios, two push-to-talk keys.
4. **Mission base** — browser client with live tracking, bearing plotting,
   retasking, and debrief replay. CalTopo for mapping.

## Operating modes

| Mode | Participants | Available |
|---|---|---|
| A — Solo | One trainee plus instructor | End of Phase 2 |
| B — Crew | MP, MO, MS at separate stations | Phase 3 |
| C — Networked | Several crews plus remote mission base staff | Phases 4–5 |

## Scenario C-1 — the reference scenario

Drawn from a sortie the unit actually flew. A 121.5 MHz ELT transmits from the
ground at the **ESCON intermediate fix** on the ILS approach to
**McClellan-Palomar (KCRQ)**, where the plate calls for **3,300 ft**. No
satellite alert — 121.5 has not been satellite-monitored since 2009 — so the
tasking arrives as reports of a signal in the approach area with no position.

SoCal Approach protects the 3,300 ft approach altitude for arriving IFR traffic
and issues the aircraft **block altitudes above and below it**. The crew works
the upper block, waits out an arrival passing between the blocks, then takes the
lower one.

The training value is not the beacon. A strong signal on flat ground near an
airport is easy to localise. The value is that the search cannot be flown at all
without continuous negotiation with a live approach controller, on the final
approach course, with the ideal search altitude occupied by traffic.

Variants cover a ramp false alert (the most common real outcome), a 406 beacon
with burst cadence, two aircraft deconflicted by ATC, and a genuine target in
terrain east of the field.

## Effort and phasing

45–73 developer-days plus 6–12 days of artwork, across five gated phases. A
usable single-seat trainer exists at the end of Phase 2, roughly 20 days in.
Volunteer time is the dominant cost.

Phase 0 foundation → Phase 1 propagation engine → Phase 2 Becker 517 head and
solo mode → Phase 3 effects, RT-600, crew mode, SME validation → Phase 4
tracking and CalTopo → Phase 5 radio net, mission base client, debrief.

## Organisation

Governance is an Executive Sponsor and a Project Officer, with a Steering Group
meeting at phase gates only. Phases 0–2 need four people. Three positions would
stop the project if vacated and each needs a named deputy: the DF Engine
Developer, the Project Officer, and the Vendor Liaison — the PilotEdge and
Laminar Research relationships are personal rather than institutional.

A **SET (Skills Evaluation Trainer)** can sign off tasks for qualification, so
SETs are the mechanism by which any training credit would reach a member's
record. Engage one from Phase 3, before the recording design is fixed.

## Partners

- **PilotEdge** (Keith Smith) — live ATC, ZLA covers SoCal. Existing relationship.
- **Laminar Research** (Austin Meyer) — X-Plane. A small dataref request would
  complete the copilot transmit path for split COM. Existing relationship.
- **Sim Innovations** — Air Manager instrument platform.
- **CalTopo** — mission base mapping, team account required.
- **CA Wing Stan/Eval and NHQ** — the training-credit path. Not yet engaged.

## Documents

Implementation plan v0.8 (49 pp), a 9-page summary for circulation, a 21-slide
concept brief, and a draft intro email to CA Wing leadership. All in the project
repository under `docs/`, and on the workstation in `~/Documents/`.

Related: [[AsBuilt_CAPVSAR]]
