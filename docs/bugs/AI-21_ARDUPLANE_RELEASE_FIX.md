# AI-21 — fix brief: ArduPlane release mode, SITL attach window, detach sequence

Self-contained implementation brief. Everything you need is in this file and
the files it names. Do not research ArduPilot behaviour: every fact you need
is stated here and was verified against the ArduPilot source (Plane-4.7.1)
on 2026-09-17; the evidence is in `docs/ARDUPLANE_TRIAL.md` under
"handoff design review" if you want to read it, but you do not need to.

## Rules (read first)

- **Offline only.** Do not start X-Plane, do not start ArduPilot SITL, do not run
  `scripts/fly_arduplane_backend.py` without `--dry-run`. Nothing here needs a simulator.
- **Do not edit** these files, they belong to other agents: `services/ai_pilot/maneuvers.py`,
  `services/ai_pilot/maneuver_server.py`, `services/ai_pilot/web*`, `services/ai_pilot/fdr*`,
  `services/ai_pilot/diag*`, `scripts/fly_direct_backend.py`, `scripts/fly_card_h0.py`,
  `docs/BOARD.md`.
- **Tests are `unittest`**, not pytest (pytest is not installed). Run:
  `python3 -m unittest services.ai_pilot.tests.test_arduplane_backend services.ai_pilot.tests.test_mavlink_min services.ai_pilot.tests.test_sitl_lifecycle -v`
  and, at the end, the whole service suite:
  `python3 -m unittest discover -s services/ai_pilot/tests -t . 2>&1 | tail -3`
  (one pre-existing error, `test_maneuvers` importing pytest, is expected and not yours).
- **Do not commit.** Leave changes in the working tree; Claude reviews and commits.
- Style: no comments that explain *what* code does; a short comment only where the *why*
  is non-obvious (several are given below — copy them). No new dependencies.

## Background in five sentences

`services/ai_pilot/arduplane_backend.py` flies the aircraft by putting an ArduPilot
ArduPlane SITL into GUIDED mode and sending it heading/altitude targets over MAVLink
(`services/ai_pilot/mavlink_min.py`). SITL is attached to X-Plane and **writes the
throttle and yoke datarefs every frame in every mode**, holding X-Plane's
`sim/operation/override/override_joystick` and `override_throttles` at 1 by re-sending
them every frame; when the SITL process dies, those overrides stay latched at 1 with the
last yoke values, and there is no exit hook. ArduPlane's MANUAL mode passes the raw RC
stick straight to the control surfaces with no limits; when its RC input is absent or
mis-mapped, that means full aileron and full throttle, or zero throttle. The backend
currently releases the aircraft into MANUAL, which is therefore unsafe unless the RC
map has been proven. Four things must change, listed below in the order to do them.

## Facts you may rely on (verified in ArduPilot source)

| Fact | Consequence for this work |
|---|---|
| ArduPlane mode numbers: MANUAL 0, FBWA 5, LOITER 12, GUIDED 15 (`mavlink_min.py` already has `PLANE_MODE_*` constants) | use the constants, never literals |
| LOITER flies itself with no RC input (auto-throttle). FBWA is attitude-stabilised and limited but takes throttle from the stick. MANUAL is raw passthrough. | release default = LOITER; FBWA only when RC was proven valid |
| `MAV_CMD_GUIDED_CHANGE_ALTITUDE` is refused (MAV_RESULT_DENIED) when `z` is exactly 0 or exactly −1 | guard before sending |
| `MAV_CMD_GUIDED_CHANGE_HEADING` param3 is a centripetal acceleration in m/s²; 0 is floored to 0.05, which cannot turn the aircraft | the constant `HEADING_ACCEL_M_S2` must never be 0; `HEADING_TYPE_DEFAULT` ignores param3 entirely, so sending 0 there is fine |
| HEARTBEAT `base_mode` bit 128 = armed. With `ARMING_REQUIRE 0` (already in `xplane/ardupilot/cap487.parm`) ArduPlane reports armed without an arm command | preflight must report it; the launcher refuses if not armed |
| Clearing the X-Plane overrides while SITL is alive is futile (it re-sends 1 every frame); clearing after SITL is stopped is mandatory | detach order: park → stop SITL → clear overrides → engage GFC 700 |
| X-Plane's `sim/GPS/g1000n1_ap` command **toggles** the autopilot; `g1000n1_hdg` and `g1000n1_alt` engage those modes; `sim/cockpit2/autopilot/servos_on` (1 = AP servos engaged) and bit 2 of `sim/cockpit/autopilot/autopilot_state` (heading mode) are readable | never press `_ap` unless `servos_on` reads 0; press `_hdg` only if bit 2 is clear |

