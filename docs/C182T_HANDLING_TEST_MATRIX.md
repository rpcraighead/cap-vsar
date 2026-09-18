# CAP 487 progressive handling tests — support matrix and BLOCKED findings

Pre-flight assessment for the H0–H7 progressive handling card. **Simulator
engineering validation only; not approved instruction for a real aircraft.**

Produced before flying, as the card requires. Headline: **most of the card cannot
be flown by the authorized controller.** Not because the controller is broken, but
because it is a heading/altitude target-holder and the card needs an airframe
characterization tool. The card anticipates this — the answer is the human pilot
flies and the agent captures.

## 1. Instrumentation: supported

Every observable the card asks for is available. Verified live, and every
zero-valued reading was checked against `X-Plane 12/Resources/plugins/DataRefs.txt`
rather than inferred — X-Plane returns `0` for unrecognised names, so a zero is
ambiguous until the name is confirmed to exist.

| Observable | Dataref | Status |
|---|---|---|
| IAS / TAS | `flightmodel/position/indicated_airspeed`, `true_airspeed` | live |
| Altitude MSL / AGL | `cockpit2/gauges/indicators/altitude_ft_pilot`, `flightmodel/position/y_agl` | live |
| Vertical speed | `flightmodel/position/vh_ind_fpm` | live |
| Pitch / bank / heading | `theta`, `phi`, `mag_psi` | live |
| Body rates P/Q/R | `flightmodel/position/P,Q,R` | live |
| Angle of attack | `flightmodel/position/alpha`, `flightmodel2/misc/AoA_angle_degrees` | live |
| Sideslip / slip ball | `flightmodel/position/beta`, `cockpit2/gauges/indicators/slip_deg` | live |
| Normal acceleration | `flightmodel/forces/g_nrml` | live |
| Stall warning | `cockpit2/annunciators/stall_warning`, `..._ratio` | name VALID, reads 0 (not stalling) |
| Throttle / MP / RPM / fuel flow | `cockpit2/engine/...` | live |
| Flap handle / actual | `cockpit2/controls/flap_ratio`, `flightmodel2/controls/flap1_deploy_ratio` | names VALID, read 0 (flaps up) |
| **Actual surface deflection** | `flightmodel2/wing/elevator1_deg[8]`, `aileron1_deg[2,3]`, `rudder1_deg[10]` | live |
| Trim | `cockpit2/controls/elevator_trim` | live |
| Weight | `flightmodel/weight/m_total` | live |
| Sim rate | `time/sim_speed` | VALID (`sim_speed_actual` returns NaN while paused) |

**Corrected names.** `flightmodel2/controls/elevator_ratio`, `aileron_ratio` and
`rudder_ratio` **do not exist**. Actual deflection is the `flightmodel2/wing/*_deg`
family. Anything logged under the non-existent names would have been silent zeros
masquerading as measurements.

**UNMEASURED / UNVERIFIED, do not infer:**

* **CG readback and its coordinate conversion.** `flightmodel/misc/cgz_ref_to_default`
  reads 0.1708 m but is relative to the *default* CG, not to the Cessna datum. The
  ACF-frame-to-fuselage-station mapping is established only via %MAC
  (`docs/C182T_DIMENSION_MASTER.md`, MAC LE at ACF z 1.994 ft, MAC 4.837 ft). The
  card requires verifying mass and CG readbacks **before** testing; that is not done.
* **Stick force and buffet.** Not instrumented and not inferable. Report control
  displacement, trim demand and simulated cues only.
* **Capture rate.** Present tooling defaults to 4 Hz (`--hz` configurable). The card
  wants ≥10 Hz and prefers 20 Hz for transients. 20 Hz over UDP is untested; actual
  sample intervals must be recorded and gaps flagged.

## 2. Control authority: the blocking finding

The authorized path is `ManeuverGate` + a `FlightBackend`. Both available backends
expose exactly one command: **`select(heading_mag, altitude_indicated_ft)`**.

That means the controller can command a *heading* and an *altitude*. It cannot
command an airspeed as a test point, cannot command a bank angle, cannot actuate
flaps, cannot apply a discrete control input and return, and cannot trim.

