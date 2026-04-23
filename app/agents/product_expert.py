"""
Product Expert agent — answers BoardBreeze feature and how-to questions.

Reads from a help-article KB (separate from the governance KB). When the
caller's account can be looked up (caller ID matches a subscriber row), the
agent personalizes the answer; otherwise it gives a generic how-to.

Scaffold-only for Wednesday. Real implementation once the help-article KB
is ingested (Saturday per playbook §11).
"""
PRODUCT_EXPERT_SYSTEM_PROMPT = """\
You are BoardBreeze's Product Expert. You answer how-to questions about the
product: creating agendas, managing board members, running closed sessions,
publishing minutes, etc.

Voice. Plain, step-by-step. If a fix involves 3+ steps, offer to text the
caller a follow-up link rather than reading all the steps aloud.

Escalation. If the caller reports a bug (something that should work but
doesn't), hand off to tech_support — don't try to troubleshoot deeply.
"""


async def run_product_expert_turn(
    caller_id: str,
    channel: str,
    caller_message: str,
) -> str:
    """Scaffold only."""
    _ = caller_id, channel, caller_message
    return (
        "I can help with that — let me pull up how BoardBreeze handles it. "
        "One sec."
    )
