#!/usr/bin/env python3
"""
Mission Scenario: Gillespie Field (KSEE 27R) to Ramona Airport (KRNM 27)
------------------------------------------------------------------------
Exercises the retired full-flight prototype against its offline mock only:
1. Cold & Dark setup on KSEE Runway 27R.
2. Authentic POH Before Start & Engine Start checklists.
3. Engine runup & Before Takeoff checklist.
4. Takeoff roll, rotation at 60 KIAS, climb out to 1,500 ft MSL.
5. Turn right heading 015° M, climb to 4,500 ft MSL enroute cruise.
6. Transit over high terrain (Iron Mountain ridge).
7. Descent into Ramona Valley to 2,400 ft MSL.
8. Intercept extended final for Runway 27 (heading 273° M).
9. Fly 3° glidepath, full flaps, flare, touchdown on Runway 27.
10. Rollout, braking to full stop, and engine shutdown.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from .c182t_checklists import (
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
from .flight_controller import FlightController, FlightPhase, haversine_distance_nm
from .xplane_udp import XPlaneUDPClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ai_pilot.mission")


class MockFlightSimulator:
    """Headless flight physics simulator to validate mission without live X-Plane."""

    def __init__(self, client: XPlaneUDPClient, controller: FlightController):
        self.client = client
        self.controller = controller

        # Initial conditions: KSEE 27R
        self.lat = controller.KSEE_27R_THRESHOLD[0]
        self.lon = controller.KSEE_27R_THRESHOLD[1]
        self.alt_msl = controller.KSEE_27R_THRESHOLD[2]
        self.heading_mag = controller.KSEE_27R_HEADING_MAG
        self.kias = 0.0
        self.pitch = 0.0
        self.roll = 0.0
        self.vvi = 0.0
        self.rpm = 0.0
        self.oil_press = 0.0

    def update(self, dt: float = 0.1) -> None:
        """Advance physics state based on controller commands."""
        c = self.client
        phase = self.controller.phase

        throttle = c.get_dref("sim/cockpit2/engine/actuators/throttle_ratio[0]")
        mixture = c.get_dref("sim/cockpit2/engine/actuators/mixture_ratio[0]")
        parking_brake = c.get_dref("sim/cockpit2/controls/parking_brake_ratio")
        starter = c.get_dref("sim/cockpit2/engine/actuators/ignition_key[0]")

        # Engine model
        if mixture > 0.1 and (starter >= 3.0 or self.rpm > 500.0):
            target_rpm = 700.0 + (throttle * 1700.0)
            self.rpm += (target_rpm - self.rpm) * min(1.0, dt * 2.0)
            self.oil_press = 45.0 + (self.rpm / 2400.0) * 15.0
        else:
            self.rpm = max(0.0, self.rpm - (dt * 400.0))
            self.oil_press = max(0.0, self.oil_press - (dt * 10.0))

        # Ground vs Flight dynamics
        if phase in (FlightPhase.COLD_AND_DARK, FlightPhase.STARTING_ENGINES, FlightPhase.BEFORE_TAKEOFF_RUNUP):
            self.kias = 0.0
            self.pitch = 0.0
            self.vvi = 0.0
            self.alt_msl = self.controller.KSEE_27R_THRESHOLD[2]

        elif phase == FlightPhase.TAKEOFF_ROLL:
            if parking_brake < 0.1:
                accel = 7.0 * throttle
                self.kias += accel * dt
            self.pitch = 0.0
            self.alt_msl = self.controller.KSEE_27R_THRESHOLD[2]

        elif phase == FlightPhase.ROTATE_AND_CLIMB:
            self.pitch = 7.5
            self.kias = 80.0
            self.vvi = 750.0
            self.alt_msl += (self.vvi / 60.0) * dt

        elif phase == FlightPhase.ENROUTE_CLIMB:
            self.pitch = 6.0
            self.kias = 80.0
            self.vvi = 700.0
            self.alt_msl += (self.vvi / 60.0) * dt
            # Turn to 015° M
            self.heading_mag = 15.0
            # Fly towards Ramona (~0.04 NM/s at 140 kts groundspeed)
            self.lat += 0.0003 * dt
            self.lon += 0.00008 * dt

        elif phase == FlightPhase.CRUISE:
            self.pitch = 1.0
            self.kias = 135.0
            self.vvi = 0.0
            self.alt_msl = 4500.0
            # Progress toward Ramona
            self.lat += 0.00045 * dt
            self.lon += 0.00010 * dt

        elif phase == FlightPhase.DESCENT:
            self.pitch = -2.0
            self.kias = 110.0
            self.vvi = -600.0
            self.alt_msl += (self.vvi / 60.0) * dt
            self.lat += 0.00035 * dt
            self.lon += 0.00015 * dt

        elif phase == FlightPhase.APPROACH_INTERCEPT:
            self.heading_mag = self.controller.KRNM_27_HEADING_MAG
            self.alt_msl = 2400.0
            self.kias = 80.0
            self.vvi = 0.0
            # Flying West onto runway 27
            self.lon -= 0.00030 * dt

        elif phase == FlightPhase.FINAL_APPROACH:
            self.heading_mag = self.controller.KRNM_27_HEADING_MAG
            self.kias = 65.0
            self.vvi = -500.0
            self.alt_msl = max(1395.0, self.alt_msl + (self.vvi / 60.0) * dt)
            self.lon -= 0.00025 * dt

        elif phase == FlightPhase.FLARE_AND_TOUCHDOWN:
            self.pitch = 4.5
            self.kias = max(50.0, self.kias - (dt * 5.0))
            self.vvi = -100.0
            self.alt_msl = 1395.0

        elif phase == FlightPhase.ROLLOUT_AND_STOP:
            self.pitch = 0.0
            decel = 8.0
            self.kias = max(0.0, self.kias - (decel * dt))
            self.vvi = 0.0
            self.alt_msl = 1395.0

        elif phase in (FlightPhase.ENGINE_SHUTDOWN, FlightPhase.COMPLETED):
            self.kias = 0.0
            self.vvi = 0.0
            self.alt_msl = 1395.0

        # Inject into mock dataref cache
        c.set_mock_dref("sim/flightmodel/position/latitude", self.lat)
        c.set_mock_dref("sim/flightmodel/position/longitude", self.lon)
        c.set_mock_dref("sim/flightmodel/position/elevation", self.alt_msl * 0.3048)
        c.set_mock_dref("sim/flightmodel/position/y_agl", max(0.0, (self.alt_msl - 1395.0 if self.lat > 33.0 else self.alt_msl - 388.0)) * 0.3048)
        c.set_mock_dref("sim/flightmodel/position/indicated_airspeed", self.kias)
        c.set_mock_dref("sim/flightmodel/position/groundspeed", self.kias * 0.51444)
        c.set_mock_dref("sim/flightmodel/position/mag_psi", self.heading_mag)
        c.set_mock_dref("sim/flightmodel/position/psi", (self.heading_mag + 11.5) % 360.0)
        c.set_mock_dref("sim/flightmodel/position/theta", self.pitch)
        c.set_mock_dref("sim/flightmodel/position/phi", self.roll)
        c.set_mock_dref("sim/flightmodel/position/vh_ind_fpm", self.vvi)
        c.set_mock_dref("sim/cockpit2/engine/indicators/engine_speed_rpm[0]", self.rpm)
        c.set_mock_dref("sim/cockpit2/engine/indicators/oil_pressure_psi[0]", self.oil_press)


def run_mission(live: bool = False, host: str = "127.0.0.1", port: int = 49000, fast_sim: bool = False) -> bool:
    """Run the offline prototype; refuse its unvalidated live control route."""
    if live:
        logger.error(
            "Live scripted mission control is retired. Position CAP 487 airborne "
            "manually and use services.ai_pilot.maneuver_server --live."
        )
        return False
    logger.info("================================================================================")
    logger.info("  MISSION DISPATCH: CIVIL AIR PATROL C182T NAV III (CAP 487)")
    logger.info("  ROUTE: GILLESPIE FIELD (KSEE 27R) -> RAMONA AIRPORT (KRNM 27)")
    logger.info("  MODE: %s", "LIVE X-PLANE 12 CONNECTION" if live else "OFFLINE SIMULATION HARNESS")
    logger.info("================================================================================")

    client = XPlaneUDPClient(host=host, port=port, mock=not live)
    controller = FlightController(client)
    mock_sim = None if live else MockFlightSimulator(client, controller)

    try:
        # Step 1: Position aircraft at KSEE Runway 27R threshold
        logger.info("\n>>> STEP 1: AIRCRAFT POSITIONING & COLD COCKPIT SETUP")
        controller.spawn_on_ksee_27r()

        # Step 2: Before Engine Start Checklist
        logger.info("\n>>> STEP 2: BEFORE ENGINE START CHECKLIST")
        cl_before_start = get_before_engine_start_checklist()
        cl_before_start.run(client, delay_between_items=0.05 if not live else 0.2)

        # Step 3: Engine Start Checklist
        logger.info("\n>>> STEP 3: ENGINE START (LYCOMING IO-540)")
        controller.set_phase(FlightPhase.STARTING_ENGINES)
        cl_start = get_engine_start_checklist()
        cl_start.run(client, delay_between_items=0.05 if not live else 0.2)

        if not live:
            # Advance mock engine start
            for _ in range(15):
                mock_sim.update(dt=0.1)

        # Step 4: Before Takeoff Checklist (Runup, bugs set, controls checked)
        logger.info("\n>>> STEP 4: BEFORE TAKEOFF CHECKLIST & RUNUP")
        cl_before_to = get_before_takeoff_checklist(runway_heading_mag=274.0, target_altitude_ft=4500.0)
        cl_before_to.run(client, delay_between_items=0.05 if not live else 0.2)

        # Step 5: Takeoff Roll
        logger.info("\n>>> STEP 5: TAKEOFF CLEARANCE & GROUND ROLL (RUNWAY 27R)")
        controller.set_phase(FlightPhase.TAKEOFF_ROLL)
        cl_climb = get_takeoff_and_climb_checklist()
        cl_climb.run(client, delay_between_items=0.05 if not live else 0.2)

        # Main flight loop
        max_duration = 300.0 if not live else 1800.0
        dt = 0.05 if (fast_sim and not live) else 0.1
        start_time = time.time()
        last_log_time = 0.0

        logger.info("\n>>> STEP 6: ENROUTE GUIDANCE & MISSION EXECUTION ACTIVE")
        while controller.phase != FlightPhase.COMPLETED:
            if not live and mock_sim:
                mock_sim.update(dt=dt * (10.0 if fast_sim else 1.0))

            phase = controller.step()

            # Periodic status log every 5 simulated seconds
            now = time.time()
            if now - last_log_time >= (0.5 if fast_sim else 5.0):
                last_log_time = now
                t = controller.telemetry
                dist = haversine_distance_nm(t.lat, t.lon, controller.KRNM_27_THRESHOLD[0], controller.KRNM_27_THRESHOLD[1])
                logger.info(
                    "STATUS: %-20s | Alt: %5.0f ft MSL (%4.0f AGL) | IAS: %3.0f kts | Hdg: %03.0f° M | To KRNM: %4.1f NM",
                    phase.value,
                    t.alt_msl_ft,
                    t.alt_agl_ft,
                    t.kias,
                    t.heading_mag,
                    dist,
                )

            if (now - start_time) > max_duration:
                logger.error("Mission timed out before reaching completion.")
                return False

            if not fast_sim:
                time.sleep(dt)

        logger.info("================================================================================")
        logger.info("  MISSION SUCCESSFUL: AIRCRAFT SHUT DOWN & SECURED ON RUNWAY 27 AT RAMONA (KRNM)")
        logger.info("  TOTAL MISSION EVENTS: %d", len(controller.mission_log))
        logger.info("================================================================================")
        return True

    finally:
        client.stop()


def main():
    parser = argparse.ArgumentParser(description="Cessna 182T NAV III Autonomous Flight: KSEE 27R to KRNM 27")
    parser.add_argument(
        "--live", action="store_true",
        help="Retired compatibility flag; live scripted control is refused",
    )
    parser.add_argument("--host", default="127.0.0.1", help="X-Plane UDP host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=49000, help="X-Plane UDP port (default: 49000)")
    parser.add_argument("--fast", action="store_true", help="Fast execution in mock mode")
    args = parser.parse_args()

    success = run_mission(live=args.live, host=args.host, port=args.port, fast_sim=args.fast)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
