"""The GFC 700 as a second owner of the flight-control bridge.

The AI pilot has two ways to fly the airplane, and exactly one may at a time:

* DIRECT: the local controllers (takeoff, landing, search pattern, cruise) write
  the primary controls through the bridge's expiring atomic frames;
* GFC700: the airplane's own autopilot flies a selected heading and altitude, and
  the bridge only holds the fence (identity, envelope, heartbeat, terrain).

This module is the executive's side of that hand-over. The bridge enforces the
rules (`xplane/capvsar_flight_control_core.py`); this makes the calls in the
order the bridge needs and verifies each step from the telemetry frame.

Two lessons from the 2026-09-17 handoff trial are built in (ARDUPLANE_TRIAL.md,
F1 and F4):

* The hand-over is OVERLAPPED. Nothing ever flies "between" controllers: the
  bridge releases the actuators and engages the autopilot in one simulator
  callback, and releases the autopilot and takes the actuators in one callback.
* Autopilot modes are engaged by command, and the toggles are read first.

Not yet flown in the simulator. Simulator engineering only.
"""
from __future__ import annotations

import secrets
import time

from .terrain_guard import TerrainGuard

AP_HDG, AP_VS, AP_ALT_HOLD = 1 << 1, 1 << 4, 1 << 14   # sim autopilot_state bits
HEADING_TOLERANCE_DEG = 2.0
ALTITUDE_BUG_TOLERANCE_FT = 1.0
RESELECT_AFTER_S = 1.5
MAX_RESELECTS = 3
RETARGET_FT = 50.            # re-select altitude only for a change at least this big
HOLD_BAND_FT = 100.          # within this of the target: hold altitude, no climb
DESCENT_FPM = -500.


class GfcOwnerError(RuntimeError):
    pass


