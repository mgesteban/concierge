# Progress Log — BoardBreeze Concierge

Running log of daily progress for the Apr 21–27 2026 hackathon.
Source material for the README's v0→v5 "Keep Thinking" narrative and the
demo video voiceover. Generated (mostly) by the `/status` skill at end of day.

**Submission deadline:** Sun 2026-04-26, 8:00 PM EST.

---

## 2026-04-22 (Wed) — Scaffold day

**Shipped today**
- Public repo initialized at https://github.com/mgesteban/concierge (MIT license).
- FastAPI skeleton: `app/main.py`, `/health`, Twilio SMS + Voice webhook routers.
- Agent modules scaffolded: Concierge supervisor, Governance Expert (wrapping the reference loop), and stubs for Sales Closer, Product Expert, Tech Support, Escalation.
- Governance tools integrated as `app/tools/governance_tools/` — 4 Anthropic tools (`search_governance_kb`, `check_jurisdiction_rules`, `generate_compliant_template`, `hand_off_to_sales`) with Supabase pgvector backing, Voyage 1024-dim embeddings, offline tests.
- `verify_citation` tool stubbed at `app/tools/verify_citation.py` — real implementation lands Thursday.
- `.claude/skills/` seeded with `/interview`, `/governance-verify`, `/status` per Tark's power-move playbook (§16).
- README written against the four judging criteria: Impact, Demo, Opus 4.7 Use, Depth & Execution.

**What evolved (Keep Thinking)**
- Entered Wednesday assuming we'd scaffold the whole multi-agent architecture from scratch. Discovered the governance_tools package Grace had built earlier in the week was already production-grade (schemas, RAG, tests, reference agent loop) — folded it in as `app/tools/governance_tools/` instead of rewriting. Saved ~6 hours.
- Decided to keep the reference agent loop (`_governance_reference_loop.py`) alongside the production wrapper (`governance_expert.py`) so the evolution from "naive one-shot" to "verified multi-turn" is legible in the repo rather than buried in git history.

**Cut from today's plan**
- Intent classification in the Concierge supervisor — Wednesday uses keyword routing; real classifier lands Thursday after the Michael Cohen Managed Agents session.
- Supabase `conversation_state` write-through — schema is in place, but webhook handlers log to memory for now. Real persistence Thursday.

**Tomorrow's top 3 (Thu Apr 23)**
1. Attend Michael Cohen's Managed Agents session; convert orchestration to the pattern he recommends.
2. Implement `verify_citation` for real: KB lookup → Claude-based claim-support classifier → `{verified, actual_text, suggested_rewrite}`. Wire into Governance Expert's tool list.
3. Wire Twilio Voice end-to-end: ngrok → FastAPI → Concierge → Polly `<Say>` for day-one latency. (Deepgram/ElevenLabs streaming is a Friday upgrade.)

**Open questions / risks**
- The `NEVER`/`ALWAYS` language in the original Governance Expert system prompt contradicts Tark's §8.6 guidance for 4.7. Need to rewrite conditionally before Thursday's live tests — otherwise the agent will over-refuse benign explanatory questions.

**Evening addendum (post-push)**
- Pushed `51eb246` to `origin/main` after rebasing on top of GitHub's stub README commit. Repo is public, MIT licensed: https://github.com/mgesteban/concierge
- Resolved the three end-of-day unknowns:
  - ✅ Subscriber outreach — Grace has 3 BoardBreeze subscribers she can line up personally tomorrow; no cold email needed.
  - ✅ Twilio — account SID, auth token, and phone number already in hand.
  - ✅ Anthropic credits — $500 received.
- `.env` populated locally with Anthropic API key, Twilio (SID + auth + phone), ElevenLabs (API key + voice ID), and Grace's personal phone number for escalations. Supabase, Voyage, and Deepgram keys deferred until Thursday when those subsystems come online.
- Ready state for Thursday: `uvicorn app.main:app --reload` should boot tomorrow with zero additional setup.

---

## 2026-04-23 (Thu) — Managed Agents pivot + first working voice loop

**The headline**

Grace asked her question live on Michael Cohen's Managed Agents session
this morning — the exact pattern we'd planned to build (distributed
6-agent topology with supervisor handoffs). His answer, verbatim:

> "I would probably just hold off until we get first-class support for
> multi-agents."

He confirmed it's shipping "very soon" but not production-ready today.
His recommendation matched Tark's from Tuesday: **one agent + many
skills/tools**, not N sub-agents. So we pivoted the whole architecture
in one pass. Details in `notes/cohen-managed-agents.md`.

**Shipped today**

