"""The entry point: assemble a team and let an agent run it.

    orchestra                          a Spanish arcade from every worker installed
    orchestra --language French        any language; it goes straight into the prompts
    orchestra --skip agno mastra       leave frameworks out
    orchestra --dry-run                show the team and stop, spending nothing
    orchestra --no-open                build it, do not open a browser at the end
    orchestra doctor                   check the environment before spending anything

Environment setup happens here, before any framework is imported, because two
things have to be true at import time: ``BOARD_PATH`` must be set before
``orchestra.core.board`` picks its file, and ``GOOGLE_GENAI_USE_VERTEXAI`` must be
false before ADK decides which backend to use.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

# The orchestrator prints its agents' own words, which can include characters
# beyond the Windows console's default code page. Make stdout UTF-8 so an emoji in
# a summary renders instead of crashing the run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(override=True)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")  # the Gemini API, not Vertex

from orchestra import config  # noqa: E402

os.environ["BOARD_PATH"] = str(config.BOARD_PATH)
os.environ["WORKER_MODEL"] = config.WORKER_MODEL

from orchestra.orchestrator import catalog, loop, qa_agent  # noqa: E402


def _doctor() -> int:
    """What is installed, what is configured, and who would be on the team."""
    print("Orchestra environment check\n")

    ok = True
    for name, value, why in [
        ("OPENAI_API_KEY", config.OPENAI_API_KEY, "the builder workers cannot run"),
        ("GOOGLE_API_KEY", config.GOOGLE_API_KEY, "the ADK orchestrator cannot run"),
    ]:
        if value:
            print(f"  [ ok ] {name}")
        else:
            ok = False
            print(f"  [FAIL] {name} is missing — {why}")

    for name, why in [
        ("npx", "the Mastra worker and the Playwright QA browser cannot start"),
        ("node", "the filesystem MCP server cannot start, so no worker can write files"),
    ]:
        path = shutil.which(name)
        print(f"  [ ok ] {name} ({path})" if path else f"  [warn] {name} not found — {why}")

    team = catalog.discover()
    print(f"\n  team      {len(team)} builder(s): {', '.join(w['name'] for w in team) or 'none'}")
    missing = [w["name"] for w in catalog.WORKERS if w["key"] not in {t["key"] for t in team}]
    if missing:
        print(f"  missing   {', '.join(missing)}")
    print(f"  site      {config.SITE_DIR}")
    print(f"  models    orchestrator={config.ORCHESTRATOR_MODEL}  workers={config.WORKER_MODEL}")
    print(f"  browser   {'headless' if config.QA_HEADLESS else 'visible Chrome'}")
    print("\nReady." if ok and team else "\nNot ready: fix the FAIL lines above.")
    return 0 if ok and team else 1


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="orchestra", description="Build a language-game arcade with a team of agents."
    )
    parser.add_argument("command", nargs="?", choices=["run", "doctor"], default="run")
    parser.add_argument("--language", default="Spanish", help="the language to learn (default: Spanish)")
    parser.add_argument("--skip", nargs="*", default=[], help="worker keys to leave out, e.g. --skip agno")
    parser.add_argument("--dry-run", action="store_true", help="show the plan; do not run the agent")
    parser.add_argument("--no-open", action="store_true", help="do not open the finished site")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "doctor":
        return _doctor()

    workers = catalog.discover(skip=tuple(args.skip))
    if not workers:
        print("No workers available. Run 'orchestra doctor' to see what is missing.", file=sys.stderr)
        return 1

    print(f"Assembling a {args.language} arcade with {len(workers)} builders:")
    for worker in workers:
        print(f"  {worker['name']:<28} -> folder {worker['slug']}/ (game invented at runtime)")
    if args.dry_run:
        print("\nDry run: stopping before the agent runs.")
        return 0

    print(f"\n{config.ORCHESTRATOR_MODEL} is leading the team. Watch the board fill in:\n")
    loop.run(args.language, workers, config.SITE_DIR, config.BOARD_PATH)

    # A deterministic final pass, so a game the agent forgot to mention is still surfaced.
    print("\nFinal check:")
    for worker in workers:
        built = loop.is_built(config.SITE_DIR / worker["slug"])
        print(f"  {worker['name']:<28} {'ok' if built else 'INCOMPLETE'}  ({worker['slug']}/)")

    index = Path(config.SITE_DIR) / "index.html"
    print("\nThe team has finished. Open this to play:")
    print(f"  {index.resolve().as_uri()}")
    if not args.no_open:
        qa_agent.open_site(index)
    return 0


if __name__ == "__main__":
    sys.exit(main())
