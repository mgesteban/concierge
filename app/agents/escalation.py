"""
Escalation Handler — the agent that actually pages Grace.

Called by any specialist when the situation needs a human: enterprise
pricing ask, hostile caller, legal-advice request, or a hot lead on a tight
timeline. Sends Grace an SMS (Twilio) + email (Gmail MCP) with a clean
summary and a link to the full transcript.

This is the memorable beat in the demo video (§12.1, 1:30–2:00).
"""
ESCALATION_SUMMARY_TEMPLATE = """\
Hot lead on the line — {agency_summary}, ~${arr_estimate} ARR, {urgency}.
Full transcript: {transcript_url}
They'd love a human callback today.
"""


async def escalate_to_grace(
    caller_id: str,
    summary: str,
    transcript_url: str,
    urgency: str = "medium",
) -> dict:
    """Scaffold only. Real Twilio + Gmail wiring lands Friday."""
    _ = caller_id, summary, transcript_url, urgency
    return {"status": "queued", "channel": "sms+email"}
