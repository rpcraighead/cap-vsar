"""Temporary stock-C172 laboratory session, separate from production qualification.

Aircraft identity is pinned by path/hash. State setting requires confirmed pause
and released ownership; native control writes are bounded during each trial.
"""
import hashlib
import math
from pathlib import Path
import time

STOCK_SHA256 = "b9c3c35c956ac5bee8c74fc9cbf933c6ecdfab73db9ad22862022aa3a20ab847"
STOCK_NAME = "Cessna_172SP_G1000.acf"
AUTHORITY = {"roll": (-.35, .35), "pitch": (-.4, .4), "yaw": (-.35, .35),
             "throttle": (.15, 1), "flap": (0, 0), "trim": (-.6, .6)}


class QualificationLab:
    def __init__(self, xp, sink, config):
        self.xp, self.sink = xp, sink
        self.aircraft = str(Path(config["aircraft_path"]).resolve())
        self.expires = config["expires_unix_s"]
        if (Path(self.aircraft).name != STOCK_NAME
                or hashlib.sha256(Path(self.aircraft).read_bytes()).hexdigest() != STOCK_SHA256
                or not time.time() < self.expires <= time.time() + 14400):
            raise ValueError("Qualification requires pinned stock C172 and a <=4 hour lease")
        self.trial_started = None
        self.previous_sim = None
        self.resume_pending = False
        self.reset_count = 0
        self.refs = {}
        for name in (
            "sim/weather/region/weather_preset", "sim/weather/region/change_mode",
            "sim/weather/region/update_immediately", "sim/weather/region/sealevel_temperature_c",
            "sim/weather/region/sealevel_pressure_pas", "sim/weather/region/variability_pct",
            "sim/weather/region/wind_speed_msc", "sim/weather/region/shear_speed_msc",
            "sim/weather/region/turbulence", "sim/weather/region/thermal_rate_ms",
            "sim/flightmodel/weight/m_fixed", "sim/flightmodel/weight/m_fuel",
            "sim/flightmodel/position/P", "sim/flightmodel/position/Q", "sim/flightmodel/position/R",
            "sim/flightmodel/position/local_x", "sim/flightmodel/position/local_y", "sim/flightmodel/position/local_z",
            "sim/flightmodel/position/local_vx", "sim/flightmodel/position/local_vy", "sim/flightmodel/position/local_vz",
            "sim/flightmodel/position/q", "sim/flightmodel/position/latitude", "sim/flightmodel/position/longitude",
            "sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot", "sim/time/sim_speed",
        ):
            ref = xp.findDataRef(name)
            if not ref:
                raise ValueError("Qualification dataref missing: " + name)
            self.refs[name] = ref
        self.resume_command = xp.findCommand("sim/operation/pause_off")
        self.pause_command = xp.findCommand("sim/operation/pause_on")
        self.quick_start = xp.findCommand("sim/operation/quick_start")

    def verify_identity(self):
        if time.time() >= self.expires or self.xp.getNthAircraftModel(0)[1] != self.aircraft:
            raise ValueError("Qualification aircraft or lease changed")

    def validate_controls(self, controls):
        if set(controls) != set(AUTHORITY):
            raise ValueError("Complete lab actuator frame required")
        for name, (low, high) in AUTHORITY.items():
            if type(controls[name]) not in (int, float) or not math.isfinite(controls[name]) or not low <= controls[name] <= high:
                raise ValueError("Qualification control limit: " + name)

    def reset(self, core, *, heading_offset=0.0, altitude_offset=0.0, speed_offset=0.0):
        self.verify_identity()
        if (not self.sink.is_paused() or self.sink.override_state() is not False
                or core.state not in ("MANUAL", "PAUSED_FAULT")):
            raise ValueError("Reset requires confirmed pause and released controls")
        for value, bound in ((heading_offset, 10), (altitude_offset, 150), (speed_offset, 5)):
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > bound:
                raise ValueError("Reset disturbance outside laboratory bounds")
        xp = self.xp
        lat = xp.getDatad(self.refs["sim/flightmodel/position/latitude"])
        lon = xp.getDatad(self.refs["sim/flightmodel/position/longitude"])
        if abs(lat - 32.75) > .5 or abs(lon + 117.45) > .5:
            raise ValueError("Reset requires local Southern California scenery already loaded")
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
        # Engineering reference loading: 170 kg payload, 100 kg fuel.
        scalar("sim/flightmodel/weight/m_fixed", 170.)
        xp.setDatavf(self.refs["sim/flightmodel/weight/m_fuel"], [50., 50.] + [0.] * 7, 0, 9)
        altitude = (4500 + altitude_offset) * .3048
        # ISA TAS from target IAS. Readiness checks measured IAS after placement.
        density_ratio = (1 - .0065 * altitude / 288.15) ** 4.25588
        tas = (100 + speed_offset) * .514444 / math.sqrt(density_ratio)
        position = xp.worldToLocal(32.75, -117.45, altitude)
        for axis, value in zip("xyz", position):
            scalar("sim/flightmodel/position/local_" + axis, value, "d")
        heading = math.radians(101 + heading_offset)
        pitch = math.radians(2.)
        # Laminar's Euler-to-q convention (Moving the Plane SDK note), bank=0.
        q = [math.cos(heading/2)*math.cos(pitch/2), -math.sin(heading/2)*math.sin(pitch/2),
             math.cos(heading/2)*math.sin(pitch/2), math.sin(heading/2)*math.cos(pitch/2)]
        xp.setDatavf(self.refs["sim/flightmodel/position/q"], q, 0, 4)
        for axis, value in zip("xyz", (tas * math.sin(heading), 0., -tas * math.cos(heading))):
            scalar("sim/flightmodel/position/local_v" + axis, value)
        xp.commandOnce(self.quick_start)
        xp.commandOnce(self.pause_command)
        for axis in "PQR":
            scalar("sim/flightmodel/position/" + axis, 0.)
        for channel, value in {"roll": 0., "pitch": 0., "yaw": 0., "trim": 0., "flap": 0., "throttle": .55}.items():
            self.sink.write_control(channel, value)
        self.trial_started = None
        self.previous_sim = None
        self.reset_count += 1
        return {"reset_count": self.reset_count, "latitude_deg": 32.75, "longitude_deg": -117.45,
                "altitude_msl_m": altitude, "heading_true_deg": 101 + heading_offset,
                "target_kias": 100 + speed_offset, "payload_kg": 170., "fuel_kg": 100.,
                "local_position_m": list(position)}

    def resume(self, core):
        self.verify_identity()
        if core.state != "ACTIVE" or not self.sink.is_paused():
            raise ValueError("Trial resume requires active controller and confirmed pause")
        self.trial_started = time.monotonic()
        self.resume_pending = True
        self.previous_sim = None
        self.xp.commandOnce(self.resume_command)

    def check_flight(self, snapshot, core):
        if core.state != "ACTIVE":
            return
        self.verify_identity()
        if self.trial_started is None:
            return  # Paused preflight, still covered by core wall watchdogs.
        v = snapshot["values"]
        if self.resume_pending:
            # Commands take effect at a simulator boundary; do not mistake the
            # last paused sample for a new pilot pause. Lease deadlines continue.
            if v["paused"]:
                if time.monotonic() - self.trial_started > .15:
                    raise ValueError("Resume was not observed within 150 ms")
                return
            if v["kias"] < 80 and time.monotonic() - self.trial_started < 2.0:
                if (40 <= v["tas_mps"] <= 70 and v["agl_m"] > 1000
                        and abs(v["roll_deg"]) < 10 and abs(v["pitch_deg"]) < 10):
                    return  # Instrument filter initialization; truth remains bounded.
            self.resume_pending = False
        if (v["paused"] or v["on_ground"] or not 80 <= v["kias"] <= 140
                or not 3500 <= v["altitude_indicated_ft"] <= 5500
                or abs(v["roll_deg"]) > 35 or abs(v["pitch_deg"]) > 20 or v["agl_m"] < 304.8
                or time.monotonic() - self.trial_started > 600):
            raise ValueError("Laboratory flight envelope or duration exceeded: %s" %
                             {k: v[k] for k in ("paused", "on_ground", "kias", "roll_deg", "pitch_deg", "altitude_indicated_ft", "agl_m")})
        if self.previous_sim is not None and v["sim_time_s"] <= self.previous_sim:
            raise ValueError("Simulation time reset or stopped")
        self.previous_sim = v["sim_time_s"]