## Step 1 — `services/ai_pilot/mavlink_min.py`

1. Add a constant next to `MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1`:
   ```python
   MAV_MODE_FLAG_SAFETY_ARMED = 128
   ```
2. In `class MockLink`, method `inject_heartbeat(self, custom_mode, base_mode=MAV_MODE_FLAG_CUSTOM_MODE_ENABLED)`:
   change the default to `base_mode=MAV_MODE_FLAG_CUSTOM_MODE_ENABLED | MAV_MODE_FLAG_SAFETY_ARMED`
   so the mock reports armed unless a test says otherwise.
3. Add to `services/ai_pilot/tests/test_mavlink_min.py`, class `MockLinkTests`:
   ```python
   def test_mock_heartbeat_reports_armed_by_default(self):
       link = mav.MockLink(clock=lambda: 10.0)
       link.inject_heartbeat(mav.PLANE_MODE_MANUAL)
       fields, _age = link.latest(mav.MSG_HEARTBEAT)
       self.assertTrue(fields["base_mode"] & mav.MAV_MODE_FLAG_SAFETY_ARMED)
   ```

## Step 2 — `services/ai_pilot/arduplane_backend.py`

### 2a. Release mode: LOITER by default, FBWA only with a proven stick

Find `_hand_back(self)`. It currently sends two frames:
`mav.guided_change_heading(mav.HEADING_TYPE_DEFAULT, 0.0, 0.0)` then
`mav.set_mode(mav.PLANE_MODE_MANUAL)`. Replace the body so that:

```python
    def _hand_back(self) -> None:
        """Clear the heading hold and leave ArduPlane in a mode that is safe
        for whatever holds the aircraft next - only if this backend engaged,
        and only once, whichever thread gets here first.

        LOITER flies itself with no RC input. FBWA hands the pilot a
        stabilised, limited aircraft, but takes throttle from the stick, so it
        is offered only when a valid, centred RC position was measured at
        engagement. MANUAL is never used: with an unmapped stick it is full
        aileron and full throttle.
        """
        with self.lock:
            engaged, self._engaged = self._engaged, False
            rc_proven = self._rc_rest is not None
        if not engaged:
            return
        mode = mav.PLANE_MODE_FBWA if rc_proven else mav.PLANE_MODE_LOITER
        for msgid, fields in (
            mav.guided_change_heading(mav.HEADING_TYPE_DEFAULT, 0.0, 0.0),
            mav.set_mode(mode),
        ):
            try:
                self.link.send(msgid, fields)
            except OSError:
                pass
        with self.lock:
            self._released_at = self.clock()
            self._last_commands["mode"] = mode
            self._last_commands["hand_back_mode"] = "FBWA" if rc_proven else "LOITER"
```

Also update the class docstring bullet that says the pilot "releases to MANUAL"
(search for "MANUAL" in the docstring and the `release()` docstring) to say LOITER /
FBWA as above. Do not change `release()`, `pause()`, `_takeover()` logic.

### 2b. Altitude guard

