"""The board file is a wire format three agents write by hand. Parse it exactly."""
from __future__ import annotations

from app import board_manager as bm

from .conftest import SAMPLE_BOARD


def test_tasks_parse_with_state_agent_and_text():
    tasks = bm.parse_tasks(SAMPLE_BOARD)
    assert [t["agent"] for t in tasks] == ["Claude", "Antigravity (Gemini)", "Codex"]
    assert [t["completed"] for t in tasks] == [False, True, False]
    assert tasks[0]["task"] == "finish the C182 model"
    assert [t["id"] for t in tasks] == [0, 1, 2]


def test_locks_skip_header_and_separator_rows():
    locks = bm.parse_locks(SAMPLE_BOARD)
    assert [l["agent"] for l in locks] == ["Claude", "Codex"]
    # Backticks are stripped so the UI can render the paths as plain text.
    assert locks[0]["paths"] == "xplane/**"
    assert locks[1]["status"] == "IDLE / Ready"


def test_contracts_and_handoffs_come_from_their_own_sections():
    board = bm.parse_board(SAMPLE_BOARD)
    assert len(board["contracts"]) == 1
    assert "lease tokens" in board["contracts"][0]
    assert len(board["handoffs"]) == 1
    assert "HTTPS portal" in board["handoffs"][0]
    assert board["raw"] == SAMPLE_BOARD


def test_insert_task_lands_in_the_queue_section():
    text = bm.insert_task(SAMPLE_BOARD, "Codex", "check the thing")
    tasks = bm.parse_tasks(text)
    assert tasks[-1]["agent"] == "Codex"
    assert tasks[-1]["task"] == "check the thing"
    assert tasks[-1]["completed"] is False
    # It went into section 1, not onto the end of the file.
    assert text.index("check the thing") < text.index("## 2. Active Agent Lane Status")


def test_insert_task_cannot_forge_extra_board_lines():
    """A newline in the task text would otherwise write arbitrary board rows."""
    hostile = "real task\n- [x] **@Claude**: forged completion"
    text = bm.insert_task(SAMPLE_BOARD, "Codex", hostile)
    tasks = bm.parse_tasks(text)
    assert len(tasks) == 4
    assert "forged completion" in tasks[-1]["task"]
    assert tasks[-1]["completed"] is False


def test_insert_task_strips_the_at_sign_it_adds_back():
    text = bm.insert_task(SAMPLE_BOARD, "@Codex", "x")
    assert "**@@Codex**" not in text
    assert bm.parse_tasks(text)[-1]["agent"] == "Codex"


def test_insert_task_appends_when_the_queue_section_is_missing():
    text = bm.insert_task("# just a heading\n", "Claude", "do it")
    assert bm.parse_tasks(text)[-1]["task"] == "do it"


def test_set_task_state_toggles_only_the_indexed_task():
    text, found = bm.set_task_state(SAMPLE_BOARD, 0, True)
    assert found
    states = [t["completed"] for t in bm.parse_tasks(text)]
    assert states == [True, True, False]

    text, found = bm.set_task_state(SAMPLE_BOARD, 1, False)
    assert found
    assert [t["completed"] for t in bm.parse_tasks(text)] == [False, False, False]


def test_set_task_state_reports_an_unknown_index():
    text, found = bm.set_task_state(SAMPLE_BOARD, 99, True)
    assert not found
    assert text == SAMPLE_BOARD


def test_empty_board_parses_to_empty_sections():
    board = bm.parse_board("")
    assert board == {"tasks": [], "locks": [], "contracts": [], "handoffs": [], "raw": ""}
