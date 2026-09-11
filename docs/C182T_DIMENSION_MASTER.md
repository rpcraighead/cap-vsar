# C182T dimensional measurement master (A-1, stage 1)

This document is the source-backed measurement master required by stage 1 of
`docs/bugs/CLAUDE_RESUME_C182_DIMENSIONS.md`. It records what the authoritative
C182T material actually says, under what attitude and between which endpoints,
and — equally important — which requested dimensions are **not** published and
must therefore stay unknown.

The machine-readable form is `scripts/c182t_dimension_master.json`. That file is
the artifact the stage-2 measurement harness consumes; this document is the
reasoning and provenance behind it.

No aircraft asset, converter or simulator file was changed to produce it.

## 1. Aircraft identified

| Field | Value |
|---|---|
| Make/model | Cessna 182T Skylane |
| Variant | NAV III with GFC 700 AFCS (Garmin G1000) |
| Type certificate | FAA TC 3A13; Model 182T approved 23 February 2001 |
| Serial range | 18280945 and on |
| Simulated identity | CAP 487 |

The NAV III / GFC 700 variant was chosen because it matches the installed
package identity `Cessna 182T NAV III`, and because TCDS 3A13 NOTE 2 names
`182TPHBUS-00` as the FAA-approved AFM part number for exactly that
configuration. The handbook consulted is that part number.

## 2. Sources

| ID | Document | Authority | SHA-256 |
|---|---|---|---|
| POH | Cessna Model 182T NAV III GFC 700 AFCS POH / FAA Approved AFM, P/N 182TPHBUS-00 / -01 | FAA approved | `ba64adab5d6e…3fd2705c` |
| TCDS | FAA Type Certificate Data Sheet No. 3A13, Revision 66, 3 November 2006 | FAA certification | `4141481297d5…03df855f` |
| SD | Cessna *Specification and Description, Skylane 182T*, December 2015 Revision C | Manufacturer | `4466093c4f53…aefcd7df5` |

Full URLs, retrieval date and per-source role are in the JSON. The PDFs are
third-party copyrighted documents and are deliberately **not** committed to this
repository, consistent with the release boundary in
`docs/FLIGHTGEAR_C182_GPL_PLAN.md`. Hashes pin which document was read.

### A caution about the manufacturer sheet

The Specification and Description prints its dimension table under the heading
**"1.2 APPROXIMATE DIMENSIONS"**. Its 9 ft 4 in / 29 ft 0 in / 36 ft 0 in are
therefore corroboration, never the acceptance master. The POH three-view is
preferred throughout because it is FAA-approved, states an attitude, and shows
where each dimension is actually taken.

## 3. The two attitudes — the most important finding

The sources define **two different** aircraft attitudes, and confusing them
makes every vertical dimension wrong.

**Normal ground attitude** — POH Figure 1-1 Sheet 2, page 1-4, NOTE, verbatim:

> Normal ground attitude is shown with nose strut showing approximately
> 2 inches of strut, and wings level.

Every dimension on the POH three-view, including overall length and overall
height, is measured in this attitude.

**Leveling attitude** — TCDS page 33 gives the leveling means as the left side
of the tailcone at 139.65 in and 171.65 in aft of datum; POH Section 6 reaches
it by deflating the nose tyre and/or raising or lowering the nose strut until
the bubble centres. This attitude is for weight and balance **only**.

Consequence for the harness: a mesh cannot be compared against the published
height until it is posed in normal ground attitude. Comparing raw mesh extrema
against 9 ft 4 in is not a measurement.

## 4. Datum

| Axis | Datum | Source |
|---|---|---|
| Longitudinal (FS, in aft) | **Lower portion of front face of firewall** | TCDS p. 33; POH p. 2-8 "Reference Datum: Front face of firewall" |
| Vertical (W.L.) | **Unknown** — TCDS cites "0.00 W.L." for rudder travel but never locates it | TCDS p. 33 |
| Lateral (B.L.) | **Unknown** — treat centreline as B.L. 0 for symmetry checks only | — |

The firewall being the datum is a fortunate result: the plan already nominates
the cockpit/firewall interface as the alignment anchor, and that anchor is
exactly FS 0. Because the waterline datum is unknown, **all vertical targets are
referenced to the ground plane in normal ground attitude**, not to a waterline.

## 5. Sourced targets

All values are as printed; metres are exact conversions at 1 in = 0.0254 m.

