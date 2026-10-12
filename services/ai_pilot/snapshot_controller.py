"""Synchronous direct-controller adapter. No sockets, worker loop or SDK calls.

One coherent snapshot in, one complete candidate frame out. Faults latch until
the caller constructs a fresh adapter after resetting/rechecking the aircraft.
"""
import math

from .direct_backend import Gains, XPlaneDirectBackend
from xplane.capvsar_flight_control_core import CHANNELS, RANGES


class CandidateBuffer:
    def __init__(self):
        self.values = {}

    def subscribe_dref(self, *args, **kwargs):
        pass

    def send_dref(self, ref, value):
        allowed = set(XPlaneDirectBackend.CONTROL_DREFS.values()) | {XPlaneDirectBackend.TRIM_DREF}
        if ref not in allowed or not math.isfinite(value):
            raise ValueError("Unexpected controller output")
        self.values[ref] = value


class SnapshotController:
    def __init__(self, aircraft_path, session):
        self.aircraft_path, self.session = aircraft_path, session
        self.sim_time = 0.0
        self.previous = None
        self.fault = None
        self.buffer = CandidateBuffer()
        self.backend = XPlaneDirectBackend(self.buffer, clock=lambda: self.sim_time)

    def step(self, snapshot, target, wall_now):
        if self.fault:
            raise ValueError("Controller fault latched: " + self.fault)
        try:
            return self._step(snapshot, target, wall_now)
        except Exception as error:
            self.fault = str(error)
            self.buffer.values.clear()
            raise

    def _step(self, s, target, wall_now):
        v, c = s["values"], s["controls"]
        if (s["schema"] != "capvsar.telemetry.v1" or s["phase"] != "after_flight_model"
                or s["session"] != self.session or s["aircraft"]["path"] != self.aircraft_path):
            raise ValueError("Snapshot identity changed")
        names = ("sim_time_s", "paused", "on_ground", "heading_mag_deg", "altitude_indicated_ft",
                 "agl_m", "kias", "roll_deg", "vvi_fpm", "pitch_deg", "beta_deg",
                 "roll_rate_dps", "pitch_rate_dps")
        if any(type(v[k]) not in (int, float) or not math.isfinite(v[k]) for k in names):
            raise ValueError("Nonfinite or missing telemetry")
        if (not math.isfinite(wall_now) or not math.isfinite(s["wall_time_s"])
                or not 0 <= wall_now - s["wall_time_s"] <= 0.2):
            raise ValueError("Stale telemetry")
        if v["paused"] or v["on_ground"]:
            raise ValueError("Pause/ground requires a new controller instance")
        if (not 80 <= v["kias"] <= 140 or v["agl_m"] < 304.8 or abs(v["roll_deg"]) > 35
                or not 3500 <= v["altitude_indicated_ft"] <= 5500):
            raise ValueError("Initial test envelope exceeded")
        if set(c) != set(CHANNELS) or any(
                type(c[k]) not in (int, float) or not math.isfinite(c[k])
                or not RANGES[k][0] <= c[k] <= RANGES[k][1] for k in CHANNELS):
            raise ValueError("Invalid measured controls")
        if (set(target) != {"heading_mag_deg", "altitude_indicated_ft", "kias"}
                or not all(type(x) in (int, float) and math.isfinite(x) for x in target.values())
                or not 4000 <= target["altitude_indicated_ft"] <= 5000 or not 90 <= target["kias"] <= 120):
            raise ValueError("Invalid target")
        self.sim_time = v["sim_time_s"]
        backend = self.backend
        values = {
            "heading_mag": v["heading_mag_deg"], "altitude_indicated_ft": v["altitude_indicated_ft"],
            "agl_ft": v["agl_m"], "kias": v["kias"], "roll_deg": v["roll_deg"],
            "vvi_fpm": v["vvi_fpm"], "pitch_deg": v["pitch_deg"], "beta_deg": v["beta_deg"],
            "roll_rate": v["roll_rate_dps"], "pitch_rate": v["pitch_rate_dps"],
            "elevator_trim": c["trim"], "aileron_position": c["roll"],
            "elevator_position": c["pitch"], "rudder_position": c["yaw"], "throttle_position": c["throttle"],
        }
        backend.samples = {k: (val, self.sim_time) for k, val in values.items()}
        backend.target_kias = target["kias"]
        if self.previous is None:
            backend._surface = {"aileron": c["roll"], "elevator": c["pitch"], "rudder": c["yaw"]}
            backend._surface_t = self.sim_time
            backend._trim = c["trim"]
            backend._throttle_i = max(-Gains.THROTTLE_I_LIMIT, min(Gains.THROTTLE_I_LIMIT,
                c["throttle"] - 0.55 - (target["kias"] - v["kias"]) * Gains.SPEED_TO_THROTTLE_P))
            self.previous = (self.sim_time, s["wall_time_s"], s["frame"])
            return dict(c)  # Transfer from measured controls without an initial step.
        old_sim, old_wall, old_frame = self.previous
        dt = self.sim_time - old_sim
        if (not 0 < dt <= 0.25 or not 0 < s["wall_time_s"] - old_wall <= 0.25
                or type(s["frame"]) is not int or s["frame"] <= old_frame):
            raise ValueError("Reset, duplicate or telemetry gap")
        self.buffer.values.clear()
        backend._step(backend.observe(), target["heading_mag_deg"], target["altitude_indicated_ft"], dt_s=dt)
        output = self.buffer.values
        result = {"roll": output[backend.CONTROL_DREFS["aileron"]],
                  "pitch": output[backend.CONTROL_DREFS["elevator"]],
                  "yaw": output[backend.CONTROL_DREFS["rudder"]],
                  "throttle": output[backend.CONTROL_DREFS["throttle"]],
                  "trim": output[backend.TRIM_DREF], "flap": c["flap"]}
        self.previous = (self.sim_time, s["wall_time_s"], s["frame"])
        return result
