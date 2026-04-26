# BoardBreeze Concierge

**The customer success team I couldn't afford to hire — running on Claude Opus 4.7.**

A voice + SMS concierge for [appboardbreeze.com](https://appboardbreeze.com/), the SaaS that helps California public-agency boards run Brown-Act-compliant meetings. Callers dial or text one phone number; a single Claude Opus 4.7 agent answers governance questions, resolves product support, closes deals, and escalates to the founder when a human is actually needed.

> My entry to the **Anthropic × Cerebral Valley Global Hackathon** (Apr 21–27 2026). Built with Claude Opus 4.7 and Claude Code.

---

## Try it now

- **Call or text:** **1-844-786-2076**
- **Live API:** https://concierge.appboardbreeze.com
- **Health:** https://concierge.appboardbreeze.com/health → `{"status":"ok"}`

Running 24/7 on AWS ECS Fargate (us-east-2) behind an Application Load Balancer with an Amazon-issued TLS certificate.

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
                  │ _kb     +        │         │ (Haiku 4.5)      │
                  │ search_product_kb│         │ section lookup + │
                  │ (Voyage 512-dim  │         │ claim-support    │
                  │  + Supabase      │         │ classifier       │
                  │  pgvector)       │         │                  │
                  └──────────────────┘         └──────────────────┘

                           ┌──────────────────┐
                           │ escalate_to_grace│
                           │ (Twilio SMS to   │
                           │  Grace's phone)  │
                           └──────────────────┘
```

The voice path and SMS path share the same custom tools (`search_governance_kb`, `search_product_kb`, `verify_citation`, `escalate_to_grace`) — the same backend handlers in `app/managed_agents/custom_tools.py`. They diverge only at the turn loop: SMS runs on Claude Managed Agents (free cross-session memory, idle for weeks at no cost); voice runs on the direct Messages API to fit inside Twilio's ~15 s webhook ceiling.

**The KB.** A single Supabase `governance_kb` table backs both retrieval tools. Rows tagged `jurisdiction='CA' / 'CA_STATE' / 'any'` are public-meeting law (Brown Act, Bagley-Keene, Robert's Rules, Ed Code) — 20 hand-curated chunks with exact statutory citations. Rows tagged `jurisdiction='product'` are the BoardBreeze product FAQ — 61 chunks covering plans, pricing, free trial, auth, audio formats, transcription, minutes formatting, security, and the glossary. Embeddings are Voyage `voyage-3-lite` (512-dim); retrieval is pgvector cosine similarity via the `match_governance_kb` RPC.

---

## How we used Opus 4.7

We chose Opus 4.7 specifically for three properties that 4.6 couldn't match:

1. **Multi-mode coherence in one prompt.** The Concierge is a single agent whose system prompt describes five specialist modes — Claude picks the right mode per turn. 4.7 stays locked on the active mode through tool use and back; 4.6 drifts (kept offering governance citations mid-sales-close in our regression script).
2. **Precise instruction following.** The system prompt specifies exactly when to cite, when to defer to counsel, when to call `verify_citation`, when to hand off. 4.7 follows these conditionals without drift.
3. **Adapted prompts to literal interpretation.** Per Tark's AMA (playbook §8.6), we rewrote `NEVER`/`ALWAYS` prohibitions as conditional language ("avoid X unless Y") to prevent 4.7 from over-triggering on adjacent legitimate behavior. The Governance Expert mode explains what the Brown Act *is* without refusing, while still declining jurisdiction-specific legal advice.

The same pattern is enforced as a project rule in [CLAUDE.md](./CLAUDE.md) so it survives future prompt edits.

---

## What Opus 4.6 couldn't do

Three concrete behaviors made 4.6 the wrong fit for this product. Each one mapped to a specific change we made for 4.7.

**1. Mode coherence under tool use.** The Concierge holds five specialist modes in a single system prompt. On 4.6, after a tool call returned (e.g. `search_governance_kb` mid-sales-conversation), the model drifted back to whichever mode the prompt mentioned first — typically Governance — and re-introduced a citation the caller hadn't asked for. 4.7 stays locked on the active mode through the tool round trip and resumes the conversation in the same register the caller was already in. Same prompt, same KB, different model: 4.7 ships, 4.6 doesn't.

**2. Long-call thread continuity.** A real support call can run 10+ minutes and 30–40 turns; an SMS thread can span days. Per the framing of 4.7's release, 4.6 loses the thread at that length. We chose to lean on 4.7's longer coherent context rather than paper over the gap with a hand-rolled summarizer in the prompt. The visible payoff is the "Jane texts Monday, again Thursday" cross-session memory flow — same CMA session, no summarization, agent picks up where Monday left off.

**3. Literal instruction-following as a feature, not a bug.** Prompt writers used to over-emphasize prohibitions in caps lock ("NEVER do X", "ALWAYS do Y") because earlier models were loose. 4.7 follows those instructions literally, which means a `NEVER` instruction over-triggers and refuses adjacent legitimate behavior. We adapted: the Concierge system prompt uses conditional language throughout ("avoid X unless Y; here's how to handle the edge case"). The Governance Expert mode now explains *what the Brown Act is* without refusing, while still declining jurisdiction-specific legal advice that requires interpreting a statute against a caller's specific facts. [CLAUDE.md rule #1](./CLAUDE.md) enforces this convention for future prompt edits.

The `verify_citation` layer is what makes the literal-following bet safe in production: even when 4.7 is willing to cite a section, the tool contract gates the citation against the actual KB text. That contract isn't a "should" the model needs to remember — it's a function call the agent has to make before it speaks.

---

## How we used Claude Managed Agents

After Michael Cohen's Thursday session at the hackathon, we pivoted from a planned six-agent supervisor topology to **one Managed Agent + specialist modes** — Anthropic's currently-recommended pattern. First-class multi-agent is shipping soon; this architecture upgrades cleanly when it does. See [`notes/cohen-managed-agents.md`](./notes/cohen-managed-agents.md) for the direct quotes.

What we use from CMA, idiomatically:

- **Agent + environment:** `boardbreeze-concierge` / `boardbreeze-concierge-env`, provisioned via `ensure_agent` / `ensure_environment` (idempotent, name-keyed find-or-create).
- **Sessions, one per caller phone:** the `phone_sessions` table maps E.164 → CMA `session_id`, so cross-session memory ("Jane texts Monday, again Thursday") is free on the SMS path. CMA sessions idle for weeks at no cost.
- **Custom tools:** `search_governance_kb`, `search_product_kb`, `verify_citation`, `escalate_to_grace` — registered as CMA custom tools whose handlers run in our FastAPI backend, not in the CMA sandbox. Keeps Supabase + Twilio credentials out of the agent's reach.

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

## Production deployment

Live in `us-east-2` on **AWS ECS Fargate**, in the same cluster as the main `appboardbreeze.com` service.

- **Image:** Python 3.11 slim, ~478 MB, pushed to Amazon ECR (`boardbreeze-concierge` repo).
- **Task:** Fargate, 1 vCPU / 2 GB, port 8000, awsvpc networking, deployment circuit-breaker with auto-rollback.
- **Secrets:** 11 API keys (Anthropic, Twilio×3, Supabase×2, Voyage, ElevenLabs×2, Grace contact) live in **AWS Secrets Manager** as one JSON secret; the task definition projects each key into its own env var via `valueFrom`. The execution role has read access scoped to that one secret ARN — least privilege.
- **Networking:** dedicated **Application Load Balancer** (separate from the existing CDK-managed ALB so the prod stack stays untouched), TLS via an **Amazon-issued ACM certificate** for `concierge.appboardbreeze.com`, HTTP→HTTPS 301 redirect on `:80`. Two security groups: ALB SG (public 80/443), task SG (8000 only from ALB SG).
- **DNS:** `concierge.appboardbreeze.com` → ALB DNS via a Vercel CNAME (the apex domain registers with Vercel).
- **Logs:** CloudWatch `/ecs/boardbreeze-concierge`, 30-day retention.
- **Container health:** Docker `HEALTHCHECK` curls `/health` every 30 s. ALB target group hits the same path on a 15 s interval.

The full step-by-step playbook with every CLI command pre-filled is in [`Deployment.md`](./Deployment.md). The original plan was AWS App Runner; we pivoted to ECS Fargate mid-hackathon to match the rest of the BoardBreeze stack and avoid running two operational mental models. The pivot took one Saturday afternoon.

---

## The evolution (Keep Thinking)

- **v0 (Wed).** Hand-rolled multi-agent supervisor in Python — six specialist files, keyword-routed handoffs. Reference loop kept in `app/agents/_governance_reference_loop.py` so the journey is legible.
- **v1 (Thu morning).** Pivoted to one Claude Managed Agent + specialist modes after Michael Cohen's session. Five `.py` files deleted; the system prompt became the routing layer. First governance question routed to Governance Expert mode unprompted.
- **v2 (Thu midday).** Real `verify_citation` (KB lookup + Haiku 4.5 claim classifier, 10/10 golden Q&A) and real `escalate_to_grace` (Twilio SMS to Grace) replaced the safe stubs. Anti-hallucination guardrail and escalation path are real, not aspirational.
- **v3 (Thu afternoon).** ElevenLabs replaced Polly on voice for quality; tightened reply cap to ~30 words to fit the latency budget; added Polly fallback so voice degrades gracefully under ElevenLabs outages.
- **v4 (Thu evening).** Measured CMA at ~6 s overhead and moved the voice path to the direct Messages API with sentence-level streaming. SMS stayed on CMA where cross-session continuity matters more than first-token latency.
- **v5 (Thu late evening).** Live test exposed Twilio's `<Play>` buffer eating 6 s of audio. Restructured to chained TwiML (`/gather` filler → background turn → `/continue` reply). Filler at ~500 ms, real reply at ~2.5 s.
- **v6 (Sat).** Closed the Product Expert mode's KB hole. Grace's internal BoardBreeze FAQ (28 sections) chunked into 61 product rows alongside the 20 governance rows in the same `governance_kb` table, tagged `jurisdiction='product'`. New `search_product_kb` tool (same Supabase RPC, jurisdiction-pinned) so Product Expert mode answers pricing / plan / feature questions from authoritative source rather than model recall. Without this, the agent dodged "what's your pricing" with a callback offer; with this, it cites the actual $29.99 / $99 / $499 tiers.
- **v7 (Sat night).** Production deployment. Started on AWS App Runner; pivoted to ECS Fargate mid-day to match the existing `appboardbreeze.com` stack pattern and consolidate ops. In one afternoon: containerized the app (Dockerfile + `.dockerignore`), pushed the image to a new ECR repo, moved 11 env values into a single AWS Secrets Manager JSON entry, built two least-privilege IAM roles, registered the task definition with Secrets Manager `valueFrom` projections, created a dedicated ALB + target group + security groups (separate from the CDK-managed ALB so the prod stack stays untouched), got an Amazon-issued ACM cert for `concierge.appboardbreeze.com` (the first attempt failed `CAA_ERROR` because Vercel's default CAA on the apex didn't authorize Amazon — added 4 records, waited 5 min for AWS's internal CAA cache to clear, retried, issued in 19 s), pointed Vercel DNS at the ALB, flipped Twilio webhooks. First production call completed end-to-end (Twilio → ALB → Fargate task → Messages API → Supabase KB → ElevenLabs → caller's ear) in ~5 s. Live at https://concierge.appboardbreeze.com. Full playbook in [`Deployment.md`](./Deployment.md).

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
│   │   └── custom_tools.py         backend dispatch for
│   │                               search_governance_kb, search_product_kb,
│   │                               verify_citation, escalate_to_grace
│   │                               (shared with voice_pipeline)
│   ├── agents/                   v0 reference loop only — nothing imports it
│   ├── tools/governance_tools/   RAG + jurisdiction tools used by custom_tools
│   ├── channels/
│   │   ├── sms.py                  Twilio SMS webhook → CMA
│   │   ├── voice.py                Twilio Voice: chained TwiML, Polly fallback
│   │   └── tts.py                  ElevenLabs synth + static/dynamic caches
│   ├── db/                       Supabase schema + migrations (phone_sessions)
│   └── kb/                       governance_kb seed (statute chunks + the
│                                 BoardBreeze FAQ chunker — both go into one
│                                 table, distinguished by `jurisdiction`)
├── Dockerfile                    python:3.11-slim, port 8000, /health curl healthcheck
├── .dockerignore                 keeps .env, KB sources, demo assets out of image
├── Deployment.md                 12-phase ECS Fargate playbook, every CLI command pre-filled
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

# 4. Seed the KB (governance statutes + BoardBreeze product FAQ).
# Place the FAQ markdown at the repo root as
# "BoardBreeze Comprehensive FAQ — AI Agent Knowledge Base.md"
# (gitignored — supply your own product KB if reproducing). The
# governance chunks ship inside seed_kb.py and need no extra files.
python -m app.kb.seed_kb

# 5. Run tests (offline, no keys needed)
python -m pytest tests/

# 6. Sanity-check that the CMA agent + environment exist
python -c "from dotenv import load_dotenv; load_dotenv('.env'); \
  from app.managed_agents.client import ensure_agent, ensure_environment; \
  print(ensure_agent(), ensure_environment())"

# 7. Start the server (local dev)
uvicorn app.main:app --reload --port 8000

# 8. Expose to Twilio (local dev only)
# In a second terminal:  ngrok http 8000
# Point the Twilio phone number's SMS webhook   at  {ngrok}/twilio/sms/inbound
# Point its Voice webhook                       at  {ngrok}/twilio/voice/inbound
```

For **production deployment** (AWS ECS Fargate, the stack actually serving https://concierge.appboardbreeze.com), follow [`Deployment.md`](./Deployment.md) — 12 phases from `Dockerfile` to live HTTPS, with every CLI command pre-filled with the relevant account, cluster, VPC, and subnet IDs.

---

## Built by

**Grace Esteban** — solo founder of BoardBreeze. Domain expert in California public-agency governance (Brown Act, Bagley-Keene, community college districts, special districts).

Paired with **Claude Code (Opus 4.7)** as development partner throughout the hackathon. See `Co-Authored-By` trailers in `git log` for per-commit attribution.

## License

MIT — see [LICENSE](./LICENSE).
