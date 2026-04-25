"""Custom tool dispatch. One function per tool name declared in
agent_spec.CUSTOM_TOOLS. Called from client._drain_stream_once when the
agent emits an agent.custom_tool_use event.

Every handler returns a JSON-serializable dict; the wrapper in client.py
wraps it in a text content block and ships it back as
user.custom_tool_result.
"""
from __future__ import annotations

import json
import logging
import os
import re
from contextvars import ContextVar
from functools import lru_cache
from typing import Any

log = logging.getLogger(__name__)


# Populated by client.handle_message for the duration of one inbound turn.
# Lets tools (e.g. escalate_to_grace) pull the caller's phone + channel
# without having to pass them through every tool call.
CALLER_CONTEXT: ContextVar[dict] = ContextVar("CALLER_CONTEXT", default={})


@lru_cache(maxsize=1)
def _anthropic():
    import anthropic

    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


@lru_cache(maxsize=1)
def _sb():
    from supabase import create_client

    return create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )


# ---------------------------------------------------------------------------
# search_governance_kb
# ---------------------------------------------------------------------------

def _search_governance_kb(query: str, jurisdiction: str | None = None) -> dict:
    """Top-k semantic search against the governance_kb table via the
    match_governance_kb RPC. Returns up to 5 matches."""
    from app.tools.governance_tools.embeddings import embed_text
    from supabase import create_client

    try:
        qvec = embed_text(query, input_type="query")
    except Exception as exc:
        log.exception("embedding failed")
        return {"matches": [], "error": f"embedding failed: {exc}"}

    sb = create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )
    res = sb.rpc(
        "match_governance_kb",
        {
            "query_embedding": qvec,
            "match_count": 5,
            "jurisdiction_filter": jurisdiction,
            "similarity_threshold": 0.3,
        },
    ).execute()

    matches = [
        {
            "source": row["source"],
            "document": row["document"],
            "section_title": row.get("section_title"),
            "jurisdiction": row["jurisdiction"],
            "content": row["content"],
            "similarity": round(row["similarity"], 3),
        }
        for row in (res.data or [])
    ]
    if not matches:
        return {
            "matches": [],
            "note": (
                "No chunks matched above the similarity threshold. Answer in "
                "general terms without a specific section number, or offer a "
                "callback from Grace."
            ),
        }
    return {"matches": matches}


# ---------------------------------------------------------------------------
# search_product_kb
# ---------------------------------------------------------------------------
# Same Supabase RPC as the governance search, but pinned to
# jurisdiction='product' — the rows seeded from the BoardBreeze FAQ. Lets
# the Product Expert mode answer pricing / feature / plan questions
# without inventing numbers, while keeping governance retrieval crisp.
# ---------------------------------------------------------------------------


def _search_product_kb(query: str) -> dict:
    return _search_governance_kb(query=query, jurisdiction="product")


# ---------------------------------------------------------------------------
# verify_citation
# ---------------------------------------------------------------------------
# Two-stage check:
#   1. Section lookup — normalize the citation, extract the section number,
#      find the KB row whose `source` field contains that number. If none,
#      the section isn't in our KB and we refuse to vouch for it.
#   2. Claim-support classification — ask Haiku 4.5 whether the KB chunk's
#      actual text supports the claim the agent is about to make. Haiku is
#      ~300ms on this size of input; calling Opus here would blow the
#      12-second voice budget.
# ---------------------------------------------------------------------------

_CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"

_CLASSIFIER_SYSTEM = (
    "You are a statutory citation verifier. Given the text of a statute "
    "section and a spoken claim an AI assistant is about to make, decide "
    "whether the statute text directly supports the claim. "
    "Respond with ONE line of JSON: "
    '{"supports": true|false, "reason": "<= 20 words"}. '
    "Supports=true only if the claim is substantively correct per the "
    "statute text — small paraphrasing is fine, but numeric thresholds, "
    "named exceptions, and scope (regular vs. special vs. emergency "
    "meetings) must match. If the claim adds facts the statute does not "
    "establish, supports=false."
)

