# Orchestra — a Multi-Framework Agent Orchestrator

An agent that commands a team of agents.

Give it a goal — *build a web arcade that teaches Spanish* — and a Google ADK
orchestrator decides on its own what each builder should teach, launches five
builder agents **written in five different frameworks** in parallel against a
shared SQLite board, watches them work, then **opens each finished game in a real
Chrome browser, plays it, and judges whether it works**. Anything broken gets one
bounded repair round. Then it authors a themed home page and hands you a link.

The loop that decides who builds, what is broken, and who goes back is an LLM's
decision, not an `if` statement. The tools own only the mechanics.

```
                          ┌───────────────────────────────────┐
                          │  ORCHESTRATOR  (Google ADK agent) │
                          │  given a goal, not a script       │
                          └──────────────┬────────────────────┘
                                         │ its six tools
        ┌──────────────┬─────────────────┼──────────────┬───────────────┐
        ▼              ▼                 ▼              ▼               ▼
  author_style   launch_worker    wait_for_team     test_game     relaunch_worker
   (art agent)    (×5, parallel)   (live board)     (QA agent)     (one fix only)
                        │                                │              │
        ┌───────────────┴───────────────┐                │              │
        ▼        ▼        ▼      ▼      ▼                ▼              │
   ┌────────┬────────┬────────┬──────┬─────────┐   ┌───────────┐        │
   │ Strands│Pydantic│  MAF   │ Agno │ Mastra  │   │ Playwright│        │
   │        │   AI   │        │      │  (TS)   │   │ MCP →     │        │
   │        │        │        │      │         │   │ real      │        │
   │  each: read goal → plan steps →  │        │   │ Chrome    │        │
   │        work them → tick off      │        │   └─────┬─────┘        │
   └────────┴────┬───┴────────┴──────┴─────────┘         │              │
                 │  filesystem MCP                        │ verdict     │
                 ▼                                        └─────────────┘
        ┌──────────────────────────┐
        │ shared board.sqlite (WAL)│  ◄── painted live with rich.Live
        │ goals + steps + status   │      while five agents write
        └──────────────────────────┘
                 │
                 ▼
           site/  →  index.html + five playable games
```

---

## Why this project is interesting

**The orchestration is genuinely agentic.** It would have been easy to write
`for worker in workers: launch(worker)`. Instead the orchestrator is an ADK
`LlmAgent` given a goal and six tools, and it chooses the learning objectives,
the order of play, which games to test, and who to send back. The tools are
deliberately dumb — `launch_worker` starts a subprocess, `wait_for_team` blocks
— because the mechanics should be reliable and the judgement should be the
model's.

**The system grades its own output.** `test_game` hands a finished game to a
short-lived QA agent equipped with the Playwright MCP server. That agent opens
the game in a real Chrome window, clicks around, reads the browser console, and
reports a verdict. The orchestrator reads the verdict and acts on it. Most
portfolio projects produce output; this one checks it and fixes it.

**Five frameworks, one shape.** AWS Strands, Pydantic AI, Microsoft Agent
Framework, Agno and Mastra (TypeScript) — the same agent five times. Each reads
a goal off the board, writes its own steps under it, works them with filesystem
MCP tools, and ticks them off. That sameness is the point: because the workers
have one shape, a coordinator can command all of them without knowing anything
about any framework.

**Everything is bounded.** An agentic loop that spawns subprocesses that spawn
browsers has a lot of ways to never return. Every one has an answer: a turn
budget on the orchestrator, a call budget on each QA agent, a wall-clock timeout
that kills a hung worker's entire process tree, a bounded MCP teardown, at most
one repair per game, and a non-LLM safety net that finishes the site even if the
agent stops early.

---

## Quick start

```bash
cp .env.example .env    # add OPENAI_API_KEY and GOOGLE_API_KEY
```

```bash
uv sync && uv run orchestra doctor
```

`doctor` reports which builders are actually installed, whether Node is present,
and what the run will cost you in models. Then:

```bash
uv run orchestra
```

Watch the board: five games light up in five colours and fill in as the agents
work, then a Chrome window opens and the orchestrator plays each one. When it
finishes it prints a link to `site/index.html`.

### Flags