class GfcOwner:
    def __init__(self, client, *, clock=time.monotonic, sleep=time.sleep):
        self.client, self.clock, self.sleep = client, clock, sleep
        self.selected = {}            # heading_mag, altitude_ft, vs_fpm as last sent
        self._awaiting = None         # (deadline, reselects) while a selection settles
        self._throttle = None
        self._entry_throttle = None   # the power the AI pilot was flying when it handed over

    # ---- bridge state ------------------------------------------------------
    def status(self):
        return self.client.request("status")

    def owned(self):
        status = self.status()
        return status["state"] == "GFC700" and status["owner"] == "GFC700"

    def keepalive(self):
        """Heartbeat for the current session and generation. The bridge faults if
        it goes more than 0.4 s without one while the autopilot owns the airplane."""
        status = self.status()
        if status["state"] not in ("WAIT_GFC", "GFC700"):
            raise GfcOwnerError("Bridge is not in GFC 700 ownership: %s" % status["state"])
        self.client.request("heartbeat", session=status["session"], generation=status["generation"])
        return status

    # ---- DIRECT -> GFC700 --------------------------------------------------
    def engage(self, heading_mag, altitude_ft, vs_fpm=None, *, timeout_s=2.0):
        """Hand the airplane from the AI pilot's controllers to the GFC 700.

        The caller must stop submitting DIRECT frames after this returns, and
        keep calling `step` or `keepalive` at least every 0.2 s.
        """
        status = self.status()
        if status["state"] != "ACTIVE" or status["owner"] != "DIRECT":
            raise GfcOwnerError("Hand-over needs DIRECT ownership, bridge is %s/%s"
                                % (status["state"], status["owner"]))
        self.client.request("transfer_gfc", generation=status["generation"], ready=True)
        deadline = self.clock() + timeout_s
        while True:
            status = self.keepalive()
            if status["state"] == "GFC700":
                break
            if self.clock() > deadline:
                raise GfcOwnerError("Autopilot engagement not observed")
            self.sleep(0.02)
        self.selected = {}
        self._entry_throttle = self._throttle = None
        self.select(heading_mag, altitude_ft, vs_fpm)
        return status

    def select(self, heading_mag=None, altitude_ft=None, vs_fpm=None):
        status = self.status()
        if status["state"] != "GFC700":
            raise GfcOwnerError("Selection needs GFC 700 ownership")
        fields = {k: v for k, v in (("heading_mag", heading_mag), ("altitude_ft", altitude_ft),
                                    ("vs_fpm", vs_fpm)) if v is not None}
        result = self.client.request("gfc_select", session=status["session"],
                                     expected_generation=status["generation"], **fields)
        self.selected = {**self.selected, **fields}
        if altitude_ft is not None and vs_fpm is None:
            self.selected.pop("vs_fpm", None)
        self._awaiting = (self.clock() + RESELECT_AFTER_S, self._awaiting[1] if self._awaiting else 0)
        return result

    def set_throttle(self, fraction):
        """Power while the autopilot flies; it has no autothrottle."""
        if self._throttle is not None and abs(self._throttle - fraction) < 0.02:
            return
        status = self.status()
        self.client.request("set_virtual_aux", channel="throttle", value=float(fraction),
                            session=status["session"], expected_generation=status["generation"])
        self._throttle = fraction

    # ---- verification ------------------------------------------------------
    def problems(self, snapshot):
        """What the telemetry says differs from what was selected."""
        v, want, found = snapshot["values"], self.selected, []
        if snapshot.get("ap_engaged") is not True:
            found.append("autopilot not engaged")
        if "heading_mag" in want:
            error = abs((v["ap_heading_bug_deg"] - want["heading_mag"] + 180) % 360 - 180)
            if error > HEADING_TOLERANCE_DEG:
                found.append("heading bug %.0f, selected %.0f" % (v["ap_heading_bug_deg"], want["heading_mag"]))
            if not int(v["ap_state"]) & AP_HDG:
                found.append("heading mode not engaged")
        if "altitude_ft" in want:
            if abs(v["ap_altitude_bug_ft"] - want["altitude_ft"]) > ALTITUDE_BUG_TOLERANCE_FT:
                found.append("altitude bug %.0f, selected %.0f" % (v["ap_altitude_bug_ft"], want["altitude_ft"]))
            # Climbing in VS may already have captured into ALT hold; holding must be ALT hold.
            vertical = (AP_VS | AP_ALT_HOLD) if "vs_fpm" in want else AP_ALT_HOLD
            if not int(v["ap_state"]) & vertical:
                found.append("vertical mode not engaged")
            if "vs_fpm" in want and abs(v["ap_vs_bug_fpm"] - want["vs_fpm"]) > 100:
                found.append("vertical-speed bug %.0f, selected %.0f" % (v["ap_vs_bug_fpm"], want["vs_fpm"]))
        return found

    def verify(self, snapshot):
        """Re-send a selection the autopilot did not take (engaging VS zeroes the rate,
        for one); raise when it will not take after MAX_RESELECTS tries."""
        if self._awaiting is None:
            return []
        found = self.problems(snapshot)
        deadline, tries = self._awaiting
        if not found:
            self._awaiting = None
            return []
        if self.clock() < deadline:
            return found
        if tries >= MAX_RESELECTS:
            raise GfcOwnerError("GFC 700 selection not taken: " + "; ".join(found))
        self._awaiting = (self.clock() + RESELECT_AFTER_S, tries + 1)
        status = self.status()
        self.client.request("gfc_select", session=status["session"],
                            expected_generation=status["generation"], **self.selected)
        return found

    # ---- one executive tick while the autopilot owns the airplane ----------
    def step(self, snapshot, *, heading_mag, altitude_ft, guard: TerrainGuard | None = None,
             cruise_throttle=None):
        """Heartbeat, apply the terrain guard, keep the selections, verify them.

        `heading_mag` and `altitude_ft` are the mission's. The guard may raise the
        altitude (and order full power) or, beyond its ceiling or leash, replace the
        heading with a course back to the area. Returns the guard's advice.
        """
        self.keepalive()
        if self._entry_throttle is None:
            self._entry_throttle = snapshot["controls"].get("throttle")   # before any full-power order
        v, advice = snapshot["values"], None
        target_alt, target_hdg = altitude_ft, heading_mag
        if guard is not None:
            advice = guard.update(snapshot)
            target_alt = guard.apply_to_altitude(altitude_ft, advice)
            if advice.turn_back and advice.return_heading_true is not None:
                variation = v["heading_true_deg"] - v["heading_mag_deg"]
                target_hdg = (advice.return_heading_true - variation) % 360
        changes = {}
        if abs(target_hdg - self.selected.get("heading_mag", -999)) >= HEADING_TOLERANCE_DEG:
            changes["heading_mag"] = round(target_hdg, 1)
        if abs(target_alt - self.selected.get("altitude_ft", -9999)) >= RETARGET_FT:
            changes["altitude_ft"] = round(target_alt)
            error = target_alt - v["altitude_indicated_ft"]
            if abs(error) <= HOLD_BAND_FT:
                changes["vs_fpm"] = None
            else:
                rate = advice.climb_fpm if (advice and advice.climb_fpm and error > 0) else 500.
                changes["vs_fpm"] = rate if error > 0 else DESCENT_FPM
        if changes:
            self.select(changes.get("heading_mag"), changes.get("altitude_ft"), changes.get("vs_fpm"))
        if advice is not None and advice.full_power:
            self.set_throttle(1.0)
        else:
            # The autopilot has no autothrottle: whoever raised the power must give it back,
            # or the airplane levels off at full throttle (130 KIAS at 6,000 ft, ESCON run 3).
            restore = cruise_throttle if cruise_throttle is not None else self._entry_throttle
            if restore is not None and (cruise_throttle is not None or self._throttle is not None):
                self.set_throttle(restore)
        self.verify(snapshot)
        return advice

    # ---- GFC700 -> DIRECT --------------------------------------------------
    def hand_back(self, controls, *, timeout_s=2.0):
        """Return the airplane to the AI pilot's controllers.

        `controls` is the complete first frame (use the measured throttle, trim and
        prop, and neutral yoke). Returns (session, generation, sequence) for the
        `exchange` loop. The caller must build a FRESH controller: integrators from
        before the hand-over describe an airplane the autopilot has since flown.
        """
        snap = self.client.request("snapshot")
        session = secrets.token_hex(16)
        self.client.request("lab_handback", session=session, controls=controls,
                            snapshot_frame=snap["frame"], snapshot_wall_time_s=snap["wall_time_s"])
        deadline, sequence = self.clock() + timeout_s, 2
        while True:
            status = self.status()
            if status["state"] == "ACTIVE" and status["owner"] == "DIRECT":
                self.selected, self._awaiting, self._throttle = {}, None, None
                return session, status["generation"], status["frame_sequence"]
            if status["state"] not in ("PREPARING", "WAIT_AP_OFF"):
                raise GfcOwnerError("Hand-back failed: bridge is %s" % status["state"])
            if self.clock() > deadline:
                raise GfcOwnerError("Autopilot release not observed")
            sequence += 1
            # The first frames expire in 0.18 s; keep a fresh one and a heartbeat
            # under the bridge while it waits to see the autopilot let go.
            self.client.request("submit_frame", session=session, generation=status["generation"],
                                sequence=sequence, expires_at=self.clock() + .18, controls=controls)
            self.client.request("heartbeat", session=session, generation=status["generation"])
            self.sleep(0.01)