| Target | Value | Endpoints | Attitude | Source |
|---|---|---|---|---|
| Overall length | 29 ft 0 in / 8.8392 m | Spinner apex → aft-most rudder trailing edge | Normal ground | POH Fig 1-1 Sheet 2 |
| Wing span | 36 ft 0 in / 10.9728 m | Wingtip → wingtip **including standard strobe lights** | Normal ground | POH Fig 1-1 Sheet 1 + NOTE |
| Overall height | 9 ft 4 in / 2.8448 m | Ground → fin tip | Normal ground | POH Fig 1-1 Sheet 2 |
| Main wheel track | 9 ft 0 in / 2.7432 m | Main wheel centre → centre | Normal ground | POH Fig 1-1 Sheet 1 |
| Wheel base | 66.5 in / 1.68910 m | Nose wheel axle → main wheel centre line | Normal ground | POH Fig 1-1 Sheet 2 NOTE |
| Propeller diameter | 79 in max, 77.5 in min / 2.00660–1.96850 m | Tip → tip through hub | n/a | TCDS p. 33; POH "79\" MAX" |
| Horizontal tail span | 11 ft 8 in / 3.5560 m | Stabiliser tip → tip | Normal ground | POH Fig 1-1 Sheet 1 |
| Propeller ground clearance | 10.875 in / 0.276225 m | Ground → bottom of prop disc | Normal ground | POH Fig 1-1 Sheet 2 NOTE |
| Wing area | 174.0 ft² / 16.1653 m² | reference area | n/a | POH NOTE; SD p. 6 |
| Min turning radius | 27.0 ft / 8.2296 m | pivot point → outboard wingtip | n/a | POH NOTE |

Three endpoint definitions were verified by reading the POH three-view at
450 dpi rather than assumed:

- **Length is measured from the spinner apex, not the propeller.** The forward
  extension line passes through the spinner tip, ahead of the blades.
- **Length ends at the rudder trailing edge**, aft of the fin.
- **Span includes the wingtip strobes**, per the POH note. The structural span
  without strobes is not published and must not be derived by subtraction.

## 6. Fuselage station ladder

These matter more than the headline length: they constrain longitudinal
correction *region by region* instead of as one number.

| FS (in) | Feature | Source |
|---|---|---|
| −14.8 | Engine oil arm | TCDS |
| **0.0** | **DATUM — lower front face of firewall** | TCDS, POH |
| 25.98 | Leading edge of MAC (MAC = 58.8 in) | TCDS |
| 32.0 – 50.0 | Front seat range | TCDS |
| 46.5 | Wing fuel tank arm | TCDS |
| 65.25 | Rear doorpost bulkhead | SD Fig II |
| 74.0 | Rear seat arm | TCDS |
| 82.0 / 109.0 / 134.0 | Baggage area A and B limits | TCDS |
| **134.0** | **Aft baggage bulkhead / rear wall of cabin** | TCDS + SD (three agreeing statements) |
| 139.65, 171.65 | Leveling points, left tailcone | TCDS |

The FS 134.0 station is the strongest cross-check in the set: TCDS gives it as
the aft baggage limit, the SD text gives "Length (firewall to aft baggage
bulkhead) 134 in", and the SD Figure II dimension chain reads 65.25 + 68.75 =
134.00. Three independent statements agree, which also confirms the firewall
datum interpretation.

**MAC leading edge at FS 25.98 is an aerodynamic reference, not the wing root
leading edge.** It must not be used to place the root rib.

## 7. Control surface travels

TCDS page 33 gives flaps 38° down (+0/−1); ailerons 20° up / 15° down (±2);
elevator 28° up / 21° down (±1) relative to stabiliser; elevator tab 24° up /
15° down; rudder 24° left and right measured parallel to 0.00 W.L., and
27° 13′ measured perpendicular to the hinge line.

These are angular limits only and locate no hinge in space, with one exception.
The rudder pair is published in two frames, so their ratio fixes the hinge cant:

    acos(24° / 27.2167°) = 28.15° from vertical

That is the only hinge-line geometry recoverable from the consulted sources.
Every other hinge pivot must continue to come from the donor's own
`Models/c182t.xml`, as the continuation prompt already requires.

## 8. Unknowns — stopped rather than invented

Stage 1 explicitly requires marking a station unknown rather than inventing a
plausible coordinate. The following requested items are **not published** in the
POH, the TCDS or the Specification and Description:

1. Wing root leading-edge, trailing-edge and root-rib stations.
2. Firewall-to-windshield-base station and windshield rake.
3. Cabin and baggage door opening fore/aft stations (sizes are published; stations are not).
4. Aileron, flap and elevator hinge-line stations.
5. Horizontal and vertical tail stations and chords; vertical tail span.
6. Individual nose-gear and main-gear fuselage stations — POH Section 6 treats
   the main-gear station as a *per-aircraft* measurement taken at weighing
   ("measurement A", main wheel centre line to a firewall plumb bob), so it has
   no fixed published value. Only their 66.5 in separation is published.
