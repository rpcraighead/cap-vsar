"""Routes, and the access rules that made this safe to put on the network."""
from __future__ import annotations

import subprocess

import pytest

from .conftest import SAMPLE_BOARD, git

TOKEN = "s3cret-engineering-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_health_reports_configuration(make_app):
    client, _ = make_app()
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["board_present"] is True
    assert body["writes_enabled"] is False
    assert body["git_sync"] is False


def test_get_board_returns_the_parsed_board(make_app):
    client, _ = make_app()
    body = client.get("/api/board").json()
    assert [t["agent"] for t in body["tasks"]] == ["Claude", "Antigravity (Gemini)", "Codex"]
    assert body["board_path"] == "docs/BOARD.md"
    assert body["sync"]["enabled"] is False


def test_api_responses_are_never_cached(make_app):
    """A cached /api/board is indistinguishable from a board nobody updated."""
    client, _ = make_app()
    assert client.get("/api/board").headers["cache-control"] == "no-store"
    assert client.get("/api/health").headers["cache-control"] == "no-store"


def test_writes_fail_closed_when_no_token_is_configured(make_app):
    """An unset credential must disable writes, not accept everyone (X-11)."""
    client, repo = make_app()
    resp = client.post("/api/board/task", json={"agent": "Codex", "task": "x"})
    assert resp.status_code == 503
    assert "CAPVSAR_BOARD_TOKEN" in resp.json()["error"]
    assert repo.joinpath("docs/BOARD.md").read_text(encoding="utf-8") == SAMPLE_BOARD


