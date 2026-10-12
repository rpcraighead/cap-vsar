"""Authenticated operator requests to an attended, running mission pilot.

The socket only queues bounded tasks. The flight loop validates them against
its current telemetry and applies them; this thread never touches X-Plane.
"""
from __future__ import annotations

import json
from pathlib import Path
import queue
import socket
import threading


class MissionRetaskServer:
    def __init__(self, path: str, secret: str):
        self.path = Path(path)
        self.secret = secret
        self.pending = queue.Queue(maxsize=4)
        self.stop_event = threading.Event()
        self.thread = None

    def __enter__(self):
        if self.path.exists():
            raise ValueError("Retask socket already exists")
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.path))
        self.path.chmod(0o600)
        self.server.listen(4)
        self.server.settimeout(.2)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.stop_event.set()
        self.thread.join(timeout=1)
        self.server.close()
        self.path.unlink(missing_ok=True)

    def _serve(self):
        while not self.stop_event.is_set():
            try:
                conn, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(1)
                try:
                    raw = bytearray()
                    while b"\n" not in raw and len(raw) <= 4096:
                        part = conn.recv(4096)
                        if not part:
                            break
                        raw.extend(part)
                    if b"\n" not in raw or len(raw) > 4096:
                        raise ValueError("Invalid retask frame")
                    message = json.loads(raw.partition(b"\n")[0])
                    if not isinstance(message, dict) or message.get("secret") != self.secret:
                        raise ValueError("Unauthorized retask")
                    task = message.get("task")
                    if not isinstance(task, dict):
                        raise ValueError("Retask must be an object")
                    reply = queue.Queue(maxsize=1)
                    self.pending.put_nowait((task, reply))
                    result = reply.get(timeout=2)
                except (ValueError, json.JSONDecodeError, queue.Empty, queue.Full, OSError) as error:
                    result = {"error": str(error)}
                conn.sendall(json.dumps(result, allow_nan=False).encode()+b"\n")

    def apply_pending(self, controller, snapshot, recorder):
        while True:
            try:
                task, reply = self.pending.get_nowait()
            except queue.Empty:
                return
            try:
                applied = controller.retask(task, snapshot)
                recorder.write("retask", {"task": task, "applied": applied,
                                          "frame": snapshot["frame"]})
                reply.put_nowait({"accepted": True, **applied})
            except (ValueError, KeyError, TypeError) as error:
                reply.put_nowait({"error": str(error)})


def send_retask(path: str, secret: str, task: dict) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(3)
        conn.connect(path)
        conn.sendall(json.dumps({"secret": secret, "task": task}, allow_nan=False).encode()+b"\n")
        raw = bytearray()
        while b"\n" not in raw:
            part = conn.recv(4096)
            if not part or len(raw)+len(part) > 4096:
                raise ValueError("Incomplete retask response")
            raw.extend(part)
    return json.loads(raw.partition(b"\n")[0])
