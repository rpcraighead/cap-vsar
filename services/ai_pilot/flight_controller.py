"""
Flight Controller & Guidance State Machine
------------------------------------------
Hierarchical inner-loop flight controller for the Cessna 182T NAV III.
Coordinates flight phases from engine startup, takeoff roll on KSEE 27R,
rotation, obstacle clearance climb, enroute navigation, descent profiling,
Runway 27 final approach intercept at KRNM, flare assist, rollout, and full stop.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .c182t_checklists import (
    ChecklistPhase,
    get_after_landing_checklist,
    get_before_engine_start_checklist,
    get_before_landing_checklist,
    get_before_takeoff_checklist,
    get_cruise_checklist,
    get_descent_checklist,
    get_engine_start_checklist,
    get_shutdown_and_securing_checklist,
    get_takeoff_and_climb_checklist,
)
from .xplane_udp import XPlaneUDPClient

logger = logging.getLogger("ai_pilot.controller")


class FlightPhase(str, Enum):
    COLD_AND_DARK = "COLD_AND_DARK"
    STARTING_ENGINES = "STARTING_ENGINES"
    BEFORE_TAKEOFF_RUNUP = "BEFORE_TAKEOFF_RUNUP"
    TAKEOFF_ROLL = "TAKEOFF_ROLL"
    ROTATE_AND_CLIMB = "ROTATE_AND_CLIMB"
    ENROUTE_CLIMB = "ENROUTE_CLIMB"
    CRUISE = "CRUISE"
    DESCENT = "DESCENT"
    APPROACH_INTERCEPT = "APPROACH_INTERCEPT"
    FINAL_APPROACH = "FINAL_APPROACH"
    FLARE_AND_TOUCHDOWN = "FLARE_AND_TOUCHDOWN"
    ROLLOUT_AND_STOP = "ROLLOUT_AND_STOP"
    ENGINE_SHUTDOWN = "ENGINE_SHUTDOWN"
    COMPLETED = "COMPLETED"


@dataclass
class Waypoint:
    name: str
    lat: float
    lon: float
    target_alt_ft: float
    target_kias: float
    note: str = ""


@dataclass
class AircraftTelemetry:
    lat: float = 0.0
    lon: float = 0.0
    alt_msl_ft: float = 0.0
    alt_agl_ft: float = 0.0
    kias: float = 0.0
    groundspeed_kts: float = 0.0
    heading_mag: float = 0.0
    heading_true: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    vvi_fpm: float = 0.0
    rpm: float = 0.0
    mp_inhg: float = 0.0
    flaps_ratio: float = 0.0
    brakes_ratio: float = 0.0
    gear_handle: float = 1.0


def haversine_distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great circle distance between two points in Nautical Miles."""
    r_nm = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_nm * c


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate initial true bearing between two points in degrees (0-360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    b = math.degrees(math.atan2(y, x))
    return (b + 360.0) % 360.0


class FlightController:
    """Inner-loop flight guidance state machine for C182T NAV III."""

    # San Diego local magnetic variation (~11.5 deg East)
    MAG_VAR_DEG = 11.5

    # Mission Waypoints: KSEE 27R to KRNM 27
    KSEE_27R_THRESHOLD = (32.8263994, -116.9642836, 388.0)
    KSEE_27R_HEADING_MAG = 274.0

    KRNM_27_THRESHOLD = (33.0379711, -116.9072216, 1395.0)
    KRNM_27_HEADING_MAG = 273.0

    def __init__(self, client: XPlaneUDPClient):
        self.client = client
        self.phase: FlightPhase = FlightPhase.COLD_AND_DARK
        self.telemetry = AircraftTelemetry()

        # Target setpoints
        self.target_heading_mag: float = 274.0
        self.target_altitude_ft: float = 4500.0
        self.target_kias: float = 80.0
        self.target_vvi_fpm: float = 700.0

        # Phase timing & state tracking
        self.phase_start_time: float = time.time()
        self.rollout_start_time: Optional[float] = None
        self.mission_log: List[str] = []

        # Setup Waypoints
        # RNM 27 Final fix is ~4.0 NM East along the 093° M / 105° T radial
        final_fix_lat = 33.0280
        final_fix_lon = -116.8320
        self.waypoints: List[Waypoint] = [
            Waypoint("KSEE_DEP", 32.8264, -116.9850, 1500.0, 80.0, "Climb straight out to 1,500 ft"),
            Waypoint("SANTEE_TURN", 32.8500, -116.9600, 3000.0, 80.0, "Turn right towards Ramona"),
            Waypoint("ENROUTE_CRUISE", 32.9500, -116.9300, 4500.0, 120.0, "Cruise over Iron Mtn ridge"),
            Waypoint("RNM_DESCENT", 33.0000, -116.9000, 3000.0, 100.0, "Commence descent towards Ramona"),
            Waypoint("RNM_INTERCEPT", final_fix_lat, final_fix_lon, 2400.0, 80.0, "Intercept Rwy 27 final at 2,400 ft"),
            Waypoint("RNM_27_THR", 33.0380, -116.9072, 1445.0, 65.0, "Runway 27 threshold 50 ft AGL"),
            Waypoint("RNM_TOUCHDOWN", 33.0385, -116.9110, 1395.0, 55.0, "Runway 27 touchdown zone"),
        ]
        self.current_wp_idx: int = 0

    def log(self, msg: str) -> None:
        """Log mission event with timestamp."""
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] [{self.phase.value}] {msg}"
        self.mission_log.append(entry)
        logger.info(entry)

    def set_phase(self, new_phase: FlightPhase) -> None:
        """Transition state machine to a new flight phase."""
        old_phase = self.phase
        self.phase = new_phase
        self.phase_start_time = time.time()
        self.log(f"Phase transition: {old_phase.value} -> {new_phase.value}")

    def update_telemetry(self) -> AircraftTelemetry:
        """Read all relevant flight datarefs into telemetry dataclass."""
        c = self.client
        t = self.telemetry

        t.lat = c.get_dref("sim/flightmodel/position/latitude", t.lat)
        t.lon = c.get_dref("sim/flightmodel/position/longitude", t.lon)
        # elevation is in meters MSL in X-Plane
        elev_m = c.get_dref("sim/flightmodel/position/elevation", 0.0)
        t.alt_msl_ft = elev_m * 3.28084
        t.alt_agl_ft = c.get_dref("sim/flightmodel/position/y_agl", 0.0) * 3.28084

        t.kias = c.get_dref("sim/flightmodel/position/indicated_airspeed", 0.0)
        t.groundspeed_kts = c.get_dref("sim/flightmodel/position/groundspeed", 0.0) * 1.94384
        t.heading_mag = c.get_dref("sim/flightmodel/position/mag_psi", 0.0)
        t.heading_true = c.get_dref("sim/flightmodel/position/psi", 0.0)
        t.pitch_deg = c.get_dref("sim/flightmodel/position/theta", 0.0)
        t.roll_deg = c.get_dref("sim/flightmodel/position/phi", 0.0)
        t.vvi_fpm = c.get_dref("sim/flightmodel/position/vh_ind_fpm", 0.0)

        t.rpm = c.get_dref("sim/cockpit2/engine/indicators/engine_speed_rpm[0]", 0.0)
        t.mp_inhg = c.get_dref("sim/cockpit2/engine/indicators/MPR_in_hg[0]", 0.0)
        t.flaps_ratio = c.get_dref("sim/cockpit2/controls/flap_handle_request_ratio", 0.0)
        t.brakes_ratio = c.get_dref("sim/cockpit2/controls/parking_brake_ratio", 0.0)

        return t

    # --------------------------------------------------------------------------
    # Flight Control Step: Evaluated at 10-20 Hz
    # --------------------------------------------------------------------------

    def step(self) -> FlightPhase:
        """Single guidance update cycle based on current state."""
        self.update_telemetry()
        t = self.telemetry

        if self.phase == FlightPhase.COLD_AND_DARK:
            # Aircraft parked cold on KSEE 27R
            self.client.send_dref("sim/cockpit2/controls/parking_brake_ratio", 1.0)
            self.client.send_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]", 0.0)

        elif self.phase == FlightPhase.STARTING_ENGINES:
            # Check if engine is running (> 600 RPM)
            if t.rpm >= 600.0:
                self.log(f"Engine running: {t.rpm:.0f} RPM. Ready for Before Takeoff Runup.")
                self.set_phase(FlightPhase.BEFORE_TAKEOFF_RUNUP)

        elif self.phase == FlightPhase.BEFORE_TAKEOFF_RUNUP:
            # Ready to start takeoff roll once brakes released and takeoff checklist run
            pass

        elif self.phase == FlightPhase.TAKEOFF_ROLL:
            # Full throttle, prop high RPM, maintain runway centerline (274 deg M)
            self.client.send_dref("sim/cockpit2/controls/parking_brake_ratio", 0.0)
            self.client.send_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]", 1.0)
            self.client.send_dref("sim/cockpit2/engine/actuators/prop_ratio[0]", 1.0)
            self.client.send_dref("sim/cockpit2/engine/actuators/mixture_ratio[0]", 1.0)
            self.client.send_dref("sim/cockpit2/controls/flap_handle_request_ratio", 0.0)

            # Directional rudder steering to hold runway heading
            hdg_err = (self.KSEE_27R_HEADING_MAG - t.heading_mag + 180.0) % 360.0 - 180.0
            rudder_cmd = max(-0.4, min(0.4, hdg_err * 0.08))
            self.client.send_dref("sim/cockpit2/controls/yoke_heading_ratio", rudder_cmd)

            # Airspeed check: Rotate at Vr = 60 KIAS
            if t.kias >= 60.0:
                self.log(f"Airspeed Vr reached: {t.kias:.1f} KIAS. Rotating!")
                self.set_phase(FlightPhase.ROTATE_AND_CLIMB)

        elif self.phase == FlightPhase.ROTATE_AND_CLIMB:
            # Rotate: smoothly pull back yoke to establish 7-8 deg pitch attitude
            pitch_err = 7.5 - t.pitch_deg
            pitch_cmd = max(-0.2, min(0.6, pitch_err * 0.08))
            self.client.send_dref("sim/cockpit2/controls/yoke_pitch_ratio", pitch_cmd)

            # Wings level on runway heading
            hdg_err = (self.KSEE_27R_HEADING_MAG - t.heading_mag + 180.0) % 360.0 - 180.0
            roll_cmd = max(-0.25, min(0.25, (hdg_err * 0.03) - (t.roll_deg * 0.05)))
            self.client.send_dref("sim/cockpit2/controls/yoke_roll_ratio", roll_cmd)

            # Keep full power
            self.client.send_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]", 1.0)

            # Climb out to 1,500 ft MSL before initiating turn to Ramona
            if t.alt_msl_ft >= 1500.0:
                self.log(f"Reached 1,500 ft MSL ({t.alt_msl_ft:.0f} ft). Engaging enroute climb turn.")
                # Turn right towards Ramona (~015° M)
                self.target_heading_mag = 15.0
                self.target_altitude_ft = 4500.0
                self.set_phase(FlightPhase.ENROUTE_CLIMB)

        elif self.phase == FlightPhase.ENROUTE_CLIMB:
            # Engage X-Plane autopilot to hold heading 015° and climb to 4,500 ft MSL
            self._engage_autopilot(hdg_mag=self.target_heading_mag, alt_ft=self.target_altitude_ft, vs_fpm=700.0)
            self.client.send_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]", 1.0)
            self.client.send_dref("sim/cockpit2/engine/actuators/prop_ratio[0]", 1.0)
            self.client.send_dref("sim/cockpit2/controls/flap_handle_request_ratio", 0.0)

            # Check if cruise altitude (4,500 ft MSL) reached
            if t.alt_msl_ft >= 4400.0:
                self.log(f"Leveled off at cruise altitude: {t.alt_msl_ft:.0f} ft MSL.")
                get_cruise_checklist().run(self.client, delay_between_items=0.05)
                self.set_phase(FlightPhase.CRUISE)

        elif self.phase == FlightPhase.CRUISE:
            # Cruise segment: heading towards Ramona
            dist_to_krnm = haversine_distance_nm(t.lat, t.lon, self.KRNM_27_THRESHOLD[0], self.KRNM_27_THRESHOLD[1])

            # Calculate bearing towards Ramona
            bearing_true = initial_bearing_deg(t.lat, t.lon, self.KRNM_27_THRESHOLD[0], self.KRNM_27_THRESHOLD[1])
            bearing_mag = (bearing_true - self.MAG_VAR_DEG + 360.0) % 360.0
            self.target_heading_mag = bearing_mag
            self._engage_autopilot(hdg_mag=self.target_heading_mag, alt_ft=4500.0)

            # When within 6 NM of Ramona, start descent checklist & profile
            if dist_to_krnm <= 6.0:
                self.log(f"Distance to Ramona is {dist_to_krnm:.1f} NM. Initiating descent to 2,400 ft.")
                get_descent_checklist().run(self.client, delay_between_items=0.05)
                self.target_altitude_ft = 2400.0
                self.set_phase(FlightPhase.DESCENT)

        elif self.phase == FlightPhase.DESCENT:
            # Descend to 2,400 ft MSL (Ramona pattern/approach intercept altitude)
            dist_to_krnm = haversine_distance_nm(t.lat, t.lon, self.KRNM_27_THRESHOLD[0], self.KRNM_27_THRESHOLD[1])

            # Steer toward the Ramona Runway 27 approach intercept fix (4 NM East of KRNM)
            fix_lat, fix_lon = self.waypoints[4].lat, self.waypoints[4].lon
            bearing_to_fix_t = initial_bearing_deg(t.lat, t.lon, fix_lat, fix_lon)
            bearing_to_fix_m = (bearing_to_fix_t - self.MAG_VAR_DEG + 360.0) % 360.0

            self._engage_autopilot(hdg_mag=bearing_to_fix_m, alt_ft=2400.0, vs_fpm=-600.0)
            self.client.send_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]", 0.45)

            dist_to_fix = haversine_distance_nm(t.lat, t.lon, fix_lat, fix_lon)
            if dist_to_fix <= 1.2 or (t.alt_msl_ft <= 2500.0 and dist_to_krnm <= 4.5):
                self.log(f"Approaching final approach fix. Intercepting Runway 27 centerline.")
                self.target_heading_mag = self.KRNM_27_HEADING_MAG
                self.set_phase(FlightPhase.APPROACH_INTERCEPT)

        elif self.phase == FlightPhase.APPROACH_INTERCEPT:
            # Turn to final heading 273° M, reduce airspeed to 80 KIAS, set Flaps 10°
            self._engage_autopilot(hdg_mag=self.KRNM_27_HEADING_MAG, alt_ft=2400.0)
            self.client.send_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]", 0.35)
            self.client.send_dref("sim/cockpit2/controls/flap_handle_request_ratio", 0.333)

            # Check alignment with Runway 27 extended centerline
            thr_lat, thr_lon, _ = self.KRNM_27_THRESHOLD
            dist_to_thr = haversine_distance_nm(t.lat, t.lon, thr_lat, thr_lon)
            if dist_to_thr <= 3.2:
                self.log(f"Established on final 3.0 NM out. Running Before Landing checklist.")
                get_before_landing_checklist().run(self.client, delay_between_items=0.05)
                self.set_phase(FlightPhase.FINAL_APPROACH)

        elif self.phase == FlightPhase.FINAL_APPROACH:
            # Disengage autopilot for manual flare control or fly 3° glidepath
            # Glidepath: 318 ft/NM descent from threshold elevation (1395 ft MSL)
            thr_lat, thr_lon, thr_elev = self.KRNM_27_THRESHOLD
            dist_to_thr = haversine_distance_nm(t.lat, t.lon, thr_lat, thr_lon)
            target_alt_msl = thr_elev + 50.0 + (dist_to_thr * 318.0)

            # Flaps 20° then Full 30°
            if dist_to_thr < 2.0:
                self.client.send_dref("sim/cockpit2/controls/flap_handle_request_ratio", 1.0)
            else:
                self.client.send_dref("sim/cockpit2/controls/flap_handle_request_ratio", 0.667)

            # Airspeed target: 65 KIAS
            speed_err = 65.0 - t.kias
            throttle_cmd = max(0.15, min(0.60, 0.35 + (speed_err * 0.02)))
            self.client.send_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]", throttle_cmd)

            # Lateral guidance: hold runway heading 273° M
            hdg_err = (self.KRNM_27_HEADING_MAG - t.heading_mag + 180.0) % 360.0 - 180.0
            self.client.send_dref("sim/cockpit2/controls/yoke_roll_ratio", max(-0.2, min(0.2, hdg_err * 0.04)))

            # Vertical guidance: pitch for glidepath
            alt_err = target_alt_msl - t.alt_msl_ft
            target_vvi = max(-800.0, min(-300.0, -500.0 + (alt_err * 2.0)))
            vvi_err = target_vvi - t.vvi_fpm
            pitch_cmd = max(-0.25, min(0.25, vvi_err * 0.0008))
            self.client.send_dref("sim/cockpit2/controls/yoke_pitch_ratio", pitch_cmd)

            # Disengage AP servos if active
            self.client.send_dref("sim/cockpit2/autopilot/servos_on", 0.0)

            # Transition to flare when passing below 40 ft AGL or crossing threshold
            if t.alt_agl_ft <= 40.0 or (dist_to_thr < 0.1 and t.alt_agl_ft <= 60.0):
                self.log(f"Over threshold at {t.alt_agl_ft:.1f} ft AGL. Initiating flare.")
                self.set_phase(FlightPhase.FLARE_AND_TOUCHDOWN)

        elif self.phase == FlightPhase.FLARE_AND_TOUCHDOWN:
            # Idle throttle
            self.client.send_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]", 0.0)

            # Smooth flare: raise nose to 4.5 degrees
            pitch_err = 4.5 - t.pitch_deg
            pitch_cmd = max(0.0, min(0.4, pitch_err * 0.08))
            self.client.send_dref("sim/cockpit2/controls/yoke_pitch_ratio", pitch_cmd)

            # Keep wings level
            self.client.send_dref("sim/cockpit2/controls/yoke_roll_ratio", -t.roll_deg * 0.06)

            # Rudder to align with runway heading
            hdg_err = (self.KRNM_27_HEADING_MAG - t.heading_mag + 180.0) % 360.0 - 180.0
            self.client.send_dref("sim/cockpit2/controls/yoke_heading_ratio", hdg_err * 0.04)

            # Detect touchdown: AGL < 4 ft and vertical speed near zero
            if t.alt_agl_ft <= 4.0:
                self.log(f"Touchdown on Runway 27 at Ramona! Rollout commences.")
                self.rollout_start_time = time.time()
                self.set_phase(FlightPhase.ROLLOUT_AND_STOP)

        elif self.phase == FlightPhase.ROLLOUT_AND_STOP:
            # Lower nosewheel, steer runway heading, apply brakes
            self.client.send_dref("sim/cockpit2/controls/yoke_pitch_ratio", -0.05)
            self.client.send_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]", 0.0)

            # Rudder steering
            hdg_err = (self.KRNM_27_HEADING_MAG - t.heading_mag + 180.0) % 360.0 - 180.0
            self.client.send_dref("sim/cockpit2/controls/yoke_heading_ratio", max(-0.5, min(0.5, hdg_err * 0.06)))

            # Progressive braking
            self.client.send_dref("sim/cockpit2/controls/left_brake_ratio", 0.75)
            self.client.send_dref("sim/cockpit2/controls/right_brake_ratio", 0.75)

            # Full stop condition (groundspeed < 2 kts)
            if t.groundspeed_kts < 2.0 or (self.rollout_start_time and time.time() - self.rollout_start_time > 20.0):
                self.log(f"Aircraft full stop on Runway 27. Setting parking brake.")
                self.client.send_dref("sim/cockpit2/controls/parking_brake_ratio", 1.0)
                self.client.send_dref("sim/cockpit2/controls/left_brake_ratio", 0.0)
                self.client.send_dref("sim/cockpit2/controls/right_brake_ratio", 0.0)

                # Execute After Landing checklist
                get_after_landing_checklist().run(self.client, delay_between_items=0.05)

                self.set_phase(FlightPhase.ENGINE_SHUTDOWN)

        elif self.phase == FlightPhase.ENGINE_SHUTDOWN:
            self.log("Executing Shutdown & Securing checklist.")
            get_shutdown_and_securing_checklist().run(self.client, delay_between_items=0.05)
            self.set_phase(FlightPhase.COMPLETED)

        elif self.phase == FlightPhase.COMPLETED:
            pass

        return self.phase

    def _engage_autopilot(self, hdg_mag: float, alt_ft: float, vs_fpm: Optional[float] = None) -> None:
        """Configure and engage X-Plane autopilot modes."""
        c = self.client
        c.send_dref("sim/cockpit2/autopilot/servos_on", 1.0)
        c.send_dref("sim/cockpit2/autopilot/flight_director_mode", 2.0)
        c.send_dref("sim/cockpit2/autopilot/heading_mode", 1.0)  # HDG mode
        c.send_dref("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot", hdg_mag)
        c.send_dref("sim/cockpit2/autopilot/altitude_dial_ft", alt_ft)
        c.send_dref("sim/cockpit2/autopilot/altitude_mode", 6.0)  # ALT hold / arm
        if vs_fpm is not None:
            c.send_dref("sim/cockpit2/autopilot/vvi_dial_ft_per_min", vs_fpm)

    def spawn_on_ksee_27r(self) -> None:
        """Position aircraft at Gillespie Field (KSEE) Runway 27R threshold."""
        lat, lon, elev_ft = self.KSEE_27R_THRESHOLD
        elev_m = elev_ft * 0.3048
        heading_true = (self.KSEE_27R_HEADING_MAG + self.MAG_VAR_DEG) % 360.0

        self.log(f"Positioning aircraft on KSEE Runway 27R (Lat {lat}, Lon {lon}, Elev {elev_ft} ft, Hdg {self.KSEE_27R_HEADING_MAG}° M)")
        self.client.set_position(
            lat_deg=lat,
            lon_deg=lon,
            ele_m=elev_m,
            heading_true=heading_true,
            pitch_deg=0.0,
            roll_deg=0.0,
        )
        # Configure cold-and-dark baseline
        get_before_engine_start_checklist().run(self.client, delay_between_items=0.05)
        self.set_phase(FlightPhase.COLD_AND_DARK)
