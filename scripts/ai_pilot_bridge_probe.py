#!/usr/bin/env python3
"""Paused stock-C172 native readbacks, rejection and revoked-authority probe."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.ai_pilot.experiment import BridgeClient
from services.ai_pilot.control_ownership import ControllerLock


def run(config, output):
    client = BridgeClient(config)
    landing = config.get("mode") == "landing"
    report = {"purpose": "paused-landing-brake-boundary" if landing else "paused-native-boundary-qualification",
              "checks": [], "outcome": "FAIL"}
    def request(action, **params):
        result = client.request(action, **params)
        report["checks"].append({"action": action, "result": result})
        return result
    try:
        request("fault_pause", reason="Paused actuator probe")
        time.sleep(.1)
        session = secrets.token_hex(16)
        request("lab_reset", session=session)
        time.sleep(.2)
        s = request("snapshot")
        assert s["values"]["paused"] and s["override_state"] is False
        c = dict(roll=.10, pitch=-.08, yaw=.06, throttle=.35 if landing else .65,
                 flap=.5 if landing else 0., trim=.02)
        if landing:
            c["brake"] = .30
        seq = 0
        generation = 0
        def frame():
            nonlocal seq
            seq += 1
            return dict(session=session, generation=generation, sequence=seq,
                        expires_at=time.monotonic()+.18, controls=c)
        request("submit_frame", **frame())
        generation = request("prepare", owner="DIRECT", session=session, expected_generation=0)["generation"]
        request("submit_frame", **frame())
        request("activate", session=session, generation=generation)
        request("exchange", **frame())
        s = request("snapshot")
        assert s["override_state"] is True and s["ap_engaged"] is False
        assert all(abs(s["controls"][name]-value) < .001 for name,value in c.items())
        if landing:
            assert abs(s["values"]["brake_left"] - .30) < .001
            assert abs(s["values"]["brake_right"] - .30) < .001
        for mutation in ({"sequence": seq}, {"session": "f"*32}, {"controls": {"roll": .2}},
                         {"expires_at": time.monotonic()-1}):
            request("exchange", **frame())
            bad = {**frame(), **mutation}
            try:
                request("submit_frame", **bad)
            except RuntimeError as error:
                report["checks"].append({"rejected": list(mutation), "reason": str(error)})
            else:
                raise AssertionError("Invalid frame was accepted")
        # Deliberately stop all producer activity beyond the frame lease.
        time.sleep(.3)
        status = request("status")
        assert status["state"] == "PAUSED_FAULT" and status["pause_confirmed"] and status["retired"]
        s = request("snapshot")
        assert s["override_state"] is False and s["values"]["paused"]
        if landing:
            assert s["values"]["brake_left"] == s["values"]["brake_right"] == 0.
        try:
            request("submit_frame", **frame())
        except RuntimeError as error:
            report["checks"].append({"retired_frame_rejected": str(error)})
        else:
            raise AssertionError("Retired writer regained authority")
        report["outcome"] = "PASS"
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        try:
            report["final_bridge"] = request("fault_pause", reason="Paused probe ended")
        finally:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x") as stream:
                json.dump(report, stream, indent=2, allow_nan=False)
            print(json.dumps({"outcome": report["outcome"], "report": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if config.get("mode") not in ("qualification", "landing"):
        raise ValueError("Requires qualification or landing mode")
    with ControllerLock():
        run(config, args.output)
