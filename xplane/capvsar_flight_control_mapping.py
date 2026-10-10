"""Generate and audit a session-specific ArduPlane candidate-only XPlane map.

The pinned SITL XPlane model sends independent DREF packets. These references
stage candidates in the plugin; they grant no native actuator authority.
"""
from __future__ import annotations

import copy
import json
import os
import re
import secrets
from pathlib import Path
from uuid import uuid4

NATIVE_TO_CHANNEL = {
    "sim/flightmodel/engine/ENGN_thro_use[0]": "throttle",
    "sim/joystick/yoke_roll_ratio": "roll",
    "sim/joystick/yoke_pitch_ratio": "pitch",
    "sim/joystick/yoke_heading_ratio": "yaw",
    "sim/cockpit2/controls/flap_ratio": "flap",
}
OVERRIDES = {
    "sim/operation/override/override_joystick",
    "sim/operation/override/override_throttles",
}
SESSION = re.compile(r"[a-f0-9]{32}\Z")


def candidate_prefix(session: str) -> str:
    if not isinstance(session, str) or not SESSION.fullmatch(session):
        raise ValueError("Expected a fresh 32-hex control session")
    return "cap/flight_control/candidate/%s/" % session


def generate_mapping(stock: dict, session: str) -> dict:
    prefix = candidate_prefix(session)
    if set(NATIVE_TO_CHANNEL) - set(stock):
        raise ValueError("Stock mapping lacks an expected native actuator")
    result = copy.deepcopy(stock)
    for native in OVERRIDES:
        result.pop(native, None)
    for native, channel in NATIVE_TO_CHANNEL.items():
        result[prefix + channel] = result.pop(native)
    validate_mapping(result, session)
    return result


def validate_mapping(mapping: dict, session: str) -> None:
    """Reject native writes and unrecognized escape paths before process start."""
    prefix = candidate_prefix(session)
    expected = {prefix + c for c in NATIVE_TO_CHANNEL.values()}
    if not isinstance(mapping, dict) or not expected <= set(mapping):
        raise ValueError("Incomplete candidate mapping")
    for key, spec in mapping.items():
        if key == "settings" or re.fullmatch(r"(?:axis|button)\d+", key):
            continue
        if key not in expected:
            raise ValueError("Unmediated ArduPlane mapping target: %s" % key)
        if not isinstance(spec, dict) or spec.get("type") not in ("range", "angle"):
            raise ValueError("Unexpected candidate mapping specification: %s" % key)


def mapping_json(stock_json: str, session: str) -> str:
    return json.dumps(generate_mapping(json.loads(stock_json), session), indent=2) + "\n"


def stage_bundle(stock_path: Path, output_dir: Path, session=None) -> dict:
    """Write attended-install inputs without touching a running simulator."""
    session = session or uuid4().hex
    mapping = mapping_json(Path(stock_path).read_text(), session)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = {"session": session, "secret": secrets.token_hex(32),
              "socket_path": "/tmp/capvsar-flight-control-%s.sock" % session}
    for name, content in (("xplane_plane.json", mapping),
                          ("capvsar_flight_control_config.json", json.dumps(config, indent=2) + "\n")):
        path = output_dir / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
    return {"session": session, "mapping": str(output_dir / "xplane_plane.json"),
            "plugin_config": str(output_dir / "capvsar_flight_control_config.json")}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stage a private candidate-only SITL mapping")
    parser.add_argument("stock", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(stage_bundle(args.stock, args.output_dir), indent=2))
