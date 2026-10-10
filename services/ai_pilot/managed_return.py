"""Managed ArduPlane return after a planned Garmin cruise segment.

This is an offline-testable orchestration procedure, not live qualification.
The stock mapping, plugin and aircraft are never touched by this module's
tests; live entry remains closed by the global qualification switch.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading
import time
from uuid import uuid4

from xplane.capvsar_flight_control_mapping import candidate_prefix, mapping_json

from . import mavlink_min as mav
from .control_ownership import require_live_qualification
from .flight_executive import Controller, Role, TransferState
from .sitl_lifecycle import SitlProcess


class ManagedArduPlaneReturn:
    def __init__(self, *, stock_mapping: Path, run_root: Path, binary: Path,
                 parm: Path, old_sitl, old_link, mavlink_port: int,
                 items: tuple, next_seq: int,
                 verify_aircraft, sitl_factory=SitlProcess,
                 link_factory=mav.MavlinkLink, session_factory=lambda: uuid4().hex,
                 offline=False, ready_timeout_s=20.0):
        if offline and (sitl_factory is SitlProcess or link_factory is mav.MavlinkLink):
            raise ValueError("Offline return requires injected process and MAVLink fakes")
        if not callable(verify_aircraft):
            raise ValueError("Independent aircraft readiness check required")
        self.stock_mapping = Path(stock_mapping)
        self.run_root = Path(run_root)
        self.binary, self.parm = Path(binary), Path(parm)
        self.old_sitl, self.old_link = old_sitl, old_link
        self.mavlink_port = mavlink_port
        if (type(next_seq) is not int or not 0 <= next_seq < len(items)
                or items[next_seq].command != mav.MAV_CMD_NAV_WAYPOINT):
            raise ValueError("Planned return must name a route waypoint")
        self.items, self.next_seq = tuple(items), next_seq
        self.verify_aircraft = verify_aircraft
        self.sitl_factory, self.link_factory = sitl_factory, link_factory
        self.session_factory = session_factory
        self.offline = offline
        if not 0 < ready_timeout_s <= 20.0:
            raise ValueError("Bounded managed return readiness deadline required")
        self.ready_timeout_s = ready_timeout_s
        self.current_sitl = None
        self.current_link = None
        self.prepared_uploader = None
        self.cancel_requested = threading.Event()
        self.done = threading.Event()
        self.worker = None
        self.error = None
        self.cleanup_errors = []
        self.session = None
        self.completed = False

    def __call__(self, executive):
        """Stage/renew quickly, then return a pollable operation.

        The caller must continue executive ticks while the worker waits for
        process, link and mission protocol readiness. A stalled caller loses
        bridge heartbeat and native authority as intended.
        """
        if not self.offline:
            require_live_qualification()
        if self.worker is not None or self.completed:
            raise ValueError("Managed return already used")
        if (executive.role != Role.AI_MISSION
                or executive.controller != Controller.GFC700
                or executive.transfer != TransferState.ACTIVE
                or executive.active_task is not None
                or executive.bridge.status().get("state") != "GFC700"):
            raise ValueError("Verified idle Garmin authority required for return")
        session = self.session_factory()
        candidate_prefix(session)
        run_dir = self.run_root / session
        run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        mapping = mapping_json(self.stock_mapping.read_text(), session)
        mapping_path = run_dir / "xplane_plane.json"
        fd = os.open(mapping_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(mapping)
        executive.renew_candidate_session(session, executive.bridge_generation)
        self.session = session
        adapter = executive.adapters[Controller.ARDUPLANE]
        self.worker = threading.Thread(target=self._prepare,
                                       args=(run_dir, adapter),
                                       name="managed-arduplane-return", daemon=True)
        self.worker.start()
        return self

    def _prepare(self, run_dir, adapter):
        try:
            if (self.old_sitl.stop() is not True
                    or getattr(self.old_sitl, "alive", None) is not False):
                raise ValueError("Previous SITL writer not confirmed stopped")
            self.old_link.close()
            if self.cancel_requested.is_set():
                raise ValueError("Managed return canceled")
            sitl = self.sitl_factory(self.binary, run_dir, self.parm,
                                     run_dir / "arduplane.log",
                                     mavlink_port=self.mavlink_port,
                                     candidate_session=self.session)
            self.current_sitl = sitl
            sitl.start()
            deadline = time.monotonic() + self.ready_timeout_s
            while not self.cancel_requested.is_set() and time.monotonic() < deadline:
                if sitl.wait_for_mavlink(timeout=0.25):
                    break
                time.sleep(0.01)
            else:
                raise TimeoutError("Restarted managed SITL MAVLink unavailable or canceled")
            if self.cancel_requested.is_set():
                raise ValueError("Managed return canceled")
            link = self.link_factory(host="127.0.0.1", port=self.mavlink_port,
                                     timeout=0.5)
            self.current_link = link
            if self.verify_aircraft(link) is not True:
                raise ValueError("Restarted aircraft readiness not independently verified")
            self.prepared_uploader = adapter.prepare_return_link(
                link, self.items, self.next_seq)
            if self.cancel_requested.is_set():
                raise ValueError("Managed return canceled")
        except BaseException as error:
            self.error = error
            self.cleanup_errors = self.shutdown()
        finally:
            self.done.set()

    def poll(self, executive):
        if self.worker is None:
            raise ValueError("Managed return was not started")
        if not self.done.is_set():
            return None
        if self.error is not None:
            if self.cleanup_errors:
                raise RuntimeError("Managed return failed: %s; cleanup: %s" %
                                   (self.error, "; ".join(self.cleanup_errors))) from self.error
            raise self.error
        if self.cancel_requested.is_set():
            raise ValueError("Managed return canceled")
        if not self.completed:
            executive.adapters[Controller.ARDUPLANE].adopt_return_link(
                self.current_link, self.prepared_uploader)
            self.completed = True
        return self.session

    def cancel(self):
        self.cancel_requested.set()
        if self.done.is_set():
            return self.shutdown()
        return []

    def shutdown(self):
        """Idempotent cleanup; preserve an unconfirmed stop as an error."""
        errors = []
        if self.current_link is not None:
            try:
                self.current_link.close()
            except Exception as error:
                errors.append("MAVLink close: %s" % error)
            self.current_link = None
        if self.current_sitl is not None:
            try:
                if (self.current_sitl.stop() is not True
                        or getattr(self.current_sitl, "alive", None) is not False):
                    errors.append("Managed SITL stop unconfirmed")
                else:
                    self.current_sitl = None
            except Exception as error:
                errors.append("Managed SITL stop: %s" % error)
        return errors
