"""Bounded ArduPlane AUTO mission upload and progress observation.

No aircraft control is attempted by constructing a plan. Mission upload and
mode observation are distinct from runway readiness, takeoff and landing.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from . import mavlink_min as mav


@dataclass(frozen=True)
class GeoPoint:
    latitude_deg: float
    longitude_deg: float
    elevation_m_msl: float

    def __post_init__(self):
        if not all(math.isfinite(x) for x in vars(self).values()):
            raise ValueError("Nonfinite runway geometry")
        if not -90 <= self.latitude_deg <= 90 or not -180 <= self.longitude_deg <= 180:
            raise ValueError("Invalid runway coordinates")


@dataclass(frozen=True)
class FlightFix:
    point: GeoPoint
    altitude_m_msl: float

    def __post_init__(self):
        if not math.isfinite(self.altitude_m_msl):
            raise ValueError("Nonfinite planned fix altitude")


@dataclass(frozen=True)
class MissionItem:
    command: int
    point: GeoPoint
    altitude_m: float
    frame: int
    param1: float = 0.0

    def fields(self, seq: int, target_system: int, target_component: int):
        if self.frame not in (mav.MAV_FRAME_GLOBAL_INT, mav.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT):
            raise ValueError("Mission altitude frame must be explicit")
        if not math.isfinite(self.altitude_m):
            raise ValueError("Mission altitude must be finite")
        return {"param1": float(self.param1), "param2": 0.0, "param3": 0.0,
                "param4": 0.0, "x": round(self.point.latitude_deg * 1e7),
                "y": round(self.point.longitude_deg * 1e7), "z": float(self.altitude_m),
                "seq": seq, "command": self.command, "target_system": target_system,
                "target_component": target_component, "frame": self.frame,
                "current": 1 if seq == 0 else 0, "autocontinue": 1,
                "mission_type": mav.MAV_MISSION_TYPE_MISSION}


def runway_sortie(departure: GeoPoint, route: tuple[FlightFix, ...],
                  approach: FlightFix, landing: GeoPoint,
                  climb_m_above_home: float) -> tuple[MissionItem, ...]:
    """Build a complete protocol plan with distinct home and runway heights.

    Approach/landing elevations use absolute MSL frames. A touchdown zero in a
    home-relative frame would be wrong on a cross-airport sortie.
    """
    if not math.isfinite(climb_m_above_home) or climb_m_above_home <= 0:
        raise ValueError("Takeoff climb height above verified home required")
    if not route:
        raise ValueError("At least one enroute point required")
    return (
        MissionItem(mav.MAV_CMD_NAV_TAKEOFF, departure, climb_m_above_home,
                    mav.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT),
        *(MissionItem(mav.MAV_CMD_NAV_WAYPOINT, fix.point, fix.altitude_m_msl,
                      mav.MAV_FRAME_GLOBAL_INT) for fix in route),
        MissionItem(mav.MAV_CMD_DO_LAND_START, approach.point, approach.altitude_m_msl,
                    mav.MAV_FRAME_GLOBAL_INT),
        MissionItem(mav.MAV_CMD_NAV_WAYPOINT, approach.point, approach.altitude_m_msl,
                    mav.MAV_FRAME_GLOBAL_INT),
        MissionItem(mav.MAV_CMD_NAV_LAND, landing, landing.elevation_m_msl,
                    mav.MAV_FRAME_GLOBAL_INT),
    )


class MissionUploader:
    REQUEST_TIMEOUT_S = 0.5
    MAX_RETRIES = 3

    def __init__(self, link):
        self.link = link
        self.uploaded = False
        self.count = 0
        self.cursor = None

    def upload(self, items: tuple[MissionItem, ...]) -> None:
        if not items or len(items) > 100:
            raise ValueError("Mission requires 1–100 items")
        self.uploaded = False
        self.count = len(items)
        target_system = self.link.target_system
        target_component = self.link.target_component
        count_fields = {"count": len(items), "target_system": target_system,
                        "target_component": target_component,
                        "mission_type": mav.MAV_MISSION_TYPE_MISSION}
        cursor = self.link.message_cursor()
        self.link.send(mav.MSG_MISSION_COUNT, count_fields)
        attempts = 0
        served = set()
        while True:
            cursor, message = self.link.wait_message(
                (mav.MSG_MISSION_REQUEST_INT, mav.MSG_MISSION_ACK), cursor,
                self.REQUEST_TIMEOUT_S)
            if message is None:
                attempts += 1
                if attempts > self.MAX_RETRIES:
                    raise TimeoutError("Mission upload request/ACK timed out")
                if not served:
                    self.link.send(mav.MSG_MISSION_COUNT, count_fields)
                else:
                    seq = max(served)
                    self.link.send(mav.MSG_MISSION_ITEM_INT,
                                   items[seq].fields(seq, target_system, target_component))
                continue
            if message.sysid != target_system or message.compid != target_component:
                continue
            fields = message.fields
            if fields.get("mission_type", 0) != mav.MAV_MISSION_TYPE_MISSION:
                raise ValueError("Unexpected mission type")
            if message.msgid == mav.MSG_MISSION_ACK:
                if (fields.get("target_system") != self.link.sysid
                        or fields.get("target_component") != self.link.compid):
                    raise ValueError("Mission ACK targeted another uploader")
                if fields["type"] != mav.MAV_MISSION_ACCEPTED:
                    raise ValueError("ArduPlane rejected mission (result %d)" % fields["type"])
                if served != set(range(len(items))):
                    raise ValueError("Mission ACK arrived before all items were requested")
                self.uploaded = True
                self.cursor = self.link.message_cursor()
                return
            seq = fields["seq"]
            if seq >= len(items) or fields.get("target_system") != self.link.sysid:
                raise ValueError("Invalid ArduPlane mission item request")
            self.link.send(mav.MSG_MISSION_ITEM_INT,
                           items[seq].fields(seq, target_system, target_component))
            served.add(seq)
            attempts = 0

    def start_auto(self, timeout=1.2) -> None:
        if not self.uploaded:
            raise ValueError("AUTO requires an acknowledged mission upload")
        self.link.arm_ack(mav.MAV_CMD_DO_SET_MODE)
        self.link.send(*mav.set_mode(mav.PLANE_MODE_AUTO,
                                     self.link.target_system, self.link.target_component))
        ack = self.link.wait_ack(mav.MAV_CMD_DO_SET_MODE, timeout)
        if ack != mav.MAV_RESULT_ACCEPTED:
            raise ValueError("ArduPlane did not ACK AUTO")
        if self.link.custom_mode() != mav.PLANE_MODE_AUTO or self.link.heartbeat_age() > timeout:
            raise ValueError("ArduPlane AUTO mode not observed")

    def resume_at(self, items: tuple[MissionItem, ...], seq: int, timeout=1.2) -> None:
        """Rebuild a restarted aircraft's mission before admitting its outputs.

        An ACK and fresh MISSION_CURRENT establish protocol state only. The
        executive still requires independent aircraft and bridge readiness.
        """
        if (type(seq) is not int or not 0 <= seq < len(items)
                or items[seq].command != mav.MAV_CMD_NAV_WAYPOINT):
            raise ValueError("Return requires an explicit route waypoint")
        heartbeat, age = self.link.latest(mav.MSG_HEARTBEAT)
        if (heartbeat is None or age > timeout
                or not heartbeat["base_mode"] & mav.MAV_MODE_FLAG_SAFETY_ARMED):
            raise ValueError("Restarted ArduPlane armed heartbeat unavailable")
        self.upload(items)
        cursor = self.link.message_cursor()
        self.link.arm_ack(mav.MAV_CMD_DO_SET_MISSION_CURRENT)
        self.link.send(*mav.command_int(
            mav.MAV_CMD_DO_SET_MISSION_CURRENT,
            self.link.target_system, self.link.target_component,
            mav.MAV_FRAME_GLOBAL, param1=float(seq)))
        if self.link.wait_ack(mav.MAV_CMD_DO_SET_MISSION_CURRENT, timeout) != mav.MAV_RESULT_ACCEPTED:
            raise ValueError("ArduPlane rejected mission rejoin item")
        cursor, current = self.link.wait_message((mav.MSG_MISSION_CURRENT,), cursor, timeout)
        if (current is None or current.sysid != self.link.target_system
                or current.compid != self.link.target_component
                or current.fields.get("seq") != seq):
            raise ValueError("Fresh ArduPlane mission-current readback absent")
        self.start_auto(timeout)
        progress = self.progress(timeout)
        if progress["current_seq"] != seq:
            raise ValueError("ArduPlane mission item moved before rejoin")

    def progress(self, max_age=2.0) -> dict:
        current, age = self.link.latest(mav.MSG_MISSION_CURRENT)
        reached, reached_age = self.link.latest(mav.MSG_MISSION_ITEM_REACHED)
        if current is None or age > max_age:
            raise ValueError("Fresh mission progress unavailable")
        return {"current_seq": current["seq"], "current_age_s": age,
                "reached_seq": reached["seq"] if reached and reached_age <= max_age else None}

    def go_around(self, altitude_m_msl: float, timeout=0.6) -> None:
        if not math.isfinite(altitude_m_msl) or altitude_m_msl <= 0:
            raise ValueError("Verified positive MSL go-around altitude required")
        self.link.arm_ack(mav.MAV_CMD_DO_GO_AROUND)
        self.link.send(*mav.command_long(mav.MAV_CMD_DO_GO_AROUND,
                                         self.link.target_system, self.link.target_component,
                                         altitude_m_msl))
        ack = self.link.wait_ack(mav.MAV_CMD_DO_GO_AROUND, timeout)
        if ack != mav.MAV_RESULT_ACCEPTED:
            raise ValueError("ArduPlane rejected go-around")
