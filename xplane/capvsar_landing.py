"""Expiring stock-C172 landing laboratory at KMYF runway 28R.

Runway endpoints are from the installed X-Plane 12 Global Airports apt.dat.
This is a simulator engineering trial, not an operational landing clearance.
"""
import math
import time

try:
    from .capvsar_qualification import QualificationLab
except ImportError:
    from capvsar_qualification import QualificationLab

THRESHOLD = (32.8128249, -117.1311307)  # 28R approach threshold
FAR_END = (32.8181752, -117.1447205)    # 10L threshold
AIRPORT_ELEV_FT = 424.0
DISPLACED_THRESHOLD_28R_M = 366.0  # apt.dat 28R endpoint displacement
GLIDEPATH_AIMPOINT_M = DISPLACED_THRESHOLD_28R_M + 25. * .3048
RUNWAY_WIDTH_M = 46.02
M_PER_DEG_LAT = 111132.92
M_PER_DEG_LON = 111412.84 * math.cos(math.radians(THRESHOLD[0]))
RUNWAY_N = (FAR_END[0] - THRESHOLD[0]) * M_PER_DEG_LAT
RUNWAY_E = (FAR_END[1] - THRESHOLD[1]) * M_PER_DEG_LON
RUNWAY_LENGTH_M = math.hypot(RUNWAY_N, RUNWAY_E)
UNIT_N, UNIT_E = RUNWAY_N / RUNWAY_LENGTH_M, RUNWAY_E / RUNWAY_LENGTH_M
HEADING_TRUE_DEG = math.degrees(math.atan2(UNIT_E, UNIT_N)) % 360
AUTHORITY = {"roll": (-.35, .35), "pitch": (-.45, .45), "yaw": (-1., 1.),
             "throttle": (0., .65), "flap": (0., 1.), "trim": (-.6, .6),
             "brake": (0., .35)}


def runway_coordinates(lat, lon):
    north = (lat - THRESHOLD[0]) * M_PER_DEG_LAT
    east = (lon - THRESHOLD[1]) * M_PER_DEG_LON
    return north * UNIT_N + east * UNIT_E, north * -UNIT_E + east * UNIT_N


