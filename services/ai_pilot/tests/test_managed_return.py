"""No process or simulator is started; managed-return boundaries are injected."""
import json
from pathlib import Path
import threading

import pytest

from services.ai_pilot import mavlink_min as mav
from services.ai_pilot.flight_executive import Controller, Phase, Role
from services.ai_pilot.managed_return import ManagedArduPlaneReturn
from services.ai_pilot.tests.test_arduplane_mission import Endpoint
from services.ai_pilot.tests.test_flight_executive import build, sortie, candidates


STOCK = Path(__file__).parents[3] / "xplane/ardupilot/xplane_plane_cap487.json"


def garmin_authority():
    clock, sim, bridge, old_link, observed, executive = build()
    class Garmin:
        def prepare(self, phase, profile): pass
        def ready(self): return True
        def activate(self): pass
        def observed_status(self):
            return {"age_seconds": 0, "vvi_fpm": 0, "roll_deg": 0,
                    "kias": 110, "agl_ft": 1500, "altitude_indicated_ft": 4500}
    class Power:
        def ready_for(self, phase): return True
    executive.adapters[Controller.GFC700] = Garmin()
    executive.power = Power()
    executive.request_mode(Role.AI_MISSION, Phase.TAKEOFF,
                           Controller.ARDUPLANE, "runway_sortie")
    executive.transfer_control(Controller.ARDUPLANE, bridge.generation)
    executive.tick()
    observed.update(on_ground=False, agl_ft=1500, kias=110)
    executive.request_mode(Role.AI_MISSION, Phase.TRANSIT,
                           Controller.GFC700, "cruise")
    executive.transfer_control(Controller.GFC700, bridge.generation)
    executive.tick()
    assert executive.controller == Controller.GFC700 and sim.ap and not sim.override
    return clock, bridge, old_link, executive, sortie(executive)[1]


@pytest.mark.parametrize("failure", [None, "old_stop", "start", "wait", "link",
                                     "verify", "resume"])
def test_managed_return_stages_isolated_mapping_and_cleans_failed_restart(
        failure, tmp_path):
    _, bridge, old_link, executive, items = garmin_authority()
    events = []
    class OldSitl:
        alive = True
        def stop(self):
            events.append("old_stop")
            if failure == "old_stop":
                return False
            self.alive = False
            return True
    class NewSitl:
        last = None
        def __init__(self, binary, cwd, parm, log_path, **kwargs):
            self.cwd, self.session = Path(cwd), kwargs["candidate_session"]
            self.stopped = False
            NewSitl.last = self
            events.append("new_construct")
        def start(self):
            if failure == "start":
                raise OSError("injected start failure")
            mapping = json.loads((self.cwd / "xplane_plane.json").read_text())
            assert any(key.startswith("cap/flight_control/candidate/" + self.session)
                       for key in mapping)
            assert not any("override" in key for key in mapping)
            events.append("new_start")
            candidates(bridge)
        def wait_for_mavlink(self, timeout):
            events.append("new_wait")
            return failure != "wait"
        def stop(self):
            events.append("new_stop")
            self.stopped = True
            return True
        @property
        def alive(self):
            return "new_start" in events and not self.stopped
    def link_factory(**kwargs):
        events.append("new_link")
        if failure == "link":
            raise OSError("injected link failure")
        link = Endpoint(reject=failure == "resume")
        link.inject_heartbeat(mav.PLANE_MODE_MANUAL)
        return link
    old_close = old_link.close
    def close_old():
        events.append("old_close")
        old_close()
    old_link.close = close_old
    procedure = ManagedArduPlaneReturn(
        stock_mapping=STOCK, run_root=tmp_path / "runs", binary=tmp_path / "fake-bin",
        parm=tmp_path / "fake.parm", old_sitl=OldSitl(), old_link=old_link,
        mavlink_port=5760, items=items, next_seq=2,
        verify_aircraft=lambda link: failure != "verify",
        sitl_factory=NewSitl, link_factory=link_factory,
        session_factory=lambda: "f" * 32, offline=True, ready_timeout_s=0.05)
    operation = procedure(executive)
    assert operation is procedure
    assert procedure.done.wait(1.0)
    if failure:
        with pytest.raises((ValueError, TimeoutError, OSError)):
            procedure.poll(executive)
        if failure == "old_stop":
            assert "old_close" not in events and NewSitl.last is None
        else:
            assert events.index("old_stop") < events.index("old_close")
            assert NewSitl.last.stopped
            assert not procedure.completed
    else:
        assert procedure.poll(executive) == "f" * 32
        assert procedure.completed
        assert executive.adapters[Controller.ARDUPLANE].link is procedure.current_link
        assert executive.adapters[Controller.ARDUPLANE].uploader.progress()["current_seq"] == 2
        assert not NewSitl.last.stopped
        assert procedure.shutdown() == []
        assert NewSitl.last.stopped
        assert procedure.shutdown() == []


