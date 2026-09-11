"""
Cessna 182T NAV III (Skylane G1000) Authentic POH Checklists
------------------------------------------------------------
Implements the authentic normal procedures checklists from the Cessna 182T
Information Manual / Pilot's Operating Handbook (POH), mapped directly to
X-Plane 12 datarefs and commands.

Supports challenge-and-response execution for AI agent (Hermes / BigBrain)
and automated copilot verification.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .xplane_udp import XPlaneUDPClient

logger = logging.getLogger("ai_pilot.checklists")


class ChecklistPhase(str, Enum):
    BEFORE_ENGINE_START = "BEFORE_ENGINE_START"
    ENGINE_START = "ENGINE_START"
    BEFORE_TAKEOFF = "BEFORE_TAKEOFF"
    TAKEOFF_AND_CLIMB = "TAKEOFF_AND_CLIMB"
    CRUISE = "CRUISE"
    DESCENT = "DESCENT"
    BEFORE_LANDING = "BEFORE_LANDING"
    AFTER_LANDING = "AFTER_LANDING"
    SHUTDOWN_AND_SECURING = "SHUTDOWN_AND_SECURING"


@dataclass
class ChecklistItem:
    """A single checklist item with POH procedure and dataref actions."""

    item: str
    target_state: str
    challenge: str
    response: str
    action_dref: Optional[str] = None
    action_val: Optional[float] = None
    action_cmd: Optional[str] = None
    verify_dref: Optional[str] = None
    verify_val: Optional[float] = None
    verify_tol: float = 0.05
    verify_fn: Optional[Callable[[float], bool]] = None
    note: str = ""

    def execute(self, client: XPlaneUDPClient) -> None:
        """Apply the action for this item."""
        if self.action_dref is not None and self.action_val is not None:
            client.send_dref(self.action_dref, self.action_val)
        if self.action_cmd:
            client.send_command(self.action_cmd)

    def verify(self, client: XPlaneUDPClient) -> bool:
        """Verify whether this item satisfies its target state."""
        if self.verify_fn and self.verify_dref:
            val = client.get_dref(self.verify_dref)
            return self.verify_fn(val)
        if self.verify_dref is not None and self.verify_val is not None:
            val = client.get_dref(self.verify_dref)
            return abs(val - self.verify_val) <= self.verify_tol
        if self.action_dref is not None and self.action_val is not None:
            val = client.get_dref(self.action_dref)
            return abs(val - self.action_val) <= self.verify_tol
        return True


@dataclass
class Checklist:
    """A sequence of checklist items comprising a flight procedure."""

    phase: ChecklistPhase
    title: str
    description: str
    items: List[ChecklistItem] = field(default_factory=list)

    def run(
        self,
        client: XPlaneUDPClient,
        delay_between_items: float = 0.2,
        interactive: bool = False,
    ) -> List[Dict[str, Any]]:
        """Execute and verify all items in order."""
        results = []
        logger.info("=== BEGIN CHECKLIST: %s ===", self.title)

        for item in self.items:
            logger.info("  [CHALLENGE] %s -> %s", item.challenge, item.response)
            item.execute(client)

            if delay_between_items > 0:
                time.sleep(delay_between_items)

            passed = item.verify(client)
            current_val = client.get_dref(item.verify_dref or item.action_dref or "")
            res = {
                "item": item.item,
                "challenge": item.challenge,
                "response": item.response,
                "passed": passed,
                "current_val": current_val,
                "note": item.note,
            }
            results.append(res)
            if not passed:
                logger.warning("  [!] Verification warning on '%s': read %s", item.item, current_val)
            else:
                logger.info("  [OK] %s: %s", item.item, item.response)

        logger.info("=== COMPLETED CHECKLIST: %s ===", self.title)
        return results


# ------------------------------------------------------------------------------
# Authentic Cessna 182T NAV III Checklist Definitions
# ------------------------------------------------------------------------------

def get_before_engine_start_checklist() -> Checklist:
    return Checklist(
        phase=ChecklistPhase.BEFORE_ENGINE_START,
        title="Before Starting Engine",
        description="POH Section 4 - Normal Procedures: Pre-start cockpit check.",
        items=[
            ChecklistItem(
                item="Preflight Inspection",
                target_state="COMPLETE",
                challenge="Preflight Inspection",
                response="COMPLETE",
                note="Airframe, controls, pitot tube, fuel caps verified.",
            ),
            ChecklistItem(
                item="Passenger Briefing",
                target_state="COMPLETE",
                challenge="Passenger Briefing",
                response="COMPLETE",
                note="Seatbelts, exits, sterile cockpit briefed.",
            ),
            ChecklistItem(
                item="Seat Belts & Shoulder Harnesses",
                target_state="FASTENED",
                challenge="Seat Belts & Harnesses",
                response="FASTENED",
            ),
            ChecklistItem(
                item="Parking Brake",
                target_state="SET",
                challenge="Parking Brake",
                response="SET",
                action_dref="sim/cockpit2/controls/parking_brake_ratio",
                action_val=1.0,
                verify_dref="sim/cockpit2/controls/parking_brake_ratio",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Circuit Breakers",
                target_state="CHECK IN",
                challenge="Circuit Breakers",
                response="CHECK IN",
                note="All breakers on essential, main, and avionics buses in.",
            ),
            ChecklistItem(
                item="Beacon Light",
                target_state="OFF",
                challenge="Beacon Light",
                response="OFF",
                action_dref="sim/cockpit2/switches/beacon_on",
                action_val=0.0,
            ),
            ChecklistItem(
                item="Landing & Taxi Lights",
                target_state="OFF",
                challenge="Landing & Taxi Lights",
                response="OFF",
                action_dref="sim/cockpit2/switches/landing_lights_on",
                action_val=0.0,
            ),
            ChecklistItem(
                item="Strobe Lights",
                target_state="OFF",
                challenge="Strobe Lights",
                response="OFF",
                action_dref="sim/cockpit2/switches/strobe_lights_on",
                action_val=0.0,
            ),
            ChecklistItem(
                item="Navigation Lights",
                target_state="OFF",
                challenge="Navigation Lights",
                response="OFF",
                action_dref="sim/cockpit2/switches/navigation_lights_on",
                action_val=0.0,
            ),
            ChecklistItem(
                item="Cowl Flaps",
                target_state="OPEN",
                challenge="Cowl Flaps",
                response="OPEN",
                action_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Fuel Selector Valve",
                target_state="BOTH",
                challenge="Fuel Selector",
                response="BOTH",
                action_dref="sim/cockpit2/fuel/fuel_tank_selector",
                action_val=4.0,  # 4 = BOTH / ALL
                verify_dref="sim/cockpit2/fuel/fuel_tank_selector",
                verify_val=4.0,
            ),
            ChecklistItem(
                item="Avionics Master Switch",
                target_state="OFF",
                challenge="Avionics Master",
                response="OFF",
                action_dref="sim/cockpit2/switches/avionics_power_on",
                action_val=0.0,
                verify_dref="sim/cockpit2/switches/avionics_power_on",
                verify_val=0.0,
            ),
        ],
    )


def get_engine_start_checklist() -> Checklist:
    return Checklist(
        phase=ChecklistPhase.ENGINE_START,
        title="Engine Starting (Normal / Cold Start)",
        description="POH Section 4 - Lycoming IO-540 fuel-injected engine start procedure.",
        items=[
            ChecklistItem(
                item="Throttle",
                target_state="OPEN 1/4 INCH",
                challenge="Throttle",
                response="OPEN 1/4 INCH",
                action_dref="sim/cockpit2/engine/actuators/throttle_ratio[0]",
                action_val=0.15,
                verify_dref="sim/cockpit2/engine/actuators/throttle_ratio[0]",
                verify_val=0.15,
                verify_tol=0.05,
            ),
            ChecklistItem(
                item="Propeller Control",
                target_state="HIGH RPM (FULL FORWARD)",
                challenge="Propeller",
                response="HIGH RPM",
                action_dref="sim/cockpit2/engine/actuators/prop_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/prop_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Mixture",
                target_state="IDLE CUT-OFF",
                challenge="Mixture",
                response="IDLE CUT-OFF",
                action_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                action_val=0.0,
                verify_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Flashing Beacon",
                target_state="ON",
                challenge="Beacon",
                response="ON",
                action_dref="sim/cockpit2/switches/beacon_on",
                action_val=1.0,
                verify_dref="sim/cockpit2/switches/beacon_on",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Master Switch (BAT)",
                target_state="ON",
                challenge="Master BAT",
                response="ON",
                action_dref="sim/cockpit2/electrical/battery_on[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/electrical/battery_on[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Auxiliary Fuel Pump",
                target_state="ON (PRIME)",
                challenge="Aux Fuel Pump",
                response="ON",
                action_dref="sim/cockpit2/engine/actuators/fuel_pump_on[0]",
                action_val=1.0,
            ),
            ChecklistItem(
                item="Mixture",
                target_state="ADVANCE TO FULL RICH (PRIME)",
                challenge="Mixture",
                response="RICH",
                action_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Auxiliary Fuel Pump",
                target_state="OFF",
                challenge="Aux Fuel Pump",
                response="OFF",
                action_dref="sim/cockpit2/engine/actuators/fuel_pump_on[0]",
                action_val=0.0,
                verify_dref="sim/cockpit2/engine/actuators/fuel_pump_on[0]",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Propeller Area",
                target_state="CLEAR",
                challenge="Propeller Area",
                response="CLEAR!",
                note="Visual scan 180 degrees forward and yell 'CLEAR PROP!'.",
            ),
            ChecklistItem(
                item="Ignition Switch",
                target_state="START",
                challenge="Ignition Switch",
                response="START",
                action_dref="sim/cockpit2/engine/actuators/ignition_key[0]",
                action_val=4.0,  # 4 = START
                action_cmd="sim/starters/engage_starter_1",
            ),
            ChecklistItem(
                item="Ignition Switch",
                target_state="BOTH (AFTER START)",
                challenge="Ignition Switch",
                response="BOTH",
                action_dref="sim/cockpit2/engine/actuators/ignition_key[0]",
                action_val=3.0,  # 3 = BOTH
                verify_dref="sim/cockpit2/engine/actuators/ignition_key[0]",
                verify_val=3.0,
            ),
            ChecklistItem(
                item="Oil Pressure",
                target_state="CHECK GREEN (> 20 PSI)",
                challenge="Oil Pressure",
                response="CHECK GREEN",
                verify_dref="sim/cockpit2/engine/indicators/oil_pressure_psi[0]",
                verify_fn=lambda psi: psi >= 15.0,
                note="Oil pressure must rise into green arc within 30 seconds.",
            ),
            ChecklistItem(
                item="Master Switch (ALT)",
                target_state="ON",
                challenge="Master ALT",
                response="ON",
                action_dref="sim/cockpit2/electrical/generator_on[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/electrical/generator_on[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Avionics Master Switch",
                target_state="ON",
                challenge="Avionics Master",
                response="ON",
                action_dref="sim/cockpit2/switches/avionics_power_on",
                action_val=1.0,
                verify_dref="sim/cockpit2/switches/avionics_power_on",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Navigation Lights",
                target_state="ON",
                challenge="Nav Lights",
                response="ON",
                action_dref="sim/cockpit2/switches/navigation_lights_on",
                action_val=1.0,
            ),
            ChecklistItem(
                item="Wing Flaps",
                target_state="UP (RETRACT)",
                challenge="Flaps",
                response="UP",
                action_dref="sim/cockpit2/controls/flap_handle_request_ratio",
                action_val=0.0,
                verify_dref="sim/cockpit2/controls/flap_handle_request_ratio",
                verify_val=0.0,
            ),
        ],
    )


def get_before_takeoff_checklist(runway_heading_mag: float = 274.0, target_altitude_ft: float = 4500.0) -> Checklist:
    return Checklist(
        phase=ChecklistPhase.BEFORE_TAKEOFF,
        title="Before Takeoff (Runup & Pre-Takeoff)",
        description="POH Section 4 - Engine runup, instrument check, and takeoff configuration.",
        items=[
            ChecklistItem(
                item="Parking Brake",
                target_state="SET",
                challenge="Parking Brake",
                response="SET",
                action_dref="sim/cockpit2/controls/parking_brake_ratio",
                action_val=1.0,
                verify_dref="sim/cockpit2/controls/parking_brake_ratio",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Cabin Doors and Windows",
                target_state="CLOSED & LOCKED",
                challenge="Doors and Windows",
                response="CLOSED & LOCKED",
            ),
            ChecklistItem(
                item="Flight Controls",
                target_state="FREE AND CORRECT",
                challenge="Flight Controls",
                response="FREE AND CORRECT",
                note="Yoke full left, full right, full aft, full forward; rudder pedals clear.",
            ),
            ChecklistItem(
                item="Flight Instruments & G1000",
                target_state="CHECK & SET",
                challenge="Flight Instruments",
                response="CHECK & SET",
                note="Altimeter set, attitude indicator level, DG aligned.",
            ),
            ChecklistItem(
                item="Autopilot Heading Bug",
                target_state=f"{runway_heading_mag:.0f} DEG MAG",
                challenge="Heading Bug",
                response=f"{runway_heading_mag:.0f} DEGREES",
                action_dref="sim/cockpit2/autopilot/heading_dial_deg_mag_pilot",
                action_val=runway_heading_mag,
                verify_dref="sim/cockpit2/autopilot/heading_dial_deg_mag_pilot",
                verify_val=runway_heading_mag,
                verify_tol=1.0,
            ),
            ChecklistItem(
                item="Autopilot Altitude Bug",
                target_state=f"{target_altitude_ft:.0f} FT",
                challenge="Altitude Bug",
                response=f"{target_altitude_ft:.0f} FEET",
                action_dref="sim/cockpit2/autopilot/altitude_dial_ft",
                action_val=target_altitude_ft,
                verify_dref="sim/cockpit2/autopilot/altitude_dial_ft",
                verify_val=target_altitude_ft,
                verify_tol=50.0,
            ),
            ChecklistItem(
                item="Fuel Selector Valve",
                target_state="BOTH",
                challenge="Fuel Selector",
                response="BOTH",
                action_dref="sim/cockpit2/fuel/fuel_tank_selector",
                action_val=4.0,
                verify_dref="sim/cockpit2/fuel/fuel_tank_selector",
                verify_val=4.0,
            ),
            ChecklistItem(
                item="Mixture",
                target_state="RICH",
                challenge="Mixture",
                response="RICH",
                action_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Propeller Control",
                target_state="HIGH RPM",
                challenge="Propeller",
                response="HIGH RPM",
                action_dref="sim/cockpit2/engine/actuators/prop_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/prop_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Cowl Flaps",
                target_state="OPEN",
                challenge="Cowl Flaps",
                response="OPEN",
                action_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Throttle (Engine Runup)",
                target_state="1800 RPM",
                challenge="Throttle",
                response="1800 RPM",
                action_dref="sim/cockpit2/engine/actuators/throttle_ratio[0]",
                action_val=0.65,
                note="Advance throttle to 1800 RPM for mag, prop, and engine gauge checks.",
            ),
            ChecklistItem(
                item="Magnetos Check",
                target_state="CHECK L / R (< 150 RPM DROP, < 50 DIFF)",
                challenge="Magnetos",
                response="CHECKED",
                note="Drop must not exceed 150 RPM on either mag, max difference 50 RPM.",
            ),
            ChecklistItem(
                item="Propeller Governor Check",
                target_state="EXERCISE (CYCLE)",
                challenge="Propeller Governor",
                response="EXERCISED",
                note="Cycle prop control toward low RPM until slight drop, then return to full high RPM.",
            ),
            ChecklistItem(
                item="Engine Indicators",
                target_state="CHECK GREEN",
                challenge="Engine Instruments",
                response="CHECK GREEN",
                verify_dref="sim/cockpit2/engine/indicators/oil_pressure_psi[0]",
                verify_fn=lambda psi: psi >= 30.0,
            ),
            ChecklistItem(
                item="Throttle",
                target_state="1000 RPM (IDLE CHECK)",
                challenge="Throttle",
                response="1000 RPM",
                action_dref="sim/cockpit2/engine/actuators/throttle_ratio[0]",
                action_val=0.20,
            ),
            ChecklistItem(
                item="Wing Flaps",
                target_state="SET 0 TO 10 DEG",
                challenge="Wing Flaps",
                response="SET 0 DEGREES",
                action_dref="sim/cockpit2/controls/flap_handle_request_ratio",
                action_val=0.0,
                verify_dref="sim/cockpit2/controls/flap_handle_request_ratio",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Elevator Trim",
                target_state="TAKEOFF BAND",
                challenge="Elevator Trim",
                response="TAKEOFF BAND",
                action_dref="sim/cockpit2/controls/elevator_trim",
                action_val=0.0,
                verify_dref="sim/cockpit2/controls/elevator_trim",
                verify_val=0.0,
                verify_tol=0.05,
            ),
            ChecklistItem(
                item="Transponder",
                target_state="ALT MODE (CODE 1200)",
                challenge="Transponder",
                response="ALT (1200)",
                action_dref="sim/cockpit2/radios/actuators/transponder_mode",
                action_val=2.0,  # 2 = ALT mode
            ),
            ChecklistItem(
                item="Strobe Lights",
                target_state="ON",
                challenge="Strobe Lights",
                response="ON",
                action_dref="sim/cockpit2/switches/strobe_lights_on",
                action_val=1.0,
                verify_dref="sim/cockpit2/switches/strobe_lights_on",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Landing & Taxi Lights",
                target_state="ON",
                challenge="Landing & Taxi Lights",
                response="ON",
                action_dref="sim/cockpit2/switches/landing_lights_on",
                action_val=1.0,
            ),
            ChecklistItem(
                item="Brakes",
                target_state="RELEASE",
                challenge="Brakes",
                response="RELEASED",
                action_dref="sim/cockpit2/controls/parking_brake_ratio",
                action_val=0.0,
                verify_dref="sim/cockpit2/controls/parking_brake_ratio",
                verify_val=0.0,
            ),
        ],
    )


def get_takeoff_and_climb_checklist() -> Checklist:
    return Checklist(
        phase=ChecklistPhase.TAKEOFF_AND_CLIMB,
        title="Takeoff & Climb",
        description="POH Section 4 - Takeoff roll, rotation (55-60 KIAS), climb (Vy 80 KIAS).",
        items=[
            ChecklistItem(
                item="Throttle",
                target_state="FULL FORWARD (2400 RPM / FULL MP)",
                challenge="Throttle",
                response="FULL FORWARD",
                action_dref="sim/cockpit2/engine/actuators/throttle_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/throttle_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Propeller Control",
                target_state="FULL FORWARD (2400 RPM)",
                challenge="Propeller",
                response="FULL FORWARD",
                action_dref="sim/cockpit2/engine/actuators/prop_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/prop_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Mixture",
                target_state="FULL RICH",
                challenge="Mixture",
                response="FULL RICH",
                action_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Airspeed Indicator",
                target_state="ALIVE & CHECKED",
                challenge="Airspeed",
                response="ALIVE",
                verify_dref="sim/flightmodel/position/indicated_airspeed",
                verify_fn=lambda kias: kias >= 20.0,
            ),
            ChecklistItem(
                item="Rotation Speed (Vr)",
                target_state="55-60 KIAS",
                challenge="Rotate",
                response="ROTATE (60 KIAS)",
                note="Ease back gently on control wheel to establish 7-8 degree climb pitch.",
            ),
            ChecklistItem(
                item="Climb Airspeed (Vy)",
                target_state="80 KIAS",
                challenge="Climb Airspeed",
                response="80 KIAS",
                note="Maintain 80 KIAS for best rate of climb (Vy).",
            ),
            ChecklistItem(
                item="Wing Flaps",
                target_state="RETRACT UP (ABOVE 70 KIAS)",
                challenge="Flaps",
                response="UP",
                action_dref="sim/cockpit2/controls/flap_handle_request_ratio",
                action_val=0.0,
                verify_dref="sim/cockpit2/controls/flap_handle_request_ratio",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Cowl Flaps",
                target_state="OPEN",
                challenge="Cowl Flaps",
                response="OPEN",
                action_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                action_val=1.0,
            ),
        ],
    )


def get_cruise_checklist() -> Checklist:
    return Checklist(
        phase=ChecklistPhase.CRUISE,
        title="Cruise",
        description="POH Section 4 - Level off, power set (23 in Hg / 2400 RPM), mixture lean.",
        items=[
            ChecklistItem(
                item="Power (Throttle)",
                target_state="21-23 IN HG MANIFOLD PRESSURE",
                challenge="Power",
                response="23 INCHES",
                action_dref="sim/cockpit2/engine/actuators/throttle_ratio[0]",
                action_val=0.80,
            ),
            ChecklistItem(
                item="Propeller Control",
                target_state="2300-2400 RPM",
                challenge="Propeller",
                response="2400 RPM",
                action_dref="sim/cockpit2/engine/actuators/prop_ratio[0]",
                action_val=0.96,
            ),
            ChecklistItem(
                item="Mixture",
                target_state="LEAN FOR CRUISE",
                challenge="Mixture",
                response="LEANED",
                action_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                action_val=0.82,
                note="Lean to recommended fuel flow or peak EGT for cruise economy.",
            ),
            ChecklistItem(
                item="Cowl Flaps",
                target_state="CLOSED",
                challenge="Cowl Flaps",
                response="CLOSED",
                action_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                action_val=0.0,
                verify_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Elevator Trim",
                target_state="ADJUST FOR LEVEL FLIGHT",
                challenge="Elevator Trim",
                response="SET",
            ),
        ],
    )


def get_descent_checklist() -> Checklist:
    return Checklist(
        phase=ChecklistPhase.DESCENT,
        title="Descent",
        description="POH Section 4 - Power adjustment, fuel system check, altimeter set.",
        items=[
            ChecklistItem(
                item="Altimeter",
                target_state="SET LOCAL BARO (29.92 IN HG)",
                challenge="Altimeter",
                response="SET (29.92)",
            ),
            ChecklistItem(
                item="Fuel Selector Valve",
                target_state="BOTH",
                challenge="Fuel Selector",
                response="BOTH",
                action_dref="sim/cockpit2/fuel/fuel_tank_selector",
                action_val=4.0,
                verify_dref="sim/cockpit2/fuel/fuel_tank_selector",
                verify_val=4.0,
            ),
            ChecklistItem(
                item="Cowl Flaps",
                target_state="CLOSED",
                challenge="Cowl Flaps",
                response="CLOSED",
                action_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                action_val=0.0,
                verify_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Power (Throttle)",
                target_state="ADJUST (15-18 IN HG / 500-700 FPM)",
                challenge="Power",
                response="16 INCHES",
                action_dref="sim/cockpit2/engine/actuators/throttle_ratio[0]",
                action_val=0.45,
            ),
            ChecklistItem(
                item="Mixture",
                target_state="ENRICH AS REQUIRED",
                challenge="Mixture",
                response="ENRICHED",
                action_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                action_val=0.95,
            ),
        ],
    )


def get_before_landing_checklist() -> Checklist:
    return Checklist(
        phase=ChecklistPhase.BEFORE_LANDING,
        title="Before Landing",
        description="POH Section 4 - Approach configuration, landing gear, flaps, propeller high RPM.",
        items=[
            ChecklistItem(
                item="Fuel Selector Valve",
                target_state="BOTH",
                challenge="Fuel Selector",
                response="BOTH",
                action_dref="sim/cockpit2/fuel/fuel_tank_selector",
                action_val=4.0,
                verify_dref="sim/cockpit2/fuel/fuel_tank_selector",
                verify_val=4.0,
            ),
            ChecklistItem(
                item="Seat Belts and Shoulder Harnesses",
                target_state="SECURE",
                challenge="Seat Belts",
                response="SECURE",
            ),
            ChecklistItem(
                item="Autopilot",
                target_state="DISENGAGE (PRIOR TO MINIMUMS / 200 FT)",
                challenge="Autopilot",
                response="DISENGAGED",
                action_dref="sim/cockpit2/autopilot/servos_on",
                action_val=0.0,
                action_cmd="sim/autopilot/servos_off",
                verify_dref="sim/cockpit2/autopilot/servos_on",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Propeller Control",
                target_state="HIGH RPM (FULL FORWARD)",
                challenge="Propeller",
                response="HIGH RPM",
                action_dref="sim/cockpit2/engine/actuators/prop_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/prop_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Mixture",
                target_state="RICH",
                challenge="Mixture",
                response="RICH",
                action_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Landing Light",
                target_state="ON",
                challenge="Landing Light",
                response="ON",
                action_dref="sim/cockpit2/switches/landing_lights_on",
                action_val=1.0,
            ),
            ChecklistItem(
                item="Cowl Flaps",
                target_state="CLOSED",
                challenge="Cowl Flaps",
                response="CLOSED",
                action_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                action_val=0.0,
                verify_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Wing Flaps",
                target_state="FULL (30 DEGREES)",
                challenge="Wing Flaps",
                response="FULL (30 DEG)",
                action_dref="sim/cockpit2/controls/flap_handle_request_ratio",
                action_val=1.0,
                verify_dref="sim/cockpit2/controls/flap_handle_request_ratio",
                verify_val=1.0,
                note="10 deg below 140 KIAS, 20 deg below 120 KIAS, full 30 deg below 100 KIAS.",
            ),
            ChecklistItem(
                item="Approach Airspeed",
                target_state="65-70 KIAS",
                challenge="Approach Airspeed",
                response="65 KIAS",
                note="Maintain 65 KIAS across threshold; reduce throttle to idle over numbers.",
            ),
        ],
    )


def get_after_landing_checklist() -> Checklist:
    return Checklist(
        phase=ChecklistPhase.AFTER_LANDING,
        title="After Landing (Clear of Runway)",
        description="POH Section 4 - Post-rollout cleanup and taxi configuration.",
        items=[
            ChecklistItem(
                item="Wing Flaps",
                target_state="RETRACT UP",
                challenge="Wing Flaps",
                response="UP",
                action_dref="sim/cockpit2/controls/flap_handle_request_ratio",
                action_val=0.0,
                verify_dref="sim/cockpit2/controls/flap_handle_request_ratio",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Cowl Flaps",
                target_state="OPEN",
                challenge="Cowl Flaps",
                response="OPEN",
                action_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Landing & Strobe Lights",
                target_state="OFF",
                challenge="Landing/Strobes",
                response="OFF",
                action_dref="sim/cockpit2/switches/landing_lights_on",
                action_val=0.0,
            ),
            ChecklistItem(
                item="Strobe Lights",
                target_state="OFF",
                challenge="Strobes",
                response="OFF",
                action_dref="sim/cockpit2/switches/strobe_lights_on",
                action_val=0.0,
                verify_dref="sim/cockpit2/switches/strobe_lights_on",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Taxi Light",
                target_state="ON",
                challenge="Taxi Light",
                response="ON",
                action_dref="sim/cockpit2/switches/taxi_light_on",
                action_val=1.0,
            ),
            ChecklistItem(
                item="Elevator Trim",
                target_state="SET TAKEOFF BAND",
                challenge="Elevator Trim",
                response="TAKEOFF BAND",
                action_dref="sim/cockpit2/controls/elevator_trim",
                action_val=0.0,
                verify_dref="sim/cockpit2/controls/elevator_trim",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Transponder",
                target_state="STANDBY / ALT",
                challenge="Transponder",
                response="STANDBY",
                action_dref="sim/cockpit2/radios/actuators/transponder_mode",
                action_val=1.0,  # 1 = STANDBY
            ),
        ],
    )


def get_shutdown_and_securing_checklist() -> Checklist:
    return Checklist(
        phase=ChecklistPhase.SHUTDOWN_AND_SECURING,
        title="Shutdown & Securing Aircraft",
        description="POH Section 4 - Engine shutdown, electrical off, aircraft secured.",
        items=[
            ChecklistItem(
                item="Parking Brake",
                target_state="SET",
                challenge="Parking Brake",
                response="SET",
                action_dref="sim/cockpit2/controls/parking_brake_ratio",
                action_val=1.0,
                verify_dref="sim/cockpit2/controls/parking_brake_ratio",
                verify_val=1.0,
            ),
            ChecklistItem(
                item="Throttle",
                target_state="IDLE (1000 RPM COOL DOWN, THEN IDLE)",
                challenge="Throttle",
                response="IDLE",
                action_dref="sim/cockpit2/engine/actuators/throttle_ratio[0]",
                action_val=0.0,
                verify_dref="sim/cockpit2/engine/actuators/throttle_ratio[0]",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Avionics Master Switch",
                target_state="OFF",
                challenge="Avionics Master",
                response="OFF",
                action_dref="sim/cockpit2/switches/avionics_power_on",
                action_val=0.0,
                verify_dref="sim/cockpit2/switches/avionics_power_on",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Electrical Switches",
                target_state="ALL OFF (EXCEPT BEACON)",
                challenge="Electrical Switches",
                response="OFF",
                action_dref="sim/cockpit2/switches/taxi_light_on",
                action_val=0.0,
            ),
            ChecklistItem(
                item="Mixture",
                target_state="IDLE CUT-OFF",
                challenge="Mixture",
                response="IDLE CUT-OFF",
                action_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                action_val=0.0,
                verify_dref="sim/cockpit2/engine/actuators/mixture_ratio[0]",
                verify_val=0.0,
                note="Pull mixture control fully aft; engine will stop within 3 seconds.",
            ),
            ChecklistItem(
                item="Ignition Switch",
                target_state="OFF",
                challenge="Ignition Switch",
                response="OFF",
                action_dref="sim/cockpit2/engine/actuators/ignition_key[0]",
                action_val=0.0,
                verify_dref="sim/cockpit2/engine/actuators/ignition_key[0]",
                verify_val=0.0,
                note="Turn key to OFF and remove key.",
            ),
            ChecklistItem(
                item="Master Switch (ALT & BAT)",
                target_state="OFF",
                challenge="Master ALT & BAT",
                response="OFF",
                action_dref="sim/cockpit2/electrical/generator_on[0]",
                action_val=0.0,
            ),
            ChecklistItem(
                item="Master Switch (BAT)",
                target_state="OFF",
                challenge="Master BAT",
                response="OFF",
                action_dref="sim/cockpit2/electrical/battery_on[0]",
                action_val=0.0,
                verify_dref="sim/cockpit2/electrical/battery_on[0]",
                verify_val=0.0,
            ),
            ChecklistItem(
                item="Cowl Flaps",
                target_state="OPEN",
                challenge="Cowl Flaps",
                response="OPEN",
                action_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                action_val=1.0,
                verify_dref="sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
                verify_val=1.0,
                note="Leave cowl flaps open on ground to prevent heat buildup.",
            ),
            ChecklistItem(
                item="Control Wheel Lock & Chocks",
                target_state="INSTALLED",
                challenge="Lock & Chocks",
                response="INSTALLED",
            ),
        ],
    )


ALL_CHECKLISTS: Dict[ChecklistPhase, Callable[..., Checklist]] = {
    ChecklistPhase.BEFORE_ENGINE_START: get_before_engine_start_checklist,
    ChecklistPhase.ENGINE_START: get_engine_start_checklist,
    ChecklistPhase.BEFORE_TAKEOFF: get_before_takeoff_checklist,
    ChecklistPhase.TAKEOFF_AND_CLIMB: get_takeoff_and_climb_checklist,
    ChecklistPhase.CRUISE: get_cruise_checklist,
    ChecklistPhase.DESCENT: get_descent_checklist,
    ChecklistPhase.BEFORE_LANDING: get_before_landing_checklist,
    ChecklistPhase.AFTER_LANDING: get_after_landing_checklist,
    ChecklistPhase.SHUTDOWN_AND_SECURING: get_shutdown_and_securing_checklist,
}


def get_checklist_by_name(name: str, **kwargs) -> Optional[Checklist]:
    """Retrieve checklist by string enum name."""
    try:
        phase = ChecklistPhase(name.upper())
        fn = ALL_CHECKLISTS.get(phase)
        if fn:
            return fn(**kwargs)
    except ValueError:
        pass
    return None
