"""
Keep the container's board file in step with the shared clone in Gitea.

Why git at all: the board is `docs/BOARD.md` inside the capvsar repository, and
agents read it from their own checkouts on the workstation. If the networked
board wrote to a private volume, the file the UI shows and the file the agents
read would drift apart within an hour, which is worse than no networked board.
Pulling before a read and pushing after a write keeps one board.

Every failure here is reported, never swallowed. A board that has quietly
stopped syncing looks exactly like a quiet board, and that confusion is the
same failure the deck's stale-cache bug (AI-7) was about.
"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .settings import log


@dataclass
class SyncResult:
    ok: bool
    detail: str = ""

    @property
    def error(self) -> Optional[str]:
        return None if self.ok else self.detail


class GitSync:
    """Serialised git operations on one working clone.

    The caller holds the board lock, so these never run concurrently; no
    locking is done here.
    """

    def __init__(self, repo: Path, remote: str, branch: str,
                 author_name: str, author_email: str, timeout: int) -> None:
        self.repo = repo
        self.remote = remote
        self.branch = branch
        self.author_name = author_name
        self.author_email = author_email
        self.timeout = timeout
        self._last_pull = 0.0

    # -- plumbing ---------------------------------------------------------

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            # Identity is passed per invocation so the image needs no global
            # git config and the mounted clone's own config is left alone.
            env={
                **_inherited_env(),
                "GIT_AUTHOR_NAME": self.author_name,
                "GIT_AUTHOR_EMAIL": self.author_email,
                "GIT_COMMITTER_NAME": self.author_name,
                "GIT_COMMITTER_EMAIL": self.author_email,
                "GIT_TERMINAL_PROMPT": "0",
            },
        )

    def _run(self, *args: str) -> SyncResult:
        try:
            proc = self._git(*args)
        except subprocess.TimeoutExpired:
            return SyncResult(False, f"git {args[0]} timed out after {self.timeout}s")
        except OSError as exc:
            return SyncResult(False, f"git {args[0]} could not run: {exc}")
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            return SyncResult(False, f"git {args[0]} failed: " + (detail[-1] if detail else "no output"))
        return SyncResult(True, (proc.stdout or "").strip())

    # -- operations -------------------------------------------------------

    def is_repo(self) -> bool:
        return (self.repo / ".git").exists()

    def current_branch(self) -> str:
        """The branch the clone is actually on ("" if detached or unreadable)."""
        try:
            proc = self._git("rev-parse", "--abbrev-ref", "HEAD")
        except (subprocess.TimeoutExpired, OSError):
            return ""
        return (proc.stdout or "").strip() if proc.returncode == 0 else ""

    def _branch_mismatch(self) -> Optional[str]:
        """Refuse to sync a clone that is not on the branch we are configured for.

        Without this, a clone left on some other branch still pushes
        `HEAD:<configured branch>` - which fast-forwards whatever that clone
        happens to be sitting on onto the shared branch. Ticking one checkbox
        would silently publish an unrelated branch. Fail closed instead; the
        board still renders from disk and the UI shows the reason.
        """
        actual = self.current_branch()
        if actual and actual != self.branch:
            return (f"clone is on branch {actual!r} but this service is configured for "
                    f"{self.branch!r} - refusing to sync across branches")
        return None

    def pull(self, min_interval: float = 0.0) -> SyncResult:
        """Fast-forward the clone. Coalesced so polling tabs cannot flood it."""
        mismatch = self._branch_mismatch()
        if mismatch:
            return SyncResult(False, mismatch)
        now = time.monotonic()
        if min_interval and (now - self._last_pull) < min_interval:
            return SyncResult(True, "skipped: pulled recently")
        self._last_pull = now
        return self._run("pull", "--ff-only", self.remote, self.branch)

    def commit_and_push(self, relpath: str, message: str) -> SyncResult:
        """Stage exactly one file, commit it, and push.

        The pathspec is a single relative path and never `-A`: three agents
        leave work in progress in this tree, and a board edit must not sweep
        their uncommitted changes into its own commit.
        """
        mismatch = self._branch_mismatch()
        if mismatch:
            return SyncResult(False, mismatch)

        staged = self._run("add", "--", relpath)
        if not staged.ok:
            return staged

        # Nothing staged means the write was a no-op; that is success, not a
        # failure, and `git commit` would exit 1 on it.
        if self._git("diff", "--cached", "--quiet", "--", relpath).returncode == 0:
            return SyncResult(True, "no change to commit")

        committed = self._run("commit", "-m", message, "--only", "--", relpath)
        if not committed.ok:
            return committed

        pushed = self._run("push", self.remote, f"HEAD:{self.branch}")
        if pushed.ok:
            return SyncResult(True, "pushed")

        # Someone else pushed between our pull and our push. Rebase the single
        # board commit on top and try once more. One retry only: if it still
        # fails the commit is safe locally and a human should look.
        log.warning("board push rejected, rebasing once: %s", pushed.detail)
        rebased = self._run("pull", "--rebase", self.remote, self.branch)
        if not rebased.ok:
            self._run("rebase", "--abort")
            return SyncResult(
                False,
                f"committed locally but not pushed ({pushed.detail}); rebase failed: {rebased.detail}",
            )
        retried = self._run("push", self.remote, f"HEAD:{self.branch}")
        if retried.ok:
            return SyncResult(True, "pushed after rebase")
        return SyncResult(
            False, f"committed locally but not pushed: {retried.detail}"
        )


def _inherited_env() -> dict:
    """Environment git needs: PATH, HOME, and the SSH command/key wiring."""
    keep = ("PATH", "HOME", "GIT_SSH_COMMAND", "SSH_AUTH_SOCK", "LANG", "LC_ALL")
    return {k: os.environ[k] for k in keep if k in os.environ}


class NullSync:
    """Git sync switched off: the board is just a file on disk."""

    def is_repo(self) -> bool:
        return False

    def pull(self, min_interval: float = 0.0) -> SyncResult:
        return SyncResult(True, "git sync disabled")

    def commit_and_push(self, relpath: str, message: str) -> SyncResult:
        return SyncResult(True, "git sync disabled")
