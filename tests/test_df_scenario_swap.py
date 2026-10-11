"""P2-2: a new beacon must not inherit the old one's receiver state.

The console swaps scenarios in one step while the sortie keeps running, so the
plugin sees only new coordinates. The held bearing, averaging store, decoded
ident and scan hold have to go with the old beacon.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xp  # noqa: E402  (the stub)

PLUGIN = os.path.abspath(os.path.join(HERE, "..", "xplane", "PI_capvsar_df.py"))
spec = importlib.util.spec_from_file_location("PI_capvsar_df_swap", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Clock:
    now = 1_700_000_000.0

    def time(self):
        return self.now

    def monotonic(self):
        return self.now


def engine():
    xp.REFS.clear()
    mod.time = Clock()
    e = mod.PythonInterface()
    e.XPluginStart()
    xp.SIM.update({"lat": 39.0833, "lon": -105.0, "elev_m": 12000.0 / 3.28084,
                   "psi": 180.0, "phi": 0.0, "theta": 0.0})
    return e


def state(lat, lon, **extra):
    sc = {"beacon_lat": lat, "beacon_lon": lon, "beacon_elev_ft": 9000.0,
          "band": 121.5, "power": 1.0, "effects": {}}
    sc.update(extra)
    return {"sortie": {"id": "s", "stopped": None}, "scenario": sc}


def swap_to(e, st):
    e.fetch_scenario = lambda: st
    e.poll_scenario_once()


def test_swap_clears_held_decode_and_scan():
    e = engine()
    swap_to(e, state(39.0, -105.0))
    e.compute()
    e.held = (mod.time.now, 11.0, 191.0)           # a bearing on the OLD beacon
    e.cs_hex15 = b"OLDIDENT0000000"
    e.scan_hold_hz = 121_500_000
    swap_to(e, state(39.4, -104.5))                # a different beacon
    e.compute()
    assert e.held is None or e.held[1] != 11.0, "old bearing survived the swap"
    assert e.cs_hex15 != b"OLDIDENT0000000", "old ident survived the swap"


def test_same_beacon_repolled_keeps_its_state():
    e = engine()
    swap_to(e, state(39.0, -105.0))
    e.compute()
    e.cs_hex15 = b"KEEPME000000000"
    swap_to(e, state(39.0, -105.0, effects={"multipath": True}))   # an effects tweak
    key_before = e.scn["beacon_key"]
    e.compute()
    assert e.scn["beacon_key"] == key_before
    assert e.cs_hex15 == b"KEEPME000000000", "an effects change reset the receiver"


def test_key_changes_with_position_channel_and_cs():
    base = {"lat": 1.0, "lon": 2.0, "band": 406.0, "beacon_freq_hz": 406_025_000, "cs": {}}
    keys = {mod.beacon_key(base)}
    for change in ({"lat": 1.5}, {"lon": 2.5}, {"beacon_freq_hz": 406_037_000},
                   {"band": 121.5}, {"cs": {"hex15": "ABC"}}):
        keys.add(mod.beacon_key(dict(base, **change)))
    assert len(keys) == 6
