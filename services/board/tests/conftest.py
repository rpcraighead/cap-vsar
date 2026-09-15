"""Build a freshly configured board app per test.

settings.py reads the environment once at import, which is what makes the
running service simple; tests therefore reload it rather than poke at module
globals, so each case gets a genuine cold start with its own configuration.
"""
from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SAMPLE_BOARD = """# CAP V-SAR Agent Coordination Board

---

## 1. User Dispatch Queue (Prompt From Here)
*Ron: Write or update tasks below.*

- [ ] **@Claude**: finish the C182 model
- [x] **@Antigravity (Gemini)**: build the FDR tap
- [ ] **@Codex**: fly card H0 run 6

---

## 2. Active Agent Lane Status & File Locks

| Agent | Current Work / Focus | Locked Paths (DO NOT TOUCH) | Status |
|---|---|---|---|
| **Claude** | CAP 487 C182 model | `xplane/**` | ACTIVE / User confirmed |
| **Codex** | Available | — | IDLE / Ready |

---

## 3. Contract Changes & Interface Broadcasts

- **[2026-09-11 | Codex] AI Pilot Maneuver Server**: lease tokens.

---

## 4. Completed Handoffs & Results Log (Last 5)

- **2026-09-14 [Codex O-8]**: single HTTPS portal deployed on ms01.
"""

ENV_KEYS = [k for k in os.environ if k.startswith("CAPVSAR_BOARD")]


@pytest.fixture
def make_app(tmp_path, monkeypatch):
    """Return a factory: make_app(**env_overrides) -> TestClient."""
    def factory(board_text: str = SAMPLE_BOARD, repo: Path | None = None, **env):
        for key in ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        root = repo or tmp_path / "repo"
        (root / "docs").mkdir(parents=True, exist_ok=True)
        if board_text is not None:
            (root / "docs" / "BOARD.md").write_text(board_text, encoding="utf-8")

        monkeypatch.setenv("CAPVSAR_BOARD_REPO", str(root))
        monkeypatch.setenv("CAPVSAR_BOARD_GIT_SYNC", env.pop("git_sync", "0"))
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        from app import settings as settings_mod
        importlib.reload(settings_mod)
        from app import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app), root

    return factory


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ,
                               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.invalid",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.invalid",
                               "GIT_TERMINAL_PROMPT": "0"})


@pytest.fixture
def git_repo(tmp_path):
    """An upstream bare repo plus a working clone holding the board."""
    upstream = tmp_path / "upstream.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(upstream)],
                   capture_output=True, check=True)
    subprocess.run(["git", "clone", str(upstream), str(work)],
                   capture_output=True, check=True)
    (work / "docs").mkdir(parents=True)
    (work / "docs" / "BOARD.md").write_text(SAMPLE_BOARD, encoding="utf-8")
    git("add", "docs/BOARD.md", cwd=work)
    git("commit", "-m", "seed board", cwd=work)
    git("push", "origin", "HEAD:main", cwd=work)
    return upstream, work