def test_writes_require_the_right_token(make_app):
    client, _ = make_app(CAPVSAR_BOARD_TOKEN=TOKEN)
    body = {"agent": "Codex", "task": "check the thing"}

    assert client.post("/api/board/task", json=body).status_code == 401
    assert client.post("/api/board/task", json=body,
                       headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/api/board/task", json=body, headers=AUTH).status_code == 200


def test_add_task_persists_to_the_board_file(make_app):
    client, repo = make_app(CAPVSAR_BOARD_TOKEN=TOKEN)
    resp = client.post("/api/board/task",
                       json={"agent": "Codex", "task": "check the thing"}, headers=AUTH)
    assert resp.json()["board"]["tasks"][-1]["task"] == "check the thing"
    assert "check the thing" in repo.joinpath("docs/BOARD.md").read_text(encoding="utf-8")


def test_toggle_marks_the_task_and_reports_an_unknown_index(make_app):
    client, repo = make_app(CAPVSAR_BOARD_TOKEN=TOKEN)

    resp = client.post("/api/board/toggle", json={"index": 0, "completed": True}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["board"]["tasks"][0]["completed"] is True
    assert "- [x] **@Claude**" in repo.joinpath("docs/BOARD.md").read_text(encoding="utf-8")

    missing = client.post("/api/board/toggle", json={"index": 99, "completed": True}, headers=AUTH)
    assert missing.status_code == 404


def test_raw_save_replaces_the_whole_board(make_app):
    client, repo = make_app(CAPVSAR_BOARD_TOKEN=TOKEN)
    new = "# Board\n\n## 1. User Dispatch Queue (Prompt From Here)\n\n- [ ] **@Claude**: only task\n"
    resp = client.post("/api/board/raw", json={"markdown": new}, headers=AUTH)
    assert resp.status_code == 200
    assert [t["task"] for t in resp.json()["board"]["tasks"]] == ["only task"]
    assert repo.joinpath("docs/BOARD.md").read_text(encoding="utf-8").startswith("# Board")


def test_cross_origin_writes_are_refused_when_an_allowlist_is_set(make_app):
    client, _ = make_app(CAPVSAR_BOARD_TOKEN=TOKEN,
                         CAPVSAR_BOARD_ORIGINS="https://ms01")
    hostile = {**AUTH, "Origin": "https://evil.example"}
    assert client.post("/api/board/task", json={"agent": "Codex", "task": "x"},
                       headers=hostile).status_code == 403
    allowed = {**AUTH, "Origin": "https://ms01"}
    assert client.post("/api/board/task", json={"agent": "Codex", "task": "x"},
                       headers=allowed).status_code == 200


def test_the_page_and_its_stylesheet_are_served(make_app):
    client, _ = make_app()
    page = client.get("/")
    assert page.status_code == 200
    assert "AGENT COORDINATION BOARD" in page.text
    # The deck's X-Plane recorder is not in this container.
    assert "fdr" not in page.text.lower()
    assert client.get("/static/style.css").status_code == 200


def test_a_missing_board_file_is_reported_not_crashed(make_app):
    client, repo = make_app(board_text=None)
    repo.joinpath("docs/BOARD.md").unlink(missing_ok=True)
    assert client.get("/api/health").json()["board_present"] is False
    assert client.get("/api/board").json()["tasks"] == []


# -- git-backed board -------------------------------------------------------

def test_a_write_commits_and_pushes_the_board(make_app, git_repo):
    """The point of the container: the board it edits is the shared board."""
    upstream, work = git_repo
    client, _ = make_app(repo=work, git_sync="1", CAPVSAR_BOARD_TOKEN=TOKEN)

    resp = client.post("/api/board/task",
                       json={"agent": "Codex", "task": "networked task"}, headers=AUTH)
    assert resp.status_code == 200
    sync = resp.json()["board"]["sync"]
    assert sync["enabled"] is True
    assert sync["ok"] is True, sync["error"]

    pushed = subprocess.run(["git", "show", "main:docs/BOARD.md"], cwd=upstream,
                            capture_output=True, text=True)
    assert "networked task" in pushed.stdout


def test_a_board_write_does_not_sweep_up_other_agents_work(make_app, git_repo):
    """Three agents leave changes in this tree; a board edit commits one file."""
    _, work = git_repo
    (work / "docs" / "OTHER.md").write_text("an agent's work in progress\n", encoding="utf-8")
    client, _ = make_app(repo=work, git_sync="1", CAPVSAR_BOARD_TOKEN=TOKEN)

    client.post("/api/board/task", json={"agent": "Codex", "task": "t"}, headers=AUTH)

    committed = git("show", "--name-only", "--format=", "HEAD", cwd=work).stdout.split()
    assert committed == ["docs/BOARD.md"]
    assert "OTHER.md" in git("status", "--short", cwd=work).stdout


def test_a_read_pulls_changes_made_elsewhere(make_app, git_repo):
    upstream, work = git_repo
    client, _ = make_app(repo=work, git_sync="1", CAPVSAR_BOARD_TOKEN=TOKEN,
                         CAPVSAR_BOARD_PULL_INTERVAL="0")

    # Someone else edits the board through another clone and pushes.
    other = work.parent / "other"
    subprocess.run(["git", "clone", str(upstream), str(other)], capture_output=True, check=True)
    board = other / "docs" / "BOARD.md"
    board.write_text(board.read_text().replace("finish the C182 model", "landed from elsewhere"),
                     encoding="utf-8")
    git("add", "docs/BOARD.md", cwd=other)
    git("commit", "-m", "elsewhere", cwd=other)
    git("push", "origin", "HEAD:main", cwd=other)

    body = client.get("/api/board").json()
    assert body["sync"]["ok"] is True, body["sync"]["error"]
    assert body["tasks"][0]["task"] == "landed from elsewhere"


def test_a_broken_remote_is_reported_rather_than_hidden(make_app, git_repo):
    """A board that stopped syncing must not look like a board nobody wrote to."""
    _, work = git_repo
    git("remote", "set-url", "origin", str(work.parent / "does-not-exist.git"), cwd=work)
    client, _ = make_app(repo=work, git_sync="1", CAPVSAR_BOARD_TOKEN=TOKEN,
                         CAPVSAR_BOARD_PULL_INTERVAL="0")

    body = client.get("/api/board").json()
    assert body["sync"]["enabled"] is True
    assert body["sync"]["ok"] is False
    assert body["sync"]["error"]
    # The board still renders from the local clone.
    assert len(body["tasks"]) == 3


def test_a_clone_on_the_wrong_branch_refuses_to_sync(make_app, git_repo):
    """The bug this guards: pushing HEAD:<configured branch> from a clone that is
    sitting on some other branch fast-forwards that branch onto the shared one,
    so ticking a checkbox silently publishes unrelated work."""
    upstream, work = git_repo
    main_head = git("rev-parse", "main", cwd=work).stdout.strip()
    git("checkout", "-b", "some-feature", cwd=work)
    (work / "unrelated.txt").write_text("work in progress\n", encoding="utf-8")
    git("add", "unrelated.txt", cwd=work)
    git("commit", "-m", "unrelated feature work", cwd=work)

    client, _ = make_app(repo=work, git_sync="1", CAPVSAR_BOARD_TOKEN=TOKEN,
                         CAPVSAR_BOARD_PULL_INTERVAL="0")

    resp = client.post("/api/board/task",
                       json={"agent": "Codex", "task": "t"}, headers=AUTH)
    sync = resp.json()["board"]["sync"]
    assert sync["ok"] is False
    assert "some-feature" in sync["error"] and "main" in sync["error"]

    # The decisive assertion: upstream main did not move.
    assert subprocess.run(["git", "rev-parse", "main"], cwd=upstream,
                          capture_output=True, text=True).stdout.strip() == main_head


def test_a_read_on_the_wrong_branch_reports_it_and_still_renders(make_app, git_repo):
    _, work = git_repo
    git("checkout", "-b", "some-feature", cwd=work)
    client, _ = make_app(repo=work, git_sync="1", CAPVSAR_BOARD_PULL_INTERVAL="0")

    body = client.get("/api/board").json()
    assert body["sync"]["ok"] is False
    assert "refusing to sync across branches" in body["sync"]["error"]
    assert len(body["tasks"]) == 3
