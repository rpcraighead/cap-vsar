#!/usr/bin/env python3
"""Supervised bounded trial of the ArduPlane backend (CONOPS gate G).

Flies heading and altitude targets through the REAL `ManeuverGate` with
`arduplane_backend.ArduPlaneBackend`, so the control lease, the strictly
increasing sequence, the exercise envelope and the capture detection apply
exactly as they do for the other two backends. ArduPilot SITL, attached to
X-Plane, does the flying; this process only commands modes and targets.

THE PILOT REMAINS IN COMMAND. Moving the yoke releases control: ArduPlane
parks in LOITER, or FBWA when the stick was proven at engagement. Ctrl-C
releases. A lost ArduPilot heartbeat pauses the simulator and clears X-Plane's
joystick override so the yoke is never dead. This launcher OWNS the SITL
process: on exit it parks the aircraft, stops SITL, clears X-Plane's overrides
and hands the aircraft to the GFC 700, in that order, because SITL re-asserts
those overrides every frame while it lives and clears nothing when it dies.
Read docs/ARDUPLANE_TRIAL.md before the first run.

Refuses to start while the maneuver deck holds its controller lock - two
writers on the surfaces is the one thing the CONOPS forbids outright.

Usage:
    python3 scripts/fly_arduplane_backend.py --dry-run
    python3 scripts/fly_arduplane_backend.py --heading 120 --altitude 4500 \\
        --axis-pitch 1 --axis-roll 0 --seconds 180
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from services.ai_pilot import mavlink_min as mav  # noqa: E402
from services.ai_pilot.arduplane_backend import ArduPlaneBackend, M_PER_FT  # noqa: E402
from services.ai_pilot.maneuvers import Limits, ManeuverGate  # noqa: E402
from services.ai_pilot.sitl_lifecycle import SitlProcess, detach  # noqa: E402
from services.ai_pilot.xplane_udp import XPlaneUDPClient  # noqa: E402

TRACE_DIR = Path.home() / ".cache" / "capvsar" / "flight-tests"
SITL_BIN = Path.home() / ".cache" / "capvsar" / "ardupilot" / "build" / "sitl" / "bin" / "arduplane"
SITL_CWD = Path.home() / ".cache" / "capvsar" / "arduplane-run"
PARM = REPO / "xplane" / "ardupilot" / "cap487.parm"
CONTROLLER_LOCK = "/tmp/cap-vsar-maneuver-controller.lock"
ALT_AGREEMENT_FT = 100.0
# Modes that hold the aircraft where it is. Anything else (RTL, AUTO, CIRCLE)
# is already navigating and must not be taken over from.
SAFE_ATTACH_MODES = (mav.PLANE_MODE_LOITER, mav.PLANE_MODE_GUIDED,
                     mav.PLANE_MODE_FBWA, mav.PLANE_MODE_MANUAL)


def parse_mavlink(spec: str) -> tuple:
    scheme, _, rest = spec.partition(":")
    if scheme != "tcp" or ":" not in rest:
        raise argparse.ArgumentTypeError("expected tcp:HOST:PORT, got %r" % spec)
    host, _, port = rest.rpartition(":")
    return host, int(port)


def describe(observation) -> str:
    return (
        "hdg %6.1f  alt %7.0f ft  agl %6.0f ft  %5.1f KIAS  roll %+5.1f  vs %+6.0f fpm  age %.2fs"
        % (observation.heading_mag, observation.altitude_indicated_ft, observation.agl_ft,
           observation.kias, observation.roll_deg, observation.vvi_fpm, observation.age_seconds)
    )


def mode_name(mode) -> str:
    names = {mav.PLANE_MODE_MANUAL: "MANUAL", mav.PLANE_MODE_FBWA: "FBWA",
             mav.PLANE_MODE_LOITER: "LOITER", mav.PLANE_MODE_GUIDED: "GUIDED"}
    return names.get(mode, str(mode))


def print_preflight(report: dict) -> None:
    print("\n=== pre-flight ===")
    print("  X-Plane telemetry age      %.2f s" % report["xplane_age_s"])
    print("  ArduPilot heartbeat age    %.2f s   mode %s   %s"
          % (report["heartbeat_age_s"], mode_name(report["ardupilot_mode"]),
             "ARMED" if report["armed"] else "DISARMED (throttle forced to zero in GUIDED)"))
    print("  magnetic -> true offset    %+.1f deg" % report["mag_offset_deg"])
    print("  indicated -> true altitude %+.0f ft  (altimeter setting)" % report["alt_offset_ft"])
    print("  ArduPilot - X-Plane true   %+.0f ft  (SITL link sanity, gpi age %.2f s)"
          % (report["ardupilot_minus_xplane_true_ft"], report["gpi_age_s"]))
    print("  RC roll/pitch/yaw at rest  %s us  (rc age %.2f s; None = no usable RC, yoke takeover via X-Plane axes only)"
          % (report["rc_position_us"], report["rc_age_s"]))
    print("  override_joystick          %s" % report["override_joystick"])
    for name, value in sorted(report["joystick_axes"].items()):
        print("  %-26s %+.3f" % (name, value))
    print()


def open_trace(args, report, observation) -> tuple:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / ("arduplane_backend_%s.jsonl" % time.strftime("%Y%m%d-%H%M%S"))
    handle = path.open("w")
    handle.write(json.dumps({
        "record": "header",
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backend": "arduplane",
        "target_heading_deg": args.heading,
        "target_altitude_ft": args.altitude,
        "mavlink": args.mavlink,
        "constants": {k: getattr(ArduPlaneBackend, k) for k in dir(ArduPlaneBackend)
                      if k.isupper() and isinstance(getattr(ArduPlaneBackend, k), (int, float))},
        "limits": {k: v for k, v in vars(Limits()).items()},
        "preflight": report,
        "entry": {k: getattr(observation, k) for k in
                  ("heading_mag", "altitude_indicated_ft", "agl_ft", "kias", "roll_deg", "vvi_fpm")},
    }, allow_nan=True) + "\n")
    handle.flush()
    return handle, path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--heading", type=float, help="magnetic heading target")
    parser.add_argument("--altitude", type=float, help="indicated altitude target, ft")
    parser.add_argument("--seconds", type=float, default=240.0)
    parser.add_argument("--xp-host", default="127.0.0.1")
    parser.add_argument("--xp-port", type=int, default=49000)
    parser.add_argument("--receive-port", type=int, default=49260)
    parser.add_argument("--mavlink", default="tcp:127.0.0.1:5760", help="SITL MAVLink endpoint")
    parser.add_argument("--axis-pitch", type=int, help="sim/joystick/joystick_axis_values index of the pitch axis")
    parser.add_argument("--axis-roll", type=int, help="sim/joystick/joystick_axis_values index of the roll axis")
    parser.add_argument("--sitl-bin", default=str(SITL_BIN))
    parser.add_argument("--sitl-cwd", default=str(SITL_CWD), help="must contain xplane_plane.json")
    parser.add_argument("--parm", default=str(PARM))
    parser.add_argument("--sim-port-in", type=int, default=49501,
                        help="UDP port SITL listens on for X-Plane data output; must match "
                             "X-Plane's Settings > Network send port, and must not be 49001 "
                             "because X-Plane binds that itself")
    parser.add_argument("--no-sitl", action="store_true",
                        help="attach to a SITL started elsewhere; this launcher will not stop it")
    parser.add_argument("--dry-run", action="store_true", help="mock X-Plane and SITL; print the pre-flight block and exit")
    args = parser.parse_args()
    if not args.dry_run and (args.heading is None or args.altitude is None):
        parser.error("--heading and --altitude are required unless --dry-run")

    axes = {}
    if args.axis_pitch is not None:
        axes["pitch"] = args.axis_pitch
    if args.axis_roll is not None:
        axes["roll"] = args.axis_roll
    if not axes and not args.dry_run:
        print("WARNING: no --axis-pitch/--axis-roll given; yoke takeover relies on ArduPilot's RC mapping alone")

    # One writer on the surfaces: hold the maneuver deck's lock for the run.
    ownership = open(CONTROLLER_LOCK, "w")
    try:
        fcntl.flock(ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Refusing to start: the maneuver controller lock is held (is maneuver_server running?)")
        return 2

    if args.dry_run:
        client = XPlaneUDPClient(mock=True)
        link = mav.MockLink()
        backend = ArduPlaneBackend(client, link, limits=Limits(), joystick_axes=axes or {"pitch": 1, "roll": 0})
        for key, value in dict(heading_mag=274, altitude_indicated_ft=4500, agl_ft=2000 / 3.28084,
                               kias=110, roll_deg=0, vvi_fpm=0).items():
            client.set_mock_dref(backend.DATAREFS[key], value)
        for key, value in dict(elevation_m=4500 * M_PER_FT, heading_true=286, ap_mode=0,
                               override_joystick=1).items():
            client.set_mock_dref(backend.AUX_DATAREFS[key], value)
        for ref in backend.axis_datarefs.values():
            client.set_mock_dref(ref, 0.0)
        link.inject_heartbeat(mav.PLANE_MODE_MANUAL)
        link.inject(mav.MSG_GLOBAL_POSITION_INT, {"time_boot_ms": 0, "lat": 0, "lon": 0,
                    "alt": int(4500 * M_PER_FT * 1000), "relative_alt": 0, "vx": 0, "vy": 0, "vz": 0, "hdg": 0})
        print_preflight(backend.preflight())
        sent_before = len(link.sent_messages)
        result = detach(backend, client, None, {"servos_on": 1, "ap_state": 2}, 274.0, 4500.0)
        modes = [f["param2"] for _m, f in link.sent_messages if f.get("command") == mav.MAV_CMD_DO_SET_MODE]
        assert float(mav.PLANE_MODE_MANUAL) not in modes, "hand-back must never use MANUAL"
        print("dry run detach: %s, SITL %s, GFC 700 %s" % (
            result["hand_back_mode"] or "not engaged",
            "stopped" if result["sitl_stopped"] else "left running",
            ", ".join(result["gfc700_commands"]) or "already engaged"))
        print("dry run: %d MAVLink frames before detach, nothing reached a simulator" % sent_before)
        return 0

    host, port = parse_mavlink(args.mavlink)
    client = XPlaneUDPClient(host=args.xp_host, port=args.xp_port, receive_port=args.receive_port, timeout=1.0)

    sitl = None
    if not args.no_sitl:
        if not Path(args.sitl_bin).is_file():
            print("no ArduPlane binary at %s - run scripts/setup_ardupilot_sitl.sh" % args.sitl_bin)
            client.stop()
            return 1
        sitl = SitlProcess(args.sitl_bin, args.sitl_cwd, args.parm,
                           Path(args.sitl_cwd) / "arduplane.log", mavlink_port=port,
                           sim_port_in=args.sim_port_in)
        print("starting ArduPlane SITL: %s" % " ".join(sitl.command()))
        sitl.start()
        if not sitl.wait_for_mavlink(timeout=20.0):
            print("SITL did not open MAVLink on %d; see %s" % (port, sitl.log_path))
            sitl.stop()
            client.stop()
            return 1

    try:
        link = mav.MavlinkLink(host=host, port=port)
    except OSError as error:
        print("cannot reach ArduPilot SITL at %s: %s" % (args.mavlink, error))
        if sitl is not None:
            sitl.stop()
        client.stop()
        return 1
    backend = ArduPlaneBackend(client, link, limits=Limits(), joystick_axes=axes)
    gate = ManeuverGate(backend, Limits())

    # Read back what the GFC 700 is doing so the hand-back never toggles a live
    # autopilot off: g1000n1_ap is a toggle, not an "on".
    last = {"servos_on": 0, "ap_state": 0}
    client.subscribe_dref("sim/cockpit2/autopilot/servos_on", freq_hz=5,
                          callback=lambda ref, value: last.__setitem__("servos_on", value))
    client.subscribe_dref("sim/cockpit/autopilot/autopilot_state", freq_hz=5,
                          callback=lambda ref, value: last.__setitem__("ap_state", value))

    trace = None

    def cleanup(reason, released_by_gate=False):
        observation = backend.observe()
        heading = observation.heading_mag if math.isfinite(observation.heading_mag) else 0.0
        altitude = observation.altitude_indicated_ft if math.isfinite(observation.altitude_indicated_ft) else 4000.0
        result = detach(backend, client, sitl, dict(last), heading, altitude,
                        release=(lambda: None) if released_by_gate else None)
        time.sleep(0.5)
        override, since = backend.readback_after_release()
        if trace is not None:
            trace.write(json.dumps({"record": "end", "reason": reason,
                                    "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                    "detach": result, "override_joystick_after_release": override,
                                    "seconds_after_release": since}, allow_nan=True) + "\n")
            trace.close()
        link.close()
        client.stop()
        fcntl.flock(ownership, fcntl.LOCK_UN)
        ownership.close()
        print("released: ArduPlane parked in %s, SITL %s, overrides cleared, GFC 700 %s"
              % (result["hand_back_mode"] or "not engaged",
                 "stopped" if result["sitl_stopped"] else "left running",
                 ", ".join(c.rsplit("_", 1)[-1].upper() for c in result["gfc700_commands"]) or "already engaged"))
        print("override_joystick reads %s %.1f s after release" % (override, since or 0.0))
        return result

    print("waiting for X-Plane telemetry, an ArduPilot heartbeat and position ...")
    first_heartbeat = None
    deadline = time.time() + 20.0
    ready = False
    while time.time() < deadline:
        _gpi, gpi_age = link.latest(mav.MSG_GLOBAL_POSITION_INT)
        if first_heartbeat is None and link.heartbeat_age() < 2.0:
            first_heartbeat = time.time()
        # SITL decodes gyros with the X-Plane 11 convention until its 1 Hz
        # version query is answered; give that a full period before commanding.
        settled = first_heartbeat is not None and time.time() - first_heartbeat >= 2.5
        if backend.observe().age_seconds < 2.0 and link.heartbeat_age() < 2.0 and gpi_age < 1.0 and settled:
            ready = True
            break
        time.sleep(0.25)
    if not ready:
        _gpi, gpi_age = link.latest(mav.MSG_GLOBAL_POSITION_INT)
        print("not ready (X-Plane age %.1f s, heartbeat age %.1f s, position age %.1f s)"
              % (backend.observe().age_seconds, link.heartbeat_age(), gpi_age))
        cleanup("never ready")
        return 1

    # Close the attach window before anything else: SITL may have come up in a
    # navigating mode with its own default Home (AI-23).
    try:
        print("securing ArduPlane on attach: Home here, LOITER ...")
        secured = backend.secure_on_attach()
        print("  ArduPlane is in %s\n" % mode_name(secured))
    except (ValueError, OSError) as error:
        print("could not secure ArduPlane: %s" % error)
        cleanup("could not secure ArduPlane")
        return 6

    report = backend.preflight()
    observation = backend.observe()
    print_preflight(report)
    print("current: " + describe(observation))
    limits = Limits()
    if not (limits.min_kias <= observation.kias <= limits.max_kias
            and observation.agl_ft >= limits.min_agl_ft
            and limits.min_altitude_ft <= observation.altitude_indicated_ft <= limits.max_altitude_ft):
        print("\nRefusing to start: the aircraft is outside the exercise envelope\n"
              "  need %.0f-%.0f KIAS, at least %.0f ft AGL, %.0f-%.0f ft indicated."
              % (limits.min_kias, limits.max_kias, limits.min_agl_ft, limits.min_altitude_ft, limits.max_altitude_ft))
        cleanup("outside the envelope")
        return 2
    disagreement = report["ardupilot_minus_xplane_true_ft"]
    if not math.isfinite(disagreement) or abs(disagreement) > ALT_AGREEMENT_FT:
        print("\nRefusing to start: ArduPilot and X-Plane disagree on true altitude (%s ft). "
              "SITL is not attached to this aircraft, or not to this X-Plane." % disagreement)
        cleanup("altitude disagreement")
        return 4
    if not report["armed"]:
        print("\nRefusing to start: ArduPlane reports disarmed (ARMING_REQUIRE 0 not loaded?). "
              "A disarmed plane has its throttle forced to zero in GUIDED.")
        cleanup("disarmed")
        return 5
    if report["ardupilot_mode"] not in SAFE_ATTACH_MODES:
        print("\nRefusing to start: ArduPilot is in %s. Only %s are safe to take over from - a "
              "navigating mode is already flying the aircraft somewhere."
              % (mode_name(report["ardupilot_mode"]), "/".join(mode_name(m) for m in SAFE_ATTACH_MODES)))
        cleanup("unsafe ArduPilot mode %s" % mode_name(report["ardupilot_mode"]))
        return 6

    print("\n*** ArduPlane is about to take the aircraft. It has never flown this airframe. ***")
    print("*** Move the yoke to take it back at any time; Ctrl-C releases. ***\n")

    trace, trace_path = open_trace(args, report, observation)
    print("recording trace to %s\n" % trace_path)

    released = False
    reason = "aborted"
    try:
        # acquire() is INSIDE the try: it can refuse (envelope, stale telemetry)
        # and if it does, SITL is already attached and flying the aircraft.
        # Anything after the process starts must reach cleanup() (AI-22).
        grant = gate.acquire()
        lease, sequence = grant["lease"], grant["next_sequence"]
        gate.submit(lease, sequence, {"heading_mag": args.heading, "altitude_indicated_ft": args.altitude})
        print("commanded heading %.0f, altitude %.0f ft\n" % (args.heading, args.altitude))
        end = time.time() + args.seconds
        while time.time() < end:
            gate.tick()
            status = gate.status()
            observation = backend.observe()
            active = status.get("active")
            phase = active["status"] if active else "captured / idle"
            fault = backend.last_fault
            commands = backend.last_commands
            print("  %-18s %s  mode %s  rc %s%s" % (
                phase, describe(observation), mode_name(link.custom_mode()),
                ("%.0f" % commands["rc_deviation_us"]) if math.isfinite(commands.get("rc_deviation_us", float("nan"))) else "n/a",
                ("  FAULT: %s" % fault) if fault else ""))
            trace.write(json.dumps({
                "record": "sample", "t": round(time.time(), 3), "phase": phase, "fault": fault,
                "observation": {k: getattr(observation, k) for k in
                                ("heading_mag", "altitude_indicated_ft", "agl_ft", "kias", "roll_deg", "vvi_fpm", "age_seconds")},
                "mavlink": {"mode": link.custom_mode(), "heartbeat_age_s": link.heartbeat_age()},
                "commands": commands,
            }, allow_nan=True) + "\n")
            trace.flush()
            if fault or not status.get("owned"):
                print("\ngate or backend faulted or released; stopping")
                break
            time.sleep(2.0)
        reason = "flight complete"
    except ValueError as error:
        print("\nrefused: %s" % error)
        reason = "gate refused: %s" % error
    except KeyboardInterrupt:
        print("\ninterrupted by pilot")
        reason = "interrupted by pilot"
    finally:
        try:
            gate.takeover()          # revokes the lease and calls backend.release()
            released = True
        except Exception:
            pass
        cleanup(reason, released_by_gate=released)
        print("trace: %s" % trace_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
