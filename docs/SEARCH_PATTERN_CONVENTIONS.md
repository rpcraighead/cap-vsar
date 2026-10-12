# Search-pattern conventions (decision D2)

The G1000 library in g1000-sar (`g1000_sar/mission.py`) is the reference
geometry. The flight planner is a front end for it: it keeps its box and
start/end-point inputs, and converts them to the library's datum form with the
two small functions below. Both repos assert against one fixture file.

## Where the two tools agree

| Convention | Planner | g1000-sar | Agree? |
|---|---|---|---|
| Heading input | true | true | yes |
| SS leg lengths / default turn | S, S, 2S, 2S ...; right | same | yes |
| SS naming | `DATUM`, `SSnn` = end of leg nn | `DATUM`, `SSnn` = end of leg nn | yes |
| SS leg count | API 1..60, UI 4..60 | 1..60 | yes |
| PS anchor | box corner in, first lane start out (conversion below) | datum = first lane start, no inset | yes |
| PS lane count | `ceil(width / spacing)` = library `legs` (conversion below) | `legs` given | yes |
| PS side | `turn_direction` (default right) | `turn` (default right) | yes |
| PS naming | `PS01` first lane start, 2 points per lane | same | yes |
| CS anchor | start/end in, centre of first sweep out (conversion below) | datum = centre of first sweep | yes |
| CS first sweep side | `first_turn` (default right) | `first_turn` (default right) | yes |
| CS sweep count | `ceil(distance / spacing)`, up to 60 | `legs` given | yes |

Every pattern point is placed as "along / across from the pattern's origin"
(`local_offset` in `app.py`, the library's `offset()`), not by walking leg by
leg, so the two agree to a few metres rather than drifting ~100 m over a large
square.

## The two conversions (`app.py`)

Both are pure functions with an inverse; the fixture test drives the planner's
generators through the datum-to-box direction.

**Parallel track** (`parallel_inputs_from_datum`, inverse `parallel_datum_from_box`)

    corner = datum moved spacing/2 across the axis, AWAY from the turn side
    width  = legs * spacing            (so ceil(width / spacing) == legs)
    datum  = corner moved min(spacing, width)/2 toward the turn side   (inverse)

The planner's generator puts the first lane half a spacing inside the corner,
on the turn side, which is the library's datum. A left-handed box is the
mirror image: lanes lie left of the axis and the corner is on its right.

**Creeping line** (`creeping_inputs_from_datum`, inverse `creeping_datum_from_endpoints`)

    distance = (legs - 0.5) * spacing
    inset    = min(spacing, distance) / 2
    start    = datum moved back `inset` along the heading
    end      = start moved `distance` along the heading

The generator puts the first sweep `min(spacing, distance)/2` along the axis
from the start and flies `ceil(distance / spacing)` sweeps. `(legs - 0.5)` is
never on a rounding boundary, so that count is exactly `legs`.

Expanding square needs no conversion: the planner's datum is the library's.

## Fixture workflow

1. `g1000-sar/scripts/make_pattern_fixtures.py` writes
   `tests/data/search_pattern_fixtures.json` (24 cases: 12 expanding square,
   6 parallel, 6 creeping line; west longitude, east, southern hemisphere,
   left and right turns; `tolerance_m` 25).
2. The file is copied byte for byte to
   `services/flightplanner/tests/data/search_pattern_fixtures.json`. Never edit
   the copy; regenerate it in g1000-sar and copy again.
3. `g1000-sar` asserts its library against the file; the planner's
   `tests/test_pattern_conventions.py` runs every case through the conversions
   and the generators (directly, and through `POST /api/sar/generate-pattern`)
   and asserts identical names and positions to `tolerance_m`.
4. A change to either side's geometry fails the other repo's test until the
   fixture is regenerated and the difference is explained.

Vendoring `g1000_sar/mission.py` into the planner is the next step once
`app.py` is split; the fixture is what makes that swap safe.

## Console push

`search_centre` is sent for every pattern and is the middle of the search
area: the datum for the expanding square, the middle of the box for the
parallel track, the middle of the sweeps for the creeping line (test:
`SearchCentre` in `test_pattern_conventions.py`, all fixture cases, 25 m).
The console anchors the alert circle and the beacon offset on it, never on
`waypoints[0]`.

## FMS file size

A `.fms` holds at most 99 entries counting the departure and destination
airport records, so a pattern may have 97 waypoints. 99 is the G1000
flight-plan size; X-Plane's real limit is unverified. The pattern dialog
warns, and `export-fms` refuses a longer pattern.

## Deliberately not changed

`scripts/fly_search_grid.py` still has its own parallel-track geometry: a box
centred on the datum with an odd leg count forced, pinned by
`tests/test_search_grid.py`. It was left alone on purpose because it belongs to
the autopilot flight-test work in progress. D2.6 (give it the same front-end
conversion and drop the odd-leg restriction) is still to do once that work is
done.
