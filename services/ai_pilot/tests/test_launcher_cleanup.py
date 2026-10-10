"""Injected acquisition failures leave legacy launchers without owned resources."""
import sys

import pytest

from scripts import fly_card_h0 as h0
from scripts import fly_arduplane_backend as ardu
from scripts import fly_direct_backend as direct
from services.ai_pilot import control_ownership


class FakeClient:
    last = None

    def __init__(self, *args, **kwargs):
        self.stops = 0
        FakeClient.last = self

    def stop(self):
        self.stops += 1

    def subscribe_dref(self, *args, **kwargs):
        raise RuntimeError("injected subscription failure")

    def send_dref(self, *args, **kwargs):
        pass


class FakeBackend:
    last = None

    def __init__(self, client, **kwargs):
        self.releases = 0
        FakeBackend.last = self

    def release(self):
        self.releases += 1

    def observe(self):
        raise RuntimeError("injected observation failure")


def test_h0_subscription_failure_stops_client_and_releases_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(control_ownership, "LOCK_PATH", str(tmp_path / "owner.lock"))
    monkeypatch.setattr(h0, "require_legacy_route_qualification", lambda: None)
    monkeypatch.setattr(h0, "XPlaneUDPClient", FakeClient)
    monkeypatch.setattr(h0, "XPlaneDirectBackend", FakeBackend)
    monkeypatch.setattr(sys, "argv", ["fly_card_h0.py"])
    with pytest.raises(RuntimeError, match="subscription failure"):
        h0.main()
    assert FakeBackend.last.releases >= 1
    assert FakeClient.last.stops >= 1


def test_direct_observation_failure_stops_client_and_releases_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(control_ownership, "LOCK_PATH", str(tmp_path / "owner.lock"))
    monkeypatch.setattr(direct, "require_legacy_route_qualification", lambda: None)
    monkeypatch.setattr(direct, "XPlaneUDPClient", FakeClient)
    monkeypatch.setattr(direct, "XPlaneDirectBackend", FakeBackend)
    monkeypatch.setattr(sys, "argv", ["fly_direct_backend.py", "--heading", "90",
                                  "--altitude", "4500"])
    with pytest.raises(RuntimeError, match="observation failure"):
        direct.main()
    assert FakeBackend.last.releases >= 1
    assert FakeClient.last.stops >= 1


def test_arduplane_subscription_failure_stops_managed_sitl_and_link(tmp_path, monkeypatch):
    class FakeSitl:
        last = None
        def __init__(self, *args, **kwargs):
            self.stopped = False
            FakeSitl.last = self
        def command(self): return ["fake-sitl"]
        def start(self): pass
        def wait_for_mavlink(self, timeout): return True
        def stop(self):
            self.stopped = True
            return True
    class FakeLink:
        last = None
        def __init__(self, *args, **kwargs):
            self.closed = False
            FakeLink.last = self
        def close(self): self.closed = True
    class FakeArduBackend:
        def __init__(self, *args, **kwargs): pass
    class FakeGate:
        def __init__(self, *args, **kwargs): pass
    binary = tmp_path / "arduplane"
    binary.touch()
    monkeypatch.setattr(control_ownership, "LOCK_PATH", str(tmp_path / "owner.lock"))
    monkeypatch.setattr(ardu, "require_legacy_route_qualification", lambda: None)
    monkeypatch.setattr(ardu, "XPlaneUDPClient", FakeClient)
    monkeypatch.setattr(ardu, "SitlProcess", FakeSitl)
    monkeypatch.setattr(ardu.mav, "MavlinkLink", FakeLink)
    monkeypatch.setattr(ardu, "ArduPlaneBackend", FakeArduBackend)
    monkeypatch.setattr(ardu, "ManeuverGate", FakeGate)
    monkeypatch.setattr(sys, "argv", ["fly_arduplane_backend.py", "--heading", "90",
                                  "--altitude", "4500", "--candidate-session", "a" * 32,
                                  "--sitl-bin", str(binary), "--sitl-cwd", str(tmp_path)])
    assert ardu.main() == 1
    assert FakeSitl.last.stopped and FakeLink.last.closed and FakeClient.last.stops >= 1


@pytest.mark.parametrize("failure", ["start", "mavlink_ready", "link",
                                     "backend", "gate", "subscription"])
def test_arduplane_acquisition_failure_releases_every_owned_resource(
        failure, tmp_path, monkeypatch):
    events = []
    class Client:
        last = None
        def __init__(self, *args, **kwargs):
            self.stopped = False
            Client.last = self
            events.append("client_created")
        def stop(self):
            self.stopped = True
            events.append("client_stopped")
        def send_dref(self, ref, value):
            events.append("override_requested")
        def subscribe_dref(self, *args, **kwargs):
            if failure == "subscription":
                raise RuntimeError("subscription failure")
    class Sitl:
        last = None
        def __init__(self, *args, **kwargs):
            self.stopped = False
            self.started = False
            self.log_path = tmp_path / "sitl.log"
            Sitl.last = self
        def command(self): return ["fake-sitl"]
        def start(self):
            if failure == "start":
                raise OSError("start failure")
            self.started = True
            events.append("sitl_started")
        def wait_for_mavlink(self, timeout):
            return failure != "mavlink_ready"
        def stop(self):
            self.stopped = True
            events.append("sitl_stopped")
            return True
    class Link:
        last = None
        def __init__(self, *args, **kwargs):
            if failure == "link":
                raise OSError("link failure")
            self.closed = False
            Link.last = self
            events.append("link_created")
        def close(self):
            self.closed = True
            events.append("link_closed")
    class Backend:
        def __init__(self, *args, **kwargs):
            if failure == "backend":
                raise RuntimeError("backend failure")
    class Gate:
        def __init__(self, *args, **kwargs):
            if failure == "gate":
                raise RuntimeError("gate failure")
    binary = tmp_path / "arduplane"
    binary.touch()
    monkeypatch.setattr(control_ownership, "LOCK_PATH", str(tmp_path / "owner.lock"))
    monkeypatch.setattr(ardu, "require_legacy_route_qualification", lambda: None)
    monkeypatch.setattr(ardu, "XPlaneUDPClient", Client)
    monkeypatch.setattr(ardu, "SitlProcess", Sitl)
    monkeypatch.setattr(ardu.mav, "MavlinkLink", Link)
    monkeypatch.setattr(ardu, "ArduPlaneBackend", Backend)
    monkeypatch.setattr(ardu, "ManeuverGate", Gate)
    monkeypatch.setattr(sys, "argv", ["fly_arduplane_backend.py", "--heading", "90",
                                  "--altitude", "4500", "--candidate-session", "a" * 32,
                                  "--sitl-bin", str(binary), "--sitl-cwd", str(tmp_path)])
    if failure in ("backend", "gate"):
        with pytest.raises(RuntimeError, match=failure):
            ardu.main()
    else:
        assert ardu.main() == 1
    assert Client.last.stopped and Sitl.last.stopped
    if Link.last is not None:
        assert Link.last.closed
    if Sitl.last.started:
        assert events.index("sitl_stopped") < events.index("client_stopped")
    if "override_requested" in events:
        assert events.index("sitl_stopped") < events.index("override_requested")
