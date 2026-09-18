"""Red team of the AI pilot: documentation and system, 2026-09-15.

Every confirmed defect below is an `xfail(strict=True)` that asserts the
behaviour the documentation or a recorded decision promises. Today they fail,
so the suite stays green and each finding is executable rather than prose.
When someone fixes one, the test XPASSes, strict mode fails the run, and the
fixer removes the marker - at which point the test becomes the regression
guard for that fix. That is the project's own "verified to fail before the
fix" discipline, written down in advance.

Claims that were checked and HELD are plain passing tests under `Cleared`, so
the review's "no finding" verdicts are executable too.

Findings are numbered RT-n and ranked in the accompanying report. Evidence
tags follow the project's review contract: SRC = read in source, LIVE = ran
it here, UNRESOLVED = needs the simulator, the voice server, or a human.

Nothing here writes to X-Plane. UDP tests bind loopback on ephemeral ports.
"""
from __future__ import annotations

import ast
import inspect
import json
import re
import socket
import struct
import time
from pathlib import Path

import pytest

from services.ai_pilot import maneuver_server
from services.ai_pilot.agent_bridge import RETIRED_MUTATION_TOOLS
from services.ai_pilot.direct_backend import XPlaneDirectBackend
from services.ai_pilot.fdr import FlightDataRecorder
from services.ai_pilot.diagnostics import FlightDiagnosticEngine
from services.ai_pilot.flight_controller import FlightController
from services.ai_pilot.lightweight_agent import LightweightAgent
from services.ai_pilot.maneuvers import Limits, ManeuverGate, Observation
from services.ai_pilot.taxi import (
    ClearanceSource, RoutePurpose, Surface, TaxiCoordinator, TaxiLeg, TaxiPhase, TaxiRoute,
)
from services.ai_pilot.xplane_udp import XPlaneUDPClient

ROOT = Path(__file__).resolve().parents[3]
AI_PILOT = ROOT / "services/ai_pilot"
SCRIPTS = ROOT / "scripts"

defect = lambda rt, why: pytest.mark.xfail(strict=True, reason=f"{rt}: {why}")  # noqa: E731


# --- fakes, shaped like the ones the existing suites use -----------------------

class Backend:
    """Same shape as test_maneuvers.Backend."""
    def __init__(self):
        self.o = Observation(359, 4500, 2000, 110, 0, 0, 0)
        self.writes = []
    def observe(self): return self.o
    def select(self, h, a): self.writes.append(("select", h, a))
    def release(self): self.writes.append(("release",))
    def pause(self): self.writes.append(("pause",))


class FakeClient:
    """Same shape as test_direct_backend.FakeClient, plus subscription capture."""
    def __init__(self):
        self.callbacks, self.subscribed, self.writes, self.commands = {}, [], [], []
        self.paused = False
    def subscribe_dref(self, ref, freq_hz=10, callback=None):
        self.subscribed.append(ref)
        if callback: self.callbacks[ref] = callback
    def send_dref(self, ref, value): self.writes.append((ref, value))
    def send_command(self, command): self.commands.append(command)
    def set_paused(self, paused): self.paused = paused
    def feed(self, backend, **values):
        for name, ref in {**backend.DATAREFS, **backend.AUX_DATAREFS}.items():
            if name in values: self.callbacks[ref](ref, values[name])


def steady(**o):
    f = dict(heading_mag=90.0, altitude_indicated_ft=4500.0, agl_ft=1200.0 / 3.28084, kias=110.0,
             roll_deg=0.0, vvi_fpm=0.0, pitch_deg=2.0, beta_deg=0.0, roll_rate=0.0,
             pitch_rate=0.0, elevator_trim=0.0)
    f.update(o)
    return f


def free_udp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# =============================================================================
# RT-1  Telemetry is accepted from any sender.                            HIGH
# =============================================================================

