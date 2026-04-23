# CLAUDE.md — BoardBreeze Concierge

Guidance for Claude Code sessions in this repo. Kept deliberately short —
long CLAUDE.md files conflict with agent prompts and skills (playbook §8.7).

## What this project is

A multi-agent voice + SMS concierge enhancing [appboardbreeze.com](https://appboardbreeze.com/),
built for the Claude Opus 4.7 Hackathon (Apr 21–27 2026).
Submission deadline: **Sun Apr 26, 8:00 PM EST.**

The source of truth for strategy, architecture, and day-by-day plan is:

> `boardbreeze-concierge-playbook-updated-04-22-2026.md` (untracked, local only)

Read it end-to-end once. Sections 5 (product), 6 (architecture),
11 (day-by-day), 12 (demo video), and 16 (Tark's power moves) are
load-bearing.

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

The Governance Expert cannot read a statute section aloud until
`verify_citation(citation, claim)` confirms the section exists in our KB
AND that its text supports the claim. This is enforced as a tool-required
check, not a prompt instruction we hope the model follows.

Location: `app/tools/verify_citation.py`. Skill wrapper:
`.claude/skills/governance-verify.md`.

### 3. Skills > role-based subagents for dev work (§16.1)

Don't create "frontend-engineer" or "prompt-engineer" subagents to help
build this project. Build skills in `.claude/skills/` instead and let
Claude combine them for the task at hand. Current skills:

- `/interview` — interview Grace before writing a non-trivial prompt/spec
- `/governance-verify` — run a drafted answer through the verification layer
- `/status` — compile today's progress into Progress.md

The six **product agents** (Concierge, Governance Expert, Sales Closer,
Product Expert, Tech Support, Escalation) are user-facing personas and
stay — this rule is about dev-side subagents, not them.

### 4. Audit for conflicting instructions periodically (§8.7)

Before committing any substantial agent/skill/CLAUDE.md change, ask:
"Read every file under `.claude/skills/`, this CLAUDE.md, and the system
prompts under `app/agents/`. Find any place two instructions conflict or
could plausibly be interpreted as conflicting. List them. Don't fix
anything yet." Triage by hand.

## Repo layout

```
app/
├── main.py               FastAPI entrypoint
├── config.py             pydantic-settings env loader
├── agents/               Concierge supervisor + 5 specialist modules
├── tools/
│   ├── governance_tools/ RAG, jurisdiction lookup, templates, handoff
│   └── verify_citation.py  §16.5 anti-hallucination layer
├── channels/             Twilio SMS + Voice webhooks
├── db/                   Supabase schema + client
└── kb/                   governance_kb seed

.claude/skills/           interview, governance-verify, status
tests/                    offline tests (no network, no keys)
Progress.md               running log — the "Keep Thinking" source
```

## Commands

```bash
# Dev server
uvicorn app.main:app --reload --port 8000

# Tests (offline, no keys needed)
python -m pytest tests/

# Seed the governance KB (requires Supabase + Voyage keys)
python -m app.kb.seed_kb
```

## End-of-day

Run the `/status` skill to append a dated entry to `Progress.md`. That
log is the source material for the README's v0→v5 "Keep Thinking"
narrative and the demo video voiceover.
