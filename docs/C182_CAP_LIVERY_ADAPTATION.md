# C172 CAP artwork adapted to the local C182 prototype

The new local livery is **Civil Air Patrol (N429CP - C172 Adapted)**. It uses
the existing `~/Documents/Civil Air Patrol.zip` download and retains its
N429CP registration, shields, diagonal tail lettering, wing artwork, and
wheel-fairing stripes. No AI image generation is involved.

The archive contains no author, license statement, or original download URL.
The archive and derived textures remain local; they are not included in this
repository. The FlightGear donor constraints in
[FLIGHTGEAR_C182_GPL_PLAN.md](FLIGHTGEAR_C182_GPL_PLAN.md) also continue to apply.

## Reproduce the texture

Requires Python 3, NumPy, SciPy, and Pillow. Run from this worktree:

```bash
python3 scripts/adapt_cap_livery.py \
  --source "$HOME/Documents/Civil Air Patrol" \
  --c172 "$HOME/X-Plane 12/Aircraft/Laminar Research/Cessna 172 SP" \
  --aircraft "$HOME/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III" \
  --base "$HOME/.cache/capvsar/capvsar-flightgear-c182-pinned/Models/Liveries/Default.png" \
  --output "$HOME/Documents/Codex/cap-livery-adaptation/final"
```

The script projects the source artwork through the C172 exterior mesh,
adjusts body landmarks for the C182, and bakes colors into the C182's existing
4096-by-2048 UV atlas. Wings, underside, and wheel fairings have separate
projections. The C182 roof, white stabilizers, mechanical parts, and actual
window openings retain their own treatment. The C172's leading-edge lamp
recess is filled with adjacent donor paint because the C182 geometry differs.
Four pixels of texture bleed protect the UV seams during mipmap filtering.

The calibration and source draw ranges are specific to these installed
models. Recheck all views after changing either model. `adaptation.json`
records all input hashes, the arguments, and the generated texture hash.

Only `objects/flightgear_c182t.png` is needed as a livery override. The
aircraft builder now runs this mapper as part of a staged rebuild when the
downloaded C172 artwork is present at `~/Documents/Civil Air Patrol` (or
supplied with `--cap-c172-livery`). It uses the pinned donor's `Default.png`
as the base, preserving the approved texture hash below. The old CAP 487
livery stays intact. N429CP is the painted registration; the aircraft's
existing CAP 487 identity in the ACF is deliberately unchanged.

## Visual checks and installation

Render the actual installed OBJ8 mesh with the new texture:

```bash
/snap/bin/blender --background --threads 8 \
  --python scripts/render_c182_livery.py -- \
  "$HOME/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III" \
  "$HOME/Documents/Codex/cap-livery-adaptation/final/objects/flightgear_c182t.png" \
  "$HOME/Documents/Codex/cap-livery-adaptation/final/previews"
```

The renderer produces port, starboard, overhead, front quarter, rear quarter,
and underside views in the mesh's rest position. These are paint checks;
they do not test X-Plane animation, loading, lighting, or flight behavior.

Install the texture beneath the new named livery directory in the C182's
`liveries` folder. The local installation also includes an aircraft-selection
icon, a thumbnail, a provenance manifest, and a short README. Select the new
name in X-Plane's aircraft customization screen; switch back to the old
livery to undo the visual change.

The review artifacts are in `~/Documents/Codex/cap-livery-adaptation/`.
The before-install hash inventory and final installation verification record
whether any existing ACF, mesh, or livery file changed.

## Approved default installation — 2026-10-10

Ron approved this paint and requested that it be committed to the simulator
and Gitea. The installed C182 now uses it as its **default** exterior texture,
with matching aircraft-selection icons. The separate named livery remains
available, as does the original CAP 487 livery. The ACF, OBJ files, and saved
aircraft preferences were not changed.

Approved `objects/flightgear_c182t.png` SHA-256:

```text
00cab7bc6c2306f1351fb6e006cb05121b3b682a29ffe2d34a130d62ee9fe248
```

The three replaced files are `objects/flightgear_c182t.png`,
`Cessna_182T_G1000_icon11.png`, and `Cessna_182T_G1000_icon11_thumb.png`.
Their originals are backed up beneath X-Plane's
`Output/capvsar-backups/cap-livery-default-*/` directory. The original
`cap-livery-default.json` receipt gives the exact backup path and before/after
hashes; after a full aircraft rebuild, that receipt is retained with the
backed-up aircraft. Restore those three files from that earlier backup to
restore the previous default; selecting the old named livery also restores
its appearance.

Gitea contains the remapping script, renderer, and this installation record.
Generated textures and simulator assets remain outside Git, consistent with
the existing local-prototype packaging. The approved output was checked in
six rendered views and verified by hash after installation. An in-simulator
load check has not been performed.

## Rebuilding the aircraft

Use a Python interpreter with NumPy, SciPy, and Pillow installed, and build
to a separate target first:

```bash
python3 scripts/build_c182t_package.py \
  --target-dir "$HOME/X-Plane 12/Output/capvsar-c182-review" \
  --cap-c172-livery "$HOME/Documents/Civil Air Patrol"
```

The builder checks all 50 source ACF fields before copying, builds in a
sibling staging directory, and publishes only after conversion and texture
generation succeed. Replacing an existing target moves its previous version
to `Output/capvsar-backups` for an installed CAP aircraft. When the C172
artwork is available the build installs the N429CP paint as a named livery;
its icon pair is reused from the installed approved livery when present
(`--cap-icon-dir` selects another icon source). Since 2026-10-11 (tracker
A2-5) the aircraft's default paint is the generated CAP 487 one, so the skin,
the G1000/ATC tail number and the selection icon agree; `--default-livery
n429cp` restores the N429CP paint as the default.

The 2026-10-10 build with the corrected aileron and flap animations was
installed at `~/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III`. Its previous
aircraft is backed up at
`~/X-Plane 12/Output/capvsar-backups/Cessna 182T NAV III-ca3008d03211`.
The installed ACF and aircraft preferences match that backup byte for byte;
the default and named N429CP textures still have the approved SHA-256 above.
The CAP 487 named livery remains available. The installed OBJ changed only
its right-aileron axis and the two flap input ranges. X-Plane animation and
flight behavior still need an attended simulator check.