Find `_command_altitude(self, alt_true_m)`. Add at the top:
```python
        if not math.isfinite(alt_true_m) or math.isclose(alt_true_m, 0.0, abs_tol=0.01) \
                or math.isclose(alt_true_m, -1.0, abs_tol=0.01):
            # ArduPlane answers DENIED to a z of exactly 0 or -1; refuse before
            # sending so the failure is ours to explain, not a bare MAV_RESULT.
            raise ValueError("Altitude target %.2f m is not accepted by ArduPilot" % alt_true_m)
```
(`math` is already imported.)

### 2c. Preflight reports the armed bit

In `preflight(self)`, add to the returned dict:
```python
            "armed": bool(hb["base_mode"] & mav.MAV_MODE_FLAG_SAFETY_ARMED) if hb else False,
```
where `hb, _ = self.link.latest(mav.MSG_HEARTBEAT)` is fetched at the top of the
method next to the existing `gpi`/`rc` fetches.

### 2d. Tests — `services/ai_pilot/tests/test_arduplane_backend.py`

Existing tests assert `param2 == float(mav.PLANE_MODE_MANUAL)` on hand-back. Every one
of those assertions must change. The rule: if the test's rig injected an
`RC_CHANNELS` frame **before** `select()` (the `SupervisionTests.engaged()` helper does),
the expected mode is `PLANE_MODE_FBWA`; otherwise it is `PLANE_MODE_LOITER`. Concretely:

| Test | Expect |
|---|---|
| `ReleaseTests.test_release_sends_default_heading_then_manual_only_if_engaged` | rename to `..._then_loiter_only_if_engaged`; expect LOITER; keep every other assertion (never pauses, no X-Plane writes, nothing if not engaged) |
| `ReleaseTests.test_release_after_pause_still_hands_back` | LOITER |
| `SupervisionTests.test_rc_yoke_input_releases` | FBWA (RC was injected) |
| `SupervisionTests.test_external_mode_change_releases` | FBWA |
| `SupervisionTests.test_g1000_engaged_releases` | FBWA |
| `SupervisionTests.test_xplane_axis_input_releases` | LOITER (builds its own rig, no RC) |
| `ThreadTests.test_release_from_supervisor_thread_does_not_self_join` | LOITER |
| `ThreadTests.test_takeover_that_also_breaks_the_envelope_releases_not_pauses` | LOITER |

Add these new tests:

```python
class HandBackModeTests(unittest.TestCase):
    def test_release_uses_fbwa_when_rc_was_valid_at_engagement(self):
        rig = Rig()
        feed(rig.client, rig.backend, **frame())
        rig.link.inject(mav.MSG_RC_CHANNELS, rc_frame())
        rig.backend.select(120.0, 4500.0)
        rig.backend.release()
        self.assertEqual(rig.link.sent_messages[-1][1]["param2"], float(mav.PLANE_MODE_FBWA))
        self.assertEqual(rig.backend.last_commands["hand_back_mode"], "FBWA")

    def test_release_uses_loiter_when_rc_unproven(self):
        rig = Rig()
        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        rig.backend.release()
        self.assertEqual(rig.link.sent_messages[-1][1]["param2"], float(mav.PLANE_MODE_LOITER))
        self.assertEqual(rig.backend.last_commands["hand_back_mode"], "LOITER")

    def test_release_never_sends_manual(self):
        for rc in (None, rc_frame(), rc_frame(chancount=0)):
            with self.subTest(rc=rc and rc["chancount"]):
                rig = Rig()
                feed(rig.client, rig.backend, **frame())
                if rc is not None:
                    rig.link.inject(mav.MSG_RC_CHANNELS, rc)
                rig.backend.select(120.0, 4500.0)
                rig.backend.release()
                modes = [f["param2"] for m, f in rig.link.sent_messages
                         if f.get("command") == mav.MAV_CMD_DO_SET_MODE]
                self.assertNotIn(float(mav.PLANE_MODE_MANUAL), modes)

    def test_heading_accel_is_never_zero(self):
        self.assertGreaterEqual(ArduPlaneBackend.HEADING_ACCEL_M_S2, 0.5)
        rig = Rig(mode=mav.PLANE_MODE_GUIDED)
        feed(rig.client, rig.backend, **frame())
        rig.backend.select(120.0, 4500.0)
        try:
            heading = [f for m, f in rig.link.sent_messages
                       if f.get("command") == mav.MAV_CMD_GUIDED_CHANGE_HEADING][0]
            self.assertGreaterEqual(heading["param3"], 0.5)
        finally:
            rig.close()

    def test_altitude_of_zero_or_minus_one_is_refused_before_sending(self):
        # frame() has the altimeter set correctly (offset 0), so a 0 ft target
        # maps to exactly 0 m true - the value ArduPlane answers DENIED to.
        # The gate is not involved: the backend is called directly.
        rig = Rig(mode=mav.PLANE_MODE_GUIDED)
        feed(rig.client, rig.backend, **frame())
        with self.assertRaisesRegex(ValueError, "not accepted"):
            rig.backend.select(120.0, 0.0)
        self.assertEqual([f for m, f in rig.link.sent_messages
                          if f.get("command") == mav.MAV_CMD_GUIDED_CHANGE_ALTITUDE], [])
        self.assertFalse(rig.backend.flying)

    def test_preflight_reports_armed_bit(self):
        rig = Rig(mode=mav.PLANE_MODE_MANUAL)
        feed(rig.client, rig.backend, **frame())
        self.assertTrue(rig.backend.preflight()["armed"])
        rig.link.inject_heartbeat(mav.PLANE_MODE_MANUAL, base_mode=mav.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED)
        self.assertFalse(rig.backend.preflight()["armed"])
```

