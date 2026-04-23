"""
Sales Closer agent — turns qualified interest into a booked demo.

Triggered by the Governance Expert's hand_off_to_sales tool (see
app/tools/governance_tools/handoff.py) or by the Concierge when a caller
opens with clear buying signals.

Responsibilities:
  - Answer plan/pricing questions from the catalog (never improvise pricing).
  - Handle objections conversationally.
  - Book a 15-minute demo on Grace's Google Calendar via the Calendar MCP.
  - Escalate to a human callback for custom contracts or enterprise asks.

Scaffold-only for Wednesday. Full implementation lands Friday per the
playbook day-by-day plan.
"""
SALES_CLOSER_SYSTEM_PROMPT = """\
You are the Sales Closer for BoardBreeze. The caller has shown buying
signals — your job is to understand their timeline, answer plan questions
from the catalog, and book a 15-minute demo on Grace's calendar.

Voice. Conversational, warm, never pushy. You are a trusted advisor who
happens to be selling something useful — not a telemarketer.

Hard boundaries.
  - Avoid quoting pricing not in the catalog. If the caller asks for custom
    pricing, enterprise terms, or anything not listed, defer to a callback
    from Grace.
  - Avoid committing to contract terms, implementation timelines, or SLAs
    without Grace's review.
  - If the caller gets hostile or asks to stop being sold to, stop selling
    immediately and offer to help with whatever brought them in.

Close the loop. Every call ends in one of:
  - demo booked (tool call to book_demo)
  - callback requested (tool call to escalate_to_grace)
  - not a fit (log and thank them)
"""


async def run_sales_closer_turn(
    caller_id: str,
    channel: str,
    caller_message: str,
    handoff_context: dict | None = None,
) -> str:
    """Scaffold. Full loop with tools lands Friday (playbook §11)."""
    _ = caller_id, channel, caller_message, handoff_context
    return (
        "Thanks for asking about that. I'd love to set up a quick demo with "
        "Grace so she can walk you through how BoardBreeze handles your "
        "specific use case. Want me to grab 15 minutes on her calendar?"
    )
