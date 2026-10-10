"""Shared process guard and live qualification gate for flight entrypoints."""
from __future__ import annotations

import fcntl
from functools import wraps

LOCK_PATH = "/tmp/cap-vsar-maneuver-controller.lock"

# This source switch is intentionally closed until an attended bridge install,
# SDK readback test, and full-flight qualification are recorded. A live command
# line flag alone cannot establish those conditions.
LIVE_CONTROL_QUALIFIED = False
# Historical launchers and the chat deck still use raw backend paths. Enabling
# the bridge after attended testing must not accidentally enable those routes.
LEGACY_ROUTE_QUALIFIED = False


def require_live_qualification():
    if not LIVE_CONTROL_QUALIFIED:
        raise RuntimeError("Live flight-control bridge is UNVERIFIED_LIVE; entrypoint disabled")


def require_legacy_route_qualification():
    require_live_qualification()
    if not LEGACY_ROUTE_QUALIFIED:
        raise RuntimeError("Legacy raw flight-control route is not migrated to the executive")


class ControllerLock:
    def __enter__(self):
        self.handle = open(LOCK_PATH, "w")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.handle.close()
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        if getattr(self, "handle", None) is not None and not self.handle.closed:
            try:
                fcntl.flock(self.handle, fcntl.LOCK_UN)
            finally:
                self.handle.close()


def exclusive_controller(fn):
    """One process lock for every legacy entrypoint, including mock runs."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with ControllerLock():
            return fn(*args, **kwargs)
    return wrapped