_SECTION_RE = re.compile(r"\d+(?:\.\d+)*(?:\([a-z0-9]+\))?", re.IGNORECASE)


def _extract_section_number(citation: str) -> str | None:
    """Pull the section number out of a freeform citation string.

    Handles 'Gov. Code § 54954.2', 'Government Code section 54954.2',
    'Robert's Rules §44', 'Ed. Code § 35144', etc. Returns the longest
    numeric-looking token found, or None.
    """
    matches = _SECTION_RE.findall(citation or "")
    if not matches:
        return None
    # The "section number" is usually the longest / most-specific token.
    return max(matches, key=len)


def _lookup_citation(citation: str) -> dict | None:
    """Find a KB row whose `source` field contains this citation's section.

    Returns the row dict (content, source, document, section_title) or
    None if nothing plausible matches.
    """
    section = _extract_section_number(citation)
    if not section:
        return None
    res = (
        _sb()
        .table("governance_kb")
        .select("content,source,document,section_title")
        .ilike("source", f"%{section}%")
        .limit(5)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return None
    # Prefer an exact section match on the full source string.
    norm = citation.lower().replace(" ", "")
    for row in rows:
        if norm and norm in row["source"].lower().replace(" ", ""):
            return row
    return rows[0]


def _classify_claim(chunk_text: str, claim: str) -> dict:
    """Ask Haiku whether `chunk_text` supports `claim`. Returns
    {supports: bool, reason: str}. Defensive on parse failures."""
    msg = _anthropic().messages.create(
        model=_CLASSIFIER_MODEL,
        max_tokens=200,
        system=_CLASSIFIER_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Statute text:\n{chunk_text}\n\n"
                    f"Claim the AI is about to make:\n{claim}\n\n"
                    "Respond with one line of JSON."
                ),
            }
        ],
    )
    raw = "".join(
        getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text"
    ).strip()
    # Find the first {...} blob — models sometimes wrap it in prose.
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        log.warning("classifier returned non-JSON: %r", raw)
        return {"supports": False, "reason": "classifier parse error"}
    try:
        parsed = json.loads(raw[start : end + 1])
        return {
            "supports": bool(parsed.get("supports")),
            "reason": str(parsed.get("reason", ""))[:200],
        }
    except Exception as exc:
        log.warning("classifier JSON parse failed: %s / %r", exc, raw)
        return {"supports": False, "reason": "classifier parse error"}


def _verify_citation(citation: str, claim: str) -> dict:
    """Verify that `citation` exists in our KB and supports `claim`.

    Returns:
        verified=true  → {verified, source, actual_text}
            Agent may read the citation aloud.
        verified=false → {verified, suggested_rewrite, reason}
            Agent should speak in general terms without the section
            number, or use `suggested_rewrite` as a lead-in.
    """
    row = _lookup_citation(citation)
    if row is None:
        log.info("verify_citation: no KB match for %r", citation)
        return {
            "verified": False,
            "suggested_rewrite": (
                "I'd rather not read a specific section number here — let me "
                "give you the general rule: "
            ),
            "reason": "citation not found in governance KB",
        }

    try:
        verdict = _classify_claim(row["content"], claim)
    except Exception as exc:
        log.exception("verify_citation classifier failed")
        return {
            "verified": False,
            "suggested_rewrite": (
                "Let me give you the general rule without a specific section "
                "number: "
            ),
            "reason": f"classifier error: {exc}",
        }

    if verdict["supports"]:
        return {
            "verified": True,
            "source": row["source"],
            "document": row["document"],
            "actual_text": row["content"],
        }

    return {
        "verified": False,
        "suggested_rewrite": (
            f"The statute covers this area but doesn't say exactly what I was "
            f"about to claim. General rule: "
        ),
        "reason": verdict["reason"] or "claim not supported by statute text",
        "source_considered": row["source"],
    }


