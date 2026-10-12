#!/usr/bin/env python3
"""Check (and regenerate) the X-Plane name allowlist the Air Manager harness enforces.

Docs: docs/DECISIONS_2026-10-10.md D3 item 2.

The instruments under instruments/ call xpl_dataref_subscribe, xpl_dataref_write
and xpl_command with X-Plane names. tests/fixtures/xplane_names.json holds
exactly the sim/... names they use, with their Air Manager types. This script:

* scans instruments/**/*.lua for every "sim/..." string literal (comments are
  skipped),
* looks each one up in X-Plane's own Resources/plugins/DataRefs.txt and
  Commands.txt and exits non-zero on a name that is in neither, a declared
  type that disagrees with X-Plane's, or a write to a read-only dataref,
* regenerates the fixture from what it found (default), or with --check only
  reports drift without writing.

Laminar's files are never copied into the repo; the fixture carries only the
names this project uses. Where the files are absent (CI, another machine) the
script falls back to an offline check: every name in the Lua must be in the
committed fixture, and every fixture name must still be used.

    scripts/check_xplane_names.py            # regenerate the fixture
    scripts/check_xplane_names.py --check    # verify, do not write

The X-Plane directory comes from --xplane, then $X_PLANE_DIR, then
~/X-Plane 12.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "xplane_names.json"
INSTRUMENTS = ROOT / "instruments"

NAME_PREFIXES = ("sim/",)
DECLARED_RE = re.compile(
    r'"(sim/[^"]+)"\s*,\s*"((?:INT|FLOAT|DOUBLE)(?:\[\d+\])?|BYTE\[\d+\])"')


# -------------------------------------------------------------------- scanning --

def lua_strings(text: str) -> list[str]:
    """Every string literal in a Lua source, ignoring comments."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if text.startswith("--", i):
            m = re.match(r"--\[(=*)\[", text[i:])
            if m:
                close = "]" + m.group(1) + "]"
                j = text.find(close, i)
                i = n if j < 0 else j + len(close)
            else:
                j = text.find("\n", i)
                i = n if j < 0 else j
        elif ch in "\"'":
            j = i + 1
            buf = []
            while j < n and text[j] != ch:
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                    continue
                if text[j] == "\n":
                    break
                buf.append(text[j])
                j += 1
            out.append("".join(buf))
            i = j + 1
        elif ch == "[" and re.match(r"\[=*\[", text[i:]):
            m = re.match(r"\[(=*)\[", text[i:])
            close = "]" + m.group(1) + "]"
            j = text.find(close, i + len(m.group(0)))
            if j < 0:
                break
            out.append(text[i + len(m.group(0)):j])
            i = j + len(close)
        else:
            i += 1
    return out


def scan_instruments(root: Path = INSTRUMENTS) -> tuple[set[str], dict[str, str]]:
    """(names used, {name: type the Lua declares for it})."""
    names: set[str] = set()
    declared: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.lua")):
        text = path.read_text(encoding="utf-8")
        for s in lua_strings(text):
            if s.startswith(NAME_PREFIXES) and re.fullmatch(r"[A-Za-z0-9_/\[\].-]+", s):
                names.add(s)
        # Declared types are read from the code, with comments blanked first.
        code = re.sub(r"--[^\n]*", "", text)
        for name, kind in DECLARED_RE.findall(code):
            declared.setdefault(name, set()).add(kind)
    conflicts = {n: k for n, k in declared.items() if len(k) > 1}
    if conflicts:
        raise SystemExit(f"error: Lua declares conflicting types: {conflicts}")
    return names, {n: next(iter(k)) for n, k in declared.items()}


# ------------------------------------------------------------------ X-Plane data --

def am_type(txt_type: str, declared: str | None) -> str | None:
    t = txt_type.strip().lower()
    if t == "data":
        return declared if declared and declared.startswith("BYTE[") else None
    return t.upper()


def load_xplane(xplane_dir: Path):
    plugins = xplane_dir / "Resources" / "plugins"
    drefs_path, cmds_path = plugins / "DataRefs.txt", plugins / "Commands.txt"
    if not (drefs_path.is_file() and cmds_path.is_file()):
        return None
    datarefs: dict[str, tuple[str, bool]] = {}
    for line in drefs_path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and "/" in parts[0]:
            datarefs[parts[0].strip()] = (parts[1].strip(), parts[2].strip().lower() == "y")
    commands: set[str] = set()
    for line in cmds_path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(None, 1)
        if parts and "/" in parts[0]:
            commands.add(parts[0])
    return datarefs, commands


