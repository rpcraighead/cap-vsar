"""Legacy entrypoints all use the same first ownership barrier."""
import pytest

from services.ai_pilot import control_ownership as ownership
from services.ai_pilot.bridge_client import BridgeClient


def test_second_process_acquisition_refused_before_any_control_work(tmp_path, monkeypatch):
    monkeypatch.setattr(ownership, "LOCK_PATH", str(tmp_path / "controller.lock"))
    writes = []

    @ownership.exclusive_controller
    def attempted_work():
        writes.append("would acquire controller")

    with ownership.ControllerLock():
        with pytest.raises(BlockingIOError):
            attempted_work()
        assert writes == []
    attempted_work()
    assert writes == ["would acquire controller"]


def test_live_capability_cannot_be_enabled_by_entrypoint_argument():
    assert ownership.LIVE_CONTROL_QUALIFIED is False
    with pytest.raises(RuntimeError, match="UNVERIFIED_LIVE"):
        ownership.require_live_qualification()
    with pytest.raises(RuntimeError, match="UNVERIFIED_LIVE"):
        BridgeClient("/tmp/there-is-no-live-bridge-config.json")


def test_legacy_raw_routes_stay_closed_even_if_bridge_qualification_changes(monkeypatch):
    assert ownership.LEGACY_ROUTE_QUALIFIED is False
    monkeypatch.setattr(ownership, "LIVE_CONTROL_QUALIFIED", True)
    with pytest.raises(RuntimeError, match="not migrated"):
        ownership.require_legacy_route_qualification()