Why that altitude test works: `select()` computes
`target_alt_m = target_ft * 0.3048 + (elevation_m - indicated_ft * 0.3048)`; with the
default `frame()` the bracket is 0, so a 0 ft target is exactly 0.0 m and the guard fires
before any MAVLink altitude frame is sent.

## Step 3 — new module `services/ai_pilot/sitl_lifecycle.py`

Two small classes, no threads, fully testable with fakes. The launcher (Step 4) uses them.

```python
"""Own the ArduPlane SITL process and the X-Plane side of attaching and
detaching it, in the one order that is safe.

SITL writes the throttle and yoke datarefs every frame in every mode and
re-sends X-Plane's joystick/throttle overrides every frame; it has no exit
hook. So the overrides can only be cleared after the process is gone, and
the aircraft must be parked (ArduPlane LOITER, then the GFC 700) around
that gap, because CAP 487 does not hold itself for more than a few seconds.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from pathlib import Path

OVERRIDE_DREFS = (
    "sim/operation/override/override_joystick",
    "sim/operation/override/override_throttles",
)


class SitlProcess:
    """Start / stop the arduplane binary with the X-Plane model."""

    def __init__(self, binary, cwd, parm, log_path, mavlink_port=5760, popen=subprocess.Popen,
                 clock=time.monotonic, sleep=time.sleep):
        self.binary, self.cwd, self.parm = str(binary), str(cwd), str(parm)
        self.log_path, self.mavlink_port = str(log_path), mavlink_port
        self._popen, self.clock, self.sleep = popen, clock, sleep
        self.process = None

    def start(self):
        Path(self.cwd).mkdir(parents=True, exist_ok=True)
        log = open(self.log_path, "ab")
        self.process = self._popen(
            [self.binary, "--model", "xplane", "--defaults", self.parm],
            cwd=self.cwd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        )
        return self.process

    def wait_for_mavlink(self, timeout=20.0, probe=None):
        """True once TCP 5760 accepts a connection. `probe` is injectable for tests."""
        probe = probe or self._tcp_open
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            if self.process is not None and self.process.poll() is not None:
                return False
            if probe(self.mavlink_port):
                return True
            self.sleep(0.25)
        return False

    @staticmethod
    def _tcp_open(port):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            return False

    def stop(self, grace=3.0):
        """SIGTERM, wait, SIGKILL. Returns True when the process is gone."""
        p = self.process
        if p is None:
            return True
        if p.poll() is None:
            p.terminate()
            deadline = self.clock() + grace
            while p.poll() is None and self.clock() < deadline:
                self.sleep(0.1)
            if p.poll() is None:
                p.kill()
                p.wait(timeout=2.0)
        self.process = None
        return True

    @property
    def alive(self):
        return self.process is not None and self.process.poll() is None


def clear_overrides(client):
    """Only meaningful once SITL is gone - alive, it re-asserts them every frame."""
    for ref in OVERRIDE_DREFS:
        client.send_dref(ref, 0)


def park_on_gfc700(client, state, heading_mag, altitude_ft):
    """Engage the aircraft's own autopilot in HDG + ALT at the given targets.

    `state` is a dict with 'servos_on' and 'ap_state' read from X-Plane just
    before the call. g1000n1_ap TOGGLES, so it is pressed only when the servos
    are off; g1000n1_hdg only when heading mode (bit 2) is not already set.
    Returns the list of commands sent, for the trace.
    """
    sent = []
    client.send_dref("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot", float(heading_mag) % 360.0)
    client.send_dref("sim/cockpit2/autopilot/altitude_dial_ft", float(round(altitude_ft / 100.0) * 100))
    client.send_dref("sim/cockpit2/autopilot/servos_on", 1)
    if not state.get("servos_on"):
        client.send_command("sim/GPS/g1000n1_ap"); sent.append("sim/GPS/g1000n1_ap")
    if not (int(state.get("ap_state", 0)) & 2):
        client.send_command("sim/GPS/g1000n1_hdg"); sent.append("sim/GPS/g1000n1_hdg")
    client.send_command("sim/GPS/g1000n1_alt"); sent.append("sim/GPS/g1000n1_alt")
    return sent


def detach(backend, client, sitl, state, heading_mag, altitude_ft, release=None):
    """The one safe order: release (ArduPlane parks itself) -> stop SITL ->
    clear overrides -> GFC 700 holds. Returns a dict describing what happened."""
    (release or backend.release)()
    stopped = sitl.stop() if sitl is not None else True
    clear_overrides(client)
    commands = park_on_gfc700(client, state, heading_mag, altitude_ft)
    return {"sitl_stopped": stopped, "gfc700_commands": commands,
            "hand_back_mode": backend.last_commands.get("hand_back_mode")}
```

