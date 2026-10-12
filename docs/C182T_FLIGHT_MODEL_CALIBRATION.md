# CAP 487 flight-model calibration: first controlled experiment

Status: **flown 2026-10-11; fuselage drag calibrated to 0.120; climb at Vy still ~18 % high with POH mixture.** A-1 remains open. See the 2026-10-11 section at the end, which supersedes the staged-experiment text above it. This is X-Plane
engineering work, not operating guidance for a real aircraft.

## Baseline and source conditions

The installed CAP 487 ACF and a clean rebuild from the pinned FlightGear donor
are byte-identical, SHA-256
`eaae3c833eee4c82f30da39fe14c36987776ca285c4fc170f99047949958b6dd`.
The builder applies 50/50 ACF patches. Its `_wing/` and `_body/` aerodynamic
definitions remain the stock Laminar C172SP except for the two corrected
horizontal-tail half spans. The main wing is already close to the C182T POH's
published 174.0 ft² area; changing it to chase cruise speed would discard that
independent geometric agreement.

The [C182T NAV III information manual](https://ilwg.cap.gov/media/cms/182TNavIIIGFC700InfoManual_4C95242EF1943.pdf)
gives 150 KTAS maximum at sea level, 145 KTAS at 80% power and 7,000 ft, and
924 FPM sea-level climb. Its note says the speed figures include standard wheel
and brake fairings, which add approximately 3 knots, and assume standard
atmosphere and the indicated weights. This online information manual says it
is a copy for general purposes and is not kept current; it is used here only
for simulator engineering. The pinned document identity and hash are in
`scripts/c182t_dimension_master.json`.

Recorded CAP 487 points at 3,100 lb: B1 was 825 FPM extrapolated to sea level
(-10.7%); C1 was 130.1 KTAS at full power and about 556 ft MSL (-13.3%). At C1,
the engine delivered 214 HP and 2,400 RPM. The existing analysis in
`CHANGELOG.md` explains why the power shortfall alone cannot account for the
speed shortfall. These are two misses, not a measured drag polar.

## Experiment 1: isolate fuselage drag coefficient

The baseline ACF has `P _body/0/_part_cd 0.200000003`. The
[X-Plane Plane Maker manual](https://developer.x-plane.com/manuals/planemaker/)
defines this as the body's coefficient of drag based on frontal area and gives
0.1 as an example for an average fuselage. That example is **not a published
C182T coefficient**. A candidate with 0.100000000 is therefore a diagnostic
perturbation, not a sourced final calibration. The baseline and candidate must
be flown at matched conditions before the direction and size of any effect is
known. Body outline, gear, propeller efficiency and engine power remain
separate uncertainties.

`scripts/c182t_flight_model_experiment.py` produces a candidate ACF only when
it finds the generated CAP 487 identity and the original 0.200 fuselage record
exactly once. It refuses an existing output, never modifies the source, and
changes exactly one record. The installed aircraft was not changed.

Local staged packages, deliberately outside git and the installed aircraft:

| Package | ACF SHA-256 | State |
| --- | --- | --- |
| `/tmp/capvsar-c182t-calibration-baseline` | `eaae3c83…958b6dd` | Clean rebuild; byte-identical to installed ACF |
| `/tmp/capvsar-c182t-calibration-body-cd-0100` | `d37545e3…e4b672ef` | One-record experimental candidate |

The unified ACF diff has one change, `_body/0/_part_cd` from 0.200000003 to
0.100000000. No claim is made that 0.100 is the correct value.

To reproduce the clean baseline and candidate without touching the installed
aircraft, run from the repository root (the builder stages output and retains
a backup if it replaces an existing target):

```sh
python3 scripts/build_c182t_package.py \
  --flightgear-donor ~/.cache/capvsar/capvsar-flightgear-c182-pinned \
  --target-dir /tmp/capvsar-c182t-calibration-baseline
python3 scripts/c182t_flight_model_experiment.py \
  --acf /tmp/capvsar-c182t-calibration-baseline/Cessna_182T_G1000.acf \
  --output /tmp/capvsar-c182t-body-cd-0100.acf --body-cd 0.100
```

Copy the baseline package to a separate local candidate directory and replace
only its ACF with the generated candidate. `diff -qr` should list only that
ACF; a unified ACF diff should show the single record above. The `/tmp`
packages are local test artifacts and are not release packages.

## Acceptance sequence

1. Load each local package in X-Plane as a separate aircraft; verify the loaded
   ACF hash and aircraft identity before recording. Do not overwrite the
   installed CAP 487 package merely to run this experiment.
2. Repeat C1 at the same 3,100 lb, CG, standard-day weather, fairings and cowl
   flap configuration, with full throttle, propeller and mixture. Record a
   stable 60-second KTAS window, engine HP, RPM, manifold pressure, altitude,
   fuel flow and drift with `scripts/capture_flight_test.py` and
   `scripts/reduce_cruise_point.py`.
3. Repeat B1 at Vy with the same mass/CG and weather. Reduce a stable 30-second
   window with `scripts/reduce_climb_point.py`. A C1 improvement that worsens
   B1, or any new stability/handling defect, rejects this candidate.
4. Compare the candidate with the POH cruise-power grid at an independently
   chosen point (C2) before accepting any fuselage coefficient. The existing
   Group A stall points remain unflown; a high-speed match cannot validate them.

The simulator is not running in this stage and no flight result is available.
If the 0.100 trial is informative, the next step is to correct the actual Plane
Maker body and gear geometry against independent dimensions, then repeat the
performance points. Do not encode an experimental Cd as a builder default from
one speed measurement.


## 2026-10-11: propeller and gear corrected, drag calibrated, engine power explained

Tracker C18 (`docs/C182T_REVIEW_2026-10-11.md`). Flown in X-Plane 12.4.3 with
`scripts/c182t_perf_card.py`, which air-starts over open water west of Point
Loma, sets ISA sea level, calm, 3,100 lb (achieved 3,100 lb, error 0) and flies
on the aircraft's own GFC 700 (ALT hold for C1/C2, FLC 80 KIAS for B1). No
control surface was written. Traces in `~/.cache/capvsar/flight-tests/`, run
summaries in `docs/evidence/c182t-2026-10-11/`.

### What changed before flying (order A2-11)

* Physics propeller 79.0 in and TCDS pitch stops 14.9/31.7 deg (A2-2). Static
  full-throttle RPM 2318-2326, inside TCDS 3A13 2300-2400.
* Gear contact track 108.0 in and wheelbase 66.5 in, read back from the
  simulator (A2-3).

Effect on performance: small. C1 went from 130.1 to 131.4 KTAS. B1 was 739 fpm
at a mean 2,071 ft, still 11 % under the POH at that altitude (September's 825
was an extrapolation to sea level and is not directly comparable). The
propeller was right to fix and is not the cause of the shortfall.

### Engine power (A2-4): not an engine defect

Full-throttle ground sweep of the mixture lever (`--mixture-sweep`,
`c182t_ground_check_6_mixture.json`, 29.88 in.hg, 15 C):

| Mixture lever | RPM | HP | EGT C | GPH |
|---|---|---|---|---|
| 1.00 (full rich) | 2323 | 215.8 | 1362 | 18.7 |
| 0.88 | 2361 | 228.1 | 1488 | 18.1 |
| **0.84** | 2364 | **229.2** | 1521 | 17.6 |
| 0.76 | 2342 | 225.1 | 1576 | 16.2 |

The IO-540 model makes its rated 230 HP at best-power mixture. The 214-216 HP
of every earlier run was X-Plane's full-rich mixture, which is richer than best
power. The POH's climb and maximum-power figures assume the maximum-power fuel
flow placard, i.e. best power, so card points must be flown leaned to best
power (`--mixture best`) to be comparable.

### Fuselage drag coefficient

`_body/0/_part_cd`, the one record `c182t_flight_model_experiment.py` changes.
C2 is the independent point the acceptance sequence required: POH Figure 5-9
sheet 7, 6,000 ft, standard temperature, 2400 RPM / 23 in.hg = 79 % MCP, 143
KTAS, flown at 23.0 in.hg leaned to peak EGT (the POH's recommended lean).

| Cd | Mixture | C1 SL max (150) | C2 6,000 ft (143) | B1 at altitude vs POH Fig 5-8 |
|---|---|---|---|---|
| 0.200 (C172) | full rich | 131.4 (-12.4 %) | 127.0 (-11.2 %) | 739 vs 832 (-11.2 %) |
| 0.100 | full rich | 150.9 (+0.6 %) | 147.1 (+2.8 %) | 906 vs 810 (+11.9 %); 899 vs 804 with cowl open |
| **0.120** | full rich | 146.5 (-2.4 %) | 141.9 (-0.7 %) | 872 vs 814 (+7.2 %) |
| **0.120** | **best power** | **149.5 (-0.3 %)** | (peak EGT: 141.9) | **955 vs 806 (+18.4 %)** |

C2 engine: 172-173 HP at 2400 / 23.0 in.hg on every candidate, against the
POH's 79 % = 182 HP; peak EGT is leaner than best power, so the shortfall is
the same mixture effect.

Decision: **the builder now writes 0.120** (`ACF_PATCHES`, with this table in
the comment). It is a flight calibration of whole-airframe drag on the
C172's unconverted aerodynamic definition, not a measured fuselage coefficient.
At POH conditions it puts both cruise points within 1 % of the handbook. The
installed ACF is byte-identical to the flown 0.120 candidate (SHA-256
`11ff17d1f15ed3c7...cd89d8`): the build is deterministic.

### What is still wrong: climb at Vy is ~18 % too strong

With correct power and cruise-correct drag, B1 climbs 955 fpm where the POH
gives 806 at that altitude. No fuselage Cd fixes both: raising it to tame the
climb slows the cruise points by about the same proportion. The excess is a
low-speed effect - induced drag of the C172 wing definition at 3,100 lb, or
propeller efficiency at 80 KIAS with the C172 blade planform and the B3D36C431
pitch range. That is the Plane Maker geometry conversion A-1 has always
listed; record it there, not as a drag fudge.

`scripts/reduce_climb_point.py` now prints the POH Figure 5-8 rate at the mean
altitude actually flown, with its own verdict. The old comparison against the
sea-level 924 fpm flattered every run by about 10 % because the points are
flown at 2,000-2,900 ft.

### Trace index

| Trace | SHA-256 (16) | Condition |
|---|---|---|
| C1_runa2-1_20261011-214234 | fd362d43862eb651 | Cd 0.200, rich |
| B1_runa2-1_20261011-214438 | 25836d53d7bf3a96 | Cd 0.200, rich |
| C2_runa2-c2-base_20261011-221005 | 560ae8479c135e88 | Cd 0.200, peak EGT |
| C1_runa2-cd0100_20261011-215130 | 6c1d19c1f053b0a8 | Cd 0.100, rich |
| B1_runa2-cd0100_20261011-215335 | cfdc97d172d275a6 | Cd 0.100, rich |
| B1_runa2-cd0100-cowl_20261011-221821 | 74decf26987ca88c | Cd 0.100, rich, cowl open |
| C2_runa2-c2-cd0100_20261011-220203 | b78dda8d34f921ef | Cd 0.100, peak EGT |
| C1_runa2-cd0120_20261011-222500 | 0ba5d274b5a4629c | Cd 0.120, rich |
| B1_runa2-cd0120_20261011-222705 | e94c16db26300bce | Cd 0.120, rich |
| C2_runa2-c2-cd0120_20261011-223432 | c5223ac10cf83909 | Cd 0.120, peak EGT |
| C1_runa2-cd0120-best_20261011-224445 | 6dcd64872720ef43 | Cd 0.120, best power |
| B1_runa2-cd0120-best_20261011-224725 | 486e0650385b238e | Cd 0.120, best power |

Group A (stall speeds) remains unflown: the aircraft's autopilot cannot fly a
stall and no agent should be given one without the scoped exception described
in `docs/C182T_H0_CONTROL_LAW_FINDINGS.md`.