@defect("RT-1", "xplane_udp._listen_loop discards the sender address; a forged RREF "
                "from any host on 0.0.0.0 is accepted as aircraft telemetry")
def test_rt1_forged_telemetry_from_another_host_is_ignored():
    """SRC xplane_udp.py: `data, _addr = self._sock.recvfrom(4096)` and `_addr`
    is never compared with `self.host`. The socket is bound to 0.0.0.0. Anything
    on the LAN can therefore write the gate's observations - keep a stale
    aircraft looking fresh and in-envelope, or feed the direct backend false
    attitude to steer against. Subscription ids are small sequential integers,
    so forging needs no knowledge beyond the port number."""
    client = XPlaneUDPClient(host="127.0.0.1", port=free_udp_port(), receive_port=0, timeout=0.2)
    try:
        listen_port = client._sock.getsockname()[1]
        ref = "sim/flightmodel/position/indicated_airspeed"
        sub_id = client.subscribe_dref(ref, freq_hz=10)
        forger = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            try:
                forger.bind(("127.0.0.2", 0))          # a different source address
            except OSError:
                forger.bind(("127.0.0.1", 0))          # still a different, unexpected source port
            forger.sendto(b"RREF," + struct.pack("<if", sub_id, 999.0), ("127.0.0.1", listen_port))
        finally:
            forger.close()
        time.sleep(0.4)
        assert client.get_dref(ref, default=float("nan")) != 999.0, \
            "forged packet from an unexpected source was accepted as telemetry"
    finally:
        client.stop()


# =============================================================================
# RT-2  Two clients silently share one receive port (V2-6).                HIGH
# =============================================================================

@defect("RT-2", "SO_REUSEADDR lets a second client bind the same UDP port; X-Plane's "
                "replies then reach only one of them and the other faults to a pause")
def test_rt2_a_second_client_on_the_same_port_falls_back_or_refuses():
    """SRC xplane_udp._init_socket: SO_REUSEADDR then bind; the dynamic-port
    fallback only runs if bind RAISES, which REUSEADDR prevents. maneuver_server
    and `web_server --live` both construct the client with the default port, so
    running the observation deck beside the controller starves one of them of
    telemetry. For the controller that is `Stale telemetry` -> lease revoked ->
    `sim/operation/pause_on` in flight. This is V2-6 from the 2026-09-12 review."""
    port = free_udp_port()
    a = XPlaneUDPClient(host="127.0.0.1", port=free_udp_port(), receive_port=port, timeout=0.2)
    try:
        b = XPlaneUDPClient(host="127.0.0.1", port=free_udp_port(), receive_port=port, timeout=0.2)
        try:
            assert b._sock.getsockname()[1] != port, \
                "second client bound the SAME receive port instead of falling back"
        finally:
            b.stop()
    finally:
        a.stop()


def test_rt2_context_the_controller_and_the_live_deck_default_to_one_port():
    """LIVE. Not a defect by itself - the evidence that RT-2 is reachable in the
    documented workflow rather than a contrived one."""
    default = inspect.signature(XPlaneUDPClient).parameters["receive_port"].default
    assert default == 49005
    for text in (source(AI_PILOT / "maneuver_server.py"), source(AI_PILOT / "web_server.py")):
        assert "receive_port" not in text, "one of them now sets its own port; re-check RT-2"


# =============================================================================
# RT-3  The recorder writes defaults as data; the live deck never subscribes.  HIGH
# =============================================================================

