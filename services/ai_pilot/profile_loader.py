"""Load an aircraft profile from a TOML file.

One autopilot, many aircraft: the control laws are shared and everything that differs between
airplanes is data in `services/ai_pilot/profiles/<aircraft>.toml` (schema and how to add an aircraft:
`profiles/README.md`). This loader is deliberately strict:

* every key the profile needs must be present. The `AircraftProfile` dataclass still carries C172
  defaults for its tuning fields; an aircraft file must never inherit them by omission, so the
  loader supplies every field explicitly or refuses;
* unknown sections and keys are errors, so a typo cannot silently fall back to a default;
* types are checked (a speed is a number, a flag is a bool), and the dataclass's own `__post_init__`
  then checks the physics (no flap gate above Vfe, threshold window sane, and so on);
* a profile must say where its numbers came from (`[sources]`, including a `tuning` entry).

It builds the existing `AircraftProfile`, so controllers do not change when a profile moves from
Python to a file. The dataclass is imported inside the functions because `aircraft_profiles` imports
this module to build `PROFILES`.
"""
from __future__ import annotations

from pathlib import Path
import tomllib

PROFILE_DIR = Path(__file__).with_name("profiles")

# section -> key -> (AircraftProfile field, kind)
# kinds: float, bool, str, pair (two floats), strs3 (three strings), vfe (list of [ratio, kias])
SCHEMA = {
    "aircraft": {
        "key": ("key", "str"), "acf_name": ("acf_name", "str"),
        "display_name": ("display_name", "str"), "tuning_validated": ("tuning_validated", "bool"),
    },
    "speeds_kias": {
        "vr": ("vr_kias", "float"), "vx": ("vx_kias", "float"), "vy": ("vy_kias", "float"),
        "climb_enroute": ("climb_enroute_kias", "float"), "cruise": ("cruise_kias", "float"),
        "approach_initial": ("approach_initial_kias", "float"),
        "approach_intermediate": ("approach_intermediate_kias", "float"),
        "approach_clean": ("approach_clean_kias", "float"), "ils_final": ("ils_final_kias", "float"),
        "final_approach": ("final_approach_kias", "float"), "missed": ("missed_kias", "float"),
        "va": ("va_kias", "float"), "search": ("search_kias", "float"),
    },
    "vfe": {"stages": ("vfe_kias", "vfe")},
    "flaps": {
        "takeoff_ratio": ("takeoff_flap_ratio", "float"), "retract_kias": ("flap_retract_kias", "float"),
        "retract_agl_ft": ("flap_retract_agl_ft", "float"), "missed_ratio": ("missed_flap_ratio", "float"),
        "ils_ratio": ("ils_flap_ratio", "float"), "stage_names": ("flap_stage_names", "strs3"),
    },
    "landing": {
        "final_speed_add_kias": ("final_speed_add_kias", "float"),
        "threshold_kias": ("threshold_kias", "pair"),
        "touchdown_pitch_deg": ("touchdown_pitch_deg", "pair"),
        "touchdown_max_groundspeed_kt": ("touchdown_max_groundspeed_kt", "float"),
    },
    "engine": {"min_roll_rpm": ("min_roll_rpm", "float")},
    "throttle": {
        "taxi_base": ("taxi_base_throttle", "float"), "taxi_speed_gain": ("taxi_speed_gain", "float"),
        "taxi_max": ("taxi_max_throttle", "float"), "cruise_base": ("cruise_base_throttle", "float"),
        "ils_base": ("ils_base_throttle", "float"), "approach_base": ("approach_base_throttle", "float"),
    },
    "envelope": {"kias": ("envelope_kias", "pair")},
    "prop": {"constant_speed": ("constant_speed_prop", "bool"), "cruise_ratio": ("prop_cruise_ratio", "float")},
}
GATE_KEYS = {"ratio", "inside_m", "max_kias"}
# Tables a file may contain beyond SCHEMA: free-form sources, and the landing flap gates (array of
# tables under [flaps], which tomllib reports as a list inside the "flaps" table).
EXTRA_FLAPS_KEY = "landing_gates"


class ProfileError(ValueError):
    pass