### Tests — new file `services/ai_pilot/tests/test_sitl_lifecycle.py`

Use `FakeClient` from `test_direct_backend.py` (it records `writes` and `commands`)
and a `FakeProcess` with `poll()`/`terminate()`/`kill()`/`wait()`:

```python
"""Offline tests for the SITL lifecycle and the detach order. No process is
started and nothing talks to a simulator: a fake Popen and a fake client
record what would have happened, in order."""
import unittest
from services.ai_pilot import sitl_lifecycle as sl
from services.ai_pilot import mavlink_min as mav
from services.ai_pilot.tests.test_direct_backend import FakeClient


class FakeProcess:
    def __init__(self):
        self.signals = []
        self._rc = None
    def poll(self):
        return self._rc
    def terminate(self):
        self.signals.append("TERM"); self._rc = 0
    def kill(self):
        self.signals.append("KILL"); self._rc = -9
    def wait(self, timeout=None):
        return self._rc


class StubbornProcess(FakeProcess):
    def terminate(self):
        self.signals.append("TERM")      # ignores it


class Timeline:
    """Interleaves client writes/commands and SITL stop into one ordered log."""
    def __init__(self, client, sitl):
        self.events = []
        cw, cc, ss = client.send_dref, client.send_command, sitl.stop
        client.send_dref = lambda r, v: (self.events.append(("dref", r, v)), cw(r, v))
        client.send_command = lambda c: (self.events.append(("cmd", c)), cc(c))
        sitl.stop = lambda *a, **k: (self.events.append(("sitl", "stop")), ss(*a, **k))[1]


class FakeBackend:
    def __init__(self):
        self.released = 0
        self.last_commands = {"hand_back_mode": "LOITER"}
    def release(self):
        self.released += 1


def make_sitl(process):
    t = [0.0]
    return sl.SitlProcess("/bin/false", "/tmp/x", "/tmp/x.parm", "/tmp/x.log",
                          popen=lambda *a, **k: process, clock=lambda: t[0],
                          sleep=lambda s: t.__setitem__(0, t[0] + s)), t


class SitlProcessTests(unittest.TestCase):
    def test_stop_terminates_then_kills_a_stubborn_process(self):
        proc = StubbornProcess()
        sitl, _ = make_sitl(proc); sitl.start()
        self.assertTrue(sitl.stop(grace=1.0))
        self.assertEqual(proc.signals, ["TERM", "KILL"])
        self.assertFalse(sitl.alive)

    def test_stop_is_gentle_when_term_suffices(self):
        proc = FakeProcess()
        sitl, _ = make_sitl(proc); sitl.start()
        sitl.stop()
        self.assertEqual(proc.signals, ["TERM"])

    def test_wait_for_mavlink_gives_up_if_process_dies(self):
        proc = FakeProcess(); proc._rc = 1
        sitl, _ = make_sitl(proc); sitl.start()
        self.assertFalse(sitl.wait_for_mavlink(timeout=5.0, probe=lambda p: False))

    def test_wait_for_mavlink_returns_when_port_opens(self):
        proc = FakeProcess()
        sitl, t = make_sitl(proc); sitl.start()
        calls = []
        self.assertTrue(sitl.wait_for_mavlink(timeout=5.0, probe=lambda p: calls.append(p) or len(calls) >= 3))
        self.assertEqual(calls, [5760, 5760, 5760])


class DetachOrderTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.proc = FakeProcess()
        self.sitl, _ = make_sitl(self.proc); self.sitl.start()
        self.backend = FakeBackend()
        self.timeline = Timeline(self.client, self.sitl)

    def test_overrides_are_cleared_only_after_sitl_is_stopped(self):
        sl.detach(self.backend, self.client, self.sitl, {"servos_on": 0, "ap_state": 0}, 270.0, 4500.0)
        kinds = [e[0] if e[0] != "dref" else e[1] for e in self.timeline.events]
        stop_at = kinds.index("sitl")
        joy = kinds.index("sim/operation/override/override_joystick")
        thr = kinds.index("sim/operation/override/override_throttles")
        self.assertLess(stop_at, joy); self.assertLess(stop_at, thr)
        self.assertEqual(self.backend.released, 1)
        self.assertIn(("sim/operation/override/override_joystick", 0), self.client.writes)
        self.assertIn(("sim/operation/override/override_throttles", 0), self.client.writes)

    def test_gfc700_engaged_after_overrides_without_toggling_a_live_ap(self):
        r = sl.detach(self.backend, self.client, self.sitl, {"servos_on": 1, "ap_state": 2}, 270.0, 4520.0)
        self.assertEqual(r["gfc700_commands"], ["sim/GPS/g1000n1_alt"])
        self.assertIn(("sim/cockpit2/autopilot/altitude_dial_ft", 4500.0), self.client.writes)
        self.assertIn(("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot", 270.0), self.client.writes)
        last_override = max(i for i, e in enumerate(self.timeline.events) if e[0] == "dref" and "override" in e[1])
        first_ap_cmd = min(i for i, e in enumerate(self.timeline.events) if e[0] == "cmd")
        self.assertLess(last_override, first_ap_cmd)

    def test_gfc700_ap_pressed_only_when_servos_off(self):
        r = sl.detach(self.backend, self.client, self.sitl, {"servos_on": 0, "ap_state": 0}, 10.0, 3000.0)
        self.assertEqual(r["gfc700_commands"], ["sim/GPS/g1000n1_ap", "sim/GPS/g1000n1_hdg", "sim/GPS/g1000n1_alt"])

    def test_detach_without_sitl_still_clears_and_parks(self):
        r = sl.detach(self.backend, self.client, None, {"servos_on": 0, "ap_state": 0}, 90.0, 4000.0)
        self.assertTrue(r["sitl_stopped"])
        self.assertIn(("sim/operation/override/override_joystick", 0), self.client.writes)


if __name__ == "__main__":
    unittest.main()
```

