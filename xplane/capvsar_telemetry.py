"""One post-flight-model snapshot. SDK calls stay on X-Plane's main thread."""
import math
import time

# key: dataref, SDK scalar type, unit. Direction/altitude datums are explicit.
FIELDS = {
    "sim_time_s": ("sim/time/total_flight_time_sec", "f", "s"),
    "paused": ("sim/time/paused", "i", "boolean"),
    "latitude_deg": ("sim/flightmodel/position/latitude", "d", "deg latitude"),
    "longitude_deg": ("sim/flightmodel/position/longitude", "d", "deg longitude"),
    "altitude_msl_m": ("sim/flightmodel/position/elevation", "d", "m MSL"),
    "altitude_indicated_ft": ("sim/cockpit2/gauges/indicators/altitude_ft_pilot", "f", "ft indicated"),
    "agl_m": ("sim/flightmodel/position/y_agl", "f", "m AGL"),
    "heading_mag_deg": ("sim/flightmodel/position/mag_psi", "f", "deg magnetic"),
    "heading_true_deg": ("sim/flightmodel/position/psi", "f", "deg true"),
    "kias": ("sim/flightmodel/position/indicated_airspeed", "f", "kt indicated"),
    "roll_deg": ("sim/flightmodel/position/phi", "f", "deg right wing down"),
    "pitch_deg": ("sim/flightmodel/position/theta", "f", "deg nose up"),
    "beta_deg": ("sim/flightmodel/position/beta", "f", "deg sideslip"),
    "vvi_fpm": ("sim/flightmodel/position/vh_ind_fpm", "f", "ft/min indicated"),
    "roll_rate_dps": ("sim/flightmodel/position/P", "f", "deg/s body roll"),
    "pitch_rate_dps": ("sim/flightmodel/position/Q", "f", "deg/s body pitch"),
    "frame_period_s": ("sim/operation/misc/frame_rate_period", "f", "s"),
    "on_ground": ("sim/flightmodel/failures/onground_any", "i", "boolean"),
}


class Telemetry:
    def __init__(self, xp, sink, session, clock=time.monotonic):
        self.xp, self.sink, self.session, self.clock = xp, sink, session, clock
        self.refs = {key: xp.findDataRef(spec[0]) for key, spec in FIELDS.items()}
        if not all(self.refs.values()):
            raise RuntimeError("Required telemetry dataref missing")
        self.frame = 0

    def capture(self, sdk_counter):
        start = self.clock()
        values = {}
        for key, (_, kind, _) in FIELDS.items():
            value = getattr(self.xp, "getData" + kind)(self.refs[key])
            if not math.isfinite(value):
                raise ValueError("Nonfinite telemetry: " + key)
            values[key] = value
        name, path = self.xp.getNthAircraftModel(0)
        controls = {key: self.sink.read_control(key) for key in self.sink.controls}
        if not all(math.isfinite(value) for value in controls.values()):
            raise ValueError("Nonfinite control readback")
        self.frame += 1
        return {
            "schema": "capvsar.telemetry.v1", "session": self.session,
            "frame": self.frame, "sdk_counter": sdk_counter,
            "wall_time_s": start, "capture_duration_s": self.clock() - start,
            "phase": "after_flight_model", "aircraft": {"name": name, "path": path},
            "values": values,
            "controls": controls,
            "ap_engaged": self.sink.ap_engaged(),
            "override_state": self.sink.override_state(),
        }

    def manifest(self):
        return {"schema": "capvsar.telemetry.v1", "units": {k: v[2] for k, v in FIELDS.items()},
                "datarefs": {k: v[0] for k, v in FIELDS.items()},
                "sampling": "All channels read in one post-flight-model callback; no cached per-channel values",
                "versions": self.xp.getVersions()}
