#!/usr/bin/env python3
"""Supervised live trial of the direct surface-control backend.

First flight for `direct_backend.XPlaneDirectBackend`. It flies heading and
altitude targets through the REAL `ManeuverGate`, so the control lease, the
strictly increasing sequence, the exercise envelope and the capture detection
all apply exactly as they do for the autopilot backend.

Scope is deliberately narrow: cruise-regime target holding only. No stall
profile, no takeoff, no landing, no ground operation. The aircraft must already
be airborne, trimmed and inside the exercise envelope before this starts.

THE PILOT REMAINS IN COMMAND. Ctrl-C releases the controls and neutralizes at
any time, and the gate's own fault path pauses the simulator if telemetry goes
stale. Take over manually the moment anything looks wrong; this controller has
never flown.

Do not run this at the same time as `services.ai_pilot.maneuver_server`, which
would put two writers on the same control surfaces.

Usage:
    python3 scripts/fly_direct_backend.py --heading 120 --altitude 4500
    python3 scripts/fly_direct_backend.py --heading 120 --altitude 4500 --seconds 180
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from services.ai_pilot.direct_backend import Gains, XPlaneDirectBackend  # noqa: E402
from services.ai_pilot.maneuvers import Limits, ManeuverGate  # noqa: E402
from services.ai_pilot.xplane_udp import XPlaneUDPClient  # noqa: E402
from services.ai_pilot.control_ownership import exclusive_controller, require_legacy_route_qualification  # noqa: E402


TRACE_DIR = Path.home() / ".cache" / "capvsar" / "flight-tests"


def open_trace(args, observation) -> tuple:
    """Open a JSONL trace and write the run header.

    Flight-test data is the deliverable, not a side effect. The header records
    the gains in force, because a trace you cannot attribute to a tune is not
    evidence of anything.
    """
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = TRACE_DIR / ("direct_backend_%s.jsonl" % stamp)
    handle = path.open("w")
    handle.write(json.dumps({
        "record": "header",
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_heading_deg": args.heading,
        "target_altitude_ft": args.altitude,
        "target_kias": args.target_kias,
        "gains": {k: getattr(Gains, k) for k in dir(Gains) if k.isupper()},
        "limits": {k: v for k, v in vars(Limits()).items()},
        "entry": {
            "heading_mag": observation.heading_mag,
            "altitude_indicated_ft": observation.altitude_indicated_ft,
            "agl_ft": observation.agl_ft,
            "kias": observation.kias,
            "roll_deg": observation.roll_deg,
            "vvi_fpm": observation.vvi_fpm,
        },
    }) + "\n")
    handle.flush()
    return handle, path


def describe(observation) -> str:
    return (
        "hdg %6.1f  alt %7.0f ft  agl %6.0f ft  %5.1f KIAS  "
        "roll %+5.1f  vs %+6.0f fpm  age %.2fs"
        % (
            observation.heading_mag,
            observation.altitude_indicated_ft,
            observation.agl_ft,
            observation.kias,
            observation.roll_deg,
            observation.vvi_fpm,
            observation.age_seconds,
        )
    )


@exclusive_controller
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heading", type=float, required=True, help="magnetic heading target")
    parser.add_argument("--altitude", type=float, required=True, help="indicated altitude target, ft")
    parser.add_argument("--seconds", type=float, default=240.0)
    parser.add_argument("--target-kias", type=float, default=110.0)
    parser.add_argument("--xp-host", default="127.0.0.1")
    parser.add_argument("--xp-port", type=int, default=49000)
    parser.add_argument("--receive-port", type=int, default=49230)
    args = parser.parse_args()
    try:
        require_legacy_route_qualification()
    except RuntimeError as error:
        print(error)
        return 7

    client = XPlaneUDPClient(
        host=args.xp_host, port=args.xp_port, receive_port=args.receive_port, timeout=1.0
    )
    try:
        backend = XPlaneDirectBackend(client, limits=Limits(), target_kias=args.target_kias)
        gate = ManeuverGate(backend, Limits())
    except Exception:
        client.stop()
        raise

    try:
        print("waiting for telemetry ...")
        deadline = time.time() + 15.0
        while time.time() < deadline:
            observation = backend.observe()
            if observation.age_seconds < 2.0:
                break
            time.sleep(0.5)
        else:
            print("no fresh telemetry on port %d - is X-Plane running with UDP enabled?" % args.xp_port)
            client.stop()
            return 1

        observation = backend.observe()
        print("current: " + describe(observation))
        limits = Limits()
        if not (limits.min_kias <= observation.kias <= limits.max_kias
                and observation.agl_ft >= limits.min_agl_ft
                and limits.min_altitude_ft <= observation.altitude_indicated_ft <= limits.max_altitude_ft):
            print(
                "\nRefusing to start: the aircraft is outside the exercise envelope\n"
                "  need %.0f-%.0f KIAS, at least %.0f ft AGL, %.0f-%.0f ft indicated."
                % (limits.min_kias, limits.max_kias, limits.min_agl_ft,
                   limits.min_altitude_ft, limits.max_altitude_ft)
            )
            client.stop()
            return 2

        print("\n*** The direct backend is about to take the controls. ***")
        print("*** It has never flown. Take over manually at any sign of trouble. ***")
        print("*** Ctrl-C releases and neutralizes. ***\n")

        # acquire() returns {'lease': ..., 'next_sequence': 1}, not a bare token.
        trace, trace_path = open_trace(args, observation)
        print("recording trace to %s\n" % trace_path)

        lease = sequence = None
        released = False
        outcome = "aborted"
        exit_status = 1
        try:
            grant = gate.acquire()
            lease, sequence = grant["lease"], grant["next_sequence"]
            command = gate.submit(lease, sequence, {
                "heading_mag": args.heading,
                "altitude_indicated_ft": args.altitude,
            })
            command_id = command["command_id"]
            print("commanded heading %.0f, altitude %.0f ft\n" % (args.heading, args.altitude))
            end = time.time() + args.seconds
            while time.time() < end:
                gate.tick()
                status = gate.status()
                observation = backend.observe()
                active = status.get("active")
                terminal = next((e for e in reversed(status["events"])
                                 if e.get("command_id") == command_id
                                 and e["status"] in ("achieved", "fault", "timed_out", "canceled")), None)
                phase = active["status"] if active else (terminal["status"] if terminal else "idle")
                fault = backend.last_fault
                print("  %-18s %s%s" % (phase, describe(observation),
                                        ("  FAULT: %s" % fault) if fault else ""))
                trace.write(json.dumps({
                    "record": "sample",
                    "t": round(time.time(), 3),
                    "phase": phase,
                    "fault": fault,
                    "gate_terminal": terminal,
                    "observation": {
                        "heading_mag": observation.heading_mag,
                        "altitude_indicated_ft": observation.altitude_indicated_ft,
                        "agl_ft": observation.agl_ft,
                        "kias": observation.kias,
                        "roll_deg": observation.roll_deg,
                        "vvi_fpm": observation.vvi_fpm,
                        "age_seconds": observation.age_seconds,
                    },
                    "commands": backend.last_commands,
                }) + "\n")
                trace.flush()
                if terminal and terminal["status"] == "achieved":
                    outcome, exit_status = "maneuver achieved", 0
                    break
                if fault or not status.get("owned"):
                    outcome = "gate/backend fault: %s" % (fault or (terminal or {}).get("reason", "ownership lost"))
                    print("\n%s" % outcome)
                    break
                time.sleep(2.0)
            else:
                gate.timeout()
                outcome, exit_status = "maneuver timed out without measured capture", 3
        except ValueError as error:
            outcome = "gate refused: %s" % error
            print(outcome)
        except KeyboardInterrupt:
            print("\ninterrupted by pilot")
            outcome, exit_status = "interrupted by pilot", 130
        finally:
            try:
                gate.takeover()          # revokes the lease and calls backend.release()
                released = True
            except Exception:
                pass
            if not released:
                backend.release()
            time.sleep(0.5)
            client.stop()
            try:
                trace.write(json.dumps({"record": "end", "reason": outcome,
                                        "gate_events": gate.status()["events"],
                                        "gate_terminal": gate.last_terminal,
                                        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
                trace.close()
            except Exception:
                pass
            print("control lease released; bridge handoff state requires verification")
            print("trace: %s" % trace_path)
        return exit_status
    finally:
        try:
            backend.release()
        finally:
            client.stop()


if __name__ == "__main__":
    raise SystemExit(main())
