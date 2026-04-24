# BoardBreeze Concierge

**The customer success team I couldn't afford to hire — running on Claude Opus 4.7.**

A voice + SMS concierge for [appboardbreeze.com](https://appboardbreeze.com/), the SaaS that helps California public-agency boards run Brown-Act-compliant meetings. Callers dial or text one phone number; a single Claude Opus 4.7 agent answers governance questions, resolves product support, closes deals, and escalates to the founder when a human is actually needed.

> Built for the Claude Opus 4.7 Hackathon, Apr 21–27 2026. Submission: Sun Apr 26, 8:00 PM EST.

---

## What it does

1. **One phone number.** Subscribers and prospects call or text; the concierge answers 24/7.
2. **Five specialist modes in one agent.** Governance Expert, Product Expert, Tech Support, Sales Closer, Escalation — described in a single consolidated system prompt; Claude Opus 4.7 picks the right mode per turn based on the caller's need.
3. **Citations get verified before they ship.** Every statutory citation passes through `verify_citation` — section-exact KB lookup → Haiku 4.5 claim-support classifier — before the agent reads it aloud. Ten-case golden Q&A passes 10/10 with zero false-positive verifications.
4. **Sub-3-second voice replies.** Voice runs on the direct Messages API with sentence-level ElevenLabs synth and chained TwiML, so the caller hears a filler within ~500 ms and the real reply streaming behind it. Perceived first-audio: ~2.5 s on governance questions.
5. **Hot leads page Grace.** When the agent escalates, `escalate_to_grace` sends Grace a Twilio SMS with the caller's phone, channel, urgency, and a clean summary.
6. **Cross-session memory on SMS.** If Jane texts Monday and texts again Thursday, the agent picks up where Monday left off — same Claude Managed Agents session, keyed by E.164 phone number.

---

## Architecture

```
                   ┌────────────────────────────────────┐
                   │   ELEVEN LABS  +  POLLY FALLBACK   │
                   │   (TTS, eleven_flash_v2_5)         │
                   └──────────────────▲─────────────────┘
                                      │
   Voice  ───▶  /gather (filler)  ──▶ /continue  ──▶ /audio
                      │                    ▲
                      ▼                    │ Future
              voice_pipeline.py  ──────────┘
              (direct Messages API,
               sentence streaming,
               inline tool dispatch)
                      │
                      ▼
   ┌───────────────────────────────────────────────────────┐
   │  CONCIERGE  —  one Claude Opus 4.7 agent              │
   │  five specialist modes in one system prompt:          │
   │   • Governance Expert  (Brown Act, Bagley-Keene,      │
   │                         Robert's Rules)               │
   │   • Product Expert     (BoardBreeze features)         │
   │   • Tech Support       (known issues, ticket creation)│
   │   • Sales Closer       (pricing, demo booking)        │
   │   • Escalation Handler (hands off to Grace)           │
   └────────────────────────▲───────────────────▲──────────┘
                            │                   │
   SMS  ───▶  managed_agents.handle_message     │
              (Claude Managed Agents,           │
               session-per-caller for           │
               cross-session memory)            │
                                                │
                            ┌───────────────────┴───────────┐
                            ▼                               ▼
                  ┌──────────────────┐         ┌──────────────────┐
                  │ search_governance│         │ verify_citation  │
                  │ _kb              │         │ (Haiku 4.5)      │
                  │ (Voyage 512-dim  │         │ section lookup + │
                  │  + Supabase      │         │ claim-support    │
                  │  pgvector)       │         │ classifier       │
                  └──────────────────┘         └──────────────────┘

                           ┌──────────────────┐
                           │ escalate_to_grace│
                           │ (Twilio SMS to   │
                           │  Grace's phone)  │
                           └──────────────────┘
```

The voice path and SMS path share the same custom tools (`search_governance_kb`, `verify_citation`, `escalate_to_grace`) — the same backend handlers in `app/managed_agents/custom_tools.py`. They diverge only at the turn loop: SMS runs on Claude Managed Agents (free cross-session memory, idle for weeks at no cost); voice runs on the direct Messages API to fit inside Twilio's ~15 s webhook ceiling.

---

## How we used Opus 4.7

We chose Opus 4.7 specifically for three properties that 4.6 couldn't match:

1. **Multi-mode coherence in one prompt.** The Concierge is a single agent whose system prompt describes five specialist modes — Claude picks the right mode per turn. 4.7 stays locked on the active mode through tool use and back; 4.6 drifts (kept offering governance citations mid-sales-close in our regression script).
2. **Precise instruction following.** The system prompt specifies exactly when to cite, when to defer to counsel, when to call `verify_citation`, when to hand off. 4.7 follows these conditionals without drift.
3. **Adapted prompts to literal interpretation.** Per Tark's AMA (playbook §8.6), we rewrote `NEVER`/`ALWAYS` prohibitions as conditional language ("avoid X unless Y") to prevent 4.7 from over-triggering on adjacent legitimate behavior. The Governance Expert mode explains what the Brown Act *is* without refusing, while still declining jurisdiction-specific legal advice.

The same pattern is enforced as a project rule in [CLAUDE.md](./CLAUDE.md) so it survives future prompt edits.

---

## How we used Claude Managed Agents

After Michael Cohen's Thursday session at the hackathon, we pivoted from a planned six-agent supervisor topology to **one Managed Agent + specialist modes** — Anthropic's currently-recommended pattern. First-class multi-agent is shipping soon; this architecture upgrades cleanly when it does. See [`notes/cohen-managed-agents.md`](./notes/cohen-managed-agents.md) for the direct quotes.

What we use from CMA, idiomatically:

- **Agent + environment:** `boardbreeze-concierge` / `boardbreeze-concierge-env`, provisioned via `ensure_agent` / `ensure_environment` (idempotent, name-keyed find-or-create).
- **Sessions, one per caller phone:** the `phone_sessions` table maps E.164 → CMA `session_id`, so cross-session memory ("Jane texts Monday, again Thursday") is free on the SMS path. CMA sessions idle for weeks at no cost.
- **Custom tools:** `search_governance_kb`, `verify_citation`, `escalate_to_grace` — registered as CMA custom tools whose handlers run in our FastAPI backend, not in the CMA sandbox. Keeps Supabase + Twilio credentials out of the agent's reach.

**Voice exception:** the voice channel runs on the direct Messages API rather than CMA. We measured ~6 s of CMA event-stream overhead on identical Opus 4.7 prompts (CMA first event at 7.66 s vs Messages API TTFT at 0.98 s, done at 1.68 s), which is unworkable inside Twilio's ~15 s webhook ceiling. The voice path re-implements the same tool dispatch loop in `app/voice_pipeline.py` against the same backend handlers, so behavior is identical — only the model interface differs.

---

## How we caught hallucinations: the verification layer

Section 16.5 of the playbook articulated the single highest-leverage piece of the architecture: the Governance Expert mode **cannot ship a citation until a separate verifier confirms (a) the cited section exists in our curated KB and (b) its actual text supports the claim.**

The flow:

1. **Draft.** Governance Expert mode generates a reply with a citation (e.g., "Government Code §54954.2 requires 72-hour posting").
2. **Verify.** The agent calls `verify_citation(citation, claim)`. The verifier extracts the section number, looks it up in `governance_kb`, and asks Haiku 4.5: *"Does this passage support this claim? yes / no / partial."* Returns `{verified, actual_text}` on a hit, `{verified: false, suggested_rewrite}` on a miss. Haiku keeps the round trip under ~300 ms — the agent gets the answer well inside the latency budget.
3. **Rewrite or hedge.** If verification fails, the agent rewrites with the suggested safe phrasing or hedges: "I'm not certain on the specific section — let me connect you with someone who can confirm."

**Result on the golden Q&A suite:** 10/10 pass. True positives on 72-hour posting, 24-hour special notice, 10-day Bagley-Keene, 2/3 vote to close debate, and open-meetings questions. Zero false positives on adversarial probes (wrong-hours, wrong-threshold, unknown-section).

The rule is enforced as a tool contract, not as prompt instruction the model "should" follow — see CLAUDE.md rule #2.

Code: `app/managed_agents/custom_tools.py::_verify_citation`. System prompt rule: `app/managed_agents/agent_spec.py`.

---

## Voice latency: getting under Twilio's ceiling

Twilio webhooks have a hard ~15 s response budget; live voice needs to feel snappy or callers hang up. Two production-blocking problems and the fixes:

1. **CMA event-stream overhead.** ~6 s on top of the underlying model on identical prompts. Voice switched to the direct Messages API with sentence-level streaming. Tokens are split on sentence + em-dash boundaries; each clause is synthesized by ElevenLabs (`eleven_flash_v2_5`) and yielded as it's ready. Tool use loop is inline against the same custom-tool handlers CMA uses.
2. **Twilio's `<Play>` buffers the whole MP3.** Live test caught Twilio waiting for the full streamed MP3 before starting playback — caller heard 6 s of silence even though our server was emitting bytes at 2.5 s. Fixed by chained TwiML: `/gather` plays a pre-synthesized filler and `<Redirect>`s to `/continue/{turn_id}`; the Claude turn runs in a background ThreadPool; `/continue` blocks up to 12 s on the Future and returns the reply MP3 + a fresh `<Gather>`. Twilio sees two short, complete MP3s and plays each immediately.

**Net:** filler audio starts within ~500 ms of the caller finishing speaking; perceived first-audio of the real reply lands around ~2.5 s on governance questions.

**Graceful degradation:** ElevenLabs synth is wrapped in a Polly fallback path — quota errors, rate limits, or outages emit `<Say voice="Polly.Joanna">` TwiML rather than 500ing the call.

---

## The evolution (Keep Thinking)

- **v0 (Wed).** Hand-rolled multi-agent supervisor in Python — six specialist files, keyword-routed handoffs. Reference loop kept in `app/agents/_governance_reference_loop.py` so the journey is legible.
- **v1 (Thu morning).** Pivoted to one Claude Managed Agent + specialist modes after Michael Cohen's session. Five `.py` files deleted; the system prompt became the routing layer. First governance question routed to Governance Expert mode unprompted.
- **v2 (Thu midday).** Real `verify_citation` (KB lookup + Haiku 4.5 claim classifier, 10/10 golden Q&A) and real `escalate_to_grace` (Twilio SMS to Grace) replaced the safe stubs. Anti-hallucination guardrail and escalation path are real, not aspirational.
- **v3 (Thu afternoon).** ElevenLabs replaced Polly on voice for quality; tightened reply cap to ~30 words to fit the latency budget; added Polly fallback so voice degrades gracefully under ElevenLabs outages.
- **v4 (Thu evening).** Measured CMA at ~6 s overhead and moved the voice path to the direct Messages API with sentence-level streaming. SMS stayed on CMA where cross-session continuity matters more than first-token latency.
- **v5 (Thu late evening).** Live test exposed Twilio's `<Play>` buffer eating 6 s of audio. Restructured to chained TwiML (`/gather` filler → background turn → `/continue` reply). Filler at ~500 ms, real reply at ~2.5 s.

See [`Progress.md`](./Progress.md) for the day-by-day narrative and [`CHANGELOG.md`](./CHANGELOG.md) for per-commit detail.

---

## Repo layout

```
boardbreeze-concierge-voice/
├── app/
│   ├── main.py                   FastAPI entrypoint (auto-loads .env)
│   ├── config.py                 pydantic-settings env loader
│   ├── voice_pipeline.py         direct Messages API turn loop for voice —
│   │                             sentence streaming, inline tool dispatch,
│   │                             ThreadPool-backed queue_turn_async
│   ├── managed_agents/           CMA integration — used by SMS
│   │   ├── agent_spec.py           system prompt, custom tool defs
│   │   ├── client.py               ensure_agent/environment/session +
│   │   │                           handle_message
│   │   └── custom_tools.py         backend dispatch for search_kb,
│   │                               verify_citation, escalate_to_grace
│   │                               (shared with voice_pipeline)
│   ├── agents/                   v0 reference loop only — nothing imports it
│   ├── tools/governance_tools/   RAG + jurisdiction tools used by custom_tools
│   ├── channels/
│   │   ├── sms.py                  Twilio SMS webhook → CMA
│   │   ├── voice.py                Twilio Voice: chained TwiML, Polly fallback
│   │   └── tts.py                  ElevenLabs synth + static/dynamic caches
│   ├── db/                       Supabase schema + migrations (phone_sessions)
│   └── kb/                       governance_kb seed
├── .claude/skills/               /interview, /governance-verify, /status
├── notes/                        external-intel notes (Cohen talk, etc.)
├── tests/                        offline tests, no network/keys required
├── CLAUDE.md                     project rules for Claude Code sessions
├── CHANGELOG.md                  per-commit detail
├── Progress.md                   day-by-day "Keep Thinking" log
└── README.md                     you are here
```

---

## Setup

```bash
# 1. Python 3.11 venv (the SDKs we use require ≥3.10; 3.11 is what we develop on)
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Environment
cp .env.example .env
# fill in keys — Anthropic, Supabase (URL + service role), Voyage,
# Twilio (SID + auth + phone), ElevenLabs (API key + voice ID),
# and Grace's phone for escalations.

# 3. Supabase schema
# Run app/db/schema.sql then app/db/migrations/001_phone_sessions.sql
# in the Supabase SQL editor.

# 4. Seed the governance KB
python -m app.kb.seed_kb

# 5. Run tests (offline, no keys needed)
python -m pytest tests/

# 6. Sanity-check that the CMA agent + environment exist
python -c "from dotenv import load_dotenv; load_dotenv('.env'); \
  from app.managed_agents.client import ensure_agent, ensure_environment; \
  print(ensure_agent(), ensure_environment())"

# 7. Start the server
uvicorn app.main:app --reload --port 8000

# 8. Expose to Twilio
# In a second terminal:  ngrok http 8000
# Point the Twilio phone number's SMS webhook   at  {ngrok}/twilio/sms/inbound
# Point its Voice webhook                       at  {ngrok}/twilio/voice/inbound
```

---

## Built by

**Grace Esteban** — solo founder of BoardBreeze. Domain expert in California public-agency governance (Brown Act, Bagley-Keene, community college districts, special districts).

Paired with **Claude Code (Opus 4.7)** as development partner throughout the hackathon. See `Co-Authored-By` trailers in `git log` for per-commit attribution.

## License

MIT — see [LICENSE](./LICENSE).
