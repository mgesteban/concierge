"""Custom tool dispatch. One function per tool name declared in
agent_spec.CUSTOM_TOOLS. Called from client._drain_stream_once when the
agent emits an agent.custom_tool_use event.

Every handler returns a JSON-serializable dict; the wrapper in client.py
wraps it in a text content block and ships it back as
user.custom_tool_result.
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)


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
# verify_citation (stub — real implementation lands today per playbook §16.5)
# ---------------------------------------------------------------------------

def _verify_citation(citation: str, claim: str) -> dict:
    """Stub. The real version looks up `citation` in the KB, runs a Claude
    classifier to check whether the chunk text supports `claim`, and
    returns a suggested rewrite if not. Until that lands, we return
    `verified: false` with a safe fallback so the agent speaks in general
    terms instead of reading an unverified section number."""
    log.info("verify_citation stub called: %r / %r", citation, claim)
    return {
        "verified": False,
        "suggested_rewrite": (
            "I don't want to read a specific section number until I've "
            "double-checked it. The general rule here is: "
        ),
        "note": "verify_citation is in stub mode; real verifier pending",
    }


# ---------------------------------------------------------------------------
# escalate_to_grace (stub — real Twilio SMS to Grace lands Friday)
# ---------------------------------------------------------------------------

def _escalate_to_grace(
    reason: str, summary: str, urgency: str = "flexible"
) -> dict:
    """Stub. Real version sends Grace an SMS + email via Twilio + Gmail MCP.
    For now, log and return success so the agent tells the caller it's
    handled."""
    log.info(
        "ESCALATION queued — reason=%s urgency=%s summary=%s",
        reason,
        urgency,
        summary,
    )
    return {
        "status": "queued",
        "channel": "sms+email",
        "callback_window": "today" if urgency == "today" else "within 24 hours",
    }


# ---------------------------------------------------------------------------
# Registry + dispatcher
# ---------------------------------------------------------------------------

_HANDLERS = {
    "search_governance_kb": _search_governance_kb,
    "verify_citation": _verify_citation,
    "escalate_to_grace": _escalate_to_grace,
}


def dispatch_custom_tool(name: str, inputs: dict[str, Any]) -> dict:
    """Look up the handler for `name` and call it with `inputs` as kwargs."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown custom tool: {name}"}
    return handler(**inputs)
