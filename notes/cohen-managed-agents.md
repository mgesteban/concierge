# Cloud Managed Agents — Michael Cohen (Anthropic)
Hackathon session, Thu 2026-04-23. Key excerpts and architectural takeaways.

## Core primitives

**Agents** — spec resource (system prompt, model, tools, skills). Versioned.
Create once per distinct persona/prompt. Reuse across sessions.

**Environments** — sandbox-container template. Network egress policy,
pre-installed packages (pip/npm). Created once, reused.

**Sessions** — one conversation / event stream between a user and Claude
in the harness. Idle for "weeks, months" with no charge. Resumed by
sending a new event.

**Custom tools** — Claude emits `agent.custom_tool_use`; your backend
handles it; you round-trip a `user.tool_result`. Good for tools that
must stay server-side (our DB, our KB, our verification layer).

**MCP servers** — connected to sessions with per-user credentials stored
in a vault. Credentials never reach Claude.

**Skills** — loaded into an agent as a capability. Cohen and Tark both
say: **bias toward skills over subagents**.

**Native sandbox tools** — bash, file read/write, glob, grep, web search,
web fetch. Free and always available inside the container.

## What Anthropic takes care of for us
- Context auto-management up to ~1M tokens (alternative strategies shipping)
- Retries, error recovery, checkpointing
- Sandbox provisioning + lifecycle
- Tool execution plumbing (long-running, oversized outputs)
- Credential isolation

## The critical quote for our architecture

Grace asked the multi-agent handoff question live. Cohen's answer:

> "We are currently in the middle of working on, like, what we, what I
> would call our basic multi-agent integration... all of this is kind of
> like coming very soon. My recommendation is that you can stitch some
> of this together today using the sessions APIs yourself, so you can
> create a different session for each one of your agents and like decide
> that certain status changes or uh events can be like brought back and
> forth between those agents. However, I think that is probably not
> going to, it's probably gonna take a lot more work on your end in
> order to, to get it working correctly. **I would probably just hold off
> until we get like first-class support for multi-agents.**"

Translation: don't build a distributed 6-agent topology today. Build
**one agent + many skills**, and upgrade when multi-agent ships.

## Second critical quote (on skills vs subagents)

> "I don't think that... for the most part, you probably don't need a
> subagent for every little nitty gritty thing. Instead, you should
> develop skills that use them... You can develop like a consumer
> application yourself that has a bunch of skills, single agent ever.
> You don't need a sub agent for or an individual agent for everything.
> Just give it the right skills, and then it'll go from there."

## Events we'll need to handle
- `status` — idle / running / rescheduling / terminated
- `agent.message` — Claude speaking (→ TTS pipeline)
- `agent.custom_tool_use` — our verify_citation, search_kb, etc.
- `agent.mcp_tool_use` — Calendar booking, Slack
- Span events — inference start/end (useful for UI "thinking…" states)
- Compaction events — let us log when 1M is hit

## Other announcements
- **Memory store** shipping "in the next couple of hours" (Thu PM).
  Cross-session memory without us writing any code.
- **Outcomes** (self-verification rubric) — research preview waitlist.
  We can simulate our own version via verify_citation.
- **Managed Agents skill for Claude Code** — Cohen used it live. Exists
  in the public Anthropic skills repo. Teaches Claude Code how to call
  the Managed Agents API. We should install it.
- Developer console has a tracing view + "Ask Claude" debug button per
  session.
- Agents are **versioned** — changing the system prompt bumps to v2,
  old sessions keep running v1.

## Architectural decision for BoardBreeze Concierge

**Before Cohen's talk:** 6 distinct agents wired via Managed Agents
multi-agent orchestration.

**After:** 1 Managed Agent ("Concierge") with 5 skills
(governance-expert, product-expert, tech-support, sales-closer,
escalation-handler) + custom tools (verify_citation,
search_governance_kb, hand_off_to_sales, escalate_to_grace) + MCP for
Google Calendar.

One session per caller, keyed by phone number. Sessions idle for weeks
→ "Jane texts Monday, texts again Thursday, agent remembers" works for
free.

When Anthropic ships first-class multi-agent (weeks, per Cohen), we
split the skills out into distinct agents with minimal code change.

## Why this is *better* for the "Best Use of Managed Agents" prize
1. We use every primitive as intended (agents, environments, sessions,
   custom tools, skills, events).
2. We follow Anthropic's *current* production guidance instead of
   fighting it.
3. We inherit auto-compaction, checkpointing, retries — real depth in
   managed infra, not reinvented.
4. We can credibly say "ready to upgrade to distributed multi-agent the
   day it ships."
