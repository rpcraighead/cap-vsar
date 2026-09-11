"""
Board Manager
-------------
Reads, parses, and writes the shared agent coordination board (`docs/BOARD.md`).
Provides structured data for the Web UI and updates the markdown file on disk.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_pilot.board")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BOARD_PATH = REPO_ROOT / "docs" / "BOARD.md"

_lock = threading.Lock()


def get_board_path() -> Path:
    return BOARD_PATH


def read_board() -> Dict[str, Any]:
    """Parse docs/BOARD.md into structured sections."""
    with _lock:
        if not BOARD_PATH.is_file():
            return {
                "tasks": [],
                "locks": [],
                "contracts": [],
                "handoffs": [],
                "raw": "",
            }

        text = BOARD_PATH.read_text(encoding="utf-8")

    # 1. Parse Tasks
    tasks: List[Dict[str, Any]] = []
    task_regex = re.compile(r"^\s*-\s*\[([ xX])\]\s*\*\*@?([^*:]+)\*\*:\s*(.*)$", re.MULTILINE)
    for idx, match in enumerate(task_regex.finditer(text)):
        done = match.group(1).lower() == "x"
        agent = match.group(2).strip()
        desc = match.group(3).strip()
        tasks.append({
            "id": idx,
            "agent": agent,
            "task": desc,
            "completed": done,
        })

    # 2. Parse Locks Table
    locks: List[Dict[str, str]] = []
    lines = text.splitlines()
    in_locks = False
    for line in lines:
        if "## 2. Active Agent Lane Status" in line:
            in_locks = True
            continue
        elif in_locks and line.startswith("## "):
            in_locks = False
            continue
        elif in_locks and line.strip().startswith("|") and not line.strip().startswith("|---"):
            cols = [c.strip() for c in line.strip().split("|")[1:-1]]
            if len(cols) >= 4 and cols[0].lower() != "agent":
                locks.append({
                    "agent": cols[0].replace("**", ""),
                    "focus": cols[1],
                    "paths": cols[2].replace("`", ""),
                    "status": cols[3],
                })

    # 3. Parse Contracts
    contracts: List[str] = []
    in_contracts = False
    for line in lines:
        if "## 3. Contract Changes" in line:
            in_contracts = True
            continue
        elif in_contracts and line.startswith("## "):
            in_contracts = False
            continue
        elif in_contracts and line.strip().startswith("-"):
            item = line.strip().lstrip("-").strip()
            if item:
                contracts.append(item)

    # 4. Parse Handoffs
    handoffs: List[str] = []
    in_handoffs = False
    for line in lines:
        if "## 4. Completed Handoffs" in line:
            in_handoffs = True
            continue
        elif in_handoffs and line.startswith("## "):
            in_handoffs = False
            continue
        elif in_handoffs and line.strip().startswith("-"):
            item = line.strip().lstrip("-").strip()
            if item:
                handoffs.append(item)

    return {
        "tasks": tasks,
        "locks": locks,
        "contracts": contracts,
        "handoffs": handoffs,
        "raw": text,
    }


def add_task(agent: str, task_text: str) -> None:
    """Add a new task for an agent to the User Dispatch Queue."""
    with _lock:
        if not BOARD_PATH.is_file():
            return
        content = BOARD_PATH.read_text(encoding="utf-8")

        # Clean agent tag
        clean_agent = agent.replace("@", "").strip()
        new_item = f"- [ ] **@{clean_agent}**: {task_text.strip()}"

        # Find where to insert under Section 1
        sec1 = "## 1. User Dispatch Queue (Prompt From Here)"
        pos = content.find(sec1)
        if pos != -1:
            end_pos = content.find("---", pos)
            if end_pos != -1:
                chunk = content[pos:end_pos].rstrip()
                updated_chunk = chunk + "\n" + new_item + "\n\n"
                new_content = content[:pos] + updated_chunk + content[end_pos:]
                BOARD_PATH.write_text(new_content, encoding="utf-8")
                return

        # Fallback append
        BOARD_PATH.write_text(content + "\n" + new_item, encoding="utf-8")


def toggle_task(task_index: int, completed: bool) -> bool:
    """Toggle a task's checkbox between [ ] and [x]."""
    with _lock:
        if not BOARD_PATH.is_file():
            return False
        content = BOARD_PATH.read_text(encoding="utf-8")

        task_regex = re.compile(r"^(\s*-\s*\[)([ xX])(\]\s*\*\*@?[^*:]+\*\*:\s*.*)$", re.MULTILINE)
        matches = list(task_regex.finditer(content))
        if 0 <= task_index < len(matches):
            m = matches[task_index]
            new_char = "x" if completed else " "
            start, end = m.start(2), m.end(2)
            new_content = content[:start] + new_char + content[end:]
            BOARD_PATH.write_text(new_content, encoding="utf-8")
            return True
    return False


def save_raw_markdown(new_markdown: str) -> None:
    """Save full updated raw markdown."""
    with _lock:
        BOARD_PATH.write_text(new_markdown.strip() + "\n", encoding="utf-8")
