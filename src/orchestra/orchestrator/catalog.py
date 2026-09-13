"""The worker manifest: who is on the team, how to launch them, what colour they fly.

Five builders, five frameworks, one shape. Each is an agent that reads a goal off
the shared board, writes its own steps under it, works them with filesystem tools,
and ticks them off. They differ only in idiom — that sameness is what lets a
single orchestrator command all of them without knowing anything about any
framework.

Discovery is "is the file there", so a team is whatever is installed. Four Python
workers ship in-tree; the Mastra one is TypeScript and only joins if its
dependencies have been installed with npm.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from orchestra.config import PROJECT_ROOT

PYTHON_WORKERS = PROJECT_ROOT / "src" / "orchestra" / "workers"
TS_WORKERS = PROJECT_ROOT / "workers_ts"

#: One record per framework, in the order they are taught.
#:   key     also the slug — the folder its game is built into
#:   module  Python workers are launched as modules, so the package imports cleanly
#:   path    TypeScript workers are launched by file path through npx tsx
#:   colour  a rich colour, so the live board reads at a glance
WORKERS: list[dict] = [
    {
        "key": "strands",
        "name": "AWS Strands",
        "colour": "cyan",
        "runner": "python",
        "module": "orchestra.workers.strands_worker",
        "file": PYTHON_WORKERS / "strands_worker.py",
    },
    {
        "key": "pydantic",
        "name": "Pydantic AI",
        "colour": "green",
        "runner": "python",
        "module": "orchestra.workers.pydantic_worker",
        "file": PYTHON_WORKERS / "pydantic_worker.py",
    },
    {
        "key": "maf",
        "name": "Microsoft Agent Framework",
        "colour": "magenta",
        "runner": "python",
        "module": "orchestra.workers.maf_worker",
        "file": PYTHON_WORKERS / "maf_worker.py",
    },
    {
        "key": "agno",
        "name": "Agno",
        "colour": "yellow",
        "runner": "python",
        "module": "orchestra.workers.agno_worker",
        "file": PYTHON_WORKERS / "agno_worker.py",
    },
    {
        "key": "mastra",
        "name": "Mastra (TypeScript)",
        "colour": "blue",
        "runner": "node",
        "file": TS_WORKERS / "worker.ts",
    },
]


def _available(worker: dict) -> bool:
    """Whether this worker can actually be launched right now."""
    if not worker["file"].exists():
        return False
    if worker["runner"] == "node":
        # tsx runs from node_modules; without an npm install this worker cannot start.
        return (TS_WORKERS / "node_modules").exists() and bool(shutil.which("npx"))
    return True


def discover(skip: tuple[str, ...] = ()) -> list[dict]:
    """The launchable workers, minus any skipped by key, each with its slug set."""
    return [
        {**worker, "slug": worker["key"]}
        for worker in WORKERS
        if worker["key"] not in skip and _available(worker)
    ]


def launch_argv(worker: dict, task_id: int, board_path: Path) -> list[str]:
    """The subprocess argv that runs one worker against the shared board.

    Python workers go through ``sys.executable -m``, which guarantees the child
    shares this interpreter and virtualenv — the alternative, a bare ``uv run``,
    can silently resolve to a different environment, and a worker that dies on
    import looks identical to a worker that produced nothing.

    ``npx`` is resolved with ``shutil.which`` first because on Windows it is a
    ``.cmd`` shim and ``subprocess.Popen`` does not consult ``PATHEXT``.
    """
    if worker["runner"] == "python":
        return [sys.executable, "-m", worker["module"], str(task_id), str(board_path)]
    return [shutil.which("npx") or "npx", "tsx", str(worker["file"]), str(task_id), str(board_path)]


def launch_cwd(worker: dict) -> str:
    """Where to start the worker's process."""
    return str(PROJECT_ROOT if worker["runner"] == "python" else TS_WORKERS)
