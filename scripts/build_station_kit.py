#!/usr/bin/env python3
"""
Build a self-contained install kit for one CAP V-SAR aircraft station (O-2).

Before this, standing up a second or third aircraft meant hand-editing
CONSOLE/CALLSIGN/PLUGIN_KEY inside xplane/PI_capvsar_df.py per station, which
is exactly the failure mode O-2 tracked: the tracked plugin source could never
be identical across stations, so deploy_xplane_plugin.py's hash check stopped
meaning anything. This script generates the one file that's allowed to differ
per station - capvsar_station.ini - and bundles it with an unmodified copy of
the plugin and the Air Manager instruments into something a member can unpack
next to their own X-Plane and Air Manager installs.

Usage:
  python3 scripts/build_station_kit.py --callsign CAP-2 \\
      --console https://192.0.2.151 [--plugin-key KEY] [--zip]

What's in the kit:
  PI_capvsar_df.py       tracked plugin source, byte-identical across stations
  capvsar_station.ini    this station's console URL, callsign, plugin key
  instruments/           Becker 517, RT-600, TDFM-136B, GMA 1347 (station-agnostic)
  README.md              where each piece goes

What's deliberately NOT in the kit, and why:
  - The C182T G1000 aircraft package. scripts/build_c182t_package.py derives it
    from the recipient's own Laminar Cessna 172SP install (SOURCE_DIR is a path
    on the *building* machine); it isn't redistributable content and can't be
    bundled generically. Point the recipient at that script instead.
  - A CA certificate. Nothing under this repo root ships one - it's issued per
    deployment on ms01. Hand it over separately (see docs/CONNECT.md for the
    equivalent Mumble/WireGuard onboarding pattern this reuses).
"""
from __future__ import annotations

import argparse
import py_compile
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_SOURCE = ROOT / "xplane" / "PI_capvsar_df.py"
INSTRUMENTS_SOURCE = ROOT / "instruments"
DEFAULT_CONSOLE = "https://192.0.2.151"

KIT_README = """\
# CAP V-SAR station kit — {callsign}

Built for console {console}.

## 1. X-Plane plugin

Copy both files into your X-Plane XPPython3 plugins folder, keeping them
side by side:

    X-Plane 12/Resources/plugins/PythonPlugins/PI_capvsar_df.py
    X-Plane 12/Resources/plugins/PythonPlugins/capvsar_station.ini

`PI_capvsar_df.py` is identical to every other station's copy — it reads
`capvsar_station.ini` at startup for this aircraft's console address,
callsign, and plugin key. Don't edit the .py; edit the .ini if anything
here needs to change later.

## 2. Air Manager instruments

Copy the four folders under `instruments/` into your Air Manager
instruments directory (Air Manager reads each one from its own folder,
same as any stock instrument). These are the same for every station —
nothing in them is specific to {callsign}.

## 3. Voice net

Not included here — follow docs/CONNECT.md from the project repo to join
the Mumble mission net, and ask the exercise controller for a WireGuard
peer if you're off the lab LAN.

## 4. Aircraft package and CA certificate

Not bundled — see the top of `scripts/build_station_kit.py` in the repo for
why, and who to ask instead. Install ms01's CA certificate in the operating
system trust store before starting X-Plane. On Linux, the repository's
`scripts/launch_xplane_cap_vsar.sh` supplies a process-local CA bundle without
changing system-wide trust. The plugin will reject an untrusted certificate.
"""


KIT_MARKER = ".capvsar-kit"


def prepare_out_dir(out_dir: Path) -> Path:
    """Make `out_dir` an empty directory, refusing anything we did not create.

    V2-9: this was `if out_dir.exists(): shutil.rmtree(out_dir)` on whatever
    `--out` named. `--out ~` erased a home directory, `--out .` the checkout.
    Deleting a tree is the one operation here that cannot be undone, so it is
    now allowed only for a directory this script made: either it does not
    exist, or it is empty, or it carries the marker file a previous kit build
    left behind.
    """
    out_dir = out_dir.expanduser().resolve()

    forbidden = [Path.home().resolve(), Path("/"), ROOT.resolve()]
    if out_dir in forbidden or out_dir in Path(out_dir).parents:
        raise SystemExit(f"refusing to build a kit into {out_dir}")
    for parent in forbidden:
        if parent == out_dir:
            raise SystemExit(f"refusing to build a kit into {out_dir}")

    if out_dir.exists():
        if not out_dir.is_dir():
            raise SystemExit(f"{out_dir} exists and is not a directory")
        contents = list(out_dir.iterdir())
        if contents and not (out_dir / KIT_MARKER).exists():
            raise SystemExit(
                f"{out_dir} is not empty and was not created by this script "
                f"(no {KIT_MARKER}). Refusing to delete it - choose an empty "
                f"directory or remove it yourself.")
        shutil.rmtree(out_dir)

    out_dir.mkdir(parents=True)
    (out_dir / KIT_MARKER).write_text(
        "Created by scripts/build_station_kit.py. This file marks the "
        "directory as safe for the script to replace on the next build.\n")
    return out_dir


def build(callsign: str, console: str, plugin_key: str, out_dir: Path, make_zip: bool) -> Path:
    py_compile.compile(str(PLUGIN_SOURCE), doraise=True)

    out_dir = prepare_out_dir(out_dir)

    shutil.copy2(PLUGIN_SOURCE, out_dir / "PI_capvsar_df.py")

    ini_lines = ["[station]", f"console = {console}", f"callsign = {callsign}"]
    if plugin_key:
        ini_lines.append(f"plugin_key = {plugin_key}")
    (out_dir / "capvsar_station.ini").write_text("\n".join(ini_lines) + "\n")

    instruments_out = out_dir / "instruments"
    shutil.copytree(INSTRUMENTS_SOURCE, instruments_out)

    (out_dir / "README.md").write_text(KIT_README.format(callsign=callsign, console=console))

    print(f"[+] Kit built: {out_dir}")
    print(f"    plugin:      {out_dir / 'PI_capvsar_df.py'}")
    print(f"    station ini: {out_dir / 'capvsar_station.ini'}  (console={console}, callsign={callsign})")
    print(f"    instruments: {instruments_out}")

    if make_zip:
        zip_path = out_dir.with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in out_dir.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(out_dir.parent))
        print(f"[+] Zipped:    {zip_path}")

    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--callsign", required=True, help="e.g. CAP-2")
    parser.add_argument("--console", default=DEFAULT_CONSOLE, help=f"default: {DEFAULT_CONSOLE}")
    parser.add_argument("--plugin-key", default="", help="CAPVSAR_TOKEN_PLUGIN value for this station, if set")
    parser.add_argument("--out", type=Path, default=None,
                         help="default: output/station-kits/<callsign>/")
    parser.add_argument("--zip", action="store_true", dest="make_zip", help="also produce a .zip alongside the folder")
    args = parser.parse_args()

    out_dir = args.out or (ROOT / "output" / "station-kits" / args.callsign)
    build(args.callsign, args.console, args.plugin_key, out_dir, args.make_zip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