# ---------------------------------------------------------------------------
# escalate_to_grace
# ---------------------------------------------------------------------------
# Sends Grace an SMS via Twilio with caller context so she can call back.
# Caller phone + channel come from CALLER_CONTEXT (populated by the client
# wrapper for the duration of a turn). Failure to send is logged but NOT
# surfaced to the agent as a hard error — we still want the caller to hear
# "Grace will reach out" rather than "sorry, my paging system is down." The
# return payload flags the failure so it shows up in logs and a future
# dashboard can pick up orphan escalations.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _twilio():
    from twilio.rest import Client

    return Client(
        os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]
    )


def _format_escalation_sms(
    reason: str, summary: str, urgency: str, caller_phone: str, channel: str
) -> str:
    urgency_label = {
        "today": "TODAY",
        "this_week": "this week",
        "flexible": "when convenient",
    }.get(urgency, urgency)
    reason_label = reason.replace("_", " ")
    # Twilio single-segment SMS is 160 chars; we deliberately allow
    # multi-segment here — Grace's carrier handles concatenation fine and
    # legibility matters more than segment count.
    return (
        f"BoardBreeze concierge — callback needed ({urgency_label})\n"
        f"Reason: {reason_label}\n"
        f"Caller: {caller_phone} (via {channel})\n"
        f"Summary: {summary}"
    )


def _escalate_to_grace(
    reason: str, summary: str, urgency: str = "flexible"
) -> dict:
    """Page Grace via SMS with the caller's context and a short summary.

    Returns:
        status: 'sent' | 'logged_only'
        channel: 'sms'
        callback_window: human-readable ETA
        sid: Twilio message SID if sent
    """
    ctx = CALLER_CONTEXT.get() or {}
    caller_phone = ctx.get("phone", "unknown")
    channel = ctx.get("channel", "unknown")
    grace_phone = os.environ.get("GRACE_PHONE_NUMBER")
    from_phone = os.environ.get("TWILIO_PHONE_NUMBER")

    body = _format_escalation_sms(
        reason, summary, urgency, caller_phone, channel
    )
    log.info(
        "escalate_to_grace: reason=%s urgency=%s caller=%s",
        reason, urgency, caller_phone,
    )

    callback_window = {
        "today": "today",
        "this_week": "this week",
        "flexible": "within 24 hours",
    }.get(urgency, "within 24 hours")

    if not grace_phone or not from_phone:
        log.warning(
            "escalate_to_grace: missing GRACE_PHONE_NUMBER or TWILIO_PHONE_NUMBER "
            "— logged only. body=%r", body,
        )
        return {
            "status": "logged_only",
            "channel": "sms",
            "callback_window": callback_window,
            "note": "SMS config missing; escalation logged to server",
        }

    try:
        msg = _twilio().messages.create(
            to=grace_phone, from_=from_phone, body=body
        )
        return {
            "status": "sent",
            "channel": "sms",
            "callback_window": callback_window,
            "sid": msg.sid,
        }
    except Exception as exc:
        log.exception("escalate_to_grace: Twilio send failed")
        return {
            "status": "logged_only",
            "channel": "sms",
            "callback_window": callback_window,
            "note": f"SMS send failed: {exc}",
        }


# ---------------------------------------------------------------------------
# Registry + dispatcher
# ---------------------------------------------------------------------------

_HANDLERS = {
    "search_governance_kb": _search_governance_kb,
    "search_product_kb": _search_product_kb,
    "verify_citation": _verify_citation,
    "escalate_to_grace": _escalate_to_grace,
}


def dispatch_custom_tool(name: str, inputs: dict[str, Any]) -> dict:
    """Look up the handler for `name` and call it with `inputs` as kwargs."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown custom tool: {name}"}
    return handler(**inputs)