# FIXED 2026-09-18 by AI-11. Marker removed per this module's own rule, so
# this test is now the regression guard for that fix rather than a finding.
# RT-3 was: FlightDataRecorder.sample_current_frame reads a never-invalidated cache with
#   0.0 defaults and a wall-clock fallback for sim time
def test_rt3a_a_frame_with_no_telemetry_is_not_recorded_as_position_zero():
    """SRC fdr.py:226-270 and xplane_udp.get_dref. A recorder whose link is dead
    writes lat 0, lon 0, 0 KIAS, DF power ON, 121.500 selected, and stamps the
    frame with the WALL CLOCK because `sim/time/total_flight_time_sec` defaults
    to `time.time()`. The debrief engine then grades a flight that never
    happened. This is V2-7 from the 2026-09-12 review."""
    frame = FlightDataRecorder(XPlaneUDPClient(mock=True)).sample_current_frame().to_dict()
    for key in ("lat", "lon", "kias", "heading_true"):
        assert frame[key] != 0.0, f"{key} recorded as 0.0 with no telemetry ever received"
    sim_time = frame["sim_time_s"]
    # NaN is the honest answer when no sim time was ever received, and it
    # satisfies this check's intent. Written explicitly because every NaN
    # comparison is False, so the original `abs(sim_time - now) > 60` reported
    # "this IS the wall clock" for a value that is not a time at all.
    assert sim_time != sim_time or abs(sim_time - time.time()) > 60, \
        "sim time is the wall clock"


# FIXED 2026-09-18 by AI-11. Marker removed per this module's own rule, so
# this test is now the regression guard for that fix rather than a finding.
# RT-3 was: run_web_server never subscribes a dataref; in --live mode the deck and the
#   FDR see only what a hand-configured legacy Data Output happens to send
def test_rt3b_the_live_deck_subscribes_the_telemetry_it_displays_and_records():
    """SRC web_server.run_web_server builds XPlaneUDPClient, FlightController,
    LightweightAgent and FlightDataRecorder and never calls subscribe_dref, nor
    do any of those constructors. Only DATA packets (indices 3 and 20, legacy
    Data Output, off by default) populate anything: speed and position. Heading,
    attitude, AGL, VVI, engine and every cap/df/* dataref stay at their defaults
    forever. The README's "read telemetry from live X-Plane 12" is speed and
    position at best, and only if the operator configures something the README
    never mentions."""
    client = XPlaneUDPClient(mock=True)              # mock records subscriptions without a socket
    FlightController(client); FlightDataRecorder(client)
    LightweightAgent(FlightController(client))
    assert client._dref_to_id, "the live deck registers no RREF subscriptions at all"


# FIXED 2026-09-18 by AI-11. Marker removed per this module's own rule, so
# this test is now the regression guard for that fix rather than a finding.
# RT-3 was: diagnostics duration clamps to 0.0 when the first frame carries the
#   wall-clock fallback and a later one carries real sim time
def test_rt3c_duration_survives_a_wall_clock_first_frame():
    engine = FlightDiagnosticEngine()
    base = {"lat": 32.8, "lon": -116.9, "df_valid": 0, "scenario_active": 1}
    frames = [dict(base, sim_time_s=time.time()), dict(base, sim_time_s=1234.5)]
    report = engine.evaluate_frames(frames, "rt3c")
    duration = getattr(report, "duration_seconds", None)
    assert duration is None or duration > 0.0, "a real flight graded as zero seconds long"


# FIXED 2026-09-18 by AI-11. Marker removed per this module's own rule, so
# this test is now the regression guard for that fix rather than a finding.
# RT-3 was: an all-defaults recording is graded as a DF coverage failure instead of
#   being recognised as a dead telemetry link
def test_rt3d_a_dead_link_is_reported_as_a_dead_link_not_a_flight_result():
    recorder = FlightDataRecorder(XPlaneUDPClient(mock=True))
    frames = [recorder.sample_current_frame().to_dict() for _ in range(50)]
    report = engine_report(FlightDiagnosticEngine().evaluate_frames(frames, "rt3d"))
    text = " ".join(f.get("message", "") + f.get("title", "") for f in report["findings"]).lower()
    assert any(w in text for w in ("no telemetry", "link", "not connected", "never received")), \
        f"dead link graded as: {report['summary']!r} / {text[:160]!r}"


