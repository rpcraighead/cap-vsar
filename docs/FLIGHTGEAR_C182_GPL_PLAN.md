# FlightGear C182 exterior: prototype and production licensing plan

## Current decision

CAP V-SAR uses the HHS81 FlightGear C182 exterior for a **local evaluation
prototype**. The Apache-2.0 repository contains the fetch, conversion and build
recipes, but no donor mesh, texture, Blender file or generated donor-derived
object.

The pinned source is:

- repository: <https://github.com/HHS81/c182s>
- commit: `1359d63393c7fc9145953b081d151d93627e791a`
- commit archive SHA-256:
  `d81628fff8489af41d312c0e0bc14e1de2ac10a50d6c0c75f937441f81343fbe`
- license presented by GitHub and the repository root: GPL-2.0
- model source used by the converter: `Models/c182s.ac`; the donor's C182T
  variant references this shared exterior. `dev/C182S.blend` is that exterior's
  editable source (88 objects, matching `Models/c182s.ac` 1:1) and is the
  preferred source for later exterior model work. `dev/C182T.blend` is the
  donor's cockpit/interior model and holds no airframe geometry
- texture source: `Models/Liveries/Default.png`, with a CAP 487 registration
  added by the converter

The generated aircraft also contains files copied from the operator's licensed
Laminar Research C172 installation. The combined output is for local use and
must not be redistributed. Its root contains the donor GPL text, a prototype
notice and a machine-readable provenance manifest.

## Reproducing the local prototype

Fetch the reviewed donor into a cache outside the repository:

```bash
python3 scripts/fetch_flightgear_c182.py \
  ~/.cache/capvsar/capvsar-flightgear-c182-pinned
```

Build into a staging directory first:

```bash
python3 scripts/build_c182t_package.py \
  --flightgear-donor ~/.cache/capvsar/capvsar-flightgear-c182-pinned \
  --target-dir /tmp/cap-vsar-c182t-prototype
```

The builder converts the exterior to OBJ8 without Blender. It replaces the
stock C172 fuselage, wing, landing-gear, propeller, glass, light and broken-part
attachments while retaining the locally installed cockpit and systems. The
primary control surfaces and three-blade propeller use X-Plane datarefs.
When the downloaded CAP C172 artwork is available in `~/Documents/Civil Air
Patrol`, the same build remaps it onto the C182 and uses the approved N429CP
paint as the default; that optional step requires NumPy, SciPy, and Pillow.
The completed package is staged before replacing a target, and a prior
installed CAP aircraft is retained under `Output/capvsar-backups`.

## Production routes

The preferred route is written permission from every relevant copyright holder
to distribute the required exterior meshes and textures under Apache-2.0, CC
BY 4.0, or another compatible permissive license. Permission must cover the
actual source files and texture inputs, not merely the assembled FlightGear
aircraft.

If that permission is unavailable, the production design can keep a separate
GPL exterior source package. That package would contain the editable donor
source, conversion changes, generated OBJ8 files, derived textures, copyright
notices and the complete corresponding source under the applicable GPL terms.
The Apache CAP V-SAR repository would remain a separate work and would not
bundle GPL assets. Operators would combine the GPL exterior and their locally
licensed Laminar installation on their own machines. This packaging design
needs a license review before public release, especially around the resulting
aircraft package and X-Plane's proprietary files.

The fallback is a clean-room exterior made from authoritative dimensions and
independently licensed references. It should not trace, retopologize or extract
coordinates from a model whose license is incompatible with the intended
release.

## Production release gate

Before any public aircraft release:

1. Inventory the copyright and source history of `Models/c182s.ac`,
   `dev/C182S.blend`, `dev/C182T.blend`, the blank livery and every texture
   layer used.
2. Resolve whether each required asset is GPL-2.0-only or has a documented
   later-version or dual-license grant.
3. Select one production route above and record the decision in `NOTICE`.
4. Keep Laminar files out of every downloadable archive and source repository.
5. Provide all license texts, attribution, modification notices and complete
   corresponding source required by the selected route.
6. Have the packaging and notices reviewed before publishing a release.
7. Rebuild from a clean machine and confirm that no donor archive, generated
   donor object or proprietary simulator file has entered the Apache git tree.

## Technical acceptance still required

The local conversion proves the model can enter the build without reusing the
stock C172 exterior. It does not close aircraft-fidelity tracker item A-1.
Production acceptance still requires:

- X-Plane visual checks from external, cockpit and night views;
- control-surface, propeller, light, glass and door/cowl-flap animation checks;
- dimension and station comparison against an authoritative C182T three-view;
- texture, normal, LOD and frame-rate work suitable for repeated training use;
- Plane Maker geometry, mass, CG, control and aerodynamic calibration against
  the selected C182T POH; and
- regression flight tests after the exterior and flight-model coordinate
  systems are aligned.

## Decision D-7 — the production licence route is out of scope (2026-09-15)

**Ron's decision.** The production licensing route in "Production routes" and
"Production release gate" above is no longer carried as outstanding work on
A-1. The prototype stays local and the exterior work continues on technical
merit alone. Full reasoning belongs in the vault decisions file; this section
records the decision and, more usefully, what it does **not** change.

Ron's reasoning: the exterior is converging on the real C182T shape, so the
result is progressively less like the HHS81 donor's model and progressively
closer to what Cessna designed — which moves the question away from the GPL
donor rather than resolving it in the donor's favour.

That reasoning is sound about the *direction of travel*. Three things it does
not change, recorded so the next reader does not re-derive them:

**There is no percentage that clears derivation.** The corrections are
parametric transforms applied to the donor mesh at load time, and
`scripts/build_c182t_package.py` cannot produce an aircraft without the pinned
donor cache present — it refuses with "donor is incomplete". Every correction
in `scripts/c182t_corrections.json` is recorded as a transform *of* that mesh.
A build that cannot run without the GPL input is derivative however far the
vertices move, and no threshold in copyright says otherwise. This needs no
action, because the existing architecture already handles it correctly: the
donor stays outside the repository, the GPL text and provenance manifest ship
inside the generated package, and the repository itself stays Apache.

**The binding constraint on redistributing the BUILT PACKAGE is Laminar, not
the donor and not Cessna.** As this document already says at "Current decision"
and at release-gate item 4, the package is a Laminar Research C172 with our
exterior on it, and carries Laminar's cockpit and systems. That constraint does
not move with mesh accuracy, because it is not about the mesh. If redistributing
the aircraft is ever contemplated, this is the thing to resolve first.

**The repository mirror is unaffected.** Donor assets and Laminar files are
already excluded from the repo, so the public mirror referenced by D-6 is not
gated on any of this.

On Cessna specifically: design patents on a 1956-origin airframe are long
expired. What remains live is trademark and trade dress — the Cessna and
Skylane word marks and the tail script — none of which this package applies.
The aircraft wears CAP markings, which CAPR 130-2 governs on its own terms, and
the scheme is drawn from CAPP 130-2 rather than traced.

This is a scope decision about a local prototype and is not legal advice.