class LandingLab(QualificationLab):
    def __init__(self, xp, sink, config):
        super().__init__(xp, sink, config)
        ref = xp.findDataRef("sim/weather/region/wind_direction_degt")
        if not ref:
            raise ValueError("Landing wind direction dataref missing")
        self.refs["sim/weather/region/wind_direction_degt"] = ref

    def validate_controls(self, controls):
        if not isinstance(controls, dict) or set(controls) != set(AUTHORITY):
            raise ValueError("Complete landing actuator frame required")
        for name, (low, high) in AUTHORITY.items():
            value = controls[name]
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError("Landing control limit: " + name)

    def reset(self, core, *, lateral_offset=0., altitude_offset=0., speed_offset=0.,
              wind_speed_kt=0., wind_from_offset_deg=0.):
        self.verify_identity()
        if (not self.sink.is_paused() or self.sink.override_state() is not False
                or core.state not in ("MANUAL", "PAUSED_FAULT")):
            raise ValueError("Reset requires confirmed pause and released controls")
        for value, bound in ((lateral_offset, 25.), (altitude_offset, 40.), (speed_offset, 3.)):
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > bound:
                raise ValueError("Landing disturbance outside laboratory bounds")
        if (type(wind_speed_kt) not in (int, float) or not math.isfinite(wind_speed_kt)
                or not 0 <= wind_speed_kt <= 15 or
                type(wind_from_offset_deg) not in (int, float)
                or not math.isfinite(wind_from_offset_deg)
                or abs(wind_from_offset_deg) > 90):
            raise ValueError("Landing wind outside laboratory bounds")
        xp = self.xp
        lat = xp.getDatad(self.refs["sim/flightmodel/position/latitude"])
        lon = xp.getDatad(self.refs["sim/flightmodel/position/longitude"])
        if abs(lat - THRESHOLD[0]) > .15 or abs(lon - THRESHOLD[1]) > .15:
            raise ValueError("KMYF scenery must already be loaded")
        def scalar(name, value, kind="f"):
            getattr(xp, "setData" + kind)(self.refs[name], value)
        self.sink.command_ap_off()
        scalar("sim/weather/region/weather_preset", 0, "i")
        scalar("sim/weather/region/change_mode", 3, "i")
        scalar("sim/weather/region/variability_pct", 0.)
        scalar("sim/weather/region/sealevel_temperature_c", 15.)
        scalar("sim/weather/region/sealevel_pressure_pas", 101325.)
        scalar("sim/weather/region/thermal_rate_ms", 0.)
        wind_from = (HEADING_TRUE_DEG + wind_from_offset_deg) % 360.
        xp.setDatavf(self.refs["sim/weather/region/wind_speed_msc"],
                     [wind_speed_kt * .514444] * 13, 0, 13)
        xp.setDatavf(self.refs["sim/weather/region/wind_direction_degt"],
                     [wind_from] * 13, 0, 13)
        for name in ("shear_speed_msc", "turbulence"):
            xp.setDatavf(self.refs["sim/weather/region/" + name], [0.] * 13, 0, 13)
        scalar("sim/weather/region/update_immediately", 1, "i")
        scalar("sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot", 29.92126)
        scalar("sim/time/sim_speed", 1, "i")
        scalar("sim/flightmodel/weight/m_fixed", 170.)
        xp.setDatavf(self.refs["sim/flightmodel/weight/m_fuel"], [50., 50.] + [0.] * 7, 0, 9)
        distance = 1.2 * 1852.
        north = -distance * UNIT_N - lateral_offset * UNIT_E
        east = -distance * UNIT_E + lateral_offset * UNIT_N
        latitude = THRESHOLD[0] + north / M_PER_DEG_LAT
        longitude = THRESHOLD[1] + east / M_PER_DEG_LON
        altitude = (AIRPORT_ELEV_FT + (distance + GLIDEPATH_AIMPOINT_M) *
                    math.tan(math.radians(3.)) * 3.28084
                    + altitude_offset) * .3048
        position = xp.worldToLocal(latitude, longitude, altitude)
        for axis, value in zip("xyz", position):
            scalar("sim/flightmodel/position/local_" + axis, value, "d")
        heading = math.radians(HEADING_TRUE_DEG)
        pitch = math.radians(1.)
        q = [math.cos(heading/2)*math.cos(pitch/2), -math.sin(heading/2)*math.sin(pitch/2),
             math.cos(heading/2)*math.sin(pitch/2), math.sin(heading/2)*math.cos(pitch/2)]
        xp.setDatavf(self.refs["sim/flightmodel/position/q"], q, 0, 4)
        density_ratio = (1 - .0065 * altitude / 288.15) ** 4.25588
        tas = (70. + speed_offset) * .514444 / math.sqrt(density_ratio)
        for axis, value in zip("xyz", (tas * math.sin(heading), -tas * math.tan(math.radians(3.)),
                                          -tas * math.cos(heading))):
            scalar("sim/flightmodel/position/local_v" + axis, value)
        xp.commandOnce(self.quick_start)
        xp.commandOnce(self.pause_command)
        for axis in "PQR":
            scalar("sim/flightmodel/position/" + axis, 0.)
        for channel, value in {"roll": 0., "pitch": 0., "yaw": 0., "trim": 0.,
                               "flap": 1/3, "throttle": .24, "brake": 0.}.items():
            self.sink.write_control(channel, value)
        self.trial_started = None
        self.previous_sim = None
        self.reset_count += 1
        return {"reset_count": self.reset_count, "latitude_deg": latitude,
                "longitude_deg": longitude, "altitude_msl_m": altitude,
                "heading_true_deg": HEADING_TRUE_DEG, "target_kias": 70. + speed_offset,
                "payload_kg": 170., "fuel_kg": 100., "local_position_m": list(position),
                "runway": "KMYF 28R", "runway_length_m": RUNWAY_LENGTH_M,
                "wind_speed_kt": wind_speed_kt, "wind_from_true_deg": wind_from}

    def check_flight(self, snapshot, core):
        if core.state != "ACTIVE":
            return
        self.verify_identity()
        if self.trial_started is None:
            return
        v = snapshot["values"]
        if self.resume_pending:
            if v["paused"]:
                if time.monotonic() - self.trial_started > .15:
                    raise ValueError("Landing resume not observed within 150 ms")
                return
            self.resume_pending = False
        along, cross = runway_coordinates(v["latitude_deg"], v["longitude_deg"])
        if (v["paused"] or abs(cross) > 180 or not -2450 <= along <= RUNWAY_LENGTH_M + 80
                or not 0 <= v["agl_m"] <= 250 or not 0 <= v["kias"] <= 110
                or abs(v["roll_deg"]) > 35 or abs(v["pitch_deg"]) > 20
                or (v["on_ground"] and along < -70)
                or time.monotonic() - self.trial_started > 240):
            raise ValueError("Landing laboratory envelope exceeded: along=%.1f cross=%.1f agl=%.1f kias=%.1f ground=%s" %
                             (along, cross, v["agl_m"], v["kias"], v["on_ground"]))
        if self.previous_sim is not None and v["sim_time_s"] <= self.previous_sim:
            raise ValueError("Landing simulation time reset or stopped")
        self.previous_sim = v["sim_time_s"]
