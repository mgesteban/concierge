"""
Reference implementation: the Governance Expert agent, running one turn.

This shows the full tool-use loop:
  1. Build system prompt + user message
  2. Call Claude Opus 4.7 with GOVERNANCE_TOOLS and extended thinking
  3. Claude emits tool_use blocks
  4. We dispatch each tool call via `dispatch_tool_call`
  5. Feed tool_result blocks back to Claude
  6. Loop until Claude returns end_turn (no more tool calls)
  7. Inspect final response; check for handoff signal

Usage:
    from example_agent import run_governance_expert_turn

    final_text, handoff = run_governance_expert_turn(
        caller_message="Does the Brown Act require us to post the "
                       "agenda for our CCD board 72 hours in advance?",
        session_id="...",
    )
"""
import os
from typing import Any

from anthropic import Anthropic

from app.tools.governance_tools import GOVERNANCE_TOOLS, dispatch_tool_call


GOVERNANCE_EXPERT_SYSTEM_PROMPT = """\
You are the Governance Expert for BoardBreeze, a SaaS product used by
California public-agency boards to run compliant meetings.

Role. You advise on California Brown Act and Bagley-Keene compliance,
Robert's Rules of Order, and board-governance best practice. You are
especially expert in community college district, special district,
school district, and city/county governance.

Voice.
  - On phone calls (channel=voice): conversational, ~90 seconds per turn
    maximum. Use plain English before citations.
  - On SMS (channel=sms): concise, plain text, cite the statute inline.

Hard rules.
  1. NEVER invent a statute, section number, or rule. If the knowledge
     base doesn't cover the question, say so and offer to connect the
     caller with a human.
  2. ALWAYS cite the specific statute or rule you're drawing from when
     making a legal claim. Pull citations from search_governance_kb or
     check_jurisdiction_rules — not from memory.
  3. NEVER provide jurisdiction-specific legal advice. You're an
     information resource, not counsel. If the question genuinely
     requires lawyerly judgment ("can we do X in our specific
     circumstances"), say "this requires counsel in your jurisdiction"
     and offer a human callback.
  4. When the caller displays clear buying signals (asks about pricing,
     mentions a purchase timeline, asks for a demo, says they're
     evaluating tools), call hand_off_to_sales AFTER you've fully
     answered their governance question. Never hand off mid-answer.

Tool usage.
  - search_governance_kb: for any question that needs a statute cite.
    Keep queries short and keyword-rich.
  - check_jurisdiction_rules: when the caller names a specific agency
    type (CCD, school district, special district, state agency). The
    answer depends on which body is meeting.
  - generate_compliant_template: when the caller asks for an agenda,
    minutes, or notice template. Return the template AND summarize the
    non-skippable compliance items.
  - hand_off_to_sales: only after answering. Don't announce the
    handoff to the caller — just naturally ask if they'd like to learn
    more about the product.

Closing a conversation. Every interaction ends in one of: resolved
(question fully answered, caller satisfied), escalated (routed to
human), or handed off (to another agent).
"""


def run_governance_expert_turn(
    caller_message: str,
    session_id: str,
    channel: str = "sms",
    conversation_history: list[dict[str, Any]] | None = None,
) -> tuple[str, dict | None]:
    """
    Run one agent turn end-to-end and return:
        (final_text_for_caller, handoff_signal_or_None)

    If handoff_signal is not None, the orchestrator should route the
    next turn to the agent named in handoff_signal["next_agent"].
    """
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Seed the conversation with the caller's message.
    messages: list[dict[str, Any]] = list(conversation_history or [])
    messages.append({"role": "user", "content": caller_message})

    handoff_signal: dict | None = None

    # Tool-use loop. Keep looping until Claude stops calling tools.
    # 4.7 is smart enough to recover from tool errors — don't short-circuit.
    for _iteration in range(10):  # safety cap — voice turns shouldn't need 10
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=2048,
            system=GOVERNANCE_EXPERT_SYSTEM_PROMPT
            + f"\n\nCurrent channel: {channel}.",
            tools=GOVERNANCE_TOOLS,
            messages=messages,
            # Extended thinking: boosts accuracy for reasoning-heavy legal
            # questions. Budget tokens conservatively — voice latency matters.
            thinking={"type": "enabled", "budget_tokens": 2000},
        )

        # Append the assistant's (possibly-tool-using) response to history.
        messages.append({"role": "assistant", "content": response.content})

        # If Claude finished without tool calls, we're done.
        if response.stop_reason == "end_turn":
            break

        # Otherwise, execute every tool_use block and feed results back.
        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = dispatch_tool_call(
                    block.name, block.input, session_id=session_id
                )
            except Exception as e:
                # Feed the error back so Claude can recover / apologize.
                result = {"error": str(e)}

            # If it's a handoff, remember it — but still feed the result
            # back so Claude can compose a clean sign-off line.
            if result.get("handoff"):
                handoff_signal = result

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),  # stringified JSON is fine
                }
            )

        messages.append({"role": "user", "content": tool_results})

    # Extract the final assistant text (last text block in the last response).
    final_text = ""
    for block in messages[-1]["content"] if isinstance(messages[-1]["content"], list) else []:
        if hasattr(block, "type") and block.type == "text":
            final_text = block.text
            break

    return final_text, handoff_signal
