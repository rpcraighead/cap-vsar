"""
Parse and rewrite the shared agent coordination board (`docs/BOARD.md`).

Everything here is a pure function over the markdown text. The board is a file
in git that three agents and a human all edit, so the read-modify-write cycle
belongs to whoever holds the lock and the git working tree - see store.py.
Keeping the parsing free of I/O is also what makes the format testable without
a repository on disk.

The section headings and the task line shape are a wire format: agents append
to this file by hand from their own sessions. Do not tighten these patterns
without updating docs/BOARD.md's own instructions to agents.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

SECTION_QUEUE = "## 1. User Dispatch Queue (Prompt From Here)"
SECTION_LANES = "## 2. Active Agent Lane Status"
SECTION_CONTRACTS = "## 3. Contract Changes"
SECTION_HANDOFFS = "## 4. Completed Handoffs"

# - [ ] **@Codex**: do the thing
TASK_RE = re.compile(r"^\s*-\s*\[([ xX])\]\s*\*\*@?([^*:]+)\*\*:\s*(.*)$", re.MULTILINE)
# Same line, split so the state character can be replaced in place.
TASK_TOGGLE_RE = re.compile(
    r"^(\s*-\s*\[)([ xX])(\]\s*\*\*@?[^*:]+\*\*:\s*.*)$", re.MULTILINE
)


def _section_lines(text: str, heading: str) -> List[str]:
    """Lines belonging to the section introduced by `heading`."""
    out: List[str] = []
    inside = False
    for line in text.splitlines():
        if heading in line:
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside:
            out.append(line)
    return out


def _bullets(text: str, heading: str) -> List[str]:
    items = []
    for line in _section_lines(text, heading):
        stripped = line.strip()
        if stripped.startswith("-"):
            item = stripped.lstrip("-").strip()
            if item:
                items.append(item)
    return items


def parse_tasks(text: str) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    for idx, match in enumerate(TASK_RE.finditer(text)):
        tasks.append({
            "id": idx,
            "agent": match.group(2).strip(),
            "task": match.group(3).strip(),
            "completed": match.group(1).lower() == "x",
        })
    return tasks


def parse_locks(text: str) -> List[Dict[str, str]]:
    """The lane table in section 2, minus its header and separator rows."""
    locks: List[Dict[str, str]] = []
    for line in _section_lines(text, SECTION_LANES):
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|---"):
            continue
        cols = [c.strip() for c in stripped.split("|")[1:-1]]
        if len(cols) >= 4 and cols[0].lower() != "agent":
            locks.append({
                "agent": cols[0].replace("**", ""),
                "focus": cols[1],
                "paths": cols[2].replace("`", ""),
                "status": cols[3],
            })
    return locks


def parse_board(text: str) -> Dict[str, Any]:
    """Parse the whole board into the shape the UI renders."""
    return {
        "tasks": parse_tasks(text),
        "locks": parse_locks(text),
        "contracts": _bullets(text, SECTION_CONTRACTS),
        "handoffs": _bullets(text, SECTION_HANDOFFS),
        "raw": text,
    }


def insert_task(text: str, agent: str, task_text: str) -> str:
    """Append a task to the dispatch queue, returning the new markdown."""
    clean_agent = agent.replace("@", "").strip()
    # A newline in either field would forge additional board lines.
    clean_agent = " ".join(clean_agent.split())
    clean_task = " ".join(task_text.split())
    new_item = f"- [ ] **@{clean_agent}**: {clean_task}"

    pos = text.find(SECTION_QUEUE)
    if pos != -1:
        end_pos = text.find("---", pos)
        if end_pos != -1:
            chunk = text[pos:end_pos].rstrip()
            return text[:pos] + chunk + "\n" + new_item + "\n\n" + text[end_pos:]

    # No recognisable queue section: append rather than lose the task.
    return text.rstrip("\n") + "\n" + new_item + "\n"


def set_task_state(text: str, task_index: int, completed: bool) -> Tuple[str, bool]:
    """Tick or untick one task by its index in document order."""
    matches = list(TASK_TOGGLE_RE.finditer(text))
    if not 0 <= task_index < len(matches):
        return text, False
    m = matches[task_index]
    start, end = m.start(2), m.end(2)
    return text[:start] + ("x" if completed else " ") + text[end:], True
