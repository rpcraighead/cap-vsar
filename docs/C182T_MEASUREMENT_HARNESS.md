# CAP 487 offline dimensional harness

Stage 2 of A-1 measures the pinned FlightGear donor against
[`c182t_dimension_master.json`](../scripts/c182t_dimension_master.json).
It changes no geometry and cannot accept an installed aircraft. A-1 remains open.
The [dimension master](C182T_DIMENSION_MASTER.md) owns source provenance and
proposed tolerances; the [GPL plan](FLIGHTGEAR_C182_GPL_PLAN.md) owns the release boundary.

## Reproduce

Run from the repository root. The fetcher defaults to the persistent donor cache
and verifies the pinned archive and required files without weakening any hashes.

```sh
python3 scripts/fetch_flightgear_c182.py
python3 scripts/measure_c182t.py --output ~/.cache/capvsar/measurements/c182t-stage2
# Identical numeric report without donor access:
python3 scripts/measure_c182t.py --fixture tests/fixtures/c182t_landmarks.json --output /tmp/c182t-fixture-replay
python3 -m unittest -v tests.test_flightgear_c182 tests.test_c182t_measurements
CAPVSAR_TEST_LIVE_DONOR=~/.cache/capvsar/capvsar-flightgear-c182-pinned python3 -m unittest -v tests.test_c182t_measurements
PYTHONPATH=. ~/.cache/capvsar/capvsar-planner-venv/bin/pytest tests/test_console.py tests/test_radio.py -q
```

Output is `report.json`, `side.svg`, `front.svg` and `top.svg`. JSON uses sorted
keys, no timestamps or output paths, and records the master and donor hashes.
SVGs show orthographic landmark projections, target/measured separation bars,
errors, tolerance bounds, source stations and all unknowns. Source station rulers
are reference-only: there is no validated donor firewall registration. Loading
arms and MAC stations cannot be treated as selected mesh vertices.

The numeric fixture is derived measurements, not a mesh or vertex cloud. Refresh
it deliberately with `--write-fixture tests/fixtures/c182t_landmarks.json` and
review the numeric diff. Donor meshes, textures, archives, PNGs, converted OBJs,
Blender files and Laminar files must remain outside this repository.

## Measurement rules

The harness reuses the converter's strict AC3D parser and fail-closed object
classification. Only vertices referenced by surfaces participate. Missing named
objects, empty selectors, invalid coordinates and broken bilateral symmetry
raise errors. The engineering symmetry threshold is 10 mm, separate from the
master's proposed dimensional tolerances.

- Spinner apex: minimum aft coordinate of `chrome_spinner`; length ends at the
  maximum aft coordinate of `Rudder`.
- Wingtip strobes: lateral extrema of `Strobe`. Structural tips are recorded
  separately from `Airframe`; no structural target is inferred by subtraction.
- Height: highest of the selected `Airframe` fin cap and `BeaconOff` top after
  ground posing. Both strobe and beacon selectors remain available in the donor,
  but those objects are currently absent from the emitted package.
- Fixed horizontal tail tips: lateral extrema of `Airframe` within the documented
  donor-native region `4 < aft < 6.3`, `abs(right) > 1.5`, `0.2 < up < 0.7` metres.
  This is a named-feature selector, not a sourced fuselage station or hinge line.
- Axles: centers of the referenced tire bounds of `MainWheel.L`, `MainWheel.R`
  and `FrontWheel`. Nominal contacts use each tire's lowest ordinate under its axle.
- Propeller: the converter's XML-derived hub and unit rotation axis, with radius
  equal to the maximum perpendicular distance of `Blade1`, `Blade2`, `Blade3`.
  Clearance uses the swept disc in the posed frame, independent of blade clocking.

The pose rotates about the transverse main-wheel contact midpoint until the
nose contact reaches the same plane, without roll. It reports the small left/right
contact residual. This is provisional: it does not establish the POH's two-inch
nose-strut extension. Length, height, wheelbase and prop clearance therefore stay
provisional even where their numeric comparisons are within tolerance. The TCDS
weight-and-balance leveling attitude is not used.

Structural bounds and actual emitted-object bounds retain separate object lists.
The latter includes light billboards, whose lateral extent exceeds the strobe
span; these bounds never substitute for named endpoints. All 9 unpublished items
remain unmeasured, as do donor FS values for the 15 source stations. Wing area
and turning radius remain outside mesh metrology.

## Initial results — 2026-09-11

| Dimension | Measured | Target | Result |
| --- | --- | --- | --- |
| Length | 28 ft 3.374 in | 29 ft | Provisional; -2.48% |
| Span with donor strobes | 35 ft 10.385 in | 36 ft | Within proposed tolerance; package strobes missing |
| Height | 9 ft 0.887 in | 9 ft 4 in | Provisional; -2.78% |
| Main wheel track | 8 ft 6.992 in | 9 ft | Fail; -4.64% |
| Wheelbase | 5 ft 4.427 in | 5 ft 6.5 in | Provisional; -3.12% |
| Propeller diameter | 79.255 in | 77.5–79.0 in hard bound | Fail |
| Horizontal tail span | 11 ft 11.026 in | 11 ft 8 in | Fail; +2.16% |
| Prop clearance | 11.254 in | 10.875 in ±1 in | Provisional; within proposed tolerance |

No dimensions have been accepted for release. `assert_accepted` fails when a
specified accepted dimension ceases to pass; its regression test uses a synthetic
accepted propeller followed by an out-of-bound diameter. No existing failed
measurement is relabelled accepted to make tests green.

Verification: two fresh donor-only exterior builds and their reports were byte
identical (14 files per output). The 10 converter tests plus 14 mandatory harness/
cache tests pass with all real donor/archive reads denied; the one explicitly
optional live comparison skips in that mode and passes when enabled. Console/
radio regression: 90 passed, 17 subtests passed (8,891 existing warnings).
All three SVGs were rendered and visually inspected. No simulator action occurred.

## Durable caches

Donor, pinned archive and relocated pytest environment now live under
`~/.cache/capvsar/` as `capvsar-flightgear-c182-pinned`,
`hhs81-c182s-1359d633.tar.gz`, and `capvsar-planner-venv`. Venv script prefixes
were updated and the regression suite ran using the durable executable.
Compatibility symlinks occupy the previous `/tmp` paths; originals are retained
with `.pre-cache-migration` suffixes until other agents finish. These backups are
not required for subsequent runs. Historical documented test commands have been
updated to the durable path.
