# Architecture

## 1. The central idea

Most "multi-agent orchestration" is a Python loop with agents inside it. The
control flow is written by a human; the agents fill in the blanks.

Here the loop *is* an agent. The orchestrator is a Google ADK `LlmAgent` given a
goal and six tools, and it decides:

* what each builder should teach (it invents the learning objectives),
* when to start them and when to wait,
* which games to test,
* whether a verdict means "broken",
* who to send back, and with what description of the problem,
* when the arcade is finished.

The tools contain no judgement at all. `launch_worker` starts a subprocess.
`wait_for_team` blocks and paints a board. `test_game` runs a QA agent and
returns its verdict as a string. The split is deliberate and it is the design
principle of the whole project:

> **The agent owns the decisions. The tools own the mechanics.**

Mechanics are where determinism is valuable — process trees, timeouts, file
existence checks. Judgement is where a model earns its cost.

---

## 2. Control flow of a run

```
cli.main
  ├─ set BOARD_PATH and WORKER_MODEL   ← before any framework imports
  ├─ catalog.discover()                ← who is actually installed
  └─ loop.run(language, workers, site, board)
       ├─ board.reset_board()
       ├─ asyncio.run(_run(team))      ← ONE event loop for the entire run
       │    └─ ADK Runner streams the orchestrator agent's turns:
       │         author_style()            → art-director agent writes common.css
       │         launch_worker(×5)         → five subprocesses, returns immediately
       │         wait_for_team()           → rich.Live paints until all exit
       │         test_game(slug) (×5)      → QA agent plays each in Chrome
       │         relaunch_worker(...)      → at most once per game
       │         wait_for_team()
       │         test_game(...)
       │         build_hub()               → art-director agent writes index.html
       └─ _ensure_site()                ← non-LLM safety net
```

### One event loop, on purpose

`loop.py`'s module docstring notes that the launch and wait tools use plain
`subprocess.Popen` rather than asyncio subprocess transports, and that the QA
agent closes its MCP toolset *in-loop* before returning.

Both are the same lesson. An asyncio subprocess transport registers cleanup
callbacks on the loop that created it; if the loop closes first, the transport's
`__del__` fires later against a dead loop and you get `RuntimeError: Event loop
is closed` spraying out of garbage collection at the end of an otherwise
successful run. Keeping every child process on plain `Popen`, and closing MCP
toolsets while the loop is still alive, removes that class of bug entirely.

---

## 3. The shared board

One SQLite file, one table:

```sql
todos(id, parent_id, task, status, result)
```

`parent_id IS NULL` means a goal; otherwise it is a step under that goal. That is
the entire hierarchy, and it is enough:

* the **orchestrator** writes one goal per builder,
* each **builder** writes its own steps under its goal and ticks them off,
* the **live board** renders goals in their owner's colour with steps indented
  beneath.

Five processes — four Python, one Node — read and write it concurrently. WAL mode
gives the orchestrator a consistent read while a builder commits; a 5-second busy
timeout absorbs the collisions.

### Why the board and not a message queue

Because the board is also the UI. The same rows that coordinate the team are what
`rich.Live` paints eight times a second, so watching the run is free — no
separate progress-reporting channel, no risk of the display disagreeing with
reality. A worker that writes "translate the phrases" as a step is simultaneously
recording its plan and telling you what it is doing.

It also means a worker never has to know anything about the team. It claims one
task id, does the work, and exits. No worker imports the orchestrator; no worker
knows another worker exists.

### Colour without coupling

A worker never learns its own colour. The orchestrator keeps a registry mapping
`goal id -> worker record`, and `live_board.render()` joins the board rows
against it. The board schema stays generic and the workers stay ignorant.

---

## 4. The worker contract

Every builder, in every language, takes the same two positional arguments:

```
<taskId> <boardPath>
```

Run bare, a worker seeds its own goal and runs a standalone demo. Given the two
arguments, the same agent — same tools, same system prompt — points its board and
file tools at the shared site, claims that one task, does it, and exits.

The branch that chooses the mode is four lines at the top of each worker, and it
runs *before* `board` is imported, because the board picks its file from
`BOARD_PATH` at import time.

This is the interface that makes the system work. Five frameworks with completely
different idioms — Strands' `@tool` decorators, Pydantic AI's `MCPToolset`, MAF's
chat clients, Agno's toolkits, Mastra's TypeScript workflows — reduce to one
launchable shape, and `catalog.py` is the only file that knows anything about
where they live or how to start them.

### Launching

```python
[sys.executable, "-m", "orchestra.workers.strands_worker", task_id, board_path]
```

`sys.executable -m` rather than `uv run <path>`. The child provably shares the
parent's interpreter and virtualenv. This matters because worker stdout and
stderr go to `DEVNULL` (a framework's startup banner would otherwise tear the
live board apart) — so a worker that dies on `ImportError` looks *identical* to a
worker that ran and produced nothing. Removing the possibility of an environment
mismatch removes the hardest failure to diagnose in the project.

