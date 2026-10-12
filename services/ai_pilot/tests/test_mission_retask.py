import socket
import threading
import time

from services.ai_pilot.mission_retask import MissionRetaskServer, send_retask


class Controller:
    def retask(self, task, snapshot):
        assert snapshot["frame"] == 42
        return {"kind": task["kind"], "stage": "retry_bakel"}


class Recorder:
    def __init__(self):
        self.entries = []

    def write(self, kind, payload):
        self.entries.append((kind, payload))


def test_operator_command_is_applied_and_recorded_while_running(tmp_path):
    path = str(tmp_path / "retask.sock")
    recorder = Recorder()
    with MissionRetaskServer(path, "a" * 32) as server:
        result = []
        worker = threading.Thread(target=lambda: result.append(send_retask(
            path, "a" * 32, {"kind": "direct", "fix": "BAKEL", "altitude_ft": 5000.})))
        worker.start()
        deadline = time.monotonic() + 2
        while not server.pending.qsize() and time.monotonic() < deadline:
            time.sleep(.001)
        server.apply_pending(Controller(), {"frame": 42}, recorder)
        worker.join(timeout=2)
        assert result[0]["accepted"] is True
        assert recorder.entries[0][0] == "retask"
        assert recorder.entries[0][1]["frame"] == 42


def test_wrong_secret_cannot_queue_retask(tmp_path):
    path = str(tmp_path / "retask.sock")
    with MissionRetaskServer(path, "a" * 32) as server:
        result = send_retask(path, "b" * 32, {"kind": "altitude", "altitude_ft": 5000.})
        assert result["error"] == "Unauthorized retask"
        assert server.pending.empty()
