# Codex resume prompt — C182T dimensional measurement harness (A-1 stage 2)

Paste this entire prompt into Codex.

---

Continue tracker item **A-1** from the shared CAP V-SAR worktree. This unit is
the dimensional measurement harness: stage 2 of
`docs/bugs/CLAUDE_RESUME_C182_DIMENSIONS.md`. Stage 1 is already done and its
output is your input contract.

This unit is **entirely offline**. Do not launch, drive, reload or screenshot
X-Plane, and do not modify anything under `/home/ron/X-Plane 12/`. The simulator
is a single shared resource and another agent is working in it.

## Shared-tree rules

This repository is shared by Claude, Codex and Gemini with no branch isolation.

1. Read the head of `CHANGELOG.md` and re-read A-1 in `docs/bugs/tracker.json`
   before editing anything. Re-read the CHANGELOG head again immediately before
   you insert your own entry — other agents insert entries while you work.
2. Run `git status --short` and inspect diffs in every file you intend to edit.
   Preserve all concurrent changes. Do not clean, reset, stash or overwrite.
3. Do not edit `instruments/`, `xplane/`, `services/ai_pilot/`,
   `tests/test_engine.py`, `tests/test_faceplate.py`, `tests/test_panel.py`, or
   `scripts/build_c182t_package.py`. They are other agents' lanes.
4. Keep the simulated aircraft identity **CAP 487**. N499CP is a real C172S and
   must never be applied to the simulated C182T.
5. `docs/FLIGHTGEAR_C182_GPL_PLAN.md` is a release boundary. Never add the donor
   archive, donor mesh, `dev/C182T.blend`, donor textures, converted OBJ files,
   generated PNGs or any Laminar file to this Apache-2.0 repository.

## State you are building on

The exterior prototype now renders correctly. On 2026-09-11 a triangle-winding
bug was found and fixed, and confirmed in X-Plane: the cabin is solid, the
magenta firewall artifact is gone, and the silhouette reads as a correct C182.
Before that fix, measurements of the rendered aircraft were meaningless. They
are meaningful now — that is why this unit is worth doing.

**Non-obvious facts. Violating any of these silently reintroduces a solved bug.**

- **X-Plane winds triangles OPPOSITE to the stored vertex normal.** Laminar's own
  `objects/fuselage.obj` shows 0.0% winding/normal agreement. AC3D winds the other
  way, so `_build_mesh` emits each triangle's refs reversed while normals stay
  computed from the original order. `WindingConventionTests` guards this. Do not
  "fix" it back.
- Bucket selection in `scripts/convert_flightgear_c182.py` is **fail-closed** by
  design. `assert_all_objects_classified` raises on any donor object matching
  neither an output bucket nor a documented exclusion
  (`DELIBERATELY_EXCLUDED`, `INTERIOR_ONLY`, `KNOWN_UNCONVERTED`). If the donor
  changes, the build **should** fail rather than silently drop geometry. Keep it
  that way.
- Five donor objects are still unconverted and listed in `KNOWN_UNCONVERTED`:
  `Strobe`, `NavLight.L`, `NavLight.R`, `NavlightTransp`, `BeaconOff`. Two of
  these matter to you directly — see the span and height notes below.

## Your input contract

`scripts/c182t_dimension_master.json` — the sourced measurement master. 10
targets, a 15-entry fuselage station ladder, and 9 explicitly unknown items.
Every target carries endpoints, reference attitude, source document, page and a
proposed tolerance. `docs/C182T_DIMENSION_MASTER.md` is the provenance and
reasoning behind it.

Targets come from the FAA-approved Cessna 182T NAV III GFC 700 POH
(182TPHBUS-00/-01), FAA TCDS 3A13 Rev 66, and Cessna's Dec 2015 Rev C
Specification and Description. All three are recorded with URL, page and SHA-256.
**Do not re-source them and do not commit the PDFs** — they are third-party
copyrighted documents.

Three contract points that are easy to get wrong:

- **Attitude.** Every published length and height is measured in POH *normal
  ground attitude*: "nose strut showing approximately 2 inches of strut, and
  wings level". The TCDS leveling means (tailcone at FS 139.65 and 171.65) is a
  weight-and-balance attitude only and must not be used for three-view
  dimensions. The donor mesh is NOT in normal ground attitude — its nose wheel
  contact sits 131 mm *below* its main-wheel plane, a pose impossible on flat
  ground. **Re-pose the mesh about the main-wheel axis before comparing any
  vertical target.** Raw mesh extrema compared against 9 ft 4 in are not a
  measurement.
- **Span includes the wingtip strobes**, per the POH note. The structural span
  without strobes is not published and must not be derived by subtraction. Note
  the consequence: `Strobe` is currently unconverted, so a span measured from the
  emitted package today measures structure only and is not comparable to the
  36 ft 0 in target. Report that condition rather than papering over it.