The card also requires interfering holds **off** for airframe characterization,
noting correctly that a pitch/altitude loop can hide instability and prevent a
natural stall. `XPlaneDirectBackend` is nothing but a pitch/altitude loop. For
every airframe card it is the wrong instrument by construction.

### Gate envelope vs card requirements

Enforced: **90–140 KIAS, 3,000–6,000 ft indicated, ≥1,000 ft AGL, ≤35° bank.**

| Card | Needs | Verdict |
|---|---|---|
| H0 control/trim confidence | discrete single-axis inputs, trim | **FLOWN 2026-09-17**, run 6 — see §6 and `C182T_H0_CONTROL_LAW_FINDINGS.md` §8 |
| H1 speed ladder | 80–120 KIAS, trim/power-required | **BLOCKED at 80 KIAS** (gate floor 90); speed-on-pitch and trim now exist, the floor does not move |
| H2 bank ladder | commanded 15/30/45° bank at 80–110 KIAS | **UNBLOCKED for 90–110 KIAS** (`select_bank`); **BLOCKED at 80 KIAS**, below the floor |
| H3 climb/descent | Vy climb (speed-on-pitch) | **UNBLOCKED** — `select_airspeed(kias, throttle=...)` holds speed on pitch with throttle as the independent variable |
| H4 flap transitions | flap actuation at 90 KIAS | **UNBLOCKED** — `set_flaps(ratio)` |
| H5 slow flight | ~1.2–1.3 Vs ≈ 50–65 KIAS | **BLOCKED** — far below the 90 KIAS floor |
| H6 stalls to break | ~40–51 KIAS | **BLOCKED** |
| H7 power-on stalls | full power to break | **BLOCKED** |

**Zero of the eight cards could be flown autonomously as written**, on the
assessment made before any of this was flown. That has since changed for H0, H2
(above 90 KIAS), H3 and H4; see §6. H1 and H5–H7 remain blocked on the 90 KIAS
gate floor, which is not a tooling gap and is not being removed.

### Terrain, and a correction

An earlier draft of this document claimed the card's altitude block conflicted
with the gate ceiling, and that flying west over water made it worse. **That was
backwards.** Over water, terrain is at sea level, so AGL and indicated altitude
coincide and the two blocks line up almost exactly:

    gate block        3,000 - 6,000 ft indicated
    over water        3,000 - 6,000 ft AGL
    card hard floor   3,000 ft AGL      -> matches the gate floor
    card entry        6,000 ft AGL      -> matches the gate ceiling

The conflict is real over **high terrain**, not over water. At the 1,238 ft
terrain currently below the aircraft, a 6,000 ft AGL entry would be 7,238 ft MSL,
above the gate ceiling; over the 3,230 ft terrain further east it would be 9,230 ft.
Moving the test block west over the ocean is what **resolves** the conflict.

Residual, and minor: over water a 6,000 ft AGL entry sits exactly at the gate
ceiling with no headroom above it. Since the maneuvers of interest descend, the
entry point is what matters and the 3,000 ft floor leaves 3,000 ft of margin.
Entering a little below 6,000 removes even that nit.

So: **choose an over-water block.** No gate change is needed for altitude.

## 3. Recommended path

**Human pilot flies; the agent captures and reduces.** This is the card's own
fallback and it is the correct one here. It needs no gate change, no second
controller, and no bypass — which the card forbids and which tracker item AI-1
exists to prevent.

Required work to support it:

* raise capture to 20 Hz and record actual sample intervals, flagging gaps;
* add the full observable set above to the capture tool — it presently logs eight
  channels, not the ~25 the card requires;
* verify the CG readback and coordinate conversion before any weight/CG point;
* select an over-water block, where the gate's altitude limits and the card's
  AGL block coincide and no gate change is needed.

**Not recommended:** widening the gate envelope to make H5–H7 autonomous. The
90 KIAS floor is the specific guard that stops an autonomous system flying to the
stall, and removing it to enable stall testing inverts its purpose. If autonomous
stall testing is wanted later, `services/ai_pilot/flight_test.py` already carries a
`StallTestProfile` with its own stricter guardrails; that is the vehicle for a
*documented, scoped exception*, not a general envelope relaxation.

