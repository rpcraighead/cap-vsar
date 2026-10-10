"""Reproducible first-cycle scenarios, trace recorder and independent observer.

The observer only consumes aircraft snapshots. It does not accept controller
completion messages. Criteria are engineering trial criteria, not POH limits.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import socket
import time


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class BridgeClient:
    """Local Unix socket protocol; no raw UDP control path."""
    def __init__(self, config):
        self.config = config

    def request(self, action, **arguments):
        payload = {**arguments, "action": action, "secret": self.config["secret"]}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(1.0)
            conn.connect(self.config["socket_path"])
            conn.sendall(json.dumps(payload, allow_nan=False).encode() + b"\n")
            raw = bytearray()
            while b"\n" not in raw:
                part = conn.recv(4096)
                if not part or len(raw) + len(part) > 65536:
                    raise RuntimeError("Incomplete or oversized bridge response")
                raw.extend(part)
        response = json.loads(raw.partition(b"\n")[0])
        if "error" in response:
            raise RuntimeError(response["error"])
        return response


@dataclass(frozen=True)
class Scenario:
    name: str = "c172-first-cycle-v1"
    aircraft_name: str = "Cessna_172SP_G1000.acf"
    heading_mag_deg: float = 90.0
    turn_deg: float = 20.0
    altitude_ft: float = 4500.0
    kias: float = 100.0
    heading_tolerance_deg: float = 3.0
    altitude_tolerance_ft: float = 75.0
    speed_tolerance_kt: float = 3.0
    bank_tolerance_deg: float = 3.0
    vvi_tolerance_fpm: float = 150.0
    dwell_s: float = 10.0
    phase_deadline_s: float = 120.0
    wall_deadline_s: float = 600.0
    max_sim_gap_s: float = 0.25
    max_wall_gap_s: float = 0.50

    def __post_init__(self):
        for key, value in asdict(self).items():
            if isinstance(value, (int, float)) and (not math.isfinite(value) or isinstance(value, bool)):
                raise ValueError("Invalid scenario value: " + key)
        for key in ("heading_tolerance_deg", "altitude_tolerance_ft", "speed_tolerance_kt",
                    "bank_tolerance_deg", "vvi_tolerance_fpm", "dwell_s", "phase_deadline_s",
                    "wall_deadline_s", "max_sim_gap_s", "max_wall_gap_s"):
            if getattr(self, key) <= 0:
                raise ValueError("Scenario tolerance/duration must be positive")
        if not (5 <= abs(self.turn_deg) <= 30 and 4000 <= self.altitude_ft <= 5000
                and 90 <= self.kias <= 120 and self.phase_deadline_s > self.dwell_s):
            raise ValueError("Scenario outside initial engineering test envelope")
        if abs(self.turn_deg) <= 2 * self.heading_tolerance_deg:
            raise ValueError("Heading capture bands must not overlap")

    def manifest(self):
        return asdict(self)


class CycleObserver:
    """Establish, observe a heading capture, then recover the original heading."""
    PHASES = ("establish", "maneuver", "recover")

    def __init__(self, scenario=Scenario()):
        self.scenario = scenario
        self.phase_index = 0
        self.outcome = "INCOMPLETE"
        self.reason = None
        self.previous = None
        self.session = None
        self.aircraft = None
        self.phase_started = None
        self.wall_started = None
        self.stable_since = None
        self.transitions = []
        self.samples = 0

    @property
    def target(self):
        s = self.scenario
        return {"heading_mag_deg": (s.heading_mag_deg + (s.turn_deg if self.phase_index == 1 else 0)) % 360,
                "altitude_indicated_ft": s.altitude_ft, "kias": s.kias}

    def fail(self, reason):
        self.outcome, self.reason = "FAIL", reason
        return self.report()

    def observe(self, snapshot):
        if self.outcome == "PASS":
            return self.fail("Samples after completed cycle")
        if self.outcome != "INCOMPLETE":
            return self.report()
        s = self.scenario
        try:
            v = snapshot["values"]
            keys = ("sim_time_s", "paused", "heading_mag_deg", "altitude_indicated_ft", "kias",
                    "roll_deg", "vvi_fpm", "agl_m", "on_ground")
            if any(type(v[k]) not in (float, int) or not math.isfinite(v[k]) for k in keys):
                return self.fail("Invalid or nonfinite telemetry")
            sim, wall, frame = v["sim_time_s"], snapshot["wall_time_s"], snapshot["frame"]
            if (type(wall) not in (float, int) or not math.isfinite(wall)
                    or type(frame) is not int or frame < 1
                    or snapshot["schema"] != "capvsar.telemetry.v1"
                    or snapshot["phase"] != "after_flight_model"):
                return self.fail("Invalid snapshot identity or timing")
            if snapshot["aircraft"]["name"] != s.aircraft_name:
                return self.fail("Wrong aircraft")
            if self.previous is None:
                self.session, self.aircraft = snapshot["session"], snapshot["aircraft"]
                self.phase_started, self.wall_started = sim, wall
            if snapshot["session"] != self.session or snapshot["aircraft"] != self.aircraft:
                return self.fail("Session or aircraft changed")
            if v["paused"] or v["on_ground"]:
                return self.fail("Pause or ground intervention")
            if self.previous is not None:
                old_sim, old_wall, old_frame = self.previous
                if frame == old_frame:
                    return self.fail("Duplicate telemetry frame")
                if (frame < old_frame or sim <= old_sim or wall <= old_wall):
                    return self.fail("Simulation reset or non-increasing telemetry")
                if sim - old_sim > s.max_sim_gap_s or wall - old_wall > s.max_wall_gap_s:
                    return self.fail("Telemetry gap exceeds criterion")
            self.previous = sim, wall, frame
            self.samples += 1
            if wall - self.wall_started > s.wall_deadline_s:
                return self.fail("Wall deadline exceeded")
            if (not 80 <= v["kias"] <= 140 or abs(v["roll_deg"]) > 35
                    or not 3500 <= v["altitude_indicated_ft"] <= 5500 or v["agl_m"] * 3.28084 < 1000):
                return self.fail("Engineering test envelope exceeded")
            if sim - self.phase_started > s.phase_deadline_s:
                return self.fail("Phase deadline exceeded: " + self.PHASES[self.phase_index])
            target = self.target
            heading_error = abs((v["heading_mag_deg"] - target["heading_mag_deg"] + 180) % 360 - 180)
            stable = (heading_error <= s.heading_tolerance_deg
                      and abs(v["altitude_indicated_ft"] - s.altitude_ft) <= s.altitude_tolerance_ft
                      and abs(v["kias"] - s.kias) <= s.speed_tolerance_kt
                      and abs(v["roll_deg"]) <= s.bank_tolerance_deg
                      and abs(v["vvi_fpm"]) <= s.vvi_tolerance_fpm)
            if not stable:
                self.stable_since = None
            elif self.stable_since is None:
                self.stable_since = sim
            elif sim - self.stable_since >= s.dwell_s:
                self.transitions.append({"phase": self.PHASES[self.phase_index], "sim_time_s": sim,
                                         "frame": frame, "stable_since_s": self.stable_since})
                self.stable_since = None
                self.phase_started = sim
                self.phase_index += 1
                if self.phase_index == len(self.PHASES):
                    self.outcome = "PASS"
        except (KeyError, TypeError, ValueError):
            return self.fail("Malformed telemetry snapshot")
        return self.report()

    def report(self):
        return {"outcome": self.outcome, "reason": self.reason, "samples": self.samples,
                "phase": self.PHASES[self.phase_index] if self.phase_index < 3 else "complete",
                "transitions": list(self.transitions)}


class Recorder:
    """Exclusive creation, provenance first, crash-visible incomplete JSONL."""
    def __init__(self, path, manifest):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("x", buffering=1)
        self.write("manifest", manifest)

    def write(self, kind, payload):
        self.stream.write(json.dumps({"kind": kind, "payload": payload}, allow_nan=False) + "\n")

    def close(self):
        self.stream.close()


def score_trace(path):
    observer = None
    finished = None
    with Path(path).open() as stream:
        for i, line in enumerate(stream):
            try:
                record = json.loads(line)
                if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
                    raise ValueError("Trace records and payloads must be objects")
                kind, payload = record["kind"], record["payload"]
                if i == 0:
                    if kind != "manifest" or payload.get("purpose") != "scored-cycle":
                        raise ValueError("Trace is not a scored cycle")
                    observer = CycleObserver(Scenario(**payload["scenario"]))
                elif kind == "snapshot":
                    if finished is not None:
                        raise ValueError("Samples after trace end")
                    observer.observe(payload)
                elif kind == "intervention":
                    observer.fail(str(payload))
                elif kind == "end":
                    if finished is not None:
                        raise ValueError("Duplicate trace end")
                    finished = payload
                else:
                    raise ValueError("Unknown trace record")
            except (ValueError, TypeError, KeyError) as error:
                return {"outcome": "FAIL", "reason": "Invalid trace: " + str(error)}
    if observer is None or finished is None:
        return {"outcome": "INCOMPLETE", "reason": "Missing manifest or trace end"}
    return {**observer.report(), "trace_sha256": digest(path)}
