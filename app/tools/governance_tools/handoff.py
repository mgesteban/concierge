"""
Tool 4: hand_off_to_sales

Signals the Concierge supervisor that the Sales Closer should take over.

Implementation:
  1. Writes a structured handoff row to the `handoffs` table in Supabase,
     which the dashboard displays as a live handoff event.
  2. Updates the `conversation_state` row for this session, setting
     `active_agent = 'sales_closer'`.
  3. Returns a structured signal for the orchestrator to inspect.

The Concierge supervisor's loop, after every tool-use response, checks for
`handoff: true` in any tool_result content and re-routes accordingly.
"""
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .db import get_supabase


def hand_off_to_sales(
    caller_summary: str,
    buying_signals: list[str],
    urgency: str,
    session_id: str,
    agency_type: str | None = None,
    open_questions_for_sales: list[str] | None = None,
) -> dict[str, Any]:
    """
    Args:
        caller_summary: Plain-language summary of who the caller is and
            what they came in asking. Written in the voice of the handing-
            off agent.
        buying_signals: Concrete signals (not speculation).
        urgency: "low" | "medium" | "high".
        session_id: The conversation session UUID from your Twilio webhook.
            MUST be supplied by the orchestrator when it invokes the tool
            — Claude never sees the session_id directly. See notes below.
        agency_type: Optional; helps the Sales Closer pull the right
            pricing table.
        open_questions_for_sales: Questions the Governance Expert
            intentionally deferred.

    Returns:
        {
          "handoff": True,
          "next_agent": "sales_closer",
          "handoff_id": str,
          "session_id": str,
          "package": { ... everything sales needs ... },
        }

    A note on session_id injection
    ------------------------------
    The Anthropic tool schema for `hand_off_to_sales` does NOT expose
    session_id to Claude. Instead, your orchestrator intercepts the
    tool_use block, looks up the active session_id from context, and calls
    this Python function with it. This keeps session identifiers out of
    Claude's reasoning surface (you don't want the model fabricating or
    swapping IDs).

    In your orchestrator:

        if tool_use.name == "hand_off_to_sales":
            result = hand_off_to_sales(
                **tool_use.input, session_id=current_session_id
            )
    """
    open_questions_for_sales = open_questions_for_sales or []
    assert urgency in {"low", "medium", "high"}, f"bad urgency: {urgency}"

    handoff_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    package = {
        "caller_summary": caller_summary,
        "buying_signals": buying_signals,
        "urgency": urgency,
        "agency_type": agency_type,
        "open_questions_for_sales": open_questions_for_sales,
        "handed_off_at": now,
        "from_agent": "governance_expert",
    }

    supabase = get_supabase()

    # 1) Record the handoff event (for dashboard & analytics).
    supabase.table("handoffs").insert(
        {
            "id": handoff_id,
            "session_id": session_id,
            "from_agent": "governance_expert",
            "to_agent": "sales_closer",
            "package": package,
            "created_at": now,
        }
    ).execute()

    # 2) Update the session's active agent (the supervisor reads this
    #    on the next turn to route the call).
    supabase.table("conversation_state").update(
        {
            "active_agent": "sales_closer",
            "last_handoff_id": handoff_id,
            "updated_at": now,
        }
    ).eq("session_id", session_id).execute()

    # 3) Return the signal for the orchestrator.
    return {
        "handoff": True,
        "next_agent": "sales_closer",
        "handoff_id": handoff_id,
        "session_id": session_id,
        "package": package,
    }
