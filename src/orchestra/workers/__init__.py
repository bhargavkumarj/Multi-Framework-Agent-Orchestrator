"""The builder workers: the same agent, written five times in five frameworks.

Each reads a goal off the shared board, plans its own steps under it, works them
with filesystem MCP tools, and ticks them off. Run one bare for its standalone
demo, or hand it a task id and a board path and it joins the team:

    python -m orchestra.workers.strands_worker                  # standalone
    python -m orchestra.workers.strands_worker <taskId> <board> # team mode
"""
