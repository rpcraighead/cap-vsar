#!/usr/bin/env python3
"""Dispatch open docs/BOARD.md tasks to the agent CLIs.

The board has always been a queue that a human drained by hand: click Copy
Prompt on the web deck, paste into a chat. This runs the same prompt through
each agent's non-interactive CLI instead, so a queued task actually starts.

Deliberate limits, because this starts agents that write to a shared working
tree with no branch isolation (board standing rule 1):

  * No auto-approve option. Each agent runs in its own default mode, so its
    normal sandbox and per-change approvals still apply. If you want an agent
    to apply edits unattended, run that agent's CLI yourself and own the
    choice; this script will not make it for you.
  * Dry run is the default. Dispatch requires --execute.
  * One task at a time unless you ask for more, so two agents do not edit the
    same tree concurrently by accident.
  * Checkboxes are never ticked here. Agents post their own receipt in board
    section 4 when they finish; a task that was dispatched but failed must not
    look completed.

Usage:
    scripts/dispatch_board.py --list
    scripts/dispatch_board.py --task 6                  # dry run, shows command
    scripts/dispatch_board.py --task 6 --execute
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from services.ai_pilot import board_manager  # noqa: E402

LOG_DIR = REPO / "logs" / "dispatch"

CODEX = Path("/usr/lib/chatgpt/resources/codex")
AGY = Path.home() / ".gemini" / "bin" / "agy"

# The exact prompt the board's Copy Prompt button builds, so a dispatched run
# and a pasted run are the same request.
PROMPT = "Check docs/BOARD.md and execute the active task assigned to you: {task}"


def build_command(agent: str, prompt: str) -> list[str]:
    """Map a board agent name to its non-interactive CLI invocation."""
    name = agent.lower()

    if "codex" in name:
        if not CODEX.is_file():
            raise SystemExit(f"codex binary not found at {CODEX}")
        # workspace-write, not danger-full-access: the agent may edit this
        # repo and nothing outside it. Stated explicitly rather than inherited
        # from config, so the blast radius is visible here.
        return [str(CODEX), "exec", "--cd", str(REPO),
                "--sandbox", "workspace-write", prompt]

    if "gemini" in name or "antigravity" in name:
        if not AGY.is_file():
            raise SystemExit(f"agy binary not found at {AGY}")
        # agy uses Go-style flags: --print takes its value attached. Passing
        # it bare lets it swallow the next flag as the prompt.
        return [str(AGY), "--add-dir", str(REPO),
                "--print-timeout", "45m", f"--print={prompt}"]

    raise SystemExit(
        f"No CLI mapping for agent {agent!r}. Claude tasks are handled in the "
        f"Claude Code session itself, not dispatched from here."
    )


# Phrases that mean the agent started, was refused, and exited without working.
# Headless runs hit these because a tool permission prompt has nobody to answer
# it, and the process still exits 0.
DID_NOTHING_MARKERS = (
    "no output produced",
    "cannot prompt for",
    "was auto-denied",
    "dangerously-skip-permissions",
    "permission denied by",
)


def did_nothing(output: str) -> str:
    """Return a reason string if the output shows the agent was blocked."""
    low = output.lower()
    for marker in DID_NOTHING_MARKERS:
        if marker in low:
            return f"agent was blocked ({marker!r} in output)"
    if not output.strip():
        return "agent produced no output at all"
    return ""


def warn_if_tree_dirty() -> None:
    """A dirty tree is the main way a dispatched agent causes a surprise."""
    try:
        out = subprocess.run(["git", "status", "--short"], cwd=REPO,
                             capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        return
    if out:
        print("WARNING: the working tree has uncommitted changes. A dispatched")
        print("agent may sweep them into its own commit. Consider committing first:")
        for line in out.splitlines()[:10]:
            print(f"    {line}")
        print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="show board tasks and exit")
    ap.add_argument("--agent", help="restrict to this agent (substring match)")
    ap.add_argument("--task", type=int, action="append",
                    help="board task id to dispatch (repeatable)")
    ap.add_argument("--execute", action="store_true",
                    help="actually run; without this the command is only printed")
    args = ap.parse_args()

    tasks = board_manager.read_board()["tasks"]

    if args.list or not (args.agent or args.task):
        for t in tasks:
            mark = "x" if t["completed"] else " "
            print(f"[{mark}] {t['id']:>2}  {t['agent']:<22}  {t['task'][:68]}")
        if not (args.agent or args.task):
            print("\nSelect work with --task ID (repeatable) or --agent NAME.")
        return 0

    selected = [t for t in tasks if not t["completed"]]
    if args.agent:
        selected = [t for t in selected if args.agent.lower() in t["agent"].lower()]
    if args.task:
        selected = [t for t in selected if t["id"] in args.task]

    if not selected:
        print("No matching open tasks.")
        return 1

    if not args.execute:
        print("DRY RUN - nothing will start. Re-run with --execute.\n")

    warn_if_tree_dirty()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    failures = 0

    for t in selected:
        cmd = build_command(t["agent"], PROMPT.format(task=t["task"]))

        if not args.execute:
            print(f"--- task {t['id']} ({t['agent']}) ---")
            print(" ".join(repr(c) if " " in c else c for c in cmd))
            print()
            continue

        slug = "".join(ch if ch.isalnum() else "-" for ch in t["agent"]).strip("-")
        log_path = LOG_DIR / f"{stamp}_task{t['id']}_{slug}.log"
        print(f"[{t['id']}] {t['agent']} -> {log_path.relative_to(REPO)}")

        with open(log_path, "w", encoding="utf-8") as log:
            log.write(f"# dispatched {dt.datetime.now().isoformat()}\n")
            log.write(f"# agent: {t['agent']}\n# task: {t['task']}\n")
            log.write(f"# command: {cmd}\n\n")
            log.flush()
            proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                                  stdin=subprocess.DEVNULL,
                                  env={**os.environ, "TERM": "dumb"})
            output = (proc.stdout or "") + (proc.stderr or "")
            log.write(output)

        rc, problem = proc.returncode, did_nothing(output)

        # Exit code alone is not a completion signal. An agent that was denied
        # every tool call in headless mode exits 0 having done nothing, which
        # is the one outcome that must not read as success.
        if problem:
            print(f"     NO WORK DONE (rc={rc}): {problem}")
            failures += 1
        elif rc != 0:
            print(f"     FAILED rc={rc} - see the log")
            failures += 1
        else:
            print(f"     rc=0 - check the log and `git status` for actual changes")

    if args.execute:
        print("\nAgents post their own receipt in board section 4. "
              "This script does not tick checkboxes.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
