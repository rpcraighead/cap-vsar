"""Expiring stock-C172 landing laboratory at selected X-Plane runways.

Runway endpoints are from the installed X-Plane 12 Global Airports apt.dat.
This is a simulator engineering trial, not an operational landing clearance.
"""
import math
import time

try:
    from .capvsar_qualification import QualificationLab, authority_for
except ImportError:
    from capvsar_qualification import QualificationLab, authority_for

class RunwayGeometry:
    def __init__(self, name, threshold, far_end, airport_elev_ft,
                 displaced_threshold_m, width_m):
        self.name = name
        self.threshold = threshold
        self.far_end = far_end
        self.airport_elev_ft = airport_elev_ft
        self.displaced_threshold_m = displaced_threshold_m
        self.aimpoint_m = displaced_threshold_m + 25. * .3048
        self.width_m = width_m
        self.m_per_deg_lon = 111412.84 * math.cos(math.radians(threshold[0]))
        north = (far_end[0] - threshold[0]) * M_PER_DEG_LAT
        east = (far_end[1] - threshold[1]) * self.m_per_deg_lon
        self.length_m = math.hypot(north, east)
        self.unit_n, self.unit_e = north / self.length_m, east / self.length_m
        self.heading_true_deg = math.degrees(math.atan2(east, north)) % 360

    def coordinates(self, lat, lon):
        north = (lat - self.threshold[0]) * M_PER_DEG_LAT
        east = (lon - self.threshold[1]) * self.m_per_deg_lon
        return (north * self.unit_n + east * self.unit_e,
                north * -self.unit_e + east * self.unit_n)


M_PER_DEG_LAT = 111132.92
RUNWAYS = {
    "KMYF 28R": RunwayGeometry("KMYF 28R", (32.8128249, -117.1311307),
                               (32.8181752, -117.1447205), 424., 366., 46.02),
    # Installed KSAN_San_Diego_Int'l v3.0 apt.dat: runway 27 end, 552 m displacement.
    "KSAN 27": RunwayGeometry("KSAN 27", (32.73136873, -117.18062185),
                              (32.73659395, -117.20217254), 17., 552., 61.02),
}
DEFAULT_RUNWAY = RUNWAYS["KMYF 28R"]
# Preserve the KMYF symbols used by earlier evidence and controller tests.
THRESHOLD = DEFAULT_RUNWAY.threshold
FAR_END = DEFAULT_RUNWAY.far_end
AIRPORT_ELEV_FT = DEFAULT_RUNWAY.airport_elev_ft
DISPLACED_THRESHOLD_28R_M = DEFAULT_RUNWAY.displaced_threshold_m
GLIDEPATH_AIMPOINT_M = DEFAULT_RUNWAY.aimpoint_m
RUNWAY_WIDTH_M = DEFAULT_RUNWAY.width_m
M_PER_DEG_LON = DEFAULT_RUNWAY.m_per_deg_lon
RUNWAY_LENGTH_M = DEFAULT_RUNWAY.length_m
UNIT_N, UNIT_E = DEFAULT_RUNWAY.unit_n, DEFAULT_RUNWAY.unit_e
HEADING_TRUE_DEG = DEFAULT_RUNWAY.heading_true_deg


def landing_agl_in_bounds(agl_m, on_ground):
    """Allow small negative AGL roundoff only after ground contact."""
    floor = -.05 if on_ground else 0.
    return math.isfinite(agl_m) and floor <= agl_m <= 250.


AUTHORITY = {"roll": (-.35, .35), "pitch": (-.45, .45), "yaw": (-1., 1.),
             "throttle": (0., .65), "flap": (0., 1.), "trim": (-.6, .6),
             "brake": (0., .35)}


def runway_coordinates(lat, lon):
    return DEFAULT_RUNWAY.coordinates(lat, lon)


