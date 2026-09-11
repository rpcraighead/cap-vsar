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
  variant references this shared exterior, and `dev/C182T.blend` remains the
  preferred editable source for later model work
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
   `dev/C182T.blend`, the blank livery and every texture layer used.
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