def test_offline_return_refuses_real_process_or_link_factory(tmp_path):
    _, bridge, old_link, executive, items = garmin_authority()
    with pytest.raises(ValueError, match="injected process"):
        ManagedArduPlaneReturn(stock_mapping=STOCK, run_root=tmp_path,
            binary=tmp_path / "bin", parm=tmp_path / "parm", old_sitl=object(),
            old_link=old_link, mavlink_port=5760, items=items, next_seq=2,
            verify_aircraft=lambda link: True, offline=True)


def test_slow_restart_keeps_normal_executive_heartbeat_without_worker_lease(tmp_path):
    clock, bridge, old_link, executive, items = garmin_authority()
    entered, release = threading.Event(), threading.Event()
    class OldSitl:
        alive = False
        def stop(self): return True
    class NewSitl:
        alive = True
        def __init__(self, *args, **kwargs): pass
        def start(self): candidates(bridge)
        def wait_for_mavlink(self, timeout):
            entered.set()
            return release.wait(timeout)
        def stop(self):
            self.alive = False
            return True
    def link_factory(**kwargs):
        link = Endpoint()
        link.inject_heartbeat(mav.PLANE_MODE_MANUAL)
        return link
    procedure = ManagedArduPlaneReturn(
        stock_mapping=STOCK, run_root=tmp_path / "runs", binary=tmp_path / "bin",
        parm=tmp_path / "parm", old_sitl=OldSitl(), old_link=old_link,
        mavlink_port=5760, items=items, next_seq=2,
        verify_aircraft=lambda link: True, sitl_factory=NewSitl,
        link_factory=link_factory, session_factory=lambda: "f" * 32, offline=True,
        ready_timeout_s=2.0)
    procedure(executive)
    assert entered.wait(1.0)
    for _ in range(5):
        clock[0] += 0.2
        executive.tick()
        assert bridge.status()["state"] == "GFC700"
        assert procedure.poll(executive) is None
    release.set()
    assert procedure.done.wait(1.0)
    assert procedure.poll(executive) == "f" * 32
    assert procedure.shutdown() == []


def test_return_teardown_reports_both_link_and_writer_failures(tmp_path):
    _, _, old_link, _, items = garmin_authority()
    class BadLink:
        def close(self): raise OSError("link close failed")
    class BadSitl:
        alive = True
        def stop(self): return False
    procedure = ManagedArduPlaneReturn(
        stock_mapping=STOCK, run_root=tmp_path, binary=tmp_path / "bin",
        parm=tmp_path / "parm", old_sitl=BadSitl(), old_link=old_link,
        mavlink_port=5760, items=items, next_seq=2,
        verify_aircraft=lambda link: True, sitl_factory=lambda *a, **k: None,
        link_factory=lambda **k: None, offline=True)
    procedure.current_link = BadLink()
    procedure.current_sitl = BadSitl()
    assert procedure.shutdown() == ["MAVLink close: link close failed",
                                     "Managed SITL stop unconfirmed"]
