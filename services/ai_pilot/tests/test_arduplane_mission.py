"""Mission protocol tests with independently generated endpoint responses."""
import pytest

from services.ai_pilot import mavlink_min as mav
from services.ai_pilot.arduplane_mission import (
    FlightFix, GeoPoint, MissionUploader, runway_sortie,
)


def plan():
    departure = GeoPoint(32.8264, -116.9643, 388.0)
    route = (FlightFix(GeoPoint(32.95, -116.90, 600.0), 1500.0),)
    approach = FlightFix(GeoPoint(33.02, -116.91, 1300.0), 1600.0)
    landing = GeoPoint(33.038, -116.907, 1395.0)
    return runway_sortie(departure, route, approach, landing, 60.0)


class Endpoint(mav.MockLink):
    """A separate MAVLink peer: it requests items and emits the final ACK."""
    def __init__(self, *, first_count_lost=False, reject=False,
                 confirm_current=True):
        super().__init__()
        self.first_count_lost = first_count_lost
        self.reject = reject
        self.confirm_current = confirm_current
        self.counts = 0
        self.seen = set()
        self.count = 0

    def request(self, seq):
        self.inject(mav.MSG_MISSION_REQUEST_INT, {
            "seq": seq, "target_system": self.sysid,
            "target_component": self.compid, "mission_type": 0,
        })

    def send(self, msgid, fields):
        super().send(msgid, fields)
        if msgid == mav.MSG_MISSION_COUNT:
            self.counts += 1
            self.count = fields["count"]
            if not self.first_count_lost or self.counts > 1:
                self.request(0)
        elif msgid == mav.MSG_MISSION_ITEM_INT:
            seq = fields["seq"]
            self.seen.add(seq)
            if len(self.seen) == self.count:
                self.inject(mav.MSG_MISSION_ACK, {
                    "target_system": self.sysid, "target_component": self.compid,
                    "type": 1 if self.reject else 0, "mission_type": 0,
                })
            else:
                self.request(seq + 1)
        elif (msgid == mav.MSG_COMMAND_INT and
              fields["command"] == mav.MAV_CMD_DO_SET_MISSION_CURRENT and
              self.confirm_current and
              self.ack_overrides.get(mav.MAV_CMD_DO_SET_MISSION_CURRENT,
                                     mav.MAV_RESULT_ACCEPTED) == mav.MAV_RESULT_ACCEPTED):
            self.inject(mav.MSG_MISSION_CURRENT, {"seq": int(fields["param1"]),
                        "total": self.count, "mission_state": 1, "mission_mode": 1})


def test_runway_geometry_preserves_home_and_arrival_msl():
    items = plan()
    assert [item.command for item in items] == [
        mav.MAV_CMD_NAV_TAKEOFF, mav.MAV_CMD_NAV_WAYPOINT,
        mav.MAV_CMD_DO_LAND_START, mav.MAV_CMD_NAV_WAYPOINT, mav.MAV_CMD_NAV_LAND,
    ]
    assert items[0].frame == mav.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
    assert items[0].altitude_m == 60.0
    assert items[-1].frame == mav.MAV_FRAME_GLOBAL_INT
    assert items[-1].altitude_m == 1395.0  # cross-airport, not home-relative zero
    assert items[-1].fields(4, 1, 1)["z"] == 1395.0


def test_real_count_request_item_ack_exchange_with_retry_and_auto_observation():
    peer = Endpoint(first_count_lost=True)
    uploader = MissionUploader(peer)
    uploader.REQUEST_TIMEOUT_S = 0.01
    uploader.upload(plan())
    assert uploader.uploaded and peer.counts == 2
    assert peer.seen == set(range(5))
    assert all(fields["mission_type"] == 0 for msgid, fields in peer.sent_messages
               if msgid == mav.MSG_MISSION_ITEM_INT)
    uploader.start_auto()
    assert peer.custom_mode() == mav.PLANE_MODE_AUTO
    peer.inject(mav.MSG_MISSION_CURRENT, {"seq": 3, "total": 5,
                                         "mission_state": 1, "mission_mode": 1})
    peer.inject(mav.MSG_MISSION_ITEM_REACHED, {"seq": 2})
    assert uploader.progress()["current_seq"] == 3
    assert uploader.progress()["reached_seq"] == 2


def test_rejected_upload_prevents_auto_and_go_around_needs_ack():
    peer = Endpoint(reject=True)
    uploader = MissionUploader(peer)
    with pytest.raises(ValueError, match="rejected mission"):
        uploader.upload(plan())
    with pytest.raises(ValueError, match="acknowledged mission"):
        uploader.start_auto()
    peer.ack_overrides[mav.MAV_CMD_DO_GO_AROUND] = mav.MAV_RESULT_DENIED
    with pytest.raises(ValueError, match="rejected go-around"):
        uploader.go_around(1600.0)
    peer.ack_overrides[mav.MAV_CMD_DO_GO_AROUND] = mav.MAV_RESULT_ACCEPTED
    uploader.go_around(1600.0)


def test_restarted_mission_rejoin_requires_upload_current_ack_readback_and_auto():
    peer = Endpoint()
    peer.inject_heartbeat(mav.PLANE_MODE_MANUAL)
    uploader = MissionUploader(peer)
    uploader.resume_at(plan(), 1)
    assert uploader.uploaded
    assert peer.custom_mode() == mav.PLANE_MODE_AUTO
    assert uploader.progress()["current_seq"] == 1
    assert mav.MAV_CMD_DO_SET_MISSION_CURRENT in peer.sent_commands()
    assert next(i for i, (msgid, _) in enumerate(peer.sent_messages)
                if msgid == mav.MSG_MISSION_ITEM_INT) < next(
                i for i, (msgid, fields) in enumerate(peer.sent_messages)
                if msgid == mav.MSG_COMMAND_INT and
                fields["command"] == mav.MAV_CMD_DO_SET_MISSION_CURRENT)


@pytest.mark.parametrize("cause", ["unarmed", "denied", "no_current"])
def test_restarted_mission_rejoin_refuses_missing_protocol_evidence(cause):
    peer = Endpoint(confirm_current=cause != "no_current")
    peer.inject_heartbeat(mav.PLANE_MODE_MANUAL,
        base_mode=1 if cause == "unarmed" else
        mav.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED | mav.MAV_MODE_FLAG_SAFETY_ARMED)
    if cause == "denied":
        peer.ack_overrides[mav.MAV_CMD_DO_SET_MISSION_CURRENT] = mav.MAV_RESULT_DENIED
    with pytest.raises((ValueError, TimeoutError)):
        MissionUploader(peer).resume_at(plan(), 1, timeout=0.01)
    assert peer.custom_mode() != mav.PLANE_MODE_AUTO
