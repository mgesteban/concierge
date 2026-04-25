"""One-shot: update the live CMA Concierge agent to today's tool list +
system prompt.

Background
----------
The CMA agent was created Thu 2026-04-23 with the tool roster present at
create time (`search_governance_kb`, `verify_citation`,
`escalate_to_grace`). `ensure_agent()` in `app/managed_agents/client.py`
is find-or-create only — it never refreshes the spec of an existing
agent. So when we add a new custom tool (today: `search_product_kb`) or
rewrite the system prompt, the SMS path stays on the old definition
until we explicitly update.

Voice is unaffected — `voice_pipeline.py` reads `CUSTOM_TOOLS` and
`SYSTEM_PROMPT` fresh on every turn.

What this script does
---------------------
1. Resolves the agent named `agent_spec.AGENT_NAME` via `agents.list()`.
2. Retrieves its current version (required for optimistic concurrency).
3. Calls `agents.update(agent_id, version=..., tools=CUSTOM_TOOLS,
   system=SYSTEM_PROMPT, model=AGENT_MODEL)`.
4. Prints before/after tool names so the diff is visible at a glance.

Why update vs. archive + recreate
---------------------------------
update() preserves the agent_id, so every existing CMA session in the
`phone_sessions` table continues to work. Cross-session memory ("Jane
texts Monday, again Thursday") survives. Archive + recreate would
orphan those sessions and force re-introduction.

Run
---
    .venv/bin/python -m scripts.update_cma_agent
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root regardless of cwd.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402

from app.managed_agents import agent_spec  # noqa: E402


def _tool_names(tools) -> list[str]:
    """Pull tool names off whatever shape the SDK returned."""
    out: list[str] = []
    for t in tools or []:
        if isinstance(t, dict):
            out.append(t.get("name", "?"))
        else:
            out.append(getattr(t, "name", "?"))
    return out


def main() -> int:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    target = None
    for a in client.beta.agents.list(limit=100):
        if a.name == agent_spec.AGENT_NAME and not getattr(
            a, "archived_at", None
        ):
            target = a
            break

    if target is None:
        print(
            f"No live agent found with name {agent_spec.AGENT_NAME!r}. "
            "Boot the app once locally so ensure_agent() creates it, then "
            "re-run this script."
        )
        return 1

    current = client.beta.agents.retrieve(target.id)
    print(
        f"Found agent: name={current.name!r} id={current.id} "
        f"version={current.version}"
    )
    print(f"  Before — tools: {_tool_names(current.tools)}")

    updated = client.beta.agents.update(
        agent_id=current.id,
        version=current.version,
        tools=agent_spec.CUSTOM_TOOLS,
        system=agent_spec.SYSTEM_PROMPT,
        model=agent_spec.AGENT_MODEL,
    )
    print(
        f"  After  — tools: {_tool_names(updated.tools)} "
        f"version={updated.version}"
    )
    print("Done. Existing CMA sessions preserved (agent_id unchanged).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
