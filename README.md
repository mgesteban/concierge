# BoardBreeze Concierge

**The customer success team I couldn't afford to hire — running on Claude Opus 4.7.**

A multi-agent voice + SMS concierge for [appboardbreeze.com](https://appboardbreeze.com/), the SaaS that helps California public-agency boards run Brown-Act-compliant meetings. Callers dial or text one phone number; a team of specialized Claude agents answers governance questions, resolves product support, closes deals, and escalates to the founder when a human is actually needed.

> Built for the Claude Opus 4.7 Hackathon, Apr 21–27 2026. Submission: Sun Apr 26, 8:00 PM EST.

---

## What it does

1. **One phone number.** Subscribers and prospects call or text; the concierge answers 24/7.
2. **Specialist agents route by intent.** Governance, product, tech support, sales, escalation — each with its own system prompt, tools, and "done" state.
3. **Citations get verified before they ship.** The Governance Expert's answers pass through a `verify_citation` layer that confirms every cited statute exists and supports the claim. No hallucinated Brown Act sections reach a live caller.
4. **Cross-channel memory.** If Jane texts Monday and calls Thursday, the agent picks up where Monday left off (Supabase-backed `conversation_state`).
5. **Hot leads page Grace.** The Escalation Handler sends an SMS with a clean summary when a prospect shows high-urgency buying signals.
6. **Scheduled background agents.** Hot-lead detector every 30 min, follow-up agent daily, digest at 6pm — all running as Claude routines on Anthropic's servers.

---

## Architecture

```
                    ┌───────────────────────────┐
   Voice/SMS ────▶  │   CONCIERGE (Supervisor)  │  ◀──── conversation_state
                    │       Claude Opus 4.7      │         (Supabase)
                    └────────────┬──────────────┘
                                 │
        ┌──────────────────┬─────┴────────┬───────────────────┐
        ▼                  ▼              ▼                   ▼
 ┌──────────────┐ ┌────────────────┐ ┌────────────┐ ┌─────────────────┐
 │ GOVERNANCE   │ │ PRODUCT EXPERT │ │ TECH       │ │ SALES CLOSER    │
 │ EXPERT       │ │  (Opus 4.7)    │ │ SUPPORT    │ │  (Opus 4.7)     │
 │ (Opus 4.7)   │ │                │ │ (Sonnet    │ │                 │
 │              │ │ • Feature KB   │ │  4.6)      │ │ • Pricing       │
 │ • Brown Act  │ │ • How-tos      │ │ • Known    │ │ • Demo booking  │
 │ • Bagley-    │ │                │ │   issues   │ │ • Objections    │
 │   Keene      │ │                │ │ • Ticket   │ │                 │
 │ • Robert's   │ │                │ │   creation │ │                 │
 │   Rules      │ │                │ │            │ │                 │
 │ • verify_    │ │                │ │            │ │                 │
 │   citation   │ │                │ │            │ │                 │
 └──────────────┘ └────────────────┘ └────────────┘ └─────────────────┘
                                 │
                                 ▼
                    ┌───────────────────────────┐
                    │   ESCALATION HANDLER       │
                    │   Texts + emails Grace     │
                    │   with a clean summary     │
                    └───────────────────────────┘

     Plus scheduled routines (Claude's servers, not our box):

     ┌────────────┐   ┌────────────────┐   ┌──────────────┐
     │ FOLLOW-UP  │   │ HOT LEAD       │   │ DAILY DIGEST │
     │ AGENT      │   │ DETECTOR       │   │ COMPILER     │
     │ (daily 8a) │   │ (every 30 min) │   │ (daily 6pm)  │
     └────────────┘   └────────────────┘   └──────────────┘
```

Every agent writes to a shared `conversation_state` table in Supabase keyed by session_id — that's what makes cross-channel, multi-day memory work. See `app/db/schema.sql`.

---

## How we used Opus 4.7

We chose Claude Opus 4.7 specifically for three properties that 4.6 couldn't match:

1. **Long-running conversations.** A support call can span 15 minutes and 40+ turns. 4.6 loses which agent is active by turn ~10; 4.7 stays coherent past turn 25 in our tests. This matters because voice handoffs compound — if the supervisor forgets which specialist just handed off, the caller feels it instantly.
2. **Precise instruction following.** The Governance Expert's system prompt specifies exactly when to cite, when to defer to counsel, and when to hand off to sales. 4.7 follows these conditionals without drift.
3. **Adapted prompts to literal interpretation.** Per Tark's AMA (playbook §8.6), we rewrote `NEVER`/`ALWAYS` prohibitions as conditional language ("avoid X unless Y") to prevent 4.7 from over-triggering on adjacent legitimate behavior. The Governance Expert explains what the Brown Act is without refusing, while still declining jurisdiction-specific legal advice.

Extended thinking (`budget_tokens=2000`) is enabled on the Concierge and Governance Expert for reasoning-heavy turns. Sales Closer and Tech Support run without it — those are pattern-match tasks where latency matters more than depth.

---

## How we used Claude Managed Agents

Each specialist is a managed agent with a narrow role, named tools, and an explicit "done" state. Handoffs are explicit tool calls (`hand_off_to_sales`, `escalate_to_grace`), so every transition is visible in the dashboard's handoff log — judges can replay a trace and see which agent decided what.

Per Tark's §16.1 power move, **capabilities inside each agent live as skills, not as system-prompt bloat.** The Governance Expert's prompt is tight (role + voice + escalation rules); the actual expertise — finding the right statute, checking agenda compliance, drafting minutes — is invoked via skills under `.claude/skills/`. This keeps system prompts reviewable and lets the same skill (e.g., `/governance-verify`) serve multiple agents.

**State flows** through the `conversation_state` table (keyed by session_id) and the `handoffs` audit table. The orchestrator injects `session_id` into every tool call — Claude itself never sees or forges it, which is how we stay safe against prompt injection through the caller's voice channel.

---

## How we caught hallucinations: the verification layer

Section 16.5 of our playbook articulated the single highest-leverage piece of the architecture: the Governance Expert **cannot ship a citation until a separate verifier confirms (a) the cited section exists in our curated KB and (b) its actual text supports the claim.**

The flow:

1. **Draft.** Governance Expert generates an answer with citations.
2. **Verify.** For each `(citation, claim)` pair, the agent calls `verify_citation(...)`. The verifier looks up the exact source in `governance_kb`, then runs a small Claude classifier: "Does this passage support this claim? yes / no / partial." Returns `{verified, actual_text, suggested_rewrite}`.
3. **Rewrite or hedge.** If any citation fails verification, the agent rewrites with verified material or emits the hedged fallback: "I'm not certain on the specific section — let me connect you with someone who can confirm."
4. **Audit.** Every verification (pass and fail) is logged. The dashboard surfaces the weekly count: "1,247 citations issued, 23 caught and rewritten by the verifier."

Code: `app/tools/verify_citation.py`. Skill wrapper: `.claude/skills/governance-verify.md`. Golden test pairs: `tests/test_verify_citation.py` (Saturday).

---

## What Opus 4.6 couldn't do

One concrete transcript diff lives in `notes/4.6-vs-4.7-transcript.md`: a 24-turn voice call where 4.6 lost track of the active agent by turn 8 (kept offering governance citations mid-sales-close), while 4.7 stayed locked through the handoff. We use the same test script for regression testing as we expand the agent roster.

---

## The evolution (Keep Thinking)

- **v0** — a single chatbot that answers texts.
- **v1** — added a sales agent to close deals.
- **v2** — realized governance questions need a specialist → added the Governance Expert trained on Brown Act + Robert's Rules.
- **v3** — voice, not just SMS, because board secretaries are over-50 and prefer calling.
- **v4** — routines running overnight to follow up on cold leads and flag hot ones.
- **v5** — added the citation-verification layer after watching real subscribers test the system on Friday. We caught the Governance Expert occasionally citing adjacent-but-wrong statutes — unacceptable in a regulated domain. Built the verifier infrastructure rather than patching prompts.

See `Progress.md` for the day-by-day narrative.

---

## Repo layout

```
concierge/
├── app/
│   ├── main.py                 FastAPI entrypoint
│   ├── config.py               env-backed settings
│   ├── agents/                 one module per specialist + Concierge
│   ├── tools/
│   │   ├── governance_tools/   RAG, jurisdiction lookup, templates, handoff
│   │   └── verify_citation.py  §16.5 anti-hallucination layer
│   ├── channels/
│   │   ├── sms.py              Twilio SMS webhook
│   │   └── voice.py            Twilio Voice webhook
│   ├── db/
│   │   ├── schema.sql          Supabase migrations (pgvector + state)
│   │   └── supabase_client.py
│   └── kb/
│       └── seed_kb.py          governance_kb seed
├── .claude/
│   └── skills/                 /interview, /governance-verify, /status
├── tests/                      offline tests, no network required
├── scripts/                    KB ingestion, local dev helpers
├── notes/                      session notes from Michael Cohen / Mike Brown / Mihal
├── Progress.md                 running log (the "Keep Thinking" source)
└── README.md                   you are here
```

---

## Setup

```bash
# 1. Python deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Environment
cp .env.example .env
# fill in keys — Anthropic, Supabase, Voyage, Twilio, Deepgram, ElevenLabs

# 3. Supabase schema
# Run app/db/schema.sql in the Supabase SQL editor.

# 4. Seed the governance KB (~20 authoritative chunks)
python -m app.kb.seed_kb

# 5. Run tests (offline, no keys needed)
python -m pytest tests/

# 6. Start the server
uvicorn app.main:app --reload --port 8000

# 7. Expose to Twilio
# In a second terminal:  ngrok http 8000
# Point Twilio phone number's SMS webhook at  {ngrok}/twilio/sms/inbound
# Point its Voice webhook at                  {ngrok}/twilio/voice/inbound
```

---

## Built by

**Grace Esteban** — solo founder of BoardBreeze. Domain expert in California public-agency governance (Brown Act, Bagley-Keene, community college districts, special districts).

Paired with **Claude Code (Opus 4.7)** as development partner throughout the hackathon. See the "How we used Opus 4.7" and "How we used Claude Managed Agents" sections above for how the collaboration actually worked — and see the `Co-Authored-By` trailers on commits in `git log` for per-commit attribution.

## License

MIT — see [LICENSE](./LICENSE).
