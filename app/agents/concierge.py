"""
Concierge supervisor — the front door for every voice call and SMS thread.

Responsibilities:
  1. Identify the caller (load or create conversation_state).
  2. Classify intent for this turn.
  3. Dispatch to the right specialist (governance / sales / product / tech /
     escalation) and return their reply to the channel layer.
  4. Respect handoff signals emitted by specialists so the next turn routes
     to the agent the last tool call named.

This is the agent that runs on every inbound turn. Specialists are invoked
as delegated tool calls rather than nested API calls — this matches the
"Best Use of Claude Managed Agents" pattern described in the playbook §9.
"""
from __future__ import annotations

from app.agents.governance_expert import run_governance_expert_turn


async def run_concierge_turn(
    caller_id: str,
    channel: str,
    caller_message: str,
) -> str:
    """
    Run one turn of the Concierge.

    For the scaffold, the Concierge routes everything governance-flavored to
    the Governance Expert. The routing layer is the first thing that gets
    upgraded on Thursday — intent classification via Claude + a real
    specialist roster (sales, product, tech, escalation).
    """
    # Temporary deterministic routing until the real supervisor prompt lands.
    # Keywords cover the Wednesday-evening milestone: "text the number, get a
    # governance answer back".
    lower = caller_message.lower()
    governance_cues = (
        "brown act",
        "robert",
        "agenda",
        "closed session",
        "minutes",
        "quorum",
        "bagley",
        "open meeting",
        "public comment",
        "board",
    )
    if any(cue in lower for cue in governance_cues):
        text, _handoff = run_governance_expert_turn(
            caller_message=caller_message,
            session_id=caller_id,  # placeholder — real session UUID lands Thursday
            channel=channel,
        )
        return text or (
            "I'm looking into that for you. Give me just a moment."
        )

    # Fallback greeting for unclassified turns — the real Concierge brain
    # replaces this.
    return (
        "Hi, this is BoardBreeze's AI concierge. I can help with governance "
        "questions (Brown Act, Robert's Rules), product support, or connect "
        "you with Grace. What are you trying to do?"
    )
