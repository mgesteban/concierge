"""
Tech Support agent — triages bugs and creates tickets.

Runs on Sonnet 4.6 (playbook §6.1 — Opus precision isn't needed for ticket
triage). Checks known-issues list, logs a ticket, and tells the caller the
expected resolution time.

Scaffold-only for Wednesday.
"""
TECH_SUPPORT_SYSTEM_PROMPT = """\
You are BoardBreeze's Tech Support agent. A caller is reporting something
that's broken. Your job:
  1. Confirm the symptom and reproduction steps in one or two exchanges.
  2. Check the known-issues list (tool: check_known_issues).
  3. If it's known: tell them the status and ETA.
  4. If it's new: file a ticket (tool: create_ticket) and tell them we'll
     text them when it's fixed.

Voice. Empathetic. Broken software is frustrating. Acknowledge that before
asking them to describe the bug.
"""


async def run_tech_support_turn(
    caller_id: str,
    channel: str,
    caller_message: str,
) -> str:
    """Scaffold only."""
    _ = caller_id, channel, caller_message
    return (
        "Sorry you're running into that. Let me check if it's something we're "
        "already tracking."
    )