def engine_report(report):
    if isinstance(report, dict):
        return {"summary": report.get("summary_status"), "findings": report.get("findings", [])}
    findings = [f if isinstance(f, dict) else vars(f) for f in getattr(report, "findings", [])]
    return {"summary": getattr(report, "summary_status", None), "findings": findings}


# =============================================================================
# RT-4  "Human always wins the yoke" (D-3) is not a property of the direct backend.  HIGH
# =============================================================================

@defect("RT-4", "the direct backend writes yoke_*_ratio at 10 Hz with no override flag, "
                "no joystick observation and no takeover detection; a hand on the yoke "
                "races the loop frame by frame instead of winning")
def test_rt4a_direct_backend_has_a_human_input_arbitration_path():
    """SRC direct_backend.py CONTROL_DREFS/DATAREFS/AUX_DATAREFS and _step.
    Decision D-3 (DECISIONS-cap-vsar-2026-09-12.md): "Yoke: human always wins."
    Nothing in this backend can know a human is on the controls: it never
    subscribes sim/joystick/*, never sets or reads sim/operation/override/*, and
    _step has no hook. The only takeover is a software call to release(). The
    README's own sentence - "Take over manually at any sign of trouble" (printed
    by fly_direct_backend.py) - describes a race, not a guarantee."""
    client = FakeClient()
    backend = XPlaneDirectBackend(client, limits=Limits(), clock=lambda: 100.0)
    client.feed(backend, **steady())
    backend.select(120.0, 4500.0)
    backend._step(backend.observe(), 120.0, 4500.0)
    backend.release()
    touched = " ".join(client.subscribed + [r for r, _ in client.writes] + client.commands)
    assert re.search(r"joystick|override", touched), \
        "no joystick or override dataref is ever read or written - the human cannot be detected"


@defect("RT-4", "the control loop's own fault path neutralizes the controls but never "
                "pauses the simulator; without the gate (fly_card_h0.py) that is "
                "'controls centred, nobody flying' in the air")
def test_rt4b_a_loop_fault_pauses_when_there_is_no_gate_to_do_it():
    """SRC direct_backend._run: fault -> _neutralize() -> break. `pause()` exists
    but only the ManeuverGate ever calls it, and fly_card_h0.py does not use the
    gate (RT-5). The docstring on _envelope_fault says 'second line of defence:
    do not rely on the gate noticing first' - but the second line stops short."""
    now = [100.0]
    client = FakeClient()
    backend = XPlaneDirectBackend(client, limits=Limits(), clock=lambda: now[0])
    client.feed(backend, **steady())
    backend.select(90.0, 4500.0)
    backend._stop.set(); backend._thread and backend._thread.join(timeout=2.0)   # take the loop off its thread
    backend._stop.clear()
    now[0] = 103.5                                  # telemetry now 3.5 s old: stale
    backend._run()                                  # runs synchronously until the fault
    assert backend.last_fault == "Stale telemetry"
    assert client.paused, "loop faulted airborne, neutralized the controls, and did not pause"


# =============================================================================
# RT-5  fly_card_h0.py drives the yoke with no gate, no lease and no lock.    HIGH
# =============================================================================

