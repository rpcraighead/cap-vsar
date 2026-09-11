#!/usr/bin/env python3
"""
Mock sim bridge - flies a synthetic aircraft so the console is demonstrable
before X-Plane exists.

This posts to exactly the endpoint the real bridge will use in Phase 4:
    POST /api/positions  {callsign, lat, lon, alt_ft, hdg_true}

Replacing this with the real thing means reading position from X-Plane over
UDP RREF and POSTing the same body. Nothing else changes.

    python3 mock_bridge.py --url http://localhost:8700 --callsign CAP-1
"""
import argparse, json, math, os, sys, time, urllib.request

# C15-2: this had its own copy of the direct solution. The console's geodesy
# lives in app/geo.py; this script runs from services/exercise/, so that
# imports cleanly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.geo import R_NM, move          # noqa: E402,F401


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8700")
    ap.add_argument("--callsign", default="CAP-1")
    ap.add_argument("--lat", type=float, default=33.1283)   # KCRQ
    ap.add_argument("--lon", type=float, default=-117.2800)
    ap.add_argument("--alt", type=float, default=4500.0)
    ap.add_argument("--kts", type=float, default=110.0)
    ap.add_argument("--rate", type=float, default=2.0, help="seconds between reports")
    a = ap.parse_args()

    lat, lon, hdg = a.lat, a.lon, 65.0
    # a lazy search box: fly legs, turning every 90 s
    leg_s, t0 = 90.0, time.time()
    print(f"{a.callsign} departing {lat:.4f},{lon:.4f} -> {a.url}")
    while True:
        elapsed = time.time() - t0
        hdg = (65.0 + 90.0 * int(elapsed / leg_s)) % 360.0
        lat, lon = move(lat, lon, hdg, a.kts * a.rate / 3600.0)
        try:
            # mock:true asks the console for its DF stub. Nothing else sets
            # it: a real station's DF comes from the plugin or not at all
            # (P-11).
            r = post(f"{a.url}/api/positions",
                     {"callsign": a.callsign, "lat": lat, "lon": lon,
                      "alt_ft": a.alt, "hdg_true": hdg, "mock": True})
            df = r.get("df")
            if df and df["valid"]:
                print(f"  {elapsed:6.0f}s  brg {df['bearing_rel']:5.1f} rel  "
                      f"{df['distance_nm']:5.1f} nm  sig {df['signal']:.2f}  {df['note']}")
            elif df:
                print(f"  {elapsed:6.0f}s  --  {df['note']}  ({df['distance_nm']:.1f} nm)")
        except Exception as e:
            print("  post failed:", e)
        time.sleep(a.rate)


if __name__ == "__main__":
    main()