If any of these fail because of a detail in the module as you wrote it (for
example the `Timeline` capture of `sitl.stop`), fix the test harness, not the
detach *order* — the order is the requirement.

## Step 4 — `scripts/fly_arduplane_backend.py`

Current behaviour: connects to an already-running SITL, flies through the gate,
and on exit calls `gate.takeover()` (→ `backend.release()`), then closes. Change it
so the launcher owns SITL and detaches safely. Keep `--dry-run` working.

1. New arguments (with defaults):
   ```
   --sitl-bin   ~/.cache/capvsar/ardupilot/build/sitl/bin/arduplane
   --sitl-cwd   ~/.cache/capvsar/arduplane-run        (contains xplane_plane.json)
   --parm       <repo>/xplane/ardupilot/cap487.parm
   --no-sitl    attach to a SITL something else started (old behaviour); the launcher then does not stop it
   ```
   `--mavlink` stays.
2. After the X-Plane client is created and **before** the MAVLink link:
   ```python
   sitl = None
   if not args.no_sitl:
       sitl = SitlProcess(args.sitl_bin, args.sitl_cwd, args.parm,
                          Path(args.sitl_cwd) / "arduplane.log", mavlink_port=port)
       print("starting ArduPlane SITL: %s --model xplane --defaults %s" % (args.sitl_bin, args.parm))
       sitl.start()
       if not sitl.wait_for_mavlink(timeout=20.0):
           print("SITL did not open MAVLink on %d; see %s" % (port, sitl.log_path)); sitl.stop(); client.stop(); return 1
   ```
