"""Low-latency voice pipeline — direct Claude Messages API with streaming.

Why not CMA for voice?
  Claude Managed Agents emits `agent.message` as ONE event at the end of
  the turn, plus ~6 s of session/environment overhead on top of the
  underlying model. For voice that's fatal — the caller sits in silence
  until the full reply is generated AND synthesized.

  Measured on 2026-04-23 with an identical prompt + model (Opus 4.7):
    - Messages API (streaming): TTFT 0.98 s, done at 1.68 s
    - Managed Agents: first event at 7.66 s, done at 7.66 s

  Voice takes the fast path; SMS keeps CMA (session memory + server-side
  orchestration, latency doesn't matter for text).

Pipeline per caller turn:
  1. Load prior messages for this CallSid (in-memory).
  2. Open `messages.stream(..., tools=[...])`.
  3. Accumulate text_delta events into a sentence buffer.
  4. When a sentence terminator lands (.!?), fire ElevenLabs synth on the
     complete sentence and yield its MP3 chunks.
  5. If the stream ends with tool_use blocks, dispatch them, append
     tool_result, reopen the stream — repeat until no more tools.
  6. Persist the final reply into the call's history so the agent can
     refer back to earlier turns within the same call.

Tool handlers are shared with the CMA path (app.managed_agents.custom_tools)
so we don't duplicate Brown Act logic.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from collections.abc import Iterator
from functools import lru_cache
from threading import Lock
from typing import Any

import anthropic

from app.channels.tts import stream_synth
from app.managed_agents.agent_spec import CUSTOM_TOOLS as _CMA_TOOLS
from app.managed_agents.agent_spec import SYSTEM_PROMPT
from app.managed_agents.custom_tools import CALLER_CONTEXT, dispatch_custom_tool

log = logging.getLogger(__name__)

MODEL = "claude-opus-4-7"
MAX_TOKENS = 300
HISTORY_LIMIT = 12  # keep last N turns in context; prune older


@lru_cache(maxsize=1)
def _anthropic() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ---------------------------------------------------------------------------
# Tool spec — convert CMA custom-tool entries to Messages API shape
# ---------------------------------------------------------------------------

def _messages_tools() -> list[dict]:
    out = []
    for t in _CMA_TOOLS:
        out.append(
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
            }
        )
    return out


TOOLS = _messages_tools()


# ---------------------------------------------------------------------------
# Per-call history (in-memory, keyed by Twilio CallSid)
# ---------------------------------------------------------------------------

_HISTORY: dict[str, list[dict]] = {}
_HISTORY_LOCK = Lock()


def _get_history(call_sid: str) -> list[dict]:
    with _HISTORY_LOCK:
        return list(_HISTORY.get(call_sid, []))


def _append_history(call_sid: str, user_text: str, assistant_blocks: list) -> None:
    with _HISTORY_LOCK:
        h = _HISTORY.setdefault(call_sid, [])
        h.append({"role": "user", "content": user_text})
        # Persist assistant turn as the full blocks list so tool_use is
        # preserved — the next turn may refer back to prior tool results.
        h.append({"role": "assistant", "content": _serialize_blocks(assistant_blocks)})
        # Trim history so context doesn't blow up on long calls.
        if len(h) > HISTORY_LIMIT * 2:
            del h[: len(h) - HISTORY_LIMIT * 2]


def forget_call(call_sid: str) -> None:
    """Drop a call's history. Call on call status-callback when available."""
    with _HISTORY_LOCK:
        _HISTORY.pop(call_sid, None)


def _serialize_blocks(blocks: list) -> list[dict]:
    """Turn SDK content blocks into plain dicts for persistence + re-send."""
    out = []
    for b in blocks:
        bt = getattr(b, "type", None)
        if bt == "text":
            out.append({"type": "text", "text": b.text})
        elif bt == "tool_use":
            out.append(
                {
                    "type": "tool_use",
                    "id": b.id,
                    "name": b.name,
                    "input": b.input,
                }
            )
        # thinking / other block types: skip — not relevant for replay
    return out


# ---------------------------------------------------------------------------
# Pending turns — cid → (call_sid, phone, user_text)
# ---------------------------------------------------------------------------

_PENDING: dict[str, dict] = {}
_PENDING_LOCK = Lock()


def queue_turn(call_sid: str, phone: str, user_text: str) -> str:
    cid = uuid.uuid4().hex
    with _PENDING_LOCK:
        _PENDING[cid] = {
            "call_sid": call_sid,
            "phone": phone,
            "user_text": user_text,
        }
    return cid


def pop_turn(cid: str) -> dict | None:
    with _PENDING_LOCK:
        return _PENDING.pop(cid, None)


# ---------------------------------------------------------------------------
# Sentence splitting — emit MP3 as soon as a full sentence is ready
# ---------------------------------------------------------------------------
# We want to synth sentence-at-a-time so the caller hears speech while
# Claude is still generating. The split must be conservative: splitting
# mid-abbreviation ("Gov. Code § 54954.2") would produce disconnected
# audio clips. We only break on .!? followed by whitespace AND a capital
# letter (or end of buffer), and never between two digits.

