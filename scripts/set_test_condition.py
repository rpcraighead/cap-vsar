#!/usr/bin/env python3
"""Set CAP 487's weight and CG for a flight-test point, and read back what was achieved.

THIS TOOL WRITES TO THE SIMULATOR. It is deliberately a separate program from
`scripts/capture_flight_test.py`, which is read-only: a data recorder that can
also move the aeroplane is a recorder you cannot trust.

It writes only mass and balance - payload, per-tank fuel and longitudinal CG. It
does not touch flight controls, the autopilot, or the maneuver gate, so it does
not conflict with `services.ai_pilot.maneuver_server` or with tracker items
AI-1/AI-2.

USE BETWEEN TEST POINTS, NEVER DURING ONE. The handling card is explicit:
"Restore identical conditions between runs rather than changing mass or CG
mid-maneuver." Changing mass mid-run invalidates the run.

WEIGHT AND CG ARE NEVER EXACT, in the simulator or in real flight test. The point
is not to hit a number but to KNOW the number: this tool reports what was actually
achieved, and `capture_flight_test.py` records weight and CG at 20 Hz throughout
every run so fuel burn is measured rather than assumed.

Usage:
    python3 scripts/set_test_condition.py --show
    python3 scripts/set_test_condition.py --weight-lb 2700 --fuel-lb 200
    python3 scripts/set_test_condition.py --weight-lb 3100 --cg-station-in 40.9
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "services" / "ai_pilot"))

from xplane_udp import XPlaneUDPClient  # noqa: E402

LB_PER_KG = 2.2046226218
M_PER_FT = 0.3048

DREFS = {
    "m_total": "sim/flightmodel/weight/m_total",       # read-only, computed
    "m_fixed": "sim/flightmodel/weight/m_fixed",       # payload, writable
    "m_fuel1": "sim/flightmodel/weight/m_fuel1",
    "m_fuel2": "sim/flightmodel/weight/m_fuel2",
    "cg_offset_z": "sim/flightmodel2/misc/cg_offset_z",
    "kias": "sim/flightmodel/position/indicated_airspeed",
    "paused": "sim/time/paused",
}

# Payload stations. Writing cg_offset_z does NOT stick - X-Plane recomputes CG
# from where the mass actually sits and overwrites it. CG is therefore set the
# way it is set in a real aeroplane: by placing mass.
N_STATIONS = 6
for _i in range(N_STATIONS):
    DREFS["stn_mass_%d" % _i] = "sim/flightmodel/weight/m_stations[%d]" % _i
    DREFS["stn_arm_%d" % _i] = "sim/aircraft/weight/acf_stations_ref_z[%d]" % _i
    DREFS["stn_max_%d" % _i] = "sim/aircraft/weight/acf_m_station_max[%d]" % _i

# --- Datum mapping, solved from the aircraft's own payload stations -----------
#
# X-Plane reports station arms and cg_offset_z as ABSOLUTE arms in the aircraft
# origin frame. The origin is NOT the Cessna reference datum, so a mapping is
# needed to talk in fuselage stations.
#
# Solved against TCDS 3A13 p.33 loading stations. The rear seat is the anchor
# because the TCDS publishes it as a single arm, FS 74.0, not a range:
#
#     station          arm_z (m)   -> FS (in)   TCDS
#     front seats       0.1361        37.4      32.0-50.0   OK
#     rear seats        1.0661        74.0      74.0        EXACT
#     baggage A         1.6161        95.7      82.0-109.0  OK
#     baggage B         2.2361       120.1     109.0-134.0  OK
#
# Six stations, all inside their published ranges, one exact.
#
# SUPERSEDES an earlier %MAC-based chain that assumed cg_offset_z was an offset
# from acf/_cgZ, as the *limit* datarefs are. It is not - it is an absolute arm.
# That error put the CG 6.6 in aft of truth (FS 44.3 instead of 37.7), about a
# third of the whole envelope, and it looked entirely plausible.
ACF_ORIGIN_FS_FT = 2.6690        # aircraft origin sits at FS 32.03 in
FUEL_ARM_FS_IN = 46.5            # TCDS 3A13: wing tanks at FS 46.5 in
FS_LE_MAC_IN = 25.98             # TCDS 3A13: leading edge of MAC
MAC_IN = 58.8                    # TCDS 3A13: mean aerodynamic chord


def arm_m_to_station_in(arm_m: float) -> float:
    """Aircraft-origin arm in metres -> inches aft of the Cessna datum."""
    return (arm_m / M_PER_FT + ACF_ORIGIN_FS_FT) * 12.0


def station_in_to_arm_m(station_in: float) -> float:
    return (station_in / 12.0 - ACF_ORIGIN_FS_FT) * M_PER_FT


def cg_offset_to_station_in(offset_m: float) -> tuple[float, float]:
    """Return (%MAC, fuselage station in inches) for a CG arm."""
    station = arm_m_to_station_in(offset_m)
    pct_mac = (station - FS_LE_MAC_IN) / MAC_IN * 100.0
    return pct_mac, station


def read_state(client) -> dict:
    for ref in DREFS.values():
        client.subscribe_dref(ref, freq_hz=4)
    time.sleep(2.5)
    cached = client.get_all_cached()
    state = {name: cached.get(ref) for name, ref in DREFS.items()}
    if state["m_total"] is None:
        raise SystemExit("no telemetry on the simulator UDP port; is X-Plane running?")
    return state


def report(state: dict, label: str) -> None:
    fuel_kg = (state["m_fuel1"] or 0.0) + (state["m_fuel2"] or 0.0)
    print("%s:" % label)
    print("   total weight   %.0f lb  (%.1f kg)" % (state["m_total"] * LB_PER_KG, state["m_total"]))
    print("   payload        %.0f lb" % ((state["m_fixed"] or 0.0) * LB_PER_KG))
    print("   fuel           %.0f lb  (L %.0f / R %.0f)" % (
        fuel_kg * LB_PER_KG,
        (state["m_fuel1"] or 0.0) * LB_PER_KG, (state["m_fuel2"] or 0.0) * LB_PER_KG))
    if state["cg_offset_z"] is not None:
        pct, station = cg_offset_to_station_in(state["cg_offset_z"])
        print("   CG             %+.4f m offset  =  %.1f%% MAC  =  FS %.1f in (derived)"
              % (state["cg_offset_z"], pct, station))


def check_envelope(weight_lb: float, station_in: float | None) -> None:
    """Warn against the TCDS weight-scheduled forward limit, which X-Plane does not enforce."""
    if station_in is None:
        return
    if weight_lb >= 3100:
        fwd = 40.9
    elif weight_lb >= 2700:
        fwd = 35.5
    else:
        fwd = 33.0
    if station_in < fwd:
        print("\n   *** WARNING: FS %.1f is FORWARD of the TCDS limit %.1f in at %.0f lb."
              % (station_in, fwd, weight_lb))
        print("   The TCDS forward limit is weight-scheduled (33.0 at 2,250 lb, 35.5 at")
        print("   2,700, 40.9 at 3,100). X-Plane holds a single forward value and will")
        print("   NOT stop you loading outside the real envelope. Choose the station from")
        print("   the POH schedule, not from what the simulator permits.")
    if station_in > 46.0:
        print("\n   *** WARNING: FS %.1f is AFT of the 46.0 in certificated aft limit." % station_in)


def _fill(arms, maxes, payload_kg, aft_kg):
    """Place `aft_kg` filling from the aft-most station, the rest from the forward-most."""
    masses = [0.0] * len(arms)
    remaining_capacity = list(maxes)
    rem = aft_kg
    for i in sorted(range(len(arms)), key=lambda i: -arms[i]):
        take = min(rem, remaining_capacity[i])
        masses[i] += take
        remaining_capacity[i] -= take
        rem -= take
        if rem <= 1e-9:
            break
    if rem > 1e-6:
        return None
    rem = payload_kg - aft_kg
    for i in sorted(range(len(arms)), key=lambda i: arms[i]):
        take = min(rem, remaining_capacity[i])
        masses[i] += take
        remaining_capacity[i] -= take
        rem -= take
        if rem <= 1e-9:
            break
    if rem > 1e-6:
        return None
    return masses


def _arm(arms, masses):
    total = sum(masses)
    return sum(m * a for m, a in zip(masses, arms)) / total if total else 0.0


def solve_payload(state: dict, payload_kg: float, target_station_in: float):
    """Place `payload_kg` across the stations so the whole aircraft balances at the target.

    Returns (masses_kg, note). `masses_kg` is None when the target cannot be
    reached, which is a real possibility rather than an error: station capacities
    are finite, so a given payload simply cannot be moved beyond a certain arm.
    A first version solved two points analytically and let capacity spill the rest
    forward silently, which missed by 4 inches and looked like a tuning problem.
    """
    arms = [state["stn_arm_%d" % i] for i in range(N_STATIONS)]
    maxes = [state["stn_max_%d" % i] or 0.0 for i in range(N_STATIONS)]
    if any(a is None for a in arms) or payload_kg <= 0:
        return None, "no usable payload stations"

    fuel_kg = (state["m_fuel1"] or 0.0) + (state["m_fuel2"] or 0.0)
    old_payload = sum((state["stn_mass_%d" % i] or 0.0) for i in range(N_STATIONS))
    empty_kg = state["m_total"] - old_payload - fuel_kg
    fuel_arm = station_in_to_arm_m(FUEL_ARM_FS_IN)
    old_payload_moment = sum((state["stn_mass_%d" % i] or 0.0) * arms[i]
                             for i in range(N_STATIONS))
    empty_moment = state["m_total"] * state["cg_offset_z"] - old_payload_moment - fuel_kg * fuel_arm

    total_kg = empty_kg + fuel_kg + payload_kg
    target_arm = station_in_to_arm_m(target_station_in)
    required_moment = total_kg * target_arm - empty_moment - fuel_kg * fuel_arm
    required_arm = required_moment / payload_kg

    lo_masses = _fill(arms, maxes, payload_kg, 0.0)
    hi_masses = _fill(arms, maxes, payload_kg, payload_kg)
    if lo_masses is None or hi_masses is None:
        return None, "payload exceeds total station capacity"
    lo_arm, hi_arm = _arm(arms, lo_masses), _arm(arms, hi_masses)
    if not lo_arm <= required_arm <= hi_arm:
        def station_for(arm):
            return (total_kg * 0 + arm_m_to_station_in(
                (empty_moment + fuel_kg * fuel_arm + payload_kg * arm) / total_kg))
        return None, (
            "unreachable: needs payload arm %.3f m, achievable range %.3f-%.3f m.\n"
            "   With this payload and fuel the CG can only be placed between "
            "FS %.1f and FS %.1f in." % (
                required_arm, lo_arm, hi_arm, station_for(lo_arm), station_for(hi_arm)))

    # Achieved arm is monotonic in how much mass is filled from the aft end.
    lo, hi = 0.0, payload_kg
    masses = hi_masses
    for _ in range(60):
        mid = (lo + hi) / 2.0
        masses = _fill(arms, maxes, payload_kg, mid)
        if masses is None:
            return None, "capacity solve failed"
        if _arm(arms, masses) < required_arm:
            lo = mid
        else:
            hi = mid
    return masses, "payload arm %.3f m" % _arm(arms, masses)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", action="store_true", help="report current condition and exit")
    parser.add_argument("--weight-lb", type=float, help="target total weight")
    parser.add_argument("--fuel-lb", type=float, default=None, help="target total fuel")
    parser.add_argument("--cg-station-in", type=float, default=None,
                        help="target CG, inches aft of datum (derived conversion)")
    parser.add_argument("--xp-host", default="127.0.0.1")
    parser.add_argument("--xp-port", type=int, default=49000)
    parser.add_argument("--receive-port", type=int, default=49350)
    args = parser.parse_args()

    client = XPlaneUDPClient(host=args.xp_host, port=args.xp_port,
                             receive_port=args.receive_port, timeout=1.0)
    try:
        before = read_state(client)
        report(before, "current condition")
        if args.show or (args.weight_lb is None and args.cg_station_in is None):
            return 0

        # X-Plane does not recompute m_total while the simulator is PAUSED.
        # Every mass figure here is derived from it - empty weight is
        # m_total minus payload minus fuel - so a stale reading poisons the
        # whole calculation and the read-back confirms the wrong number.
        # Observed: paused at 1,924 lb, the empty weight came out 1,124 lb
        # instead of 1,924, and chasing a 3,100 lb target loaded 1,735 lb of
        # payload. On unpause m_total recomputed to 3,900 lb - 800 lb over
        # max gross - on a card whose every figure is AT max gross.
        if before["paused"]:
            print("\n   REFUSING: the simulator is PAUSED, and X-Plane does not recompute")
            print("   m_total while paused. Every mass figure here derives from it, so the")
            print("   numbers above are stale and any correction computed from them would")
            print("   be wrong while reporting success. Unpause, then run this again.")
            return 4

        if before["kias"] and before["kias"] > 40:
            print("\n   note: the aircraft is flying. Set conditions BETWEEN test points,")
            print("   never during one - changing mass mid-run invalidates the run.")

        if args.weight_lb is not None:
            fuel_kg = (before["m_fuel1"] or 0.0) + (before["m_fuel2"] or 0.0)
            empty_kg = before["m_total"] - (before["m_fixed"] or 0.0) - fuel_kg
            target_fuel_kg = (args.fuel_lb / LB_PER_KG) if args.fuel_lb is not None else fuel_kg
            target_payload_kg = args.weight_lb / LB_PER_KG - empty_kg - target_fuel_kg
            if target_payload_kg < 0:
                print("\n   cannot reach %.0f lb: empty %.0f lb plus fuel %.0f lb already exceeds it."
                      % (args.weight_lb, empty_kg * LB_PER_KG, target_fuel_kg * LB_PER_KG))
                return 2
            print("\n   empty weight computed as %.0f lb" % (empty_kg * LB_PER_KG))
            client.send_dref(DREFS["m_fuel1"], target_fuel_kg / 2.0)
            client.send_dref(DREFS["m_fuel2"], target_fuel_kg / 2.0)
            client.send_dref(DREFS["m_fixed"], target_payload_kg)

        if args.cg_station_in is not None:
            # Re-read AFTER the mass writes. Solving from the pre-write state backs
            # the empty moment out of numbers that have already changed, which put
            # the CG 4 in adrift on the first attempt.
            time.sleep(2.0)
            mid = read_state(client)
            payload_kg = sum((mid["stn_mass_%d" % i] or 0.0) for i in range(N_STATIONS))
            masses, note = solve_payload(mid, payload_kg, args.cg_station_in)
            if masses is None:
                print("\n   cannot reach FS %.1f with %.0f lb of payload: %s"
                      % (args.cg_station_in, payload_kg * LB_PER_KG, note))
            else:
                for i, m in enumerate(masses):
                    client.send_dref(DREFS["stn_mass_%d" % i], m)
                print("\n   payload placed across stations (lb): %s"
                      % ", ".join("%.0f" % (m * LB_PER_KG) for m in masses))

        time.sleep(2.5)
        after = read_state(client)
        print()
        report(after, "achieved condition")
        achieved_station = None
        if after["cg_offset_z"] is not None:
            _, achieved_station = cg_offset_to_station_in(after["cg_offset_z"])
        check_envelope(after["m_total"] * LB_PER_KG, achieved_station)

        if args.weight_lb is not None:
            error = after["m_total"] * LB_PER_KG - args.weight_lb
            print("\n   weight error %+.0f lb against the %.0f lb target" % (error, args.weight_lb))
        if args.cg_station_in is not None and achieved_station is not None:
            print("   CG error     %+.2f in against the FS %.1f target"
                  % (achieved_station - args.cg_station_in, args.cg_station_in))
        print("\n   Record the ACHIEVED values with the test point, not the targets.")
    finally:
        for ref in DREFS.values():
            try:
                client.unsubscribe_dref(ref)
            except Exception:
                pass
        time.sleep(0.3)
        client.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