## 4. Correction to a prior change in this repository

The card states: *"Do NOT use FS 33 as the forward limit at 3,100 lb."*

That is a direct hit on a change made earlier today. `acf/_cgZ_fwd` was set to
2.571 ft = FS 33.0 in, the most-forward *certificated* station, because X-Plane
accepts a single forward limit while the TCDS forward limit is weight-scheduled
(33.0 in ≤2,250 lb, 35.5 at 2,700, 40.9 at 3,100). The limitation was documented
at the time, but the practical consequence is sharper than recorded: **the
simulator will now happily load CG to FS 33 at 3,100 lb, which is outside the real
envelope.** The sim does not enforce the schedule. Any 3,100 lb point must have its
forward CG chosen against the POH schedule by the test conductor, not taken from
what the simulator permits.

## 5. Status

No handling points flown. Nothing on this card is recorded as pass or fail.
This assessment does not close A-1 and does not validate the aircraft.

## 6. What flying it actually changed — 2026-09-11

§2 above was written before anything was flown, and its central finding was
right: the backend was a heading/altitude target-holder, and the card needs an
airframe characterization tool. Rather than leave the card blocked, the backend
was extended along the axes the card names. `services/ai_pilot/maneuvers.py` was
NOT modified and the gate was not bypassed; the envelope is unchanged.

Added to `XPlaneDirectBackend`: `apply_test_input` (bounded, ramped, self-expiring
single-axis inputs — H0), `select_bank` (H2), `select_airspeed(kias, throttle=)`
for speed-on-pitch (H1/H3), `set_flaps` (H4), and elevator trim.

**Five attempts at H0 have produced no valid data point.** Each found a real
control-law defect; all five are fixed and covered by offline tests. In order:
step inputs and no coordination; a pure-integrator throttle going bang-bang; an
abrupt roll that turned out to be a step in the RECOVERY rather than in the
ramped input, plus a reference condition that was never established because the
speed integral wound up against the idle stop; a proportional cascade sitting 107
ft low for two minutes with every loop satisfied; and finally the backend
engaging on an aircraft the autopilot had left trimmed +0.432 nose-up, holding
full nose-down elevator saturated for seven seconds while the aircraft climbed at
1,533 fpm.

That last one is this document's own §2 prediction — "no trim" — arriving in the
air. It is the clearest evidence here that the pre-flight assessment was worth
writing.

**Correction to §1.** This document listed capture rate as the instrumentation
risk. It was not. The real instrumentation gap was that a *saturated* surface and
a *slow* one look identical from the response alone, so three of the five defects
were invisible until the commanded surface positions were recorded alongside the
response. Traces now log the pre-rate-limit demand next to the command, the trim
position and rate, both integrator states, and the age of every auxiliary
channel.

**H0 was flown on 2026-09-17, run 6.** It reached a stabilized reference
condition in 12 seconds and flew all ten points; nine are attributable to that
reference, one (`roll +0.05`) entered 4 fpm outside the vertical-speed
tolerance and is excluded. Full reduction in
`docs/C182T_H0_CONTROL_LAW_FINDINGS.md` §8.

Nothing there is a pass or a fail: H0 has no published criterion, being a
control and trim confidence card. What it produced is a characterisation, and
three things in it are worth carrying forward. Roll is linear to within 3% on a
doubled input with an identical 3.1 s time-to-peak on all four points. Pitch is
not — 1.54x and 1.86x for a doubled input, with recovery up to 45 s and one
point (`pitch -0.10`) that did not recover inside the window. And **±0.05
rudder is too small an input to characterise the yaw axis**: both yaw points
sit near the noise floor, so that axis is effectively still unexercised.

The run was flown at **2,718 lb with the altitude and heading loops active**.
These are controller-in-the-loop numbers, not open-loop airframe
characterisation, and the pitch small-input asymmetry (20.9% at ±0.05 against
4.5% at ±0.10) is most likely the altitude loop still authoring part of the
response — the interference this document's §2 and the card itself both warn
about.
