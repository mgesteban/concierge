# CLAUDE.md — BoardBreeze Concierge

Guidance for Claude Code sessions in this repo. Kept deliberately short —
long CLAUDE.md files conflict with agent prompts and skills (playbook §8.7).

## What this project is

A voice + SMS concierge enhancing [appboardbreeze.com](https://appboardbreeze.com/),
built for the Claude Opus 4.7 Hackathon (Apr 21–27 2026).
Submission deadline: **Sun Apr 26, 8:00 PM EST.**

Architecture (post Michael Cohen talk, Thu 2026-04-23): **one Claude
Managed Agent** with five specialist modes (Governance Expert, Product
Expert, Tech Support, Sales Closer, Escalation) expressed in the system
prompt + custom tools for KB search, citation verification, and
escalation. Anthropic's own guidance today is "one agent + many skills"
rather than separate sub-agents — first-class multi-agent is shipping
soon, at which point we can split the modes out with minimal code
change. See `notes/cohen-managed-agents.md` for the direct quotes.

Sources of truth:
- `boardbreeze-concierge-playbook-updated-04-22-2026.md` — strategy,
  day-by-day plan, demo-video shot list, Tark's power moves. Untracked,
  local only. Sections 5, 6, 11, 12, 16 are load-bearing.
- `notes/cohen-managed-agents.md` — what we actually use from Managed
  Agents and why.

## Project-specific rules

### 1. No `NEVER` / `ALWAYS` caps-lock in agent prompts (§8.6)

Claude Opus 4.7 follows instructions literally, so hard prohibitions
over-trigger on adjacent benign behavior. Use conditional language:

- Bad: "NEVER give legal advice."
- Good: "Avoid jurisdiction-specific legal advice. If a question requires
  interpreting a statute against the caller's specific facts, defer to
  counsel and offer a callback. General explanations of how the Brown
  Act works are fine and welcome."

If any agent over-refuses during testing, the first thing to check is
whether a NEVER/ALWAYS instruction is causing it.

### 2. Every statutory citation passes `verify_citation` before shipping (§16.5)

The Governance Expert mode may not read a statute section number aloud
until `verify_citation(citation, claim)` confirms the section exists in
our KB AND that its text supports the claim. Enforced via the custom-
tool contract, not a prompt instruction we hope the model follows.

Registered on the Concierge agent as a CMA custom tool (see
`app/managed_agents/agent_spec.py`). Backend handler:
`app/managed_agents/custom_tools.py::_verify_citation`.

### 3. One Managed Agent + specialist modes, not N sub-agents

The Concierge is a single CMA agent whose system prompt describes five
modes (Governance, Product, Tech Support, Sales, Escalation) it adopts
based on the caller's need. This is Anthropic's current recommended
pattern (Cohen 2026-04-23; see `notes/cohen-managed-agents.md`). First-
class multi-agent is coming; we're positioned to upgrade with minimal
churn.

*Also* the rule for dev-side work: don't spawn per-role subagents
("prompt-engineer", "frontend-engineer") to help build this project.
Build skills in `.claude/skills/` and let Claude combine them. Current
dev skills: `/interview`, `/governance-verify`, `/status`.

### 4. Audit for conflicting instructions periodically (§8.7)

Before committing any substantial agent/skill/CLAUDE.md change, ask:
"Read every file under `.claude/skills/`, this CLAUDE.md, the system
prompt in `app/managed_agents/agent_spec.py`, and the tool descriptions
in the same file. Find any place two instructions conflict or could
plausibly be interpreted as conflicting. List them. Don't fix anything
yet." Triage by hand.

## Repo layout

```
app/
├── main.py               FastAPI entrypoint
├── config.py             pydantic-settings env loader
├── managed_agents/       CMA integration — the production Concierge
│   ├── agent_spec.py       system prompt, custom tool defs, agent kwargs
│   ├── client.py           ensure_agent/environment/session + handle_message
│   └── custom_tools.py     backend dispatch for search_kb, verify_citation,
│                           escalate_to_grace
├── agents/               historical only (v0 reference loop, kept for the
│                         README's v0→v1 narrative — nothing imports it)
├── tools/governance_tools/ RAG + jurisdiction tools used by custom_tools
├── channels/             Twilio SMS + Voice webhooks → handle_message
├── db/                   Supabase schema + migrations
└── kb/                   governance_kb seed

.claude/skills/           interview, governance-verify, status
notes/                    external-intel notes (Cohen talk, etc.)
tests/                    offline tests (no network, no keys)
Progress.md               running log — the "Keep Thinking" source
```

## Commands

```bash
# Dev server (use Python 3.11 venv — `.venv/bin/activate`)
.venv/bin/uvicorn app.main:app --reload --port 8000

# Tests (offline, no keys needed)
.venv/bin/pytest tests/

# Seed the governance KB (requires Supabase + Voyage keys)
.venv/bin/python -m app.kb.seed_kb

# Sanity-check that the CMA agent + environment exist
.venv/bin/python -c "from dotenv import load_dotenv; load_dotenv('.env'); \
  from app.managed_agents.client import ensure_agent, ensure_environment; \
  print(ensure_agent(), ensure_environment())"
```

## End-of-day

Run the `/status` skill to append a dated entry to `Progress.md`. That
log is the source material for the README's v0→v5 "Keep Thinking"
narrative and the demo video voiceover.
