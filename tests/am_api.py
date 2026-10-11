"""Air Manager 4.2 API contract for the offline Lua harness (docs/DECISIONS_2026-10-10.md D3).

Two tables live here and tests/am.py builds its Lua stubs from them:

1. SIGNATURES: every Air Manager function an instrument may call, with its
   exact positional signature. A stub raises a Lua error on an extra argument,
   a missing required argument or a wrong type; a function that is not listed
   is undefined, as it is in Air Manager.

   Sources: the AM 4.2 code snippets in
   ~/Documents/Air Manager 4.2 Home use/code_snippets/*/*.json, and the stock
   Sim Innovations G1000 instrument (button_add over a dial centre, the
   optional dial step argument, nil delay/interval on timer_start,
   video_stream_add with a source rectangle, img_add with a style string).

2. The X-Plane name allowlist: the sim/... datarefs and commands the
   instruments use (tests/fixtures/xplane_names.json, regenerated and checked
   against X-Plane's own DataRefs.txt/Commands.txt by
   scripts/check_xplane_names.py) plus the cap/df/* names the plugin registers,
   scraped from xplane/PI_capvsar_df.py every time the harness starts.

Type codes in a signature string, one per positional argument:

    s string   n number   f function   b boolean   a any value (must be present)
    c colour string (a name, #RGB, #RRGGBB or #RRGGBBAA; the CSS rgba() form is
      not one of Air Manager's accepted colours)

A trailing ``?`` means nil is accepted and, on a trailing argument, the
argument may be left out.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "xplane_names.json"
DF_PLUGIN = ROOT / "xplane" / "PI_capvsar_df.py"


def _switch_shapes() -> list[str]:
    # switch_add(img_pos0, img_pos1 [, img_pos2 ...], x, y, w, h, callback)
    return [" ".join(["s"] * k + ["n", "n", "n", "n", "f"]) for k in (2, 3, 4, 5)]


# name -> list of accepted shapes. A shape is a space-separated type string.
# "dataref_pairs" is a custom validator (alternating name/type then a callback).
SIGNATURES: dict[str, list[str] | str] = {
    # --- Sim Innovations variables (instrument <-> instrument bus) ---------
    "si_variable_create": ["s s a"],
    "si_variable_subscribe": ["s s f"],
    "si_variable_write": ["a a"],
    "si_variable_read": ["a"],
    # --- X-Plane ------------------------------------------------------------
    "xpl_dataref_subscribe": "dataref_pairs",
    "xpl_dataref_write": ["s s a"],
    "xpl_command": ["s"],
    # --- timers -------------------------------------------------------------
    # timer_start(delay, interval, cb) with either numeric field nil, or the
    # two-argument form timer_start(delay, cb) the stock G1000 uses.
    "timer_start": ["n? n? f", "n f"],
    "timer_stop": ["n?"],
    "timer_running": ["n?"],
    # --- graphics -----------------------------------------------------------
    "img_add": ["s n n n n s?"],
    "txt_add": ["s s n n n n"],
    "txt_set": ["n s"],
    "txt_style": ["n s"],
    "canvas_add": ["n n n n f?"],
    "canvas_draw": ["n f"],
    "video_stream_add": ["s n n n n", "s n n n n n n n n"],
    "visible": ["n b"],
    "opacity": ["n n"],
    "rotate": ["n n"],
    "move": ["n n n n? n?"],
    # --- controls -----------------------------------------------------------
    # button_add(up, down, x, y, w, h, press [, release]). Either image may be
    # nil, which makes a transparent hit region.
    "button_add": ["s? s? n n n n f f?"],
    # dial_add(img, x, y, w, h [, step], turn): ONE callback, called with
    # direction +1/-1. There is no press or release callback.
    "dial_add": ["s n n n n f", "s n n n n n f"],
    "switch_add": _switch_shapes(),
    "switch_set_position": ["n n"],
    "switch_get_position": ["n"],
    # --- sound --------------------------------------------------------------
    "sound_add": ["s", "s n"],
    "sound_volume": ["n n"],
    "sound_play": ["n"],
    "sound_loop": ["n"],
    "sound_stop": ["n"],
    # --- user properties ----------------------------------------------------
    "user_prop_add_enum": ["s s s s?"],
    "user_prop_add_integer": ["s n n n s?"],
    "user_prop_add_boolean": ["s b s?"],
    "user_prop_get": ["a"],
    # --- canvas drawing primitives (valid inside a canvas callback) ---------
    "_rect": ["n n n n"],
    "_circle": ["n n n"],
    "_triangle": ["n n n n n n"],
    "_move_to": ["n n"],
    "_line_to": ["n n"],
    "_stroke": ["c n?"],
    "_fill": ["c"],
    "_txt": ["s s n n"],
}

# Lua standard-library entry points Air Manager's sandbox does not provide.
# (The instrument comments say the same of require().)
SANDBOX_REMOVED = ("require", "dofile", "loadfile", "package", "io")

DATAREF_TYPE_RE = re.compile(r"^(?:(?:INT|FLOAT|DOUBLE)(?:\[\d+\])?|BYTE\[\d+\])$")


def lua_signature_table() -> str:
    """Render SIGNATURES as a Lua table literal for the preamble."""
    def q(s: str) -> str:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    lines = ["_SIG = {"]
    for name, shapes in SIGNATURES.items():
        if isinstance(shapes, str):
            lines.append(f"    {name} = {q(shapes)},")
        else:
            body = ", ".join(q(s) for s in shapes)
            lines.append(f"    {name} = {{ {body} }},")
    lines.append("}")
    return "\n".join(lines)


# ----------------------------------------------------------------- name tables --

def load_fixture(path: Path = FIXTURE) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


_DF_CALL_RE = re.compile(
    r"\b(i|f|b|in_int|in_float)\(\s*\"(cap/df/[a-z0-9_]+)\"")
_DF_TYPE = {"i": "INT", "in_int": "INT", "f": "FLOAT", "in_float": "FLOAT",
            "b": "BYTE[15]"}


def scrape_df_names(path: Path = DF_PLUGIN) -> dict[str, dict]:
    """cap/df/* datarefs the plugin registers: {name: {"type", "writable"}}.

    The plugin declares outputs with i()/f()/b() and the panel-written inputs
    with in_int()/in_float(); clear_average is the one hand-registered input.
    """
    text = path.read_text(encoding="utf-8")
    names: dict[str, dict] = {}
    for helper, name in _DF_CALL_RE.findall(text):
        names[name] = {
            "type": _DF_TYPE[helper],
            "writable": helper.startswith("in_"),
        }
    if '"cap/df/clear_average"' in text:
        names["cap/df/clear_average"] = {"type": "INT", "writable": True}
    if not names:
        raise RuntimeError(f"no cap/df/* names found in {path}")
    return names


def allowed_names() -> dict:
    """The merged allowlist the harness enforces.

    {"datarefs": {name: {"type", "writable"}}, "commands": [name, ...]}
    """
    fixture = load_fixture()
    datarefs = dict(fixture["datarefs"])
    for name, meta in scrape_df_names().items():
        datarefs.setdefault(name, meta)
    return {"datarefs": datarefs, "commands": list(fixture["commands"])}
