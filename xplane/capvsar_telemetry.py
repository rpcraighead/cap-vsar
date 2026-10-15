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
    "groundspeed_mps": ("sim/flightmodel/position/groundspeed", "f", "m/s"),
    "track_true_deg": ("sim/flightmodel/position/hpath", "f", "deg true ground track"),
    # GFC 700 / X-Plane autopilot selections, so an executive that hands the
    # airplane to the autopilot reads back what it asked for from the same frame.
    "ap_state": ("sim/cockpit/autopilot/autopilot_state", "i", "bitfield"),
    "ap_heading_bug_deg": ("sim/cockpit/autopilot/heading_mag", "f", "deg magnetic"),
    "ap_altitude_bug_ft": ("sim/cockpit/autopilot/altitude", "f", "ft indicated"),
    "ap_vs_bug_fpm": ("sim/cockpit/autopilot/vertical_velocity", "f", "ft/min"),
    "brake_left": ("sim/flightmodel/controls/l_brake_add", "f", "ratio"),
    "brake_right": ("sim/flightmodel/controls/r_brake_add", "f", "ratio"),
    "toe_brake_left": ("sim/cockpit2/controls/left_brake_ratio", "f", "ratio"),
    "toe_brake_right": ("sim/cockpit2/controls/right_brake_ratio", "f", "ratio"),
    "parking_brake_ratio": ("sim/cockpit2/controls/parking_brake_ratio", "f", "ratio"),
    "mass_kg": ("sim/flightmodel/weight/m_total", "f", "kg"),
    "payload_kg": ("sim/flightmodel/weight/m_fixed", "f", "kg"),
    "fuel_kg": ("sim/flightmodel/weight/m_fuel_total", "f", "kg"),
    "wind_mps": ("sim/weather/aircraft/wind_now_speed_msc", "f", "m/s"),
    "wind_from_true_deg": ("sim/weather/aircraft/wind_now_direction_degt", "f", "deg true from"),
    "qnh_pa": ("sim/weather/aircraft/qnh_pas", "f", "Pa"),
    "sim_speed": ("sim/time/sim_speed", "i", "ratio"),
    "flap_actual": ("sim/cockpit2/controls/flap_system_deploy_ratio", "f", "ratio"),
    "local_x_m": ("sim/flightmodel/position/local_x", "d", "m local east"),
    "local_y_m": ("sim/flightmodel/position/local_y", "d", "m local up"),
    "local_z_m": ("sim/flightmodel/position/local_z", "d", "m local south"),
    "tas_mps": ("sim/flightmodel/position/true_airspeed", "f", "m/s true airspeed"),
    "nav1_frequency_10khz": ("sim/cockpit2/radios/actuators/nav1_frequency_hz", "i", "10 kHz"),
    "nav1_hdef_dots": ("sim/cockpit2/radios/indicators/nav1_hdef_dots_pilot", "f", "dots"),
    "nav1_vdef_dots": ("sim/cockpit2/radios/indicators/nav1_vdef_dots_pilot", "f", "dots"),
    "nav1_lateral_valid": ("sim/cockpit2/radios/indicators/nav1_display_horizontal", "i", "boolean"),
    "nav1_glideslope_flag": ("sim/cockpit2/radios/indicators/nav1_flag_glideslope_mech", "i", "boolean"),
    "nav1_dme_nm": ("sim/cockpit2/radios/indicators/nav1_dme_distance_nm", "f", "NM"),
}
ARRAY_FIELDS = {"engine_running": ("sim/flightmodel/engine/ENGN_running", "i", "boolean"),
                "engine_rpm": ("sim/cockpit2/engine/indicators/engine_speed_rpm", "f", "rpm")}


class Telemetry:
    def __init__(self, xp, sink, session, clock=time.monotonic, terrain=None):
        self.xp, self.sink, self.session, self.clock = xp, sink, session, clock
        self.terrain = terrain   # xplane.capvsar_terrain.TerrainScanner or None
        self.refs = {key: xp.findDataRef(spec[0]) for key, spec in FIELDS.items()}
        self.array_refs = {key: xp.findDataRef(spec[0]) for key, spec in ARRAY_FIELDS.items()}
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
        for key, (_, kind, _) in ARRAY_FIELDS.items():
            buf = [0]
            if getattr(self.xp, "getDatav" + kind)(self.array_refs[key], buf, 0, 1) != 1 or not math.isfinite(buf[0]):
                raise ValueError("Engine telemetry unavailable")
            values[key] = buf[0]
        name, path = self.xp.getNthAircraftModel(0)
        controls = {key: self.sink.read_control(key) for key in self.sink.controls}
        if not all(math.isfinite(value) for value in controls.values()):
            raise ValueError("Nonfinite control readback")
        self.frame += 1
        snapshot = {
            "schema": "capvsar.telemetry.v1", "session": self.session,
            "frame": self.frame, "sdk_counter": sdk_counter,
            "wall_time_s": start, "capture_duration_s": self.clock() - start,
            "phase": "after_flight_model", "aircraft": {"name": name, "path": path},
            "values": values,
            "controls": controls,
            "ap_engaged": self.sink.ap_engaged(),
            "override_state": self.sink.override_state(),
        }
        if self.terrain is not None:
            snapshot["terrain"] = self.terrain.update(
                values["latitude_deg"], values["longitude_deg"], values["heading_true_deg"],
                values["track_true_deg"], values["groundspeed_mps"])
        return snapshot

    def manifest(self):
        all_fields = {**FIELDS, **ARRAY_FIELDS}
        return {"schema": "capvsar.telemetry.v1", "units": {k: v[2] for k, v in all_fields.items()},
                "datarefs": {k: v[0] for k, v in all_fields.items()},
                "sampling": "All channels read in one post-flight-model callback; no cached per-channel values",
                "versions": self.xp.getVersions()}
