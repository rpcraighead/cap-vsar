"""DF plugin review items P2-1, P2-3..P2-8, improvements 1/5/8 and Q3.

Pytest-style companions to the import-time tests/test_engine.py script: one
file per concern would be tidier, but they share the fake sim, so they share a
file. Each test names the item it pins and fails on the pre-fix plugin.
"""
import importlib.util
import math
import os
import ssl
import sys
import tempfile
import threading
import urllib.error

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import xp  # noqa: E402  (the stub)

PLUGIN = os.path.join(ROOT, "xplane", "PI_capvsar_df.py")
spec = importlib.util.spec_from_file_location("PI_capvsar_df_waveb", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Clock:
    """Separate wall and monotonic readings, so a test can step one alone."""

    def __init__(self):
        self.mono = 5_000.0
        self.wall = 1_700_000_000.0

    def time(self):
        return self.wall

    def monotonic(self):
        return self.mono

    def advance(self, dt):
        self.mono += dt
        self.wall += dt


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(mod, "time", c)
    xp.REFS.clear()
    xp.LOG.clear()
    xp.TERRAIN_FT = 0.0
    xp.TERRAIN_FN = None
    xp.SIM["paused"] = 0
    yield c
    xp.TERRAIN_FT = 0.0
    xp.TERRAIN_FN = None
    xp.SIM["paused"] = 0


def beacon_engine(clock, lat=39.0, lon=-105.0, elev=9000.0, band=406.0,
                  north_nm=5.0, alt_ft=12000.0, effects=None):
    e = mod.PythonInterface()
    e.XPluginStart()
    e.scn.update({"active": 1, "lat": lat, "lon": lon, "elev_ft": elev,
                  "band": band, "beacon_freq_hz": None, "power": 1.0,
                  "cs": {}, "effects": effects if effects is not None else {}})
    xp.SIM.update({"lat": lat + north_nm / 60.0, "lon": lon,
                   "elev_m": alt_ft / 3.28084, "psi": 180.0,
                   "phi": 0.0, "theta": 0.0})
    return e


def tick(e, clock, n=1, burst=True):
    for _ in range(n):
        clock.advance(mod.LOOP_S)
        if burst:
            e.started = clock.mono          # the beacon is radiating
        e.compute()


# ----------------------------------------------------------------- P2-1
class SlowConsole:
    """A urlopen that blocks until released, like a console that takes 4 s."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, req, timeout=None):
        self.entered.set()
        self.release.wait(10.0)
        raise urllib.error.URLError("slow console gave up")


def test_p2_1_disable_enable_does_not_leak_a_worker(monkeypatch, clock):
    slow = SlowConsole()
    monkeypatch.setattr(mod.urllib.request, "urlopen", slow)
    plugin = mod.PythonInterface()
    plugin.XPluginStart()
    new = None
    try:
        plugin.XPluginEnable()
        assert slow.entered.wait(5.0), "worker never reached urlopen"
        old = plugin.net
        plugin.XPluginDisable()              # join(1.0) times out: still in urlopen
        assert old.is_alive(), "setup: the worker must still be inside urlopen"
        plugin.XPluginEnable()               # rebinds plugin.stop to a clear Event
        new = plugin.net
        slow.release.set()                   # the old worker's urlopen returns
        old.join(5.0)
        assert not old.is_alive(), (
            "the old worker kept running against the new stop Event (P2-1)")
    finally:
        slow.release.set()
        plugin.XPluginDisable()
        if new is not None:
            new.join(5.0)


# ----------------------------------------------------------------- P2-8
def test_p2_8_disable_after_a_failed_enable_does_not_raise(clock):
    plugin = mod.PythonInterface()
    assert plugin.net is None
    plugin.XPluginDisable()                  # never enabled


# ----------------------------------------------------------------- P2-3
def test_p2_3_default_console_is_the_front_door():
    console, _, _ = mod._load_station_config("/nonexistent/capvsar_station.ini")
    assert console == "https://192.0.2.151"
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    try:
        import build_station_kit
    finally:
        sys.path.pop(0)
    assert console == build_station_kit.DEFAULT_CONSOLE


def fetching_engine():
    e = mod.PythonInterface()
    return e


def test_p2_3_first_failure_and_recovery_are_each_logged_once(monkeypatch, clock):
    e = fetching_engine()
    state = {"fail": True}

    class Ok:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, *a):
            return b'{"sortie": null, "scenario": null}'

    def urlopen(req, timeout=None):
        if state["fail"]:
            raise urllib.error.URLError(ConnectionRefusedError("refused"))
        return Ok()

    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
    for _ in range(5):
        assert e.poll_scenario_once() is False        # transport failure
    e.drain_log()
    down = [m for m in xp.LOG if "unreachable" in m]
    assert len(down) == 1, xp.LOG
    state["fail"] = False
    e.poll_scenario_once()
    e.poll_scenario_once()
    e.drain_log()
    assert sum("truth channel open" in m for m in xp.LOG) == 1, xp.LOG
    state["fail"] = True
    e.poll_scenario_once()
    e.drain_log()
    assert sum("unreachable" in m for m in xp.LOG) == 2, "a new outage is a new first failure"


def test_p2_3_ssl_error_class_is_logged_once(monkeypatch, clock):
    e = fetching_engine()

    def urlopen(req, timeout=None):
        raise urllib.error.URLError(ssl.SSLCertVerificationError(
            1, "certificate verify failed: unable to get local issuer certificate"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
    for _ in range(4):
        e.poll_scenario_once()
    e.drain_log()
    tls = [m for m in xp.LOG if "SSLCertVerificationError" in m]
    assert len(tls) == 1, xp.LOG
    assert "ssl.get_default_verify_paths" in tls[0]


def test_p2_3_a_down_console_keeps_the_last_scenario(monkeypatch, clock):
    e = fetching_engine()
    before = e.scn
    monkeypatch.setattr(mod.urllib.request, "urlopen",
                        lambda req, timeout=None: (_ for _ in ()).throw(
                            urllib.error.URLError("down")))
    e.poll_scenario_once()
    assert e.scn is before


# ----------------------------------------------------------------- Q3
def _ini(text):
    d = tempfile.mkdtemp()
    path = os.path.join(d, "capvsar_station.ini")
    with open(path, "w") as f:
        f.write(text)
    return path


def test_q3_plain_http_to_a_lan_console_warns_once(clock):
    del mod.STARTUP_WARNINGS[:]
    path = _ini("[station]\nconsole = http://10.0.0.5:8700\n")
    mod._load_station_config(path)
    mod._load_station_config(path)
    assert len(mod.STARTUP_WARNINGS) == 1
    assert "plain http" in mod.STARTUP_WARNINGS[0]
    e = mod.PythonInterface()
    e.XPluginStart()
    e.drain_log()
    assert any("plain http" in m for m in xp.LOG)
    del mod.STARTUP_WARNINGS[:]


@pytest.mark.parametrize("console", ["http://127.0.0.1:8700", "http://localhost:8700",
                                     "http://[::1]:8700", "https://10.0.0.5"])
def test_q3_loopback_and_https_do_not_warn(console):
    del mod.STARTUP_WARNINGS[:]
    mod._load_station_config(_ini("[station]\nconsole = %s\n" % console))
    assert mod.STARTUP_WARNINGS == []


# ----------------------------------------------------------------- P2-4
class CountingEngine(mod.PythonInterface):
    """Counts reads of the scenario attribute."""
    scn_reads = 0

    @property
    def scn(self):
        self.scn_reads += 1
        return self._scn

    @scn.setter
    def scn(self, value):
        self._scn = value


def test_p2_4_one_scenario_read_per_tick(clock):
    xp.REFS.clear()
    e = CountingEngine()
    e.XPluginStart()
    base = beacon_engine(clock)
    e._scn.update(base.scn)
    # A panel is attached and scanning, so beacon_hz, effective_freq_hz,
    # tuned_hz and the decode all run inside the tick.
    e.panel_seen, e.scan_enable = True, 1
    e.active_freq_hz = 406_025_000
    e.started = clock.mono
    clock.advance(mod.LOOP_S)
    e.scn_reads = 0
    e.compute()
    assert e.cs_sync == 1, "setup: the tick should have decoded a frame"
    assert e.scn_reads == 1, "compute() re-read the scenario %d times" % e.scn_reads


# ----------------------------------------------------------------- P2-5
def _audible(e, clock):
    tick(e, clock, 6)
    return bool(e.valid)


def test_p2_5_mountain_beacon_is_not_a_tower(clock):
    xp.TERRAIN_FT = 9000.0                 # the beacon sits on 9,000 ft ground
    near = beacon_engine(clock, north_nm=50.0)
    assert _audible(near, clock), "inside the 67 NM horizon it should be heard"
    far = beacon_engine(clock, north_nm=80.0)      # moves the shared fake sim
    # In MSL terms the old horizon was 251 NM. Above the ground it is the
    # aircraft's 3,000 ft only: about 67 NM.
    assert not _audible(far, clock), "80 NM is past the ground-relative horizon"


def test_p2_5_missing_probe_falls_back_to_msl(clock, monkeypatch):
    xp.TERRAIN_FT = 9000.0
    far = beacon_engine(clock, north_nm=80.0)
    monkeypatch.setattr(far, "terrain_ft", lambda lat, lon: None)
    assert _audible(far, clock), "unloaded scenery must keep the old MSL horizon"


# ------------------------------------------------------- improvement 1 (snap)
def test_imp1_zero_elevation_snaps_to_probed_terrain_once(clock):
    xp.TERRAIN_FT = 9000.0
    e = beacon_engine(clock, elev=0.0)
    tick(e, clock, 2)
    d_nm = 5.0                              # beacon to aircraft, ground distance
    assert e.distance == pytest.approx(math.hypot(d_nm, 3000.0 / mod.FT_PER_NM), abs=0.02)
    xp.TERRAIN_FT = 5000.0                  # terrain changes under the same scenario
    tick(e, clock, 2)
    assert e.distance == pytest.approx(math.hypot(d_nm, 3000.0 / mod.FT_PER_NM), abs=0.02), (
        "the snap is made once per scenario, not re-probed every tick")
    e.scn["lat"] = 39.5                     # a different beacon: snap again
    xp.SIM["lat"] = 39.5 + 5.0 / 60.0
    tick(e, clock, 2)
    assert e.distance == pytest.approx(math.hypot(d_nm, 7000.0 / mod.FT_PER_NM), abs=0.02)


def test_imp1_an_explicit_elevation_is_left_alone(clock):
    xp.TERRAIN_FT = 9000.0
    e = beacon_engine(clock, elev=8000.0)
    tick(e, clock, 2)
    assert e.distance == pytest.approx(math.hypot(5.0, 4000.0 / mod.FT_PER_NM), abs=0.02)


# ----------------------------------------------------------------- P2-6
def _holding(clock):
    """An engine with a live bearing, then the burst closed so only TIMEHOLD
    keeps it on screen."""
    e = beacon_engine(clock)
    tick(e, clock, 8)
    assert e.valid
    e.started = clock.mono - mod.BURST_PERIOD_S / 2.0
    tick(e, clock, 1, burst=False)
    assert e.valid, "setup: TIMEHOLD should be carrying the bearing"
    return e


def test_p2_6_unpaused_hold_expires(clock):
    e = _holding(clock)
    clock.advance(60.0)
    tick(e, clock, 1, burst=False)
    assert not e.valid, "control: 60 s unpaused outlasts the 10 s TIMEHOLD"


def test_p2_6_a_pause_does_not_age_the_hold(clock):
    e = _holding(clock)
    xp.SIM["paused"] = 1
    tick(e, clock, 1, burst=False)          # the first paused tick sees the pause
    clock.advance(60.0)
    tick(e, clock, 1, burst=False)
    assert e.valid
    xp.SIM["paused"] = 0
    tick(e, clock, 1, burst=False)
    assert e.valid, "60 s of pause expired the held bearing"


def test_p2_6_compute_is_frozen_while_paused(clock):
    e = beacon_engine(clock)
    tick(e, clock, 2)
    pos = e.pos
    xp.SIM["paused"] = 1
    xp.SIM["lat"] += 1.0
    tick(e, clock, 1)
    assert e.pos == pos


def test_p2_6_a_wall_clock_step_does_not_expire_the_hold(clock):
    e = _holding(clock)
    clock.wall += 3600.0                    # NTP, or someone changed the time
    tick(e, clock, 1, burst=False)
    assert e.valid


def test_p2_6_decode_hold_survives_a_pause(clock):
    e = beacon_engine(clock)
    tick(e, clock, 8)
    assert e.cs_sync == 1
    xp.SIM["paused"] = 1
    tick(e, clock, 1)
    clock.advance(mod.DECODE_HOLD_S * 2)
    tick(e, clock, 1)
    xp.SIM["paused"] = 0
    e.started = clock.mono - mod.BURST_PERIOD_S / 2.0
    tick(e, clock, 1, burst=False)
    assert e.cs_sync == 1 and e.cs_msg_age() < mod.DECODE_HOLD_S


# ------------------------------------------------------- improvement 8 (backoff)
def test_imp8_backoff_schedule():
    b = mod.PythonInterface.net_backoff_s
    assert [b(n) for n in range(0, 8)] == [0.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]


class FakeNet(mod.PythonInterface):
    def __init__(self):
        super().__init__()
        self.pos_seen = True
        self.ok = False
        self.polls = []
        self.reports = []

    def poll_scenario_once(self):
        self.polls.append(self.t)
        return self.ok

    def report_position_once(self):
        self.reports.append(self.t)
        return self.ok


def _run(e, seconds):
    sched = mod.NetSchedule()
    t = 0.0
    while t < seconds:
        e.t = t
        e.net_tick(t, sched)
        t += mod.NET_TICK_S
    return sched


def test_imp8_a_dead_console_is_not_hammered():
    e = FakeNet()
    _run(e, 120.0)
    # Unbacked-off, 120 s is 40 polls and 60 reports.
    assert len(e.polls) <= 12 and len(e.reports) <= 12, (len(e.polls), len(e.reports))
    gaps = [b - a for a, b in zip(e.polls, e.polls[1:])]
    assert gaps == sorted(gaps), "the gap must only grow while the console stays down"


def test_imp8_recovery_restores_the_real_cadence():
    e = FakeNet()
    sched = mod.NetSchedule()
    t = 0.0
    while t < 60.0:                         # long outage, deep in backoff
        e.t = t
        e.net_tick(t, sched)
        t += mod.NET_TICK_S
    assert sched.failures >= 3
    e.ok = True
    e.polls.clear()
    e.reports.clear()
    for _ in range(int(60 / mod.NET_TICK_S)):
        e.t = t
        e.net_tick(t, sched)
        t += mod.NET_TICK_S
    assert sched.failures == 0
    gaps = [b - a for a, b in zip(e.reports, e.reports[1:])]
    assert gaps and max(gaps) <= mod.REPORT_S + mod.NET_TICK_S, gaps


# ------------------------------------------------------- improvement 5 (xp stub)
def test_imp5_stub_records_the_declared_type(clock):
    e = beacon_engine(clock)
    assert xp.REFS["cap/df/valid"]["dataType"] == xp.Type_Int
    assert xp.REFS["cap/df/signal"]["dataType"] == xp.Type_Float
    assert xp.REFS["cap/scenario/beacon_lat"]["dataType"] == xp.Type_Double
    assert xp.REFS["cap/df/cs_hex15"]["dataType"] == xp.Type_Data


def test_imp5_stub_rejects_a_mismatched_read_callback():
    xp.REFS.clear()
    with pytest.raises(TypeError):
        xp.registerDataAccessor("t/float_with_int_reader", xp.Type_Float, 0,
                                readInt=lambda r: 1)
    xp.registerDataAccessor("t/int_returns_float", xp.Type_Int, 0, readInt=lambda r: 1.0)
    with pytest.raises(TypeError):
        xp.read("t/int_returns_float")
    xp.registerDataAccessor("t/float_returns_int", xp.Type_Float, 0, readFloat=lambda r: 1)
    with pytest.raises(TypeError):
        xp.read("t/float_returns_int")
    xp.REFS.clear()


@pytest.mark.parametrize("panel", [False, True])
def test_imp5_every_published_dataref_returns_its_declared_type(clock, panel):
    e = beacon_engine(clock, effects={"multipath": True, "airframe_shadowing": True})
    e.panel_seen = panel
    e.scn["cs"] = {"hex15": "ABCDEF012345678", "lat": 39.1, "lon": -105.2,
                   "has_position": True, "protocol": 2, "country": 366}
    tick(e, clock, 12)
    assert e.valid, "setup: want a live bearing so the float fields hold real values"
    for name in sorted(xp.REFS):
        xp.read(name)                       # the stub raises TypeError on a mismatch
    # ...and with the scenario's nullable fields null, the accessors that read
    # them (V2-8) still return the declared type.
    e.scn["elev_ft"] = mod.as_float(None)
    e.scn["effects"] = {"error_code": None}
    for name in sorted(xp.REFS):
        xp.read(name)
