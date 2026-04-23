# Changelog

All notable changes to BoardBreeze Concierge are logged here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `CLAUDE.md` — session guidance for Claude Code (playbook rule digest,
  repo layout, commands).
- `CHANGELOG.md` (this file).

### Configured (local, not committed)
- `.env` populated with Anthropic API key, Twilio (account SID + auth
  token + phone number), ElevenLabs (API key + voice ID), and Grace's
  personal phone number for escalations. Supabase, Voyage, and Deepgram
  keys deferred to Thursday.

## [0.1.0] — 2026-04-22

Initial scaffold pushed to https://github.com/mgesteban/concierge.

### Added
- FastAPI entrypoint (`app/main.py`) with `/health`, Twilio SMS and Voice
  webhook routers.
- Concierge supervisor (`app/agents/concierge.py`) with keyword-based
  routing to the Governance Expert (full intent classifier lands Thu).
- Governance Expert agent (`app/agents/governance_expert.py`) wrapping
  the reference Claude Opus 4.7 tool-use loop.
- Scaffold modules for Sales Closer, Product Expert, Tech Support, and
  Escalation Handler agents.
- Governance tools package (`app/tools/governance_tools/`) — four
  Anthropic tools (`search_governance_kb`, `check_jurisdiction_rules`,
  `generate_compliant_template`, `hand_off_to_sales`) with Supabase
  pgvector backing, 1024-dim Voyage embeddings, offline tests, and the
  full example agent loop.
- `verify_citation` stub (`app/tools/verify_citation.py`) — the §16.5
  anti-hallucination layer. Real implementation lands Thursday.
- Supabase schema (`app/db/schema.sql`) covering `governance_kb`,
  `conversation_state`, `handoffs`, and the `match_governance_kb` RPC.
- `.claude/skills/`: `/interview`, `/governance-verify`, `/status`.
- `README.md` shaped against the four judging criteria (Impact, Demo,
  Opus 4.7 Use, Depth & Execution) with the v0→v5 evolution story.
- `Progress.md` — running daily log and source material for the
  "Keep Thinking" narrative.
- `.env.example`, `.gitignore`, MIT `LICENSE`, `requirements.txt`.

### Infra
- Git repo initialized locally and wired to `origin =
  https://github.com/mgesteban/concierge.git`.
- Scaffold rebased on top of GitHub's auto-generated `Initial commit`
  (stub README) to keep linear history without force-pushing. First
  scaffold commit: `51eb246`.