# Sentence boundary: terminating punctuation + whitespace + capital letter.
# The capital-letter lookahead avoids false splits on abbreviations and
# decimals ("Gov. Code", "§ 54954.2").
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

# Mid-reply pause: em-dash surrounded by whitespace. Claude Opus 4.7
# uses this as a rhythmic break a lot ("72 hours ahead — posted publicly
# and on your agency's website."). Splitting here lets us start synth
# on the first clause a beat earlier. We only split when the left-hand
# side is at least ~40 chars so we don't synth a micro-fragment.
_EMDASH_SPLIT = re.compile(r"\s+—\s+")
_MIN_CLAUSE_CHARS = 40


def _split_sentences(buf: str) -> tuple[list[str], str]:
    """Return (complete_clauses, remainder).

    A clause is complete when we've seen either:
      - a sentence terminator (.!?) followed by whitespace + capital
      - a mid-sentence em-dash pause, provided the preceding clause is
        long enough to be worth synthesizing on its own.
    """
    if not buf:
        return [], ""

    complete: list[str] = []
    remainder = buf

    # First, greedily pull off full sentences.
    while True:
        m = _SENTENCE_END.search(remainder)
        if not m:
            break
        head, remainder = remainder[: m.start()], remainder[m.end():]
        head = head.strip()
        if head:
            complete.append(head)

    # Then, if the remainder contains a substantial left-of-em-dash clause,
    # split that too. Preserve the em-dash on the right side so the next
    # stretch flows correctly when Claude resumes.
    m = _EMDASH_SPLIT.search(remainder)
    if m and m.start() >= _MIN_CLAUSE_CHARS:
        head = remainder[: m.start()].strip()
        tail = remainder[m.end():]
        if head:
            complete.append(head)
        remainder = tail

    return complete, remainder


# ---------------------------------------------------------------------------
# Main entry: drive one caller turn, yield MP3 bytes
# ---------------------------------------------------------------------------

def run_turn(call_sid: str, phone: str, user_text: str) -> Iterator[bytes]:
    """Generator: drive the turn end-to-end, yield MP3 chunks to Twilio.

    Tool calls are dispatched inline. The caller phone is exposed to tool
    handlers via CALLER_CONTEXT so escalate_to_grace can look it up.

    Note: CALLER_CONTEXT is a ContextVar, but we only .set() it (no .reset()
    at the end). Calling .reset() fails here because FastAPI's
    StreamingResponse runs the generator in a different Python Context
    than the one where .set() returned the token. Leaving the var set is
    safe — the next turn overwrites it, and other concurrent turns have
    their own Context copies.
    """
    c = _anthropic()
    CALLER_CONTEXT.set({"phone": phone, "channel": "voice"})
    history = _get_history(call_sid)
    messages: list[dict] = history + [{"role": "user", "content": user_text}]

    sentence_buf = ""
    final_assistant_blocks: list = []

    try:
        while True:
            log.info("voice_pipeline: stream open, %d messages", len(messages))
            stream_ctx = c.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            with stream_ctx as stream:
                # Iterate token-level events via text_stream; get full
                # content (incl. tool_use blocks) from get_final_message.
                for text in stream.text_stream:
                    sentence_buf += text
                    complete, remainder = _split_sentences(sentence_buf)
                    sentence_buf = remainder
                    for s in complete:
                        log.info("voice_pipeline: synth sentence: %r", s)
                        for chunk in stream_synth(s):
                            if chunk:
                                yield chunk

                final_msg = stream.get_final_message()

            final_assistant_blocks = list(final_msg.content)

            tool_uses = [
                b for b in final_assistant_blocks if getattr(b, "type", None) == "tool_use"
            ]

            if not tool_uses:
                # Reply is done. Flush any trailing sentence.
                if sentence_buf.strip():
                    log.info(
                        "voice_pipeline: synth trailing: %r", sentence_buf.strip()
                    )
                    for chunk in stream_synth(sentence_buf.strip()):
                        if chunk:
                            yield chunk
                    sentence_buf = ""
                break

            # Flush any partial sentence before the tool pause — better to
            # play a half-sentence than leave the caller in silence while
            # the tool runs. The next stream picks up with the continuation.
            if sentence_buf.strip():
                log.info(
                    "voice_pipeline: synth pre-tool flush: %r", sentence_buf.strip()
                )
                for chunk in stream_synth(sentence_buf.strip()):
                    if chunk:
                        yield chunk
                sentence_buf = ""

            # Dispatch tools + append tool_results; continue loop.
            messages.append(
                {"role": "assistant", "content": _serialize_blocks(final_assistant_blocks)}
            )
            tool_results = []
            for tu in tool_uses:
                try:
                    result = dispatch_custom_tool(tu.name, tu.input)
                    payload = json.dumps(result, default=str)
                    is_error = False
                except Exception as exc:
                    log.exception("voice tool %s failed", tu.name)
                    payload = json.dumps({"error": str(exc)})
                    is_error = True
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": payload,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
    finally:
        # Persist what we built for this turn even on early exit.
        if final_assistant_blocks:
            _append_history(call_sid, user_text, final_assistant_blocks)
