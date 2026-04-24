# Changelog

All notable changes to BoardBreeze Concierge are logged here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Thu 2026-04-23 (evening) — Voice latency fight, real anti-hallucination, real escalation

After the morning CMA pivot landed, the rest of Thursday was spent
making the voice channel actually answerable inside Twilio's ~15 s
webhook ceiling and turning the two safety stubs (`verify_citation`,
`escalate_to_grace`) into real implementations.

#### Added
- `app/voice_pipeline.py` — direct Messages API turn loop for voice.
  Streams Claude tokens, splits on sentence + em-dash boundaries, fires
  ElevenLabs synth per clause, yields MP3 chunks. Tool use loop is
  inline and dispatches to the same `custom_tools` handlers CMA uses,
  so `search_governance_kb` / `verify_citation` / `escalate_to_grace`
  work identically. Pre-tool flush synthesizes any half-finished clause
  before the tool pause so the caller doesn't hear dead air mid-sentence.
  `queue_turn_async` / `get_turn_result` expose a ThreadPool-backed
  Future so the chained-TwiML production path (see below) can collect
  the streaming generator's output into a single MP3 blob.
- `app/channels/tts.py` — ElevenLabs `eleven_flash_v2_5` synth via
  `<Play>`. Static-bytes cache for the greeting + reprompt (skips a
  synth round-trip on first touch); dynamic-text cache + queue/pop for
  per-call clause streaming; `register_audio(bytes)` so a background
  turn can hand a pre-computed blob to `/audio` without re-running synth.
- Polly fallback path in `voice.py` — `<Say voice="Polly.Joanna">`
  TwiML when ElevenLabs synth fails (quota, rate limit, outage). Call
  stays up; voice quality degrades rather than the app 500ing.
- Caller-phone propagation via `ContextVar` (`custom_tools.py`) so the
  turn handler can pass the caller's E.164 to `escalate_to_grace`
  without leaking it into the dispatcher signature.

#### Changed
- `app/managed_agents/custom_tools.py::_verify_citation` —
  stub replaced with real implementation: extract section number from
  the agent's citation string, look it up in `governance_kb`, ask Haiku
  4.5 whether the chunk text actually supports the claim. Returns
  `verified` + `actual_text` on a hit, `suggested_rewrite` on a miss.
  Ten-case golden Q&A passes 10/10 — true positives on 72-hour posting,
  24-hour special notice, 10-day Bagley-Keene, 2/3 vote to close
  debate, open-meetings; guarded against wrong-hours / wrong-threshold /
  unknown-section false positives. Haiku keeps the round trip under
  ~300 ms so voice stays inside Twilio's ceiling.
- `app/managed_agents/custom_tools.py::_escalate_to_grace` —
  stub replaced with real implementation: Twilio SMS to Grace's phone
  with caller phone, channel, reason, urgency, and summary. Missing
  Twilio config or send failures log and return `status=logged_only`
  instead of surfacing as an error — the caller still hears "Grace will
  reach out".
- `app/channels/voice.py` — restructured to chained TwiML:
  `/gather` plays a pre-synthesized filler and `<Redirect POST>`s to
  `/continue/{turn_id}`; the Claude turn runs in a background thread;
  `/continue` blocks up to 12 s on the Future and returns
  `<Play>reply</Play><Gather/>`. Twilio sees two short, complete MP3s
  and plays each one immediately. Filler audio starts within ~500 ms
  of the caller finishing speaking. `/status` endpoint cleans up
  per-call history on `CallStatus=completed`.
- `app/managed_agents/agent_spec.py` — system prompt tightened to a
  ~30-word / two-sentence cap, with explicit guidance to skip tool
  calls on general-knowledge questions so replies fit the latency
  budget.
- `app/main.py` — auto-loads `.env` from repo root so `uvicorn` picks
  up creds without a shell export; `logging.basicConfig` so `app.*`
  loggers surface alongside uvicorn's.

#### Removed
- The "say a 2-word filler before tool calls" system-prompt rule. It
  worked, but combined with the static `/gather` filler it played
  back-to-back redundant fillers and wasted ~2 s of Opus generation
  time. Chained-TwiML filler is enough on its own.

