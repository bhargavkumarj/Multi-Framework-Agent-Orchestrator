"""Tests for the shared board.

The board is the coordination substrate: five agent processes, written in five
frameworks, in three languages' worth of runtimes, read and write this one SQLite
file concurrently. If the board is wrong, the whole team is wrong, and the
failure looks like an LLM problem when it is a locking problem.

These tests need no API key and call no model.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="orchestra-tests-"))
os.environ["BOARD_PATH"] = str(_TMP / "board.sqlite")

from orchestra.core import board  # noqa: E402


@pytest.fixture
def fresh_board(tmp_path: Path) -> Path:
    path = tmp_path / "board.sqlite"
    board.reset_board(path)
    return path


def test_reset_creates_an_empty_board(fresh_board: Path) -> None:
    assert board.list_todos(fresh_board) == []


def test_a_goal_gets_an_id_and_appears(fresh_board: Path) -> None:
    goal_id = board.add_goal("Build a game", fresh_board)
    todos = board.list_todos(fresh_board)
    assert len(todos) == 1
    assert todos[0]["id"] == goal_id
    assert todos[0]["parent_id"] is None
    assert todos[0]["status"] == "pending"


def test_steps_hang_off_their_goal(fresh_board: Path) -> None:
    """parent_id is the entire hierarchy: None means goal, set means step."""
    goal_id = board.add_goal("Build a game", fresh_board)
    step_ids = [board.add_step(goal_id, f"Step {i}", fresh_board) for i in range(3)]

    todos = board.list_todos(fresh_board)
    steps = [t for t in todos if t["parent_id"] == goal_id]
    assert [s["id"] for s in steps] == step_ids


def test_claiming_marks_a_todo_in_progress(fresh_board: Path) -> None:
    goal_id = board.add_goal("Build a game", fresh_board)
    board.claim_todo(goal_id, fresh_board)
    assert board.list_todos(fresh_board)[0]["status"] == "in_progress"


def test_completing_records_the_result(fresh_board: Path) -> None:
    goal_id = board.add_goal("Build a game", fresh_board)
    board.complete_todo(goal_id, "Built colours.html", fresh_board)
    todo = board.list_todos(fresh_board)[0]
    assert todo["status"] == "done"
    assert todo["result"] == "Built colours.html"


def test_ordering_is_insertion_order(fresh_board: Path) -> None:
    """The live board renders in this order, so it has to be stable."""
    ids = [board.add_goal(f"Goal {i}", fresh_board) for i in range(5)]
    assert [t["id"] for t in board.list_todos(fresh_board)] == ids


def test_reset_drops_previous_work(fresh_board: Path) -> None:
    board.add_goal("Old goal", fresh_board)
    board.reset_board(fresh_board)
    assert board.list_todos(fresh_board) == []


def test_wal_mode_is_on(fresh_board: Path) -> None:
    """WAL is what lets the orchestrator paint the board while five workers write."""
    conn = sqlite3.connect(fresh_board)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_concurrent_writers_do_not_lose_work(fresh_board: Path) -> None:
    """Five builders claiming and completing at once is the normal case, not the edge."""
    goal_ids = [board.add_goal(f"Goal {i}", fresh_board) for i in range(5)]

    def work(goal_id: int) -> None:
        board.claim_todo(goal_id, fresh_board)
        for step in range(4):
            step_id = board.add_step(goal_id, f"Step {step} of {goal_id}", fresh_board)
            board.complete_todo(step_id, "ok", fresh_board)
        board.complete_todo(goal_id, "done", fresh_board)

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(work, goal_ids))

    todos = board.list_todos(fresh_board)
    assert len(todos) == 5 + 5 * 4
    assert all(todo["status"] == "done" for todo in todos)