3. Readiness wait, replacing the current "wait for telemetry and heartbeat" loop: require
   all of, within 20 s: X-Plane telemetry age < 2 s, heartbeat age < 2 s,
   `GLOBAL_POSITION_INT` age < 1 s, **and at least 2.5 s since the first heartbeat was seen**
   (comment: `# SITL decodes gyros with the X-Plane 11 convention until its 1 Hz version query is answered; give it a full period`).
4. Refusals after the pre-flight block (keep the existing envelope and altitude-agreement
   refusals) — add: if `report["armed"]` is False → print
   `"Refusing to start: ArduPlane reports disarmed (ARMING_REQUIRE 0 not loaded?)"`, detach, exit 5.
   Every refusal path and the `finally` block must go through **one** cleanup function
   (below) so SITL never outlives the launcher.
5. **Replace the `finally` block** with a single cleanup:
   ```python
   def cleanup(reason):
       state = {"servos_on": last["servos_on"], "ap_state": last["ap_state"]}
       observation = backend.observe()
       try:
           gate.takeover()                      # revokes the lease; calls backend.release()
           released_via_gate = True
       except Exception:
           released_via_gate = False
       result = detach(backend, client, sitl, state, observation.heading_mag,
                       observation.altitude_indicated_ft,
                       release=(lambda: None) if released_via_gate else None)
       ...write the "end" trace record with reason, result, and readback_after_release()...
       link.close(); client.stop(); release the flock
       print("released: ArduPlane parked in %s, SITL %s, overrides cleared, GFC 700 %s"
             % (result["hand_back_mode"], "stopped" if result["sitl_stopped"] else "left running",
                "+".join(c.split("_")[-1].upper() for c in result["gfc700_commands"]) or "already engaged"))
   ```
   where `last` is a dict fed by two extra client subscriptions made right after the
   backend is built: `sim/cockpit2/autopilot/servos_on` → `last["servos_on"]` and
   `sim/cockpit/autopilot/autopilot_state` → `last["ap_state"]` (initialise both to 0).
   `detach` is imported from `services.ai_pilot.sitl_lifecycle`. If `gate.takeover()`
   already released, pass a no-op `release` so the backend is not released twice
   (it is idempotent, but the trace should show one release).
