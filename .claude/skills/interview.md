---
name: interview
description: Interview Grace in depth about a feature/agent/artifact before writing any code or prompt. Ask one question at a time. Per Tark's AMA (playbook §16.2) — this is our planning multiplier.
---

# /interview

Use this skill any time Grace is about to ask for a non-trivial artifact
(agent system prompt, dashboard layout, verification rule set, Remotion
segment, etc.) and the right shape isn't yet obvious.

## How to run it

1. Confirm the topic Grace wants to interview on in one sentence. If her
   ask is ambiguous, propose an interpretation before starting questions.
2. Ask **one question at a time**. Never batch.
3. After each answer, summarize the current understanding in 1–2 sentences
   so context doesn't drift, then ask the next question.
4. Target 5–10 questions. Stop when you have enough to propose an artifact.
5. Propose the concrete artifact (spec, prompt, layout, schema) as editable
   text — do not implement code from the interview directly. Grace edits,
   THEN you implement.

## Questions to always cover

- What's the one-sentence purpose of this artifact?
- Who is the primary user/caller/reader, and what's their context?
- What's the single most important thing it MUST do?
- What should it explicitly NOT do (boundaries)?
- What's a concrete example of a successful interaction?
- What's a concrete example of a failure mode to avoid?
- How does Grace want to know it's working (what's the visible signal)?

## Context-specific prompts

- **For an agent system prompt:** cover opening line, when to hand off,
  when to escalate, voice (on phone vs. SMS), what it should refuse.
- **For a dashboard:** cover the metric she checks first thing in the
  morning, what she'd want to see live, what would tell her it's broken,
  what she'd want to share publicly.
- **For the verification layer:** cover how a citation is structured,
  where canonical text lives, exact vs. paraphrased matching, what to do
  on failure, how to surface failures on the dashboard.

## Don'ts

- Don't skip ahead and propose the artifact after 2 questions.
- Don't batch questions ("A few things — what is X, what is Y, and what
  is Z?"). One at a time.
- Don't ask leading questions that telegraph the answer you want.
