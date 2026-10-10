"""Bounded local authority protocol client for the flight-control plugin."""
from __future__ import annotations

import json
from pathlib import Path
import socket

from xplane.capvsar_flight_control_mapping import candidate_prefix

from .control_ownership import require_live_qualification


class BridgeClient:
    def __init__(self, config_path: Path):
        require_live_qualification()
        config = json.loads(Path(config_path).read_text())
        self.session = config["session"]
        candidate_prefix(self.session)
        self.secret = config["secret"]
        self.socket_path = config["socket_path"]
        if not self.socket_path.startswith("/tmp/capvsar-flight-control-"):
            raise ValueError("Unexpected flight-control socket path")
        self.generation = self.status()["generation"]

    def _request(self, action, **fields):
        payload = json.dumps({"action": action, "secret": self.secret, **fields}).encode() + b"\n"
        if len(payload) > 4096:
            raise ValueError("Flight-control request too large")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.3)
            connection.connect(self.socket_path)
            connection.sendall(payload)
            raw = bytearray()
            while b"\n" not in raw and len(raw) <= 4096:
                part = connection.recv(4096)
                if not part:
                    break
                raw.extend(part)
        if b"\n" not in raw or len(raw) > 4096:
            raise OSError("Incomplete flight-control bridge response")
        result = json.loads(raw.partition(b"\n")[0])
        if "error" in result:
            raise ValueError(result["error"])
        expected_session = fields["session"] if action == "renew_session" else self.session
        if result.get("session") != expected_session:
            raise ValueError("Flight-control session changed")
        if action == "renew_session":
            self.session = expected_session
        self.generation = result["generation"]
        return result

    def status(self): return self._request("status")
    def tick(self): return self.status()  # plugin owns its independent tick
    def prepare(self, owner, session, expected_generation):
        return self._request("prepare", owner=owner, session=session,
                             expected_generation=expected_generation)
    def activate(self, session, generation):
        return self._request("activate", session=session, generation=generation)
    def heartbeat(self, session, generation):
        return self._request("heartbeat", session=session, generation=generation)
    def transfer_gfc(self, generation, ready):
        return self._request("transfer_gfc", generation=generation, ready=ready)
    def renew_session(self, session, expected_generation):
        candidate_prefix(session)
        return self._request("renew_session", session=session,
                             expected_generation=expected_generation)
    def set_virtual_aux(self, channel, value, session, expected_generation):
        return self._request("set_virtual_aux", channel=channel, value=value,
                             session=session, expected_generation=expected_generation)
    def human_takeover(self, reason):
        return self._request("human_takeover", reason=reason)
    def fault_pause(self, reason):
        return self._request("fault_pause", reason=reason)