The TypeScript worker goes through `shutil.which("npx")` first, because on
Windows `npx` is a `.cmd` shim and `subprocess.Popen` does not consult `PATHEXT`.

### Killing

`start_new_session=True` on POSIX puts each worker and its `npx`/MCP child tree
in its own process group, so a timeout can `killpg` the whole tree at once. On
Windows the same job is done by `taskkill /F /T /PID`. Without this, killing a
worker leaves its MCP servers running and the run hangs on a wait that will never
complete.

---

## 5. Agent-driven evaluation

This is the part worth the most in an interview.

```
orchestrator ──test_game(slug)──► fresh QA LlmAgent
                                    ├── Playwright MCP toolset  ──► real Chrome
                                    └── report_game(works, note) ──► verdict
                                             │
              verdict string ◄───────────────┘
                    │
                    └──► orchestrator decides: fine, or relaunch_worker(framework, problem)
```

The QA agent gets a browser through the Playwright MCP server (`npx
@playwright/mcp`, driving the system Chrome), opens the game, clicks around,
reads the console, and calls a `report_game` function tool with its verdict.

Design decisions inside that:

**A fresh agent per game.** Not one QA agent that tests five games. Each browser
session and each context window stays small, and one confusing game cannot run
the check away to the call cap and starve the rest.

**`report_game` as the exit.** The agent finishes by calling a tool, not by
emitting text. A verdict that arrives as a structured `{works, note}` needs no
parsing and cannot be ambiguous.

**Exhausting the budget counts as a pass.** If a QA agent uses all 25 calls
without reporting, it was clearly still interacting with a responsive game. That
is treated as working rather than firing a spurious repair round — a false
negative here costs a whole extra build cycle.

**No browser is not a failure.** If Chrome or the MCP server is unavailable,
`test_game` says so and the orchestrator moves on. The arcade still gets built and
opened. Evaluation is a check, not a gate.

---

## 6. Everything is bounded

An agentic loop that spawns subprocesses that spawn browsers has many ways to
never return. Each has an explicit answer:

| Risk | Bound | Where |
|---|---|---|
| Orchestrator thrashes between test and relaunch | 80 LLM calls | `MAX_ORCHESTRATOR_CALLS` |
| QA agent plays a game forever | 25 LLM calls | `MAX_QA_CALLS` |
| A worker hangs | 300s, then its whole process tree is killed | `WORKER_TIMEOUT_S` |
| A browser check wedges | 150s, then abandoned | `QA_TIMEOUT_S` |
| MCP teardown wedges | 10s per close | `CLOSE_TIMEOUT_S` |
| A game is unfixable | at most one repair per game | `Team.fixed` |
| The orchestrator errors or runs out of budget | caught; the site is finished anyway | `_run` + `_ensure_site` |
| An art-director call fails | a built-in template is written | `author_agent._safe` |

The last two are the ones I would point at. `LlmCallsLimitExceededError` and any
transient model error are caught, and `_ensure_site()` then writes whatever is
missing from plain templates. **The run always produces a playable arcade**, even
if the agent leading it stopped early. Graceful degradation is not an
afterthought bolted on; it is why the demo never fails on camera.

---

## 7. Prompt design

Every prompt is in `prompts.py`, and they are all *goal-focused* rather than
procedural.

The orchestrator prompt names the seven steps of the loop but leaves the
judgement explicitly to the agent — it ends with "Judge a game by playing it, not
by assuming it works because it was built." The worker task text names the
learning objective and the constraints (three files, vanilla JS, must open from
`file://`) and then says *"You decide what the game is and how it plays."*

The consequence is that the same prompt produces five different games, and
`--language French` produces a French arcade with no code change at all. The
language is a string that flows from the CLI into the prompts and nowhere else.

One constraint in the worker prompt is worth noting as engineering rather than
prose: *"As your final step, read your three files back through your file tools
to confirm they exist and are complete before you mark the task done."* Agents
routinely report success on writes that did not land. Making verification an
explicit step of the task catches it at the cheapest possible moment.

---

## 8. What I would change

* **Structured verdicts across the boundary.** `test_game` returns a string like
  `"strands: BROKEN. The submit button throws."` The orchestrator parses it with
  a model. A typed object would be more robust, at the cost of ADK tool-schema
  complexity.
* **More than one repair round, with a budget.** One fix per game is a blunt
  instrument chosen so the run always terminates. A global repair budget shared
  across games would be better.
* **Cache the QA browser.** Each `test_game` cold-starts `npx @playwright/mcp`.
  Five games means five cold starts. A single long-lived browser with a fresh
  context per game would cut minutes off the run — at the cost of the isolation
  that currently makes a wedged check harmless.
* **Record the trajectory.** The board captures what each worker planned and did,
  but the orchestrator's own reasoning only goes to the console. Persisting it
  would make runs comparable across model changes.
* **A regression corpus.** Right now the only evaluation is the live browser
  check. Keeping the generated games and re-running the QA agent against them
  after a prompt change would turn prompt edits into measurable ones.
