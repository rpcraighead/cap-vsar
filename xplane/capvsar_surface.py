"""Expiring attended stock-C172 KSEE surface and initial-takeoff laboratory."""
import math
import time

try:
    from .capvsar_qualification import QualificationLab
except ImportError:
    from capvsar_qualification import QualificationLab


PARKING = (32.824456, -116.968545)
PARKING_HEADING_TRUE_DEG = 91.3
HOLD = (32.825969, -116.964412)
HOLD_HEADING_TRUE_DEG = 352.7
AUTHORITY = {"roll": (-.35, .35), "pitch": (-.45, .45),
             "yaw": (-1., 1.), "throttle": (0., 1.), "flap": (0., 0.),
             "trim": (-.6, .6), "brake": (0., 1.)}


class SurfaceLab(QualificationLab):
    def __init__(self, xp, sink, config):
        super().__init__(xp, sink, config)
        if config.get("parking") != "KSEE East Transient Parking 12":
            raise ValueError("Surface laboratory requires surveyed KSEE parking 12")
        self.parking_brake = xp.findDataRef("sim/cockpit2/controls/parking_brake_ratio")
        if not self.parking_brake:
            raise ValueError("Surface laboratory parking brake dataref unavailable")

    def validate_controls(self, controls):
        if not isinstance(controls, dict) or set(controls) != set(AUTHORITY):
            raise ValueError("Complete surface actuator frame required")
        for name, (low, high) in AUTHORITY.items():
            value = controls[name]
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError("Surface control limit: " + name)

    def reset(self, core, checkpoint=None):
        self.verify_identity()
        if checkpoint not in (None, "D8 hold"):
            raise ValueError("Unknown KSEE surface diagnostic checkpoint")
        if (not self.sink.is_paused() or self.sink.override_state() is not False
                or core.state not in ("MANUAL", "PAUSED_FAULT")):
            raise ValueError("Surface reset requires confirmed pause and released controls")
        xp = self.xp
        target = HOLD if checkpoint == "D8 hold" else PARKING
        target_heading = (HOLD_HEADING_TRUE_DEG if checkpoint == "D8 hold"
                          else PARKING_HEADING_TRUE_DEG)
        lat = xp.getDatad(self.refs["sim/flightmodel/position/latitude"])
        lon = xp.getDatad(self.refs["sim/flightmodel/position/longitude"])
        if abs(lat-PARKING[0]) > .08 or abs(lon-PARKING[1]) > .08:
            raise ValueError("KSEE scenery must already be loaded")
        x, y, z = xp.worldToLocal(target[0], target[1], 130.)
        probe = xp.createProbe(xp.ProbeY)
        try:
            info = xp.probeTerrainXYZ(probe, x, y, z)
        finally:
            xp.destroyProbe(probe)
        if info.result != xp.ProbeHitTerrain:
            raise ValueError("KSEE parking terrain probe failed")
        _, _, ground_alt_m = xp.localToWorld(info.locationX, info.locationY, info.locationZ)
        if not 100 <= ground_alt_m <= 135:
            raise ValueError("KSEE parking elevation outside surveyed airport envelope")
        position = (info.locationX, info.locationY+1.5, info.locationZ)
        def scalar(name, value, kind="f"):
            getattr(xp, "setData" + kind)(self.refs[name], value)
        self.sink.command_ap_off()
        scalar("sim/weather/region/weather_preset", 0, "i")
        scalar("sim/weather/region/change_mode", 3, "i")
        scalar("sim/weather/region/variability_pct", 0.)
        scalar("sim/weather/region/sealevel_temperature_c", 15.)
        scalar("sim/weather/region/sealevel_pressure_pas", 101325.)
        scalar("sim/weather/region/thermal_rate_ms", 0.)
        for name in ("wind_speed_msc", "shear_speed_msc", "turbulence"):
            xp.setDatavf(self.refs["sim/weather/region/" + name], [0.] * 13, 0, 13)
        scalar("sim/weather/region/update_immediately", 1, "i")
        scalar("sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot", 29.92126)
        scalar("sim/time/sim_speed", 1, "i")
        scalar("sim/flightmodel/weight/m_fixed", 170.)
        xp.setDatavf(self.refs["sim/flightmodel/weight/m_fuel"], [50., 50.] + [0.] * 7, 0, 9)
        for axis, value in zip("xyz", position):
            scalar("sim/flightmodel/position/local_" + axis, value, "d")
        heading = math.radians(target_heading)
        xp.setDatavf(self.refs["sim/flightmodel/position/q"],
                     [math.cos(heading/2), 0., 0., math.sin(heading/2)], 0, 4)
        for axis in "xyz":
            scalar("sim/flightmodel/position/local_v" + axis, 0.)
        xp.commandOnce(self.quick_start)
        xp.commandOnce(self.pause_command)
        xp.setDataf(self.parking_brake, 0.)
        if xp.getDataf(self.parking_brake) > .05:
            raise ValueError("Parking brake release not confirmed")
        for axis in "PQR":
            scalar("sim/flightmodel/position/" + axis, 0.)
        for channel, value in {"roll": 0., "pitch": 0., "yaw": 0., "trim": 0.,
                               "flap": 0., "throttle": 0., "brake": .35}.items():
            self.sink.write_control(channel, value)
        self.trial_started = None
        self.previous_sim = None
        self.reset_count += 1
        return {"reset_count": self.reset_count,
                "latitude_deg": target[0], "longitude_deg": target[1],
                "heading_true_deg": target_heading,
                "ground_altitude_msl_m": ground_alt_m,
                "local_position_m": list(position),
                "parking": "KSEE East Transient Parking 12" if checkpoint is None else "D8 hold diagnostic checkpoint"}

    def check_flight(self, snapshot, core):
        if core.state != "ACTIVE":
            return
        self.verify_identity()
        if self.trial_started is None:
            return
        v = snapshot["values"]
        if self.resume_pending:
            if v["paused"]:
                if time.monotonic()-self.trial_started > .15:
                    raise ValueError("Surface resume not observed within 150 ms")
                return
            self.resume_pending = False
        if (v["paused"] or v["parking_brake_ratio"] > .05
                or not 32.80 <= v["latitude_deg"] <= 32.85
                or not -117.05 <= v["longitude_deg"] <= -116.94
                or not -1 <= v["agl_m"] <= 700
                or not 0 <= v["kias"] <= 110
                or not 0 <= v["groundspeed_mps"] <= 65
                or abs(v["roll_deg"]) > 30 or abs(v["pitch_deg"]) > 20
                or time.monotonic()-self.trial_started > 600):
            raise ValueError("KSEE surface/takeoff laboratory envelope exceeded: %s" %
                             {k: v[k] for k in ("paused", "parking_brake_ratio",
                                               "latitude_deg", "longitude_deg",
                                               "agl_m", "kias", "groundspeed_mps",
                                               "roll_deg", "pitch_deg")})
        if self.previous_sim is not None and v["sim_time_s"] <= self.previous_sim:
            raise ValueError("Surface simulation time reset or stopped")
        self.previous_sim = v["sim_time_s"]