- **Length runs spinner apex to rudder trailing edge**, verified against the
  three-view at 450 dpi. Not the propeller, and not a global bounding box.

## Objective

Build the reproducible measurement harness described in section 2 of
`docs/bugs/CLAUDE_RESUME_C182_DIMENSIONS.md`. Place it beside the existing
converter. It must:

1. Parse the pinned donor through the existing strict parser in
   `scripts/convert_flightgear_c182.py`. Do not write a second parser.
2. Identify landmarks by **named donor objects and documented selectors**, never
   by whichever vertex happens to be the current global minimum or maximum.
   Derived landmarks must be derived: propeller diameter and ground clearance
   come from the hub axis and disc radius, because the donor's blade clocking is
   arbitrary and the lowest modelled blade vertex is meaningless.
3. Report **structural bounds and all-rendered bounds separately**, so
   ground-service clutter, tiedowns and light lenses can never silently set an
   extremum.
4. Report every landmark and derived dimension in **metres and feet/inches**.
5. Compare measured values against the master's targets and tolerances, and
   treat the propeller as a hard certification bound (77.5–79.0 in), not a
   percentage error.
6. Emit machine-readable JSON plus orthographic side/front/top overlays showing
   target stations against measured stations.
7. **Fail closed on the 9 unknowns.** Items such as wing root leading edge,
   hinge-line stations, tail stations and individual gear stations are not
   published. Report them as unmeasured. Do not substitute a plausible
   coordinate — that is the single most important rule in this unit.

## Tests — read this before writing any

The existing suite is deliberately **donor-free**: all 10 tests pass without the
136 MB donor cache, using a synthetic AC3D fixture and patched hashes. Keep that
property. A test that needs the donor will either skip silently on every clean
checkout (passing vacuously, assuring nothing) or fail red for everyone.

The licence-safe way to test real measurements: commit a **derived landmark
fixture** — the measured numbers as JSON, no vertices, no geometry — pinned to
the donor archive SHA-256 already recorded in the master. Numeric measurements of
a GPL mesh are not a distribution of that mesh. Tests then assert
fixture-versus-target always, and fixture-versus-live-donor only when the cache
is present. Regressions become a reviewable diff instead of a re-run.

Per the stage-2 spec, tests must fail when a required landmark disappears, when
left/right symmetry breaks, or when an accepted dimension leaves tolerance.

## Second, smaller unit — cache-path hygiene

Independent of the harness and safe to do first.

Cache migration completed during stage 2: the pinned donor, archive and pytest venv now live under `~/.cache/capvsar/`:

    ~/.cache/capvsar/capvsar-flightgear-c182-pinned     136 MB donor cache
    ~/.cache/capvsar/hhs81-c182s-1359d633.tar.gz        pinned archive
    ~/.cache/capvsar/capvsar-planner-venv               the venv the test baseline depends on

These durable paths replace the original `/tmp` locations. The fetcher uses this cache by default and retains the same pinned checksum checks.

## Acceptance and verification

Before reporting this unit complete:

1. Rebuild from the pinned donor into a fresh directory and confirm the
   measurement report is byte-reproducible.
2. Show the overlays with each accepted target, measured value, error and
   tolerance.
3. Confirm the full suite still runs **without the donor cache present**.
4. Run:

   ```text
   python3 -m unittest -v tests.test_flightgear_c182
   PYTHONPATH=. ~/.cache/capvsar/capvsar-planner-venv/bin/pytest tests/test_console.py tests/test_radio.py -q
   git diff --check
   ```

5. Re-read `docs/bugs/tracker.json` immediately before any status or evidence
   edit, regenerate `docs/BUG_TRACKER.md` with
   `python3 scripts/render_bug_tracker.py`, and add a dated entry at the top of
   `CHANGELOG.md` with real results and unresolved work.

Record this as **progress** in A-1. Do not mark A-1 fixed. A-1 stays open until
exterior dimensions, X-Plane visual acceptance, Plane Maker geometry, flight-model
validation and a production licensing route are all complete — and Plane Maker
geometry is still entirely stock C172, with 0 of 40 ACF patches touching wing,
body, gear or tail.

## Last known test baseline

```text
python3 -m unittest tests.test_flightgear_c182
Ran 10 tests in 0.002s
OK

PYTHONPATH=. ~/.cache/capvsar/capvsar-planner-venv/bin/pytest tests/test_console.py tests/test_radio.py -q
90 passed, 8891 warnings, 17 subtests passed
```

`git diff --check` reports one pre-existing blank-line-at-EOF warning in
`docs/BOARD.md`, which is another agent's file. Leave it alone.

## Out of scope for this unit

Do not correct any geometry. Do not touch the CAP 487 registration texture
placement, the five unconverted light fixtures, the Plane Maker aerodynamic
model, or anything in the running simulator. A measurement harness that reports
honestly — including honestly reporting what it cannot measure — is the whole
deliverable.
