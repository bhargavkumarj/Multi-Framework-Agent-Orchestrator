"""Every knob the run has, in one place.

Two models matter: the one the orchestrator (and its QA and art-director
sub-agents) runs on, and the one shared by the five builder workers. The
orchestrator passes ``WORKER_MODEL`` down to each worker through the environment,
so one setting reaches every framework — including the TypeScript one, which
never imports this file.

The timeouts are not decoration. Every one of them is the answer to "what happens
if this never returns?", and in a system that spawns subprocesses that spawn
browsers, that question has to have an answer everywhere.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent

#: Where the arcade is built, and where the shared board file lives.
SITE_DIR = Path(os.environ.get("SITE_DIR", PROJECT_ROOT / "site")).resolve()
BOARD_PATH = SITE_DIR / "board.sqlite"

#: The ADK agent that leads the team, authors the look, and judges the games.
ORCHESTRATOR_MODEL = os.environ.get("ORCHESTRATOR_MODEL", "gemini-3.5-flash")  # cheaper: gemini-3.1-flash-lite
#: The model every builder worker runs on, whatever framework it is written in.
WORKER_MODEL = os.environ.get("WORKER_MODEL", "gpt-5.5")  # cheaper: gpt-5.4-mini

#: Bounds the outer loop. The happy path is roughly 15 calls; this stops a
#: confused orchestrator from thrashing between test and relaunch forever.
MAX_ORCHESTRATOR_CALLS = int(os.environ.get("MAX_ORCHESTRATOR_CALLS", "80"))
#: One QA agent's budget for judging one game. A quick check needs about five.
MAX_QA_CALLS = int(os.environ.get("MAX_QA_CALLS", "25"))

#: A worker still running after this is killed, along with its whole child tree,
#: so a single hung framework cannot stall the run.
WORKER_TIMEOUT_S = int(os.environ.get("WORKER_TIMEOUT_S", "300"))
#: A browser QA wedged past this is abandoned and its game left as built.
QA_TIMEOUT_S = int(os.environ.get("QA_TIMEOUT_S", "150"))
#: Bounds MCP teardown, so a wedged browser cannot hang the run on the way out.
CLOSE_TIMEOUT_S = int(os.environ.get("CLOSE_TIMEOUT_S", "10"))

#: Run the QA browser without a window (CI, or when you do not want Chrome
#: stealing focus five times).
QA_HEADLESS = os.environ.get("QA_HEADLESS") == "1"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
