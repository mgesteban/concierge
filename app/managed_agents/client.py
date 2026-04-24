"""Claude Managed Agents client wrapper.

One-liner: exposes `handle_message(phone, text) -> str` for the SMS and
Voice channels. Everything else — agent spec, environment config,
session lookup, event streaming, custom tool dispatch — is internal.

Design notes:
  - Agent + environment are created once and reused across boots by
    name-lookup via list(). Safe to call `ensure_agent()` every startup.
  - Sessions are keyed on caller phone number via a Supabase table
    (see app/db/migrations/001_phone_sessions.sql). Sessions on the CMA
    side can idle for weeks, so we reuse the same session across calls
    — this is what gives us "Jane texts Monday, texts again Thursday,
    agent remembers" for free.
  - Custom tools are dispatched by this module (not by Claude). When the
    agent calls one, CMA emits agent.custom_tool_use and the session
    idles until we send back user.custom_tool_result.

Cohen, 2026-04-23: "one agent + many skills/tools, not a fleet of
sub-agents." See notes/cohen-managed-agents.md.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Optional

import anthropic
from supabase import create_client, Client as SupabaseClient

from app.managed_agents import agent_spec
from app.managed_agents.custom_tools import dispatch_custom_tool

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Clients (lazy singletons)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _anthropic() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


@lru_cache(maxsize=1)
def _supabase() -> SupabaseClient:
    return create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )


# ---------------------------------------------------------------------------
# Agent + environment provisioning (idempotent)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def ensure_agent() -> str:
    """Find-or-create the Concierge agent. Returns agent_id."""
    c = _anthropic()
    for a in c.beta.agents.list(limit=100):
        if a.name == agent_spec.AGENT_NAME and not getattr(a, "archived_at", None):
            log.info("reusing agent %s (%s)", agent_spec.AGENT_NAME, a.id)
            return a.id
    created = c.beta.agents.create(**agent_spec.agent_create_kwargs())
    log.info("created agent %s (%s)", agent_spec.AGENT_NAME, created.id)
    return created.id


@lru_cache(maxsize=1)
def ensure_environment() -> str:
    """Find-or-create the Concierge environment. Returns environment_id."""
    c = _anthropic()
    for e in c.beta.environments.list(limit=100):
        if e.name == agent_spec.ENVIRONMENT_NAME:
            log.info(
                "reusing environment %s (%s)", agent_spec.ENVIRONMENT_NAME, e.id
            )
            return e.id
    created = c.beta.environments.create(name=agent_spec.ENVIRONMENT_NAME)
    log.info(
        "created environment %s (%s)", agent_spec.ENVIRONMENT_NAME, created.id
    )
    return created.id


# ---------------------------------------------------------------------------
# Session lookup (phone → cma_session_id) via Supabase
# ---------------------------------------------------------------------------

def _get_session_for_phone(phone: str) -> Optional[str]:
    sb = _supabase()
    res = (
        sb.table("phone_sessions")
        .select("cma_session_id")
        .eq("phone", phone)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["cma_session_id"]
    return None


def _store_session_for_phone(phone: str, cma_session_id: str) -> None:
    sb = _supabase()
    sb.table("phone_sessions").upsert(
        {"phone": phone, "cma_session_id": cma_session_id}
    ).execute()


def _touch_session(phone: str) -> None:
    sb = _supabase()
    sb.table("phone_sessions").update({"last_used_at": "now()"}).eq(
        "phone", phone
    ).execute()


def get_or_create_session(phone: str, channel: str) -> str:
    """Return a CMA session_id for this phone, creating one if needed."""
    existing = _get_session_for_phone(phone)
    if existing:
        _touch_session(phone)
        return existing

    c = _anthropic()
    session = c.beta.sessions.create(
        agent=ensure_agent(),
        environment_id=ensure_environment(),
        metadata={"phone": phone, "channel": channel},
        title=f"{channel} with {phone}",
    )
    _store_session_for_phone(phone, session.id)
    log.info("created CMA session %s for %s (%s)", session.id, phone, channel)
    return session.id


# ---------------------------------------------------------------------------
# The main entry point
# ---------------------------------------------------------------------------

def handle_message(phone: str, user_text: str, channel: str = "sms") -> str:
    """Round-trip one inbound message and return the assembled reply text.

    Sends user.message, streams events, dispatches custom tools, and
    returns the concatenated agent.message text. Synchronous + blocking —
    simplest model for a webhook handler. Voice streaming can be added
    later without changing this interface.
    """
    session_id = get_or_create_session(phone, channel)
    c = _anthropic()

    # Emit the user's message.
    c.beta.sessions.events.send(
        session_id=session_id,
        events=[
            {
                "type": "user.message",
                "content": [{"type": "text", "text": user_text}],
            }
        ],
    )

    # Consume the event stream until the session goes idle. If we see a
    # custom_tool_use event, dispatch it and send the result back — the
    # session resumes and streams more events.
    reply_parts: list[str] = []
    while True:
        idled = _drain_stream_once(session_id, reply_parts)
        if idled == "done":
            break
        # idled == "tool_pending" → dispatch tool result was sent inside the
        # drain; loop to pick up the continuation.

    return "".join(reply_parts).strip() or (
        "I'm here — could you say that again?"
    )


def _drain_stream_once(session_id: str, reply_parts: list[str]) -> str:
    """Consume the event stream until the session idles. Handle custom
    tool calls inline. Returns 'done' if the session idled cleanly, or
    'tool_pending' if we dispatched a tool and need to resume."""
    c = _anthropic()
    tool_dispatched = False
    stream = c.beta.sessions.events.stream(session_id=session_id)
    with stream as events:
        for event in events:
            etype = getattr(event, "type", None)

            if etype == "agent.message":
                for block in event.content:
                    text = getattr(block, "text", None)
                    if text:
                        reply_parts.append(text)

            elif etype == "agent.custom_tool_use":
                # Dispatch synchronously and round-trip the result.
                try:
                    result = dispatch_custom_tool(event.name, event.input)
                    payload = json.dumps(result, default=str)
                    is_error = False
                except Exception as exc:
                    log.exception(
                        "custom tool %s failed", getattr(event, "name", "?")
                    )
                    payload = json.dumps({"error": str(exc)})
                    is_error = True
                c.beta.sessions.events.send(
                    session_id=session_id,
                    events=[
                        {
                            "type": "user.custom_tool_result",
                            "custom_tool_use_id": event.id,
                            "content": [{"type": "text", "text": payload}],
                            "is_error": is_error,
                        }
                    ],
                )
                tool_dispatched = True
                # Close this stream and open a new one to pick up the
                # continuation — the stream ends when the session idles.
                break

            elif etype in (
                "session.status_idle",
                "session.status_terminated",
            ):
                # Clean end of the turn.
                return "done"

            elif etype == "session.error":
                log.warning(
                    "session.error event: %s", getattr(event, "error", event)
                )
                return "done"

            # Other events (thinking, span_*, status_running, tool_use for
            # native tools, thread_context_compacted) are informational.

    return "tool_pending" if tool_dispatched else "done"