```bash
uv run orchestra --language French      # any language, straight into the prompts
uv run orchestra --skip agno mastra     # leave builders out
uv run orchestra --dry-run              # show the team, spend nothing
uv run orchestra --no-open              # build it, do not open a browser
```

### Requirements

* Python 3.12+
* `OPENAI_API_KEY` (the five builders) and `GOOGLE_API_KEY` (the ADK orchestrator)
* Node.js 18+ — `npx` launches the filesystem and Playwright MCP servers
* Google Chrome, for the QA agent. Without it the run still completes; `test_game`
  reports that it could not reach a browser and the orchestrator moves on.

### Adding the TypeScript builder

The four Python builders ship ready. Mastra is TypeScript and joins the team once
its dependencies are installed:

```bash
cd workers_ts && npm install
```

`orchestra doctor` will then list five builders instead of four.

---

## Layout

```
src/orchestra/
├── config.py               models, budgets, timeouts — every knob in one file
├── cli.py                  entry point; sets the environment before ADK imports
├── core/
│   ├── board.py              the shared SQLite board (WAL, multi-process)
│   └── quiet.py              silence library chatter so the agent trace is readable
├── orchestrator/
│   ├── loop.py               the ADK agent, its six tools, and the run
│   ├── catalog.py            the worker manifest: who, how to launch, what colour
│   ├── prompts.py            every prompt in the system
│   ├── qa_agent.py           plays a game in real Chrome via Playwright MCP
│   ├── author_agent.py       writes common.css and index.html, with fallbacks
│   └── live_board.py         the rich.Live view of five agents working at once
└── workers/                  the same agent, five times
    ├── strands_worker.py     AWS Strands
    ├── pydantic_worker.py    Pydantic AI
    ├── maf_worker.py         Microsoft Agent Framework
    └── agno_worker.py        Agno
workers_ts/worker.ts          Mastra (TypeScript)
```

---

## The worker contract

Every builder, in every language, obeys the same two-argument interface:

```bash
python -m orchestra.workers.strands_worker                    # standalone demo
python -m orchestra.workers.strands_worker <taskId> <board>   # join the team
npx tsx workers_ts/worker.ts <taskId> <board>                 # same, in TypeScript
```

Run bare, a worker seeds its own goal and translates `notes.txt` into Spanish —
useful for comparing frameworks side by side. Given a task id and a board path,
the *same* agent with the *same* tools and the *same* instructions joins the
team instead. Only the mode selection differs. That is what makes the workers
interchangeable to the orchestrator.

---

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `OPENAI_API_KEY` | — | **Required.** The five builders. |
| `GOOGLE_API_KEY` | — | **Required.** The ADK orchestrator, QA and art director. |
| `ORCHESTRATOR_MODEL` | `gemini-3.5-flash` | Cheaper: `gemini-3.1-flash-lite` |
| `WORKER_MODEL` | `gpt-5.5` | Cheaper: `gpt-5.4-mini`. Passed down to every worker, including the TS one. |
| `MAX_ORCHESTRATOR_CALLS` | `80` | Outer-loop turn budget |
| `MAX_QA_CALLS` | `25` | One QA agent judging one game |
| `WORKER_TIMEOUT_S` | `300` | A hung worker's whole process tree is killed |
| `QA_TIMEOUT_S` | `150` | A wedged browser check is abandoned |
| `QA_HEADLESS` | unset | `1` runs the QA browser without a window |

---

## Tests

```bash
uv run --extra dev pytest
```

17 tests, no API key, no model calls. They cover the shared board — including
five concurrent writers, the case that actually happens — and the worker
manifest, where a mistake means a builder silently never joins the team.

---

## Cost

A full five-builder run on the default models is a few dollars: five agents each
writing three files, plus an orchestrator, an art director, and five browser QA
sessions. Set both models to the cheaper alternatives in `.env` and it drops
substantially. `--dry-run` shows the team and spends nothing.

---

## Provenance

Built from the week 5 capstone of Ed Donner's *Master AI Agentic Engineering*
course, restructured into a standalone application: the five framework workers
(previously scattered across three sibling course directories) are vendored into
one installable package, workers launch as modules through `sys.executable`
rather than by relative path through `uv run`, every budget and timeout is
centralised in `config.py`, and there is a CLI with an environment doctor and a
test suite. See `ARCHITECTURE.md`.