def _number(value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileError("%s must be a number, got %r" % (where, value))
    return float(value)


def _convert(value, kind, where):
    if kind == "float":
        return _number(value, where)
    if kind == "bool":
        if not isinstance(value, bool):
            raise ProfileError("%s must be true or false, got %r" % (where, value))
        return value
    if kind == "str":
        if not isinstance(value, str) or not value.strip():
            raise ProfileError("%s must be a non-empty string" % where)
        return value
    if kind == "pair":
        if not isinstance(value, list) or len(value) != 2:
            raise ProfileError("%s must be a list of two numbers" % where)
        return tuple(_number(v, where) for v in value)
    if kind == "strs3":
        if (not isinstance(value, list) or len(value) != 3
                or any(not isinstance(v, str) or not v for v in value)):
            raise ProfileError("%s must be a list of three names" % where)
        return tuple(value)
    if kind == "vfe":
        if (not isinstance(value, list) or not value
                or any(not isinstance(s, list) or len(s) != 2 for s in value)):
            raise ProfileError("%s must be a list of [flap ratio, Vfe KIAS] stages" % where)
        return tuple((_number(r, where), _number(v, where)) for r, v in value)
    raise AssertionError(kind)


PERFORMANCE_KEYS = {"acf_sha256", "altitude_ft", "mass_kg", "conditions", "evidence", "points"}


def _performance(table, name):
    from .performance import PerformanceError, PerformanceTable
    if not isinstance(table, dict) or set(table) != PERFORMANCE_KEYS:
        raise ProfileError("%s: [performance] needs exactly %s" % (name, sorted(PERFORMANCE_KEYS)))
    points = table["points"]
    if (not isinstance(points, list) or not points
            or any(not isinstance(p, list) or len(p) != 3 for p in points)):
        raise ProfileError("%s: [performance].points must be a list of [throttle, vertical speed fpm, KIAS]" % name)
    try:
        return PerformanceTable(
            acf_sha256=_convert(table["acf_sha256"], "str", name + " [performance] acf_sha256"),
            altitude_ft=_number(table["altitude_ft"], name + " [performance] altitude_ft"),
            mass_kg=_number(table["mass_kg"], name + " [performance] mass_kg"),
            conditions=_convert(table["conditions"], "str", name + " [performance] conditions"),
            evidence=_convert(table["evidence"], "str", name + " [performance] evidence"),
            points=tuple(tuple(_number(x, name + " [performance] points") for x in p) for p in points))
    except PerformanceError as error:
        raise ProfileError("%s: %s" % (name, error)) from error


def load_profile(path):
    """Build an `AircraftProfile` from a TOML file, or raise `ProfileError` saying what is wrong."""
    from .aircraft_profiles import AircraftProfile, FlapGate
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ProfileError("%s: cannot read profile: %s" % (path.name, error)) from error
    allowed = set(SCHEMA) | {"sources", "performance"}
    unknown = set(data) - allowed
    if unknown:
        raise ProfileError("%s: unknown section(s) %s" % (path.name, sorted(unknown)))
    kwargs = {}
    for section, keys in SCHEMA.items():
        table = data.get(section)
        if not isinstance(table, dict):
            raise ProfileError("%s: missing [%s]" % (path.name, section))
        extra = set(table) - set(keys) - ({EXTRA_FLAPS_KEY} if section == "flaps" else set())
        if extra:
            raise ProfileError("%s: unknown key(s) in [%s]: %s" % (path.name, section, sorted(extra)))
        for key, (field, kind) in keys.items():
            if key not in table:
                raise ProfileError("%s: [%s] is missing %r (an aircraft file must state every value; "
                                   "nothing is inherited)" % (path.name, section, key))
            kwargs[field] = _convert(table[key], kind, "%s [%s] %s" % (path.name, section, key))
    gates = data["flaps"].get(EXTRA_FLAPS_KEY)
    if not isinstance(gates, list) or not gates:
        raise ProfileError("%s: [[flaps.landing_gates]] needs at least one gate" % path.name)
    parsed = []
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != GATE_KEYS:
            raise ProfileError("%s: each landing gate needs exactly %s" % (path.name, sorted(GATE_KEYS)))
        parsed.append(FlapGate(*(_number(gate[k], "%s landing gate %s" % (path.name, k))
                                 for k in ("ratio", "inside_m", "max_kias"))))
    kwargs["landing_flap_gates"] = tuple(parsed)
    sources = data.get("sources")
    if (not isinstance(sources, dict) or not sources
            or any(not isinstance(v, str) or not v.strip() for v in sources.values())):
        raise ProfileError("%s: [sources] must be a table of non-empty strings" % path.name)
    if "tuning" not in sources:
        raise ProfileError("%s: [sources] needs a 'tuning' entry saying where the controller "
                           "constants came from and whether they are validated" % path.name)
    kwargs["sources"] = dict(sources)
    if "performance" in data:
        kwargs["performance"] = _performance(data["performance"], path.name)
    try:
        return AircraftProfile(**kwargs)
    except ValueError as error:
        raise ProfileError("%s: %s" % (path.name, error)) from error


def load_profiles(directory=PROFILE_DIR):
    """Every `*.toml` in `directory`, keyed by the profile's `key`. Adding an aircraft is adding a file."""
    profiles = {}
    for path in sorted(Path(directory).glob("*.toml")):
        profile = load_profile(path)
        if profile.key in profiles:
            raise ProfileError("%s: duplicate profile key %r" % (path.name, profile.key))
        profiles[profile.key] = profile
    if not profiles:
        raise ProfileError("no aircraft profiles found in %s" % directory)
    return profiles