7. Waterline and buttock-line datum locations.
8. Wing dihedral, incidence, washout and airfoil section.
9. Structural wing span excluding strobes.

Closing items 1–5 would require a Cessna Model 182 Series Maintenance Manual,
Structural Repair Manual or Illustrated Parts Catalogue. Until then, the wing,
empennage and door regions have **no sourced longitudinal target**, and the
correction stage must leave their stations alone.

## 9. Proposed tolerances (not yet ratified)

Tolerances are an engineering choice, not a sourced fact, so they are proposed
here and flagged as such in the JSON.

| Target | Proposed | Rationale |
|---|---|---|
| Wing span | ±0.5 % | Endpoint defined; value printed to the inch |
| Overall length | ±1.0 % | Endpoints clear; printed to the whole foot |
| Wheel base | ±1.0 % | Printed to 0.1 in — the most precise exterior figure available |
| Track, h-tail span | ±1.0 % | Endpoint convention slightly unannotated |
| **Overall height** | **±2.5 %** | Compounded beacon-inclusion and strut-extension ambiguity |
| Prop ground clearance | ±1.0 in | Highly sensitive to strut and tyre state |
| Propeller diameter | 77.5–79.0 in, hard | Certification bound, not a tolerance |

Overall height is the highest-risk target and deserves the loosest band: it is
ambiguous both in endpoint (whether the fin-tip beacon counts — unresolvable
beyond ±1–2 in at drawing resolution) and in attitude ("approximately 2 inches
of strut"). **The fin must not be reshaped to chase this number alone.**

## 10. Appendix — preliminary donor comparison (informational)

Not the stage-2 harness. These figures come from parsing the pinned donor
through the existing strict parser using the endpoint rules established above,
and are recorded so stage 2 has a baseline to reproduce.

| Target | Sourced | Donor | Δ |
|---|---|---|---|
| Wing span (with strobe) | 10.9728 m | 10.9318 m | −0.37 % |
| Wing span (structure only) | — | 10.9115 m | −0.56 % vs headline |
| Overall length (spinner→rudder) | 8.8392 m | 8.5008 m | **−3.83 %** |
| Horizontal tail span | 3.5560 m | 3.6359 m | +2.25 % |
| Main wheel track | 2.7432 m | 2.6160 m | **−4.64 %** |
| Wheel base | 1.68910 m | 1.6277 m | **−3.64 %** |
| Propeller diameter | 77.5–79.0 in | 79.17 in | marginally over max |
| Height, main-wheel plane → fin top | 2.8448 m | 3.0889 m | **+8.58 %** |
| Height, main-wheel plane → beacon top | 2.8448 m | 3.1619 m | **+11.14 %** |
| Prop ground clearance (disc bottom) | 10.875 in | 2.74 in vs main-wheel plane; 7.91 in vs nose contact | **far short** |

Three observations follow, and they should shape stage 3:

**The donor is not in normal ground attitude.** Its nose wheel contact sits
131 mm *below* the main-wheel plane — a pose that cannot exist on flat ground.
Every height and clearance figure above is therefore provisional until the mesh
is re-posed, and the very poor propeller ground clearance is mostly this pose,
not a mis-sized cowling.

**A whole-model scale is refuted by the data, more strongly than the plan
claims.** Span is −0.4 % and propeller diameter is within 0.2 % of the
certificated maximum, while length is −3.8 % and height is +8.6 %. No scalar,
uniform or per-axis, fixes length and height without breaking span and
propeller, both of which are already right.

**The longitudinal shortfall is coherent.** Length −3.83 %, wheel base −3.64 %
and track −4.64 % cluster together, which is consistent with a fuselage and gear
that are uniformly a few percent small while the wing and propeller are correct.
That is a regional correction, exactly as the continuation prompt specifies.

The propeller diameter and ground clearance figures also demonstrate why the
plan's landmark rule matters: both must be derived from the hub axis and disc
radius. Taking the lowest modelled blade vertex gives a meaningless answer,
because the donor's blade clocking is arbitrary.

## 11. What stage 1 does not deliver

A-1 stays open. This is the measurement master only: no harness, no geometry
change, no X-Plane run, and no Plane Maker work. The named unknowns in §8 mean
stage 3 cannot correct wing, empennage or door stations on sourced evidence
today.