def build_from_xplane(names, declared, datarefs, commands):
    """-> (fixture dict, [error strings])."""
    errors: list[str] = []
    out_drefs: dict[str, dict] = {}
    out_cmds: list[str] = []
    for name in sorted(names):
        if name in datarefs:
            txt_type, writable = datarefs[name]
            kind = am_type(txt_type, declared.get(name))
            if kind is None:
                errors.append(f"{name}: X-Plane type '{txt_type}' needs a BYTE[n] declaration in the Lua")
                continue
            if name in declared and declared[name] != kind:
                errors.append(f"{name}: the Lua uses {declared[name]} but X-Plane has {kind}")
                continue
            out_drefs[name] = {"type": kind, "writable": writable}
        elif name in commands:
            out_cmds.append(name)
        else:
            errors.append(f"{name}: not in DataRefs.txt or Commands.txt")
    return {"datarefs": out_drefs, "commands": out_cmds}, errors


def write_checks(names_in_code: set[str], fixture: dict) -> list[str]:
    """A name written with xpl_dataref_write must be writable in X-Plane."""
    errors = []
    pat = re.compile(r"xpl_dataref_write\(\s*\"(sim/[^\"]+)\"")
    for path in sorted(INSTRUMENTS.rglob("*.lua")):
        for name in pat.findall(re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))):
            meta = fixture["datarefs"].get(name)
            if meta is not None and not meta["writable"]:
                errors.append(f"{name}: written by {path.relative_to(ROOT)} but read-only in X-Plane")
    return errors


# --------------------------------------------------------------------- main --

HEADER = (
    "Generated by scripts/check_xplane_names.py from the Lua under instruments/ "
    "and checked against X-Plane's DataRefs.txt and Commands.txt. Only the names "
    "this project uses are kept; Laminar's lists are not committed. Do not edit "
    "by hand."
)


def render(fixture: dict) -> str:
    doc = {"_comment": HEADER, "datarefs": fixture["datarefs"],
           "commands": sorted(fixture["commands"])}
    return json.dumps(doc, indent=2, sort_keys=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="verify only; exit 1 if the fixture is stale or a name is unknown")
    ap.add_argument("--xplane", type=Path,
                    default=Path(os.environ.get("X_PLANE_DIR", Path.home() / "X-Plane 12")))
    args = ap.parse_args(argv)

    names, declared = scan_instruments()
    committed = json.loads(FIXTURE.read_text(encoding="utf-8")) if FIXTURE.is_file() else None
    xp = load_xplane(args.xplane)

    if xp is None:
        print(f"note: X-Plane name files not found under {args.xplane}; "
              "checking the Lua against the committed fixture only", file=sys.stderr)
        if committed is None:
            print("error: no fixture and no X-Plane files", file=sys.stderr)
            return 1
        known = set(committed["datarefs"]) | set(committed["commands"])
        missing = sorted(names - known)
        stale = sorted(known - names)
        for n in missing:
            print(f"error: {n} is used by the instruments but is not in the fixture", file=sys.stderr)
        for n in stale:
            print(f"error: {n} is in the fixture but no instrument uses it", file=sys.stderr)
        for n, kind in declared.items():
            meta = committed["datarefs"].get(n)
            if meta and meta["type"] != kind:
                print(f"error: {n} is {meta['type']} in the fixture but the Lua uses {kind}", file=sys.stderr)
                missing.append(n)
        errors = write_checks(names, committed)
        for e in errors:
            print("error:", e, file=sys.stderr)
        return 1 if (missing or stale or errors) else 0

    datarefs, commands = xp
    fixture, errors = build_from_xplane(names, declared, datarefs, commands)
    errors += write_checks(names, fixture)
    for e in errors:
        print("error:", e, file=sys.stderr)
    if errors:
        return 1

    text = render(fixture)
    if args.check:
        current = FIXTURE.read_text(encoding="utf-8") if FIXTURE.is_file() else ""
        if current != text:
            print("error: tests/fixtures/xplane_names.json is out of date; "
                  "run scripts/check_xplane_names.py", file=sys.stderr)
            return 1
        print(f"ok: {len(fixture['datarefs'])} datarefs, {len(fixture['commands'])} commands")
        return 0

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(text, encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(ROOT)}: {len(fixture['datarefs'])} datarefs, "
          f"{len(fixture['commands'])} commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