#### Performance
- Measured CMA event-stream overhead at ~6 s on top of the underlying
  model on identical Opus 4.7 prompts (Messages API streaming: TTFT
  0.98 s, done at 1.68 s; Managed Agents: first event at 7.66 s). Voice
  switched to direct Messages API; SMS stays on CMA where the
  cross-session continuity matters more than first-token latency.
- End-to-end voice perceived latency: ~7 s → ~2.5 s for governance
  questions (filler audio at 500 ms, real reply streaming as clauses
  finish).

### Thu 2026-04-23 — Architecture pivot to Claude Managed Agents

Michael Cohen's "Cloud Managed Agents" hackathon session landed this
morning. Grace's live question got answered: **first-class multi-agent
is not production-ready yet**, and the current Anthropic-recommended
pattern is one agent + many skills/tools. See
`notes/cohen-managed-agents.md` for the full transcript and the direct
quotes driving the pivot.

#### Added
- `app/managed_agents/` — production integration layer.
  - `agent_spec.py`: consolidated system prompt (5 specialist modes),
    three custom tools (`search_governance_kb`, `verify_citation`,
    `escalate_to_grace`), and `agent_create_kwargs()`.
  - `client.py`: idempotent `ensure_agent()` / `ensure_environment()`
    (name-keyed find-or-create), phone-keyed `get_or_create_session()`
    against Supabase, and `handle_message(phone, text, channel)` — the
    single entry point both Twilio channels call.
  - `custom_tools.py`: backend dispatch. `search_governance_kb` hits the
    `match_governance_kb` RPC with Voyage query embeddings;
    `verify_citation` stub returns `verified=false` + a safe rewrite
    until the real classifier lands; `escalate_to_grace` logs + returns
    queued status until the Twilio-to-Grace SMS wiring lands Fri.
- `app/db/migrations/001_phone_sessions.sql` — one-table migration
  `(phone, cma_session_id, created_at, last_used_at)` that backs the
  "Jane texts Monday, again Thursday, agent remembers" feature.
- `notes/cohen-managed-agents.md` — distilled talk notes, Grace's
  live-Q&A quote, and the architectural decision.
- `CLAUDE.md` session-guidance doc.
- `CHANGELOG.md` (this file).
- Python 3.11 venv at `.venv/` with all SDKs installed via `uv`.
- `python-multipart` added to requirements for FastAPI Form parsing.

#### Changed
- `app/channels/sms.py` + `voice.py`: both now call
  `handle_message(...)` via `run_in_threadpool` instead of the old
  `run_concierge_turn` supervisor. TwiML shape unchanged.
- `app/db/schema.sql` and `app/tools/governance_tools/embeddings.py`:
  embedding width corrected from 1024-dim → 512-dim after discovering
  `voyage-3-lite` doesn't support 1024 (it's a fixed-512 model). Schema
  applied to live Supabase; old tables never existed so no migration.
- `CLAUDE.md` rule #3 rewritten as "one managed agent + specialist
  modes, not N sub-agents" — driven by Cohen's guidance.

#### Removed
- `app/agents/{concierge,governance_expert,sales_closer,product_expert,
  tech_support,escalation}.py` — the hand-rolled supervisor + specialist
  stubs. Their work lives in the consolidated system prompt on the CMA
  agent. `_governance_reference_loop.py` kept as the v0 reference for
  the README's "Keep Thinking" narrative.

#### Infra
- Supabase: `governance-concierge` project provisioned. Schema
  (`governance_kb`, `conversation_state`, `handoffs`,
  `match_governance_kb` RPC) live with RLS enabled. `phone_sessions`
  migration pending at time of writing.
- Anthropic CMA: Concierge agent and environment provisioned
  (`boardbreeze-concierge` / `boardbreeze-concierge-env`). End-to-end
  round-trip verified against a test session — agent correctly adopted
  Governance Expert mode, called `search_governance_kb`, handled empty
  KB gracefully per system prompt.
- Voyage AI: `voyage-3-lite` connectivity confirmed (512-dim).
- Deepgram: signup deferred to Friday when streaming STT comes online.

#### Configured (local, not committed)
- `.env` populated with Anthropic, Supabase (URL + service role),
  Voyage, Twilio (SID + auth + phone), ElevenLabs (API key + voice ID),
  and Grace's phone for escalations. Deepgram deferred.

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
