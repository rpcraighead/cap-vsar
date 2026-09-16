"""
The read-modify-write cycle for the board file, and the only place that holds
the lock.

Ordering matters and is deliberate: a mutation pulls first with no coalescing
window, so it edits the current board rather than a cached one, then writes,
then commits and pushes. A read may use the coalescing window, because a read
that is a few seconds stale is fine and a pull per poll per open tab is not.
"""
from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path
from typing import Any, Dict, Tuple

from . import board_manager
from .git_sync import SyncResult


class BoardStore:
    def __init__(self, path: Path, relpath: str, sync, pull_interval: float) -> None:
        self.path = path
        self.relpath = relpath
        self.sync = sync
        self.pull_interval = pull_interval
        self._lock = threading.Lock()
        self._last_sync: SyncResult = SyncResult(True, "not yet synced")
        self._last_sync_at: str = ""

    # -- helpers ----------------------------------------------------------

    def _read_text(self) -> str:
        if not self.path.is_file():
            return ""
        return self.path.read_text(encoding="utf-8")

    def _write_text(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")

    def _record(self, result: SyncResult) -> None:
        self._last_sync = result
        self._last_sync_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    def _envelope(self, text: str) -> Dict[str, Any]:
        board = board_manager.parse_board(text)
        board["sync"] = {
            "enabled": self.sync.is_repo(),
            "ok": self._last_sync.ok,
            "detail": self._last_sync.detail,
            "error": self._last_sync.error,
            "at": self._last_sync_at,
        }
        board["board_path"] = self.relpath
        board["server_time"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        return board

    def _commit(self, summary: str) -> None:
        self._record(self.sync.commit_and_push(self.relpath, f"board: {summary}"))

    # -- API --------------------------------------------------------------

    def read(self) -> Dict[str, Any]:
        with self._lock:
            self._record(self.sync.pull(min_interval=self.pull_interval))
            return self._envelope(self._read_text())

    def add_task(self, agent: str, task_text: str) -> Dict[str, Any]:
        with self._lock:
            self._record(self.sync.pull())
            text = board_manager.insert_task(self._read_text(), agent, task_text)
            self._write_text(text)
            self._commit(f"queue a task for {agent.replace('@', '').strip()}")
            return self._envelope(text)

    def toggle_task(self, index: int, completed: bool) -> Tuple[Dict[str, Any], bool]:
        with self._lock:
            self._record(self.sync.pull())
            text, found = board_manager.set_task_state(self._read_text(), index, completed)
            if not found:
                return self._envelope(self._read_text()), False
            self._write_text(text)
            self._commit(f"mark task {index} {'done' if completed else 'open'}")
            return self._envelope(text), True

    def save_raw(self, markdown: str) -> Dict[str, Any]:
        with self._lock:
            self._record(self.sync.pull())
            text = markdown.strip() + "\n"
            self._write_text(text)
            self._commit("edit the board directly")
            return self._envelope(text)