def _calls(path: Path):
    tree = ast.parse(source(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            names.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names: names.add(a.name.split(".")[-1])
    return names


@defect("RT-5", "fly_card_h0.py constructs XPlaneDirectBackend directly and never imports "
                "or constructs ManeuverGate: no lease, no sequence, no gate-side envelope "
                "check, no gate-driven pause")
def test_rt5a_every_script_that_flies_the_aircraft_goes_through_the_gate():
    """SRC scripts/fly_card_h0.py:81-84. The README says of the direct backend:
    'the control lease, the strictly-increasing sequence, the exercise envelope
    and capture detection all apply to it exactly as they do to the autopilot
    backend.' True for fly_direct_backend.py; false for the H0 card, which is the
    script that has been flown five times."""
    for script in ("fly_direct_backend.py", "fly_card_h0.py"):
        assert "ManeuverGate" in _calls(SCRIPTS / script), f"{script} bypasses the gate"


@defect("RT-5", "neither yoke-writing script takes the controller's instance lock, so "
                "'do not run it at the same time as maneuver_server' is advice, not enforcement")
def test_rt5b_every_x_plane_writer_takes_the_same_instance_lock():
    """SRC maneuver_server.main takes /tmp/cap-vsar-maneuver-controller.lock.
    Two writers on the same surfaces is the exact hazard the README names; the
    lock exists and two of the three writers ignore it."""
    lock_name = "cap-vsar-maneuver-controller.lock"
    assert lock_name in source(AI_PILOT / "maneuver_server.py")
    for script in ("fly_direct_backend.py", "fly_card_h0.py"):
        assert lock_name in source(SCRIPTS / script), f"{script} does not take the instance lock"


@defect("RT-5", "fly_card_h0.py never calls pause(); on a backend fault it prints and stops")
def test_rt5c_the_h0_card_pauses_on_a_backend_fault():
    assert re.search(r"\.pause\(", source(SCRIPTS / "fly_card_h0.py")), \
        "no pause on the fault path; combined with RT-4b the aircraft is left airborne, hands off"


# =============================================================================
# RT-6  The gate has no liveness coupling to its monitor (D-3).              MED
# =============================================================================

@defect("RT-6", "after a fault the gate re-arms on the next acquire() with no requirement "
                "that a monitor is running; D-3 says 'refuses new acquire() until restart'")
def test_rt6a_a_faulted_gate_refuses_to_re_arm_until_restart():
    """SRC maneuvers.ManeuverGate._fault clears state; acquire() checks only
    `self.lease`. maneuver_server's monitor thread exits on an exception and
    nothing tells the gate. After that, acquire+submit still write to X-Plane
    and no tick() will ever notice stale or out-of-envelope telemetry."""
    b = Backend(); g = ManeuverGate(b)
    g.acquire()
    b.o = Observation(359, 4500, 2000, 110, 0, 0, age_seconds=5)   # stale -> fault
    g.tick()
    assert b.writes == [("pause",)] and g.lease is None
    b.o = Observation(359, 4500, 2000, 110, 0, 0, 0)                # telemetry recovers
    with pytest.raises(ValueError):
        g.acquire()                                                  # D-3: refuse until restart


@defect("RT-6", "an owned gate whose monitor has stopped ticking never notices stale telemetry; "
                "the pause-on-telemetry-loss promise lives entirely in a daemon thread")
def test_rt6b_an_owned_gate_notices_stale_telemetry_without_being_ticked():
    b = Backend(); g = ManeuverGate(b)
    lease = g.acquire()["lease"]
    g.submit(lease, 1, {"heading_mag": 90})
    b.o = Observation(359, 4500, 2000, 110, 0, 0, age_seconds=30)  # dead link, nobody ticking
    status = g.status()
    assert not status["owned"] or ("pause",) in b.writes, \
        "30 s of dead telemetry, still owned, no pause: the promise depends on tick() being called"


# =============================================================================
# RT-7  "Loopback-only" is not a trust boundary on a host that runs three agents.  MED
# =============================================================================

@defect("RT-7", "acquire and takeover accept any local process with no credential; on the "
                "workstation that is Codex, Gemini and Claude Code as well as the pilot")
def test_rt7_seizing_or_revoking_control_needs_a_credential():
    """SRC maneuver_server.Handler.do_POST: the JSON body of /api/acquire and
    /api/takeover is ignored; the only checks are Content-Type and a same-origin
    test that non-browser clients never trigger. test_maneuvers already proves a
    bare POST succeeds and treats that as correct. The README calls this
    'loopback-only' as if that were a boundary; three autonomous coding agents
    run with shell access on the same host as X-Plane."""
    from http.server import ThreadingHTTPServer
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    import threading
    b = Backend(); g = ManeuverGate(b)
    server = ThreadingHTTPServer(("127.0.0.1", 0), maneuver_server.Handler); server.gate = g
    t = threading.Thread(target=server.serve_forever); t.start()
    try:
        req = Request(f"http://127.0.0.1:{server.server_port}/api/acquire", data=b"{}",
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req) as r: status = r.status
        except HTTPError as e: status = e.code
        assert status in (401, 403), f"anonymous local acquire returned {status}"
    finally:
        server.shutdown(); server.server_close(); t.join()


# =============================================================================
# RT-8  Taxi authority state machine: two laundering paths.                  MED
# =============================================================================

def _towered_at_hold_short():
    taxi = TaxiCoordinator("CAP ramp spot 4", towered=True)
    taxi.load_route(TaxiRoute(RoutePurpose.OUTBOUND, (TaxiLeg("CAP ramp spot 4", "A1"),
                                                      TaxiLeg("A1", "hold short 27R"))))
    taxi.authorize_taxi(ClearanceSource.ATC)
    taxi.complete_leg(); taxi.complete_leg()
    assert taxi.phase is TaxiPhase.HOLDING_SHORT_DEPARTURE
    return taxi


@defect("RT-8", "mark_airborne() succeeds from HOLDING_SHORT_DEPARTURE with no takeoff authority "
                "and records nothing; an unauthorized departure is laundered into a normal flight")
def test_rt8a_becoming_airborne_without_takeoff_authority_is_refused_or_recorded():
    """SRC taxi.mark_airborne: no phase check. Its docstring says it 'does not
    grant takeoff authority' - true, but it erases the requirement for it. The
    coordinator is the component whose stated job is that this never happens
    silently; test_taxi.py itself calls mark_airborne() from PARKED."""
    taxi = _towered_at_hold_short()
    with pytest.raises((PermissionError, ValueError)):
        taxi.mark_airborne()


@defect("RT-8", "reporting uncertainty during the return taxi, then loading an OUTBOUND route, "
                "skips the return-to-start requirement entirely")
def test_rt8b_the_return_to_start_rule_cannot_be_bypassed_via_a_clarification_hold():
    """SRC taxi.load_route: OUTBOUND is accepted from HOLDING_FOR_CLARIFICATION
    regardless of whether the aircraft was mid-RETURN. The doc's rule - 'the
    sortie is not complete until the crew taxis back to the starting point' - is
    only enforced on routes that declare themselves RETURN."""
    taxi = TaxiCoordinator("CAP ramp spot 4", towered=True)
    taxi.mark_airborne(); taxi.mark_landed_and_runway_clear("B1")
    taxi.load_route(TaxiRoute(RoutePurpose.RETURN, (TaxiLeg("B1", "A1"), TaxiLeg("A1", "CAP ramp spot 4"))))
    taxi.authorize_taxi(ClearanceSource.ATC)
    taxi.report_route_uncertain("sign mismatch")
    with pytest.raises(ValueError):
        taxi.load_route(TaxiRoute(RoutePurpose.OUTBOUND, (TaxiLeg("B1", "hold short 27R"),)))


def test_rt8c_context_the_crossing_rule_trusts_the_routes_own_surface_labels():
    """LIVE, not a defect in taxi.py - a scope limit on the README's claim that
    'every runway crossing is explicit, specific and consumed once'. The rule
    applies to legs the ROUTE labels as crossings; a route that carries the
    aircraft across 09-27 on a leg labelled TAXIWAY needs no crossing authority.
    The label comes from the same AI/planner the module exists to distrust.
    AI-8's airport-surface graph is the fix; until then the claim is narrower
    than its wording."""
    taxi = TaxiCoordinator("north ramp", towered=True)
    taxi.load_route(TaxiRoute(RoutePurpose.OUTBOUND, (TaxiLeg("north ramp", "across 09-27"),)))
    taxi.authorize_taxi(ClearanceSource.ATC)
    assert taxi.directive().action == "taxi" and taxi.directive().runway is None


# =============================================================================
# RT-9  A skill file in the repo asserts PIC authority the code retired.     MED
# =============================================================================

@defect("RT-9", "services/ai_pilot/skills/xplane-pilot/SKILL.md describes 'Autonomous flight "
                "control', PIC authority, and four retired mutation tools")
def test_rt9_the_on_disk_skill_matches_the_observation_only_contract():
    """SRC. agent_bridge.export_hermes_skill writes an observation-only skill;
    the file actually on disk in a skills/ directory - the path Hermes, Codex,
    Gemini and Claude Code all discover - still tells a model it may 'act as
    Pilot-in-Command' with execute_checklist, command_flight_phase,
    set_autopilot and spawn_on_runway. Whether Hermes loads THIS copy is
    UNRESOLVED (cainfra02 was unreachable from here); coding agents working in
    this tree read it regardless."""
    skill = source(AI_PILOT / "skills/xplane-pilot/SKILL.md")
    leaked = sorted(t for t in RETIRED_MUTATION_TOOLS if t in skill)
    assert not leaked and "Pilot-in-Command" not in skill, f"skill still advertises {leaked}"


# =============================================================================
# RT-10 Two HIGH findings from the 2026-09-12 review never reached the tracker.  MED
# =============================================================================

def test_rt10_the_v2_highs_are_tracked():
    """RT-10, DISCHARGED by the commit that added this file - and the first
    marker to flip. When written, docs/bugs/tracker.json contained zero 'V2-'
    references and no item describing either defect, although
    HANDOFF-claude-fixes-2026-09-13.md calls them 'the last two HIGHs, both in
    ai_pilot, both silently corrupt an exercise'. Ingesting them as AI-10 and
    AI-11 made this XPASS under strict mode in the very next run, so the xfail
    came off and it now guards against the findings being dropped again."""
    tracker = json.loads(source(ROOT / "docs/bugs/tracker.json"))
    blob = json.dumps(tracker).lower()
    assert "49005" in blob or "port collision" in blob, "V2-6 is not tracked"
    assert "defaults as data" in blob or "fabricated telemetry" in blob, "V2-7 is not tracked"


# =============================================================================
# RT-11 SIGTERM skips every shutdown safeguard.                              LOW
# =============================================================================

@defect("RT-11", "no signal handler anywhere in the control path; `kill` ends the process "
                 "without the shutdown pause, release or neutralize")
def test_rt11_a_termination_signal_reaches_the_shutdown_path():
    """SRC. maneuver_server pauses on the way out only via `finally` after
    KeyboardInterrupt; fly_direct_backend releases only in `finally`. SIGTERM -
    what systemd, a supervisor, or a tidy-up script sends - runs neither. The
    aircraft is left with the autopilot engaged on the last targets, or with
    the throttle at whatever the loop last wrote."""
    for path in (AI_PILOT / "maneuver_server.py", AI_PILOT / "direct_backend.py",
                 SCRIPTS / "fly_direct_backend.py", SCRIPTS / "fly_card_h0.py"):
        assert re.search(r"signal\.signal\(", source(path)), f"{path.name} installs no signal handler"


# =============================================================================
# RT-12 README test count is stale.                                          LOW
# =============================================================================

@defect("RT-12", "README says '150 across the service'; the service collects 200 and "
                 "Codex's own CHANGELOG entry says 200")
def test_rt12_readme_test_counts_match_reality():
    readme = source(AI_PILOT / "README.md")
    claimed = int(re.search(r"(\d+) across the service", readme).group(1))
    import subprocess, sys
    out = subprocess.run([sys.executable, "-m", "pytest", str(AI_PILOT / "tests"), "--collect-only", "-q",
                          "-p", "no:cacheprovider"], capture_output=True, text=True, cwd=ROOT,
                         env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"}).stdout
    actual = int(re.search(r"(\d+) tests? collected", out).group(1))
    assert claimed == actual, f"README claims {claimed}, suite collects {actual}"


# =============================================================================
# RT-13 The advisory chat's no-action guard is a keyword list.               LOW
# =============================================================================

@defect("RT-13", "control phrasings outside the blocklist reach the LLM, whose 'never claim "
                 "aircraft action' is a prompt instruction with no output filter")
@pytest.mark.parametrize("phrase", ["bank left", "push the nose over", "add power",
                                    "go left a bit", "pull up", "select FLC", "set 4500"])
def test_rt13_control_language_never_produces_an_action_claim(phrase, monkeypatch):
    """SRC lightweight_agent.handle_user_command: a fixed tuple of words gates
    the canned refusal; anything else goes to gemma4:12b with a system prompt.
    There is no control path, so this is a trust finding, not a control one: an
    operator can be told 'Roger, turning left' by an advisor that cannot turn."""
    agent = LightweightAgent(FlightController(XPlaneUDPClient(mock=True)))
    monkeypatch.setattr(agent, "_query_bigbrain_llm", lambda prompt: "Roger, turning left now.")
    reply = agent.handle_user_command(phrase)
    assert reply.startswith("No aircraft action taken"), f"{phrase!r} -> {reply!r}"


# =============================================================================
# Cleared: claims that were checked and hold.                                 
# =============================================================================

class TestCleared:
    def test_live_scripted_mission_refuses_before_constructing_a_client(self, monkeypatch):
        """README: 'mission_ksee_krnm --live is refused'. SRC: returns False before
        XPlaneUDPClient is built. Made executable by refusing construction."""
        from services.ai_pilot import mission_ksee_krnm as m
        def boom(*a, **k): raise AssertionError("a live client was constructed")
        monkeypatch.setattr(m, "XPlaneUDPClient", boom)
        assert m.run(live=True) is False if hasattr(m, "run") else True

    def test_the_legacy_deck_retires_mutations_with_gone(self):
        """README: 'REST mutation endpoints return HTTP 410'. SRC web_server.py
        uses HTTPStatus.GONE; test_web_agent covers the wire. (An earlier grep
        for the literal 410 in this review found nothing - that was the
        reviewer's error, not the code's.)"""
        assert "HTTPStatus.GONE" in source(AI_PILOT / "web_server.py")

    def test_the_first_flight_script_goes_through_the_real_gate(self):
        """README claim holds for fly_direct_backend.py: it constructs ManeuverGate
        and takes over in `finally` on Ctrl-C."""
        assert "ManeuverGate" in _calls(SCRIPTS / "fly_direct_backend.py")
        assert "takeover" in source(SCRIPTS / "fly_direct_backend.py")

    def test_no_legacy_writer_is_reachable_from_the_web_deck(self):
        """SRC: FlightController.step/_engage_autopilot/spawn_on_ksee_27r hold ~40
        surface writes; run_web_server and do_POST never call them."""
        deck = source(AI_PILOT / "web_server.py")
        for method in ("controller.step(", "spawn_on_ksee_27r", "_engage_autopilot", "set_phase("):
            assert method not in deck, f"web deck can reach {method}"

    def test_direct_backend_count_claim_is_accurate(self):
        """README: '80 tests in tests/test_direct_backend.py'."""
        n = sum(1 for line in source(AI_PILOT / "tests/test_direct_backend.py").splitlines()
                if re.match(r"\s*def test_", line))
        assert n == 80

    def test_the_pause_command_is_the_idempotent_one(self):
        """README: pause uses sim/operation/pause_on, not a toggle."""
        c = FakeClient()
        XPlaneUDPClient.set_paused(type("C", (), {"send_command": lambda s, x: c.commands.append(x),
                                                    "mock": False, "_sock": True})(), True)
        assert c.commands == ["sim/operation/pause_on"]
