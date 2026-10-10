# CAP 487 flight-model calibration: first controlled experiment

Status: **staged, not flown, not accepted**. A-1 remains open. This is X-Plane
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
aircraft, run from the repository root (use new target paths, because the
builder replaces its target directory):

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
