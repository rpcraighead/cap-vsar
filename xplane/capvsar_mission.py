"""Attended KSEE-to-KMYF stock-C172 flight; adopts an already paused departure."""
import math
import time

try:
    from .capvsar_qualification import QualificationLab
    from .capvsar_surface import SurfaceLab
except ImportError:
    from capvsar_qualification import QualificationLab
    from capvsar_surface import SurfaceLab


AUTHORITY = {"roll": (-.35, .35), "pitch": (-.45, .45),
             "yaw": (-1., 1.), "throttle": (0., 1.),
             "flap": (0., 1.), "trim": (-.6, .6), "brake": (0., 1.)}


class MissionLab(QualificationLab):
    def __init__(self, xp, sink, config):
        super().__init__(xp, sink, config)
        self.nav1 = xp.findDataRef("sim/cockpit2/radios/actuators/nav1_frequency_hz")
        self.obs1 = xp.findDataRef("sim/cockpit2/radios/actuators/nav1_obs_deg_mag_pilot")
        if not self.nav1 or not self.obs1:
            raise ValueError("NAV1 tuning datarefs unavailable")

    def validate_controls(self, controls):
        if not isinstance(controls, dict) or set(controls) != set(AUTHORITY):
            raise ValueError("Complete mission actuator frame required")
        for key, (low, high) in AUTHORITY.items():
            value = controls[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError("Mission actuator limit: " + key)

    def reset(self, core, checkpoint=None):
        self.verify_identity()
        if (not self.sink.is_paused() or self.sink.override_state() is not False
                or self.sink.ap_engaged() is not False
                or core.state not in ("MANUAL", "PAUSED_FAULT")):
            raise ValueError("Mission adoption requires paused manual aircraft")
        if checkpoint == "KSEE parking":
            setup = SurfaceLab(self.xp, self.sink,
                               {"aircraft_path": self.aircraft,
                                "expires_unix_s": self.expires,
                                "parking": "KSEE East Transient Parking 12"})
            result = setup.reset(core)
            self.xp.setDatai(self.nav1, 11195)
            self.xp.setDataf(self.obs1, 281.)
            self.trial_started = None
            self.previous_sim = None
            self.reset_count += 1
            return {**result, "reset_count": self.reset_count,
                    "nav1_frequency_hz": 11195}
        if checkpoint is not None:
            raise ValueError("Unknown mission checkpoint")
        xp = self.xp
        lat = xp.getDatad(self.refs["sim/flightmodel/position/latitude"])
        lon = xp.getDatad(self.refs["sim/flightmodel/position/longitude"])
        alt = xp.getDataf(xp.findDataRef("sim/cockpit2/gauges/indicators/altitude_ft_pilot"))
        ias = xp.getDataf(xp.findDataRef("sim/flightmodel/position/indicated_airspeed"))
        agl = xp.getDataf(xp.findDataRef("sim/flightmodel/position/y_agl"))
        airborne = (32.65 <= lat <= 33.06 and -117.40 <= lon <= -116.75
                    and 500 <= alt <= 6500 and 50 <= ias <= 140 and agl >= 60)
        rollout = (32.805 <= lat <= 32.825 and -117.15 <= lon <= -117.12
                   and 380 <= alt <= 500 and 0 <= ias <= 80 and -1 <= agl <= 3
                   and xp.getDatai(xp.findDataRef("sim/flightmodel/failures/onground_any")) == 1)
        if not (airborne or rollout):
            raise ValueError("Mission adoption requires paused route or KMYF 28R rollout")
        self.sink.command_ap_off()
        xp.setDatai(self.nav1, 11195)
        xp.setDataf(self.obs1, 281.)
        if xp.getDatai(self.nav1) != 11195:
            raise ValueError("ILS NAV1 tuning not confirmed")
        self.trial_started = None
        self.previous_sim = None
        self.reset_count += 1
        return {"reset_count": self.reset_count, "adopted": True,
                "latitude_deg": lat, "longitude_deg": lon,
                "altitude_indicated_ft": alt, "kias": ias, "agl_m": agl,
                "nav1_frequency_hz": 11195}

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
                    raise ValueError("Mission resume not observed within 150 ms")
                return
            self.resume_pending = False
        rollout = (v["on_ground"] and 32.805 <= v["latitude_deg"] <= 32.825
                   and -117.15 <= v["longitude_deg"] <= -117.12
                   and 380 <= v["altitude_indicated_ft"] <= 500
                   and 0 <= v["kias"] <= 80 and 0 <= v["groundspeed_mps"] <= 45
                   and abs(v["roll_deg"]) <= 15 and abs(v["pitch_deg"]) <= 15)
        ksee_surface = (32.80 <= v["latitude_deg"] <= 32.85
                        and -117.05 <= v["longitude_deg"] <= -116.94
                        and 0 <= v["kias"] <= 110 and 0 <= v["groundspeed_mps"] <= 65
                        and -1 <= v["agl_m"] <= 3
                        and abs(v["roll_deg"]) <= 15 and abs(v["pitch_deg"]) <= 15)
        airborne = (not v["on_ground"] and 32.65 <= v["latitude_deg"] <= 33.06
                    and -117.40 <= v["longitude_deg"] <= -116.75
                    and 300 <= v["altitude_indicated_ft"] <= 6500
                    and 40 <= v["kias"] <= 145
                    and abs(v["roll_deg"]) <= 38 and abs(v["pitch_deg"]) <= 24)
        if (v["paused"] or not (airborne or rollout or ksee_surface)
                or time.monotonic()-self.trial_started > 3600):
            raise ValueError("Mission flight envelope exceeded")
        if self.previous_sim is not None and v["sim_time_s"] <= self.previous_sim:
            raise ValueError("Mission simulation time reset or stopped")
        self.previous_sim = v["sim_time_s"]