- Morning infra: Python 3.11 venv via `uv`, Supabase project
  (`governance-concierge`) provisioned and schema-applied, Voyage
  account live, connectivity smoke-tested end-to-end. Caught and fixed
  a dimension mismatch (`voyage-3-lite` is 512-dim only, the tools
  package assumed 1024) before it could cause a runtime failure.
- `app/managed_agents/` — full CMA integration. `agent_spec.py` holds
  the consolidated Concierge system prompt (five specialist modes as
  described in §5 of the playbook, expressed as conditional-language
  guidance per CLAUDE.md rule #1). `client.py` is the single
  `handle_message(phone, text, channel) -> str` entry point both Twilio
  channels use — it idempotently ensures the agent + environment exist,
  finds-or-creates a CMA session keyed on caller phone via Supabase,
  sends `user.message`, streams events, dispatches custom tools inline,
  and returns assembled reply text. `custom_tools.py` implements
  `search_governance_kb`, `verify_citation` (stub), and
  `escalate_to_grace` (stub).
- CMA provisioning executed for real: agent `boardbreeze-concierge`
  (id `agent_011CaMckX2etSZait4iM4kfi`) and environment
  `boardbreeze-concierge-env` (id `env_01LFKsSa8ntB3j3MqeCuGUS4`) are
  live in Grace's Anthropic account.
- **First working reply from the Concierge**, via smoke test:
  > "Yes, this is the BoardBreeze concierge — how can I help you
  > today?"
- **First working tool dispatch**, also smoke-tested. Asked "how far
  ahead do I have to post the Brown Act agenda" — the agent adopted
  Governance Expert mode unprompted, called `search_governance_kb`
  with `jurisdiction: "CA"`, got an empty result (KB not seeded yet),
  and correctly fell back to a general 72-hour explanation plus a
  callback offer — exactly what the system prompt instructs on empty
  KB hits. The anti-hallucination guardrail (CLAUDE.md rule #2) works
  on day one of the new architecture.
- `app/channels/sms.py` + `voice.py`: rewired to call `handle_message`
  via `run_in_threadpool`. TwiML shape unchanged, so Twilio's console
  config doesn't need to change. Old supervisor scaffolding deleted.
- `app/db/migrations/001_phone_sessions.sql` — small table that makes
  "Jane texts Monday, texts again Thursday, agent remembers" free: we
  reuse the same CMA session across calls for the same E.164 number,
  and CMA sessions idle for weeks at no cost (Cohen confirmed live).

**What evolved (Keep Thinking)**

- Entered Thursday about to build a hand-rolled 6-agent supervisor loop
  in Python with explicit handoff payloads between modules. Cohen's
  session flipped the whole plan before any code was written. Net
  outcome: less code (five specialist `.py` files deleted), better
  prize positioning (we now use every CMA primitive idiomatically —
  agents, environments, sessions, custom tools, events), and a clean
  upgrade path when first-class multi-agent ships.
- The system prompt doubled as routing layer: instead of a keyword
  classifier in Python dispatching to specialist modules, the single
  consolidated prompt describes each specialist mode and lets Claude
  4.7 pick. The first governance question we threw at it routed
  correctly without any tuning.
- Realized we don't need the CMA sandbox container at all for this
  product — the Concierge is a chat concierge, not a coding agent.
  Custom tools (which run in our FastAPI backend, not in the sandbox)
  are the right shape for `verify_citation`, `search_governance_kb`,
  and `escalate_to_grace`. Keeps our KB and SMS credentials out of
  Claude's reach — good for demo narrative too.

**Cut from today's plan**

- Deepgram signup + streaming STT — still Friday, per original plan.
  Day-one voice uses Twilio `<Gather input="speech">` + Polly `<Say>`.
  Latency is ~3–5s/turn, fine for the Thursday milestone.
- Real `verify_citation` classifier — tool is registered and the stub
  is safe (returns `verified=false` with a conservative rewrite). Real
  classifier lands later today or Fri morning.
- KB seed from the Brown Act PDF — pending (task #7). Was going to do
  it this afternoon while Grace runs the migration; writing this
  entry first.

**Tomorrow's top 3 (Fri Apr 24)**

1. Real `verify_citation`: section-exact KB lookup → Claude-based
   claim-support classifier → `{verified, actual_text, suggested_rewrite}`.
   Golden-Q&A suite of 10 pairs, tune threshold until false-pass = 0.
2. Real `escalate_to_grace`: Twilio SMS to Grace + email via Gmail
   MCP, with caller transcript link.
3. Deepgram + ElevenLabs streaming upgrade to the voice channel. Same
   `handle_message` under the hood.
4. First real-subscriber user test — Grace has 3 BoardBreeze
   subscribers lined up.

**Open questions / risks**

- Memory store: Cohen teased it launching "in the next couple of hours"
  at ~11am PT. Haven't wired it yet. If it ships before Sun we get
  true cross-session memory for free — should check the Anthropic
  Twitter and docs tonight.
- Session reuse + RLS: the new `phone_sessions` table uses Supabase
  RLS like everything else. Our service-role key bypasses RLS so
  functionally fine, but if we ever add a public dashboard that reads
  this table, we need policies.
- TwiML `<Say>` with long Claude replies: if the agent produces a
  multi-paragraph answer, Polly will read the whole thing before
  listening again. Need to either cap reply length in the system
  prompt (already hinted with "two to four sentences") or chunk the
  `<Say>` blocks with intermediate `<Gather>` for barge-in. Revisit
  after first live call.

**Evening addendum — voice latency fight + real safety tools**

What landed after the morning entry:

- **ElevenLabs replaces Polly + ~30-word reply cap** (`7e24e59`).
  `<Say>` swapped for `<Play>` against `eleven_flash_v2_5`. Greeting
  + reprompt static-cached so first touch skips a synth round-trip.
  System prompt tightened to two sentences / ~30 words and told to
  skip tool calls on general-knowledge questions so replies fit
  Twilio's webhook ceiling. `main.py` now auto-loads `.env` from repo
  root.
- **Real `verify_citation` + real `escalate_to_grace` + Polly
  fallback** (`3bb5edf`). Verify: extract section number → KB lookup
  → Haiku 4.5 claim-support classifier. Ten-case golden Q&A passes
  10/10 (true positives on 72-hour posting, 24-hour special notice,
  10-day Bagley-Keene, 2/3 vote to close debate, open-meetings;
  guards against wrong-hours / wrong-threshold / unknown-section
  false positives). Haiku keeps the round trip under ~300 ms so
  voice stays under budget. Escalate: Twilio SMS to Grace with
  caller phone (via `ContextVar`), channel, reason, urgency,
  summary; missing Twilio config or send failures degrade to
  `status=logged_only` so the caller still hears "Grace will reach
  out". Voice channel wraps ElevenLabs in a Polly fallback path so
  outages or quota errors degrade voice quality rather than 500 the
  app.
- **Direct Messages API for voice + sentence streaming** (`5069f0f`).
  Measured CMA at ~6 s overhead on top of the underlying model on
  identical Opus 4.7 prompts (TTFT 0.98 s vs first event at 7.66 s).
  Voice now drives a direct-Messages turn loop in
  `app/voice_pipeline.py` — streams tokens, splits on sentence + em-
  dash boundaries, fires ElevenLabs synth per clause, handles tool
  use inline against the same `custom_tools` handlers CMA uses. SMS
  stays on CMA. (CLAUDE.md updated to reflect the voice exception.)
- **Chained TwiML to defeat Twilio's `<Play>` buffer** (`bab60ee`).
  Live test caught Twilio buffering the streamed MP3 — caller heard
  6 s of silence even though our server was emitting bytes at 2.5 s.
  Fix: `/gather` plays a pre-synthesized filler and `<Redirect>`s to
  `/continue/{turn_id}`; the Claude turn runs in a background thread
  pool; `/continue` blocks up to 12 s on the Future and returns the
  reply MP3 + a fresh `<Gather>`. Twilio sees two short complete
  MP3s and plays each immediately. Filler starts within ~500 ms.
  Removed the "say 'Let me check.' before tool calls" prompt rule —
  combined with the static filler it played back-to-back redundant
  fillers and burned ~2 s of Opus generation.

**End-of-day net result**

- Perceived voice latency: ~7 s → ~2.5 s for governance questions.
- Anti-hallucination guardrail (CLAUDE.md rule #2) is real, not a
  stub — section claims get verified against the KB before the agent
  speaks them.
- Escalation path is real — Grace gets a Twilio SMS with the
  caller's number when the Concierge hands off.
- Voice degrades gracefully across two failure modes: Polly fallback
  when ElevenLabs fails, `status=logged_only` when Twilio SMS fails.

**Adjusted Friday top 3**

Original Friday list had real `verify_citation` + real
`escalate_to_grace` + Deepgram/ElevenLabs streaming. First two are
done. Revised list:

1. Seed the governance KB from the Brown Act + Bagley-Keene PDFs
   (still pending — golden Q&A above ran against hand-curated chunks).
2. First real-subscriber user test on the chained-TwiML voice path.
   Watch for: filler-to-reply gap on long answers, barge-in behavior,
   `/continue` 12 s ceiling under tool-use load.
3. Decide whether the SMS path also moves to direct Messages API. The
   ~6 s CMA overhead matters less for SMS, but if cross-session
   continuity can be reproduced on top of Supabase + direct Messages
   with acceptable code, consolidating to one turn-loop simplifies
   the demo narrative.

---
