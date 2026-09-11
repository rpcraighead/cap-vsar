# Claude continuation — CAP 487 C182T dimensional correction (A-1)

Continue tracker item **A-1** from the shared CAP V-SAR worktree. The local
FlightGear exterior prototype is built and installed, but its dimensions have
not been accepted and its Plane Maker geometry still comes from the stock
C172S. This handoff is for the exterior measurement and correction stage.

## Shared-tree rules

This repository is shared by Claude, Codex and Gemini with no branch
isolation. Before editing anything:

1. Read the head of `CHANGELOG.md` and re-read A-1 in
   `docs/bugs/tracker.json`.
2. Run `git status --short` and inspect current diffs in every file you intend
   to edit. Preserve all concurrent changes and do not clean, reset, stash or
   overwrite the worktree.
3. Keep the simulated aircraft identity **CAP 487**. N499CP is a real C172S
   and must not be applied to the simulated C182T.
4. Do not edit `instruments/`, `xplane/PI_capvsar_df.py`,
   `tests/test_engine.py`, `tests/test_faceplate.py` or `tests/test_panel.py`
   in this unit. They contain other agents' work and are not needed to measure
   or correct the exterior mesh.
5. Treat `docs/FLIGHTGEAR_C182_GPL_PLAN.md` as a release boundary. Do not add
   the donor archive, donor mesh, `dev/C182T.blend`, donor textures, converted
   OBJ files or any Laminar file to this Apache repository.

## Current implementation

The prototype uses HHS81's FlightGear C182 project:

- repository: `https://github.com/HHS81/c182s`
- pinned commit: `1359d63393c7fc9145953b081d151d93627e791a`
- pinned archive SHA-256:
  `d81628fff8489af41d312c0e0bc14e1de2ac10a50d6c0c75f937441f81343fbe`
- validated local donor cache: `~/.cache/capvsar/capvsar-flightgear-c182-pinned`
- downloaded source archive: `~/.cache/capvsar/hhs81-c182s-1359d633.tar.gz`
- editable donor source: `dev/C182T.blend` inside that external cache

The relevant repository files are:

- `scripts/fetch_flightgear_c182.py` — pinned, checksum-verifying fetcher
- `scripts/convert_flightgear_c182.py` — strict AC3D-to-OBJ8 conversion,
  object selection, textures and animation pivots
- `scripts/build_c182t_package.py` — local Laminar C172-derived package build
- `tests/test_flightgear_c182.py` — converter, donor and attachment tests
- `docs/FLIGHTGEAR_C182_GPL_PLAN.md` — prototype and production license plan

The installed prototype is:

`/home/ron/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III`

The preserved pre-FlightGear package is:

`/home/ron/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III.pre-flightgear-20260911-20260911`

The clean staging build is `/tmp/capvsar-c182t-flightgear-prototype`. The
installed main exterior OBJ SHA-256 was
`1fc7adfd13cf77186d7c2e1caae85be49245a3b7d52f33dd8d108b3e6ad3ece9` and
matched staging when installed.

The current converter maps donor AC3D coordinates `(longitudinal, vertical,
left)` to X-Plane OBJ8 `(right, up, aft)` as `(-z, y, x)`. Animation centers
and axes in `MAIN_ROTATIONS` and `PROP_ROTATION` came from the pinned donor's
`Models/c182t.xml`. Any geometry correction that moves a hinge or propeller
axis must update those centers and axes from the same correction data.

The generated objects total 26,867 triangles. The main object's raw bounds are
approximately 8.03 m fore/aft, 10.91 m span and 3.22 m high; the combined
visible donor objects yield an overall length of roughly 8.50 m. The published
current Skylane headline dimensions are about 8.84 m long, 10.97 m span and
2.84 m high. These numbers are not yet an apples-to-apples comparison: raw
mesh extrema can include propeller, gear, lights or antennas, while published
height depends on the aircraft attitude and named endpoints. Do not use these
ratios as a global XYZ scale.

## Objective

Create a reproducible dimensional acceptance harness, establish comparable
C182T measurement definitions, and correct the exterior only where the
evidence shows it is wrong. The result must preserve cockpit alignment,
control-surface hinges, propeller alignment, UVs and left/right symmetry.

### 1. Establish the measurement master

Use authoritative C182T material for every target dimension. Record the exact
model/year, aircraft attitude, endpoints, units, source URL or document, page,
and any ambiguity. At minimum define:

- spinner/nose to aft-most tail length;
- structural wingtip-to-wingtip span;
- ground-to-highest structural point height at the specified attitude;
- propeller diameter and hub axis;
- main- and nose-wheel contact points and track/wheelbase;
- wing root, leading edge and trailing edge stations;
- horizontal- and vertical-tail stations and spans;
- firewall, windshield base, instrument-panel/cockpit reference and door
  opening stations; and
- aileron, flap, elevator and rudder hinge lines.

Headline length/span/height alone are insufficient to reshape the model. If a
needed station cannot be sourced, mark it unknown and stop before inventing a
plausible coordinate.

### 2. Build the measurement harness before changing geometry

Add a small, reviewable data profile and Python report path beside the existing
converter. It should:

- parse the pinned donor through the existing strict parser;
- identify named donor objects and explicit landmark selectors;
- report structural and all-rendered bounds separately;
- report each landmark and derived dimension in metres and feet/inches;
- compare measured values with sourced targets and tolerances;
- emit machine-readable JSON plus an orthographic side/front/top overlay that
  shows target stations and measured stations; and
- fail tests when a required landmark disappears, symmetry breaks, or an
  accepted dimension leaves tolerance.

Use named landmarks or documented vertex/object selectors. Avoid silently
using whichever vertex happens to be the current global minimum or maximum
for measurements whose endpoint has an operational definition.

### 3. Correct by aircraft region

Keep the cockpit/firewall/instrument-panel interface as the initial alignment
anchor because the package retains Laminar's locally installed cockpit.
Correct the cowling/spinner, cabin/tailcone, wing, landing gear and empennage
as separate regions. Preserve or regenerate UVs and normals. Maintain the
centreline and left/right symmetry explicitly. Recompute every affected
animation pivot from the corrected landmark profile.

Prefer an external Blender workflow based on the donor's editable
`dev/C182T.blend`, with a reproducible Blender Python correction/export script
stored in this repository. Keep the `.blend`, exports and generated GPL assets
outside git. If Blender is unavailable, the measurement harness and a concrete
correction specification are still useful deliverables; do not substitute a
whole-model non-uniform scale just to produce a changed OBJ.

### 4. Keep visual geometry and flight geometry distinct

This unit may measure and correct the exterior mesh. Do not claim A-1 fixed
while the ACF still has C172 Plane Maker body, wing, tail and gear geometry.
After exterior acceptance, make the Plane Maker calibration a separate,
source-backed stage using the selected C182T POH/TCDS. Visual mesh dimensions
must not be assumed to change X-Plane aerodynamics.

## Acceptance and verification

Before calling the exterior dimensional stage complete:

1. Rebuild from the pinned donor into a fresh `/tmp` directory and confirm the
   measurement report is reproducible.
2. Show before/after side, front and top overlays with each accepted target,
   measured value, error and tolerance.
3. Confirm OBJ8 structure, triangle ranges, symmetry, UV availability and all
   animation pivots in automated tests.
4. Load CAP 487 in X-Plane 12 and inspect external, cockpit and night views;
   control surfaces; three-blade propeller and disc; glass; lights; gear;
   cowling; and cockpit/exterior seams. State explicitly if X-Plane could not
   be run.
5. Run:

   ```text
   python3 -m unittest -v tests.test_flightgear_c182
   PYTHONPATH=. ~/.cache/capvsar/capvsar-planner-venv/bin/pytest tests/test_console.py tests/test_radio.py -q
   git diff --check
   ```

6. Re-read `docs/bugs/tracker.json` immediately before any status or evidence
   edit, regenerate `docs/BUG_TRACKER.md` with
   `python3 scripts/render_bug_tracker.py`, and add a dated entry at the top of
   `CHANGELOG.md` with the real results and unresolved work.

Keep A-1 open unless exterior dimensions, X-Plane visual/animation acceptance,
Plane Maker geometry and flight-model validation, and a production licensing
route are all complete. A completed measurement/correction stage should be
recorded as progress in A-1 rather than overstated as the full fix.

## Last known test baseline

```text
python3 -m unittest -v tests.test_flightgear_c182
Ran 5 tests in 0.003s
OK

PYTHONPATH=. ~/.cache/capvsar/capvsar-planner-venv/bin/pytest tests/test_console.py tests/test_radio.py -q
90 passed, 8891 warnings, 17 subtests passed in 3.30s
```