class LandingLab(QualificationLab):
    def __init__(self, xp, sink, config):
        super().__init__(xp, sink, config)
        self.authority = authority_for(AUTHORITY, config)
        self.runway = RUNWAYS[config.get("runway", "KMYF 28R")]
        ref = xp.findDataRef("sim/weather/region/wind_direction_degt")
        if not ref:
            raise ValueError("Landing wind direction dataref missing")
        self.refs["sim/weather/region/wind_direction_degt"] = ref

    def validate_controls(self, controls):
        if not isinstance(controls, dict) or set(controls) != set(self.authority):
            raise ValueError("Complete landing actuator frame required")
        for name, (low, high) in self.authority.items():
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
                or abs(wind_from_offset_deg) > 120):
            raise ValueError("Landing wind outside laboratory bounds")
        xp = self.xp
        runway = self.runway
        lat = xp.getDatad(self.refs["sim/flightmodel/position/latitude"])
        lon = xp.getDatad(self.refs["sim/flightmodel/position/longitude"])
        if abs(lat - runway.threshold[0]) > .15 or abs(lon - runway.threshold[1]) > .15:
            raise ValueError(runway.name + " scenery must already be loaded")
        def scalar(name, value, kind="f"):
            getattr(xp, "setData" + kind)(self.refs[name], value)
        self.sink.command_ap_off()
        scalar("sim/weather/region/weather_preset", 0, "i")
        scalar("sim/weather/region/change_mode", 3, "i")
        scalar("sim/weather/region/variability_pct", 0.)
        scalar("sim/weather/region/sealevel_temperature_c", 15.)
        scalar("sim/weather/region/sealevel_pressure_pas", 101325.)
        scalar("sim/weather/region/thermal_rate_ms", 0.)
        wind_from = (runway.heading_true_deg + wind_from_offset_deg) % 360.
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
        north = -distance * runway.unit_n - lateral_offset * runway.unit_e
        east = -distance * runway.unit_e + lateral_offset * runway.unit_n
        latitude = runway.threshold[0] + north / M_PER_DEG_LAT
        longitude = runway.threshold[1] + east / runway.m_per_deg_lon
        altitude = (runway.airport_elev_ft + (distance + runway.aimpoint_m) *
                    math.tan(math.radians(3.)) * 3.28084
                    + altitude_offset) * .3048
        position = xp.worldToLocal(latitude, longitude, altitude)
        for axis, value in zip("xyz", position):
            scalar("sim/flightmodel/position/local_" + axis, value, "d")
        heading = math.radians(runway.heading_true_deg)
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
                               "flap": 1/3, "throttle": .24, "brake": 0.,
                               **({"prop": 1.} if "prop" in self.authority else {})}.items():
            self.sink.write_control(channel, value)
        self.trial_started = None
        self.previous_sim = None
        self.reset_count += 1
        return {"reset_count": self.reset_count, "latitude_deg": latitude,
                "longitude_deg": longitude, "altitude_msl_m": altitude,
                "heading_true_deg": runway.heading_true_deg, "target_kias": 70. + speed_offset,
                "payload_kg": 170., "fuel_kg": 100., "local_position_m": list(position),
                "runway": runway.name, "runway_length_m": runway.length_m,
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
        along, cross = self.runway.coordinates(v["latitude_deg"], v["longitude_deg"])
        if (v["paused"] or abs(cross) > 180 or not -2450 <= along <= self.runway.length_m + 80
                or not landing_agl_in_bounds(v["agl_m"], bool(v["on_ground"]))
                or not 0 <= v["kias"] <= 110
                or abs(v["roll_deg"]) > 35 or abs(v["pitch_deg"]) > 20
                or (v["on_ground"] and along < -70)
                or time.monotonic() - self.trial_started > 240):
            raise ValueError("Landing laboratory envelope exceeded: along=%.1f cross=%.1f agl=%.1f kias=%.1f ground=%s" %
                             (along, cross, v["agl_m"], v["kias"], v["on_ground"]))
        if self.previous_sim is not None and v["sim_time_s"] <= self.previous_sim:
            raise ValueError("Landing simulation time reset or stopped")
        self.previous_sim = v["sim_time_s"]
