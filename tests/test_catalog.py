"""Tests for worker discovery and launching.

The catalog is the only place the cross-language layout is written down, so a
mistake here means a worker that silently never joins the team — the worst
failure mode in the project, because the run completes and just produces fewer
games than expected.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="orchestra-tests-"))
os.environ.setdefault("BOARD_PATH", str(_TMP / "board.sqlite"))

from orchestra.orchestrator import catalog  # noqa: E402


def test_every_manifest_entry_is_complete() -> None:
    for worker in catalog.WORKERS:
        assert {"key", "name", "colour", "runner", "file"} <= worker.keys()
        assert worker["runner"] in {"python", "node"}
        if worker["runner"] == "python":
            assert "module" in worker


def test_keys_and_colours_are_unique() -> None:
    """The key is the folder name and the colour is the board legend; collisions
    would silently merge two builders in the UI."""
    keys = [w["key"] for w in catalog.WORKERS]
    assert len(keys) == len(set(keys))
    colours = [w["colour"] for w in catalog.WORKERS]
    assert len(colours) == len(set(colours))


def test_every_python_worker_file_ships_in_tree() -> None:
    for worker in catalog.WORKERS:
        if worker["runner"] == "python":
            assert worker["file"].exists(), f"missing worker file: {worker['file']}"


def test_discover_finds_the_python_workers() -> None:
    keys = {w["key"] for w in catalog.discover()}
    assert {"strands", "pydantic", "maf", "agno"} <= keys


def test_discover_sets_the_slug_to_the_key() -> None:
    assert all(w["slug"] == w["key"] for w in catalog.discover())


def test_skip_removes_a_worker() -> None:
    keys = {w["key"] for w in catalog.discover(skip=("agno", "maf"))}
    assert "agno" not in keys and "maf" not in keys
    assert "strands" in keys


def test_python_workers_launch_with_this_interpreter() -> None:
    """A bare 'uv run' could resolve a different virtualenv; a worker that dies on
    import looks exactly like a worker that produced nothing."""
    worker = next(w for w in catalog.discover() if w["runner"] == "python")
    argv = catalog.launch_argv(worker, 7, Path("/tmp/board.sqlite"))
    assert argv[:2] == [sys.executable, "-m"]
    assert argv[2] == worker["module"]
    assert argv[3:] == ["7", "/tmp/board.sqlite"]


def test_the_task_id_and_board_path_are_the_worker_contract() -> None:
    """Every worker, in every language, takes exactly these two positional args."""
    for worker in catalog.WORKERS:
        argv = catalog.launch_argv(worker, 42, Path("/tmp/b.sqlite"))
        assert argv[-2:] == ["42", "/tmp/b.sqlite"]