6. In `--dry-run`: build `sitl = None`, and after printing the pre-flight block call
   `detach(backend, client, None, {"servos_on": 1, "ap_state": 2}, 274.0, 4500.0)` and
   print its result, so the dry run exercises the detach path with mocks. Assert in the
   dry-run branch that `link.sent_messages` contains no `DO_SET_MODE` to MANUAL.
7. Update the module docstring: replace "Moving the yoke releases control (ArduPlane goes
   to MANUAL, which is RC passthrough)" with "Moving the yoke releases control (ArduPlane
   parks in LOITER, or FBWA when the stick was proven at engagement); on exit the
   launcher stops SITL, clears X-Plane's overrides and hands the aircraft to the GFC 700."

Verify: `python3 scripts/fly_arduplane_backend.py --dry-run` exits 0 and prints the
detach result. Do **not** run it without `--dry-run`.

## Step 5 — docs

1. `services/ai_pilot/README.md`, section "ArduPlane backend (offline, not flown)",
   sub-section "Yoke authority": change the `release()` bullet to:
   `release()` clears the heading hold and parks ArduPlane in **LOITER** (or **FBWA** when
   a valid, centred RC position was measured at engagement); it never uses MANUAL, never
   pauses and never touches X-Plane controls, trim or the override. Add a bullet: the
   launcher owns the SITL process; on exit it parks, stops SITL, clears both overrides,
   then engages the GFC 700 in HDG+ALT — in that order, because SITL re-asserts the
   overrides every frame while it lives.
2. `docs/ARDUPLANE_TRIAL.md`: in the "Changes required before Leg 3 (AI-21)" list, mark
   items 1–4 done with the date; in the cases table change T3's "MANUAL" wording to
   "LOITER / FBWA"; add case **T0**: "attach with X-Plane paused — record whether SITL
   receives DATA and heartbeats while paused" (unflown).
3. `docs/bugs/tracker.json`: set the `AI-21` entry's `"status"` to `"fixed"` and put a
   one-paragraph summary of what changed into its `"fix"` field (files, the LOITER/FBWA
   rule, the detach order, test counts). Then run `python3 scripts/render_bug_tracker.py`.
   Edit the JSON with Python and write it back with
   `json.dumps(d, indent=2, ensure_ascii=False) + "\n"` — that is the file's existing
   formatting; anything else produces a 4,000-line diff.
4. `CHANGELOG.md`: read the first 10 lines first (other agents insert at the head), then
   add a dated entry at the head: what changed and why, test counts, "not flown".

## Definition of done

- `python3 -m unittest discover -s services/ai_pilot/tests -t . 2>&1 | tail -3` shows
  only the pre-existing `test_maneuvers` import error.
- `git diff --stat` touches only: `services/ai_pilot/{arduplane_backend.py,mavlink_min.py,sitl_lifecycle.py,README.md}`,
  `services/ai_pilot/tests/{test_arduplane_backend.py,test_mavlink_min.py,test_sitl_lifecycle.py}`,
  `scripts/fly_arduplane_backend.py`, `docs/ARDUPLANE_TRIAL.md`, `docs/bugs/tracker.json`,
  `docs/BUG_TRACKER.md`, `CHANGELOG.md`. Nothing else.
- `grep -n "PLANE_MODE_MANUAL" services/ai_pilot/arduplane_backend.py` returns nothing.
- `python3 scripts/fly_arduplane_backend.py --dry-run` exits 0.
- Changes left uncommitted, with a one-paragraph report of what was done and the test counts.
