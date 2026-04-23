"""
governance_tools — four Anthropic tools for the BoardBreeze Governance Expert.

Public API:
    GOVERNANCE_TOOLS        — list of tool schemas to pass to the Anthropic API
    dispatch_tool_call      — the function your orchestrator uses to execute
                              whichever tool Claude called
"""
from .schemas import (
    GOVERNANCE_TOOLS,
    SEARCH_GOVERNANCE_KB_SCHEMA,
    CHECK_JURISDICTION_RULES_SCHEMA,
    GENERATE_COMPLIANT_TEMPLATE_SCHEMA,
    HAND_OFF_TO_SALES_SCHEMA,
)
from .kb_search import search_governance_kb
from .jurisdictions import check_jurisdiction_rules
from .templates import generate_compliant_template
from .handoff import hand_off_to_sales


def dispatch_tool_call(
    tool_name: str, tool_input: dict, *, session_id: str
) -> dict:
    """
    Central dispatcher called by your orchestrator whenever Claude emits a
    tool_use block. The orchestrator supplies `session_id` — Claude itself
    never sees it.

    Example:
        for block in response.content:
            if block.type == "tool_use":
                result = dispatch_tool_call(
                    block.name, block.input, session_id=sess_id
                )
                # feed result back into the next client.messages.create(...)

    Raises KeyError on an unknown tool_name, so a misbehaving agent fails
    loudly rather than silently.
    """
    if tool_name == "search_governance_kb":
        return search_governance_kb(**tool_input)
    if tool_name == "check_jurisdiction_rules":
        return check_jurisdiction_rules(**tool_input)
    if tool_name == "generate_compliant_template":
        return generate_compliant_template(**tool_input)
    if tool_name == "hand_off_to_sales":
        # session_id injected here — NOT from Claude's input.
        return hand_off_to_sales(session_id=session_id, **tool_input)
    raise KeyError(f"Unknown tool: {tool_name!r}")


__all__ = [
    "GOVERNANCE_TOOLS",
    "SEARCH_GOVERNANCE_KB_SCHEMA",
    "CHECK_JURISDICTION_RULES_SCHEMA",
    "GENERATE_COMPLIANT_TEMPLATE_SCHEMA",
    "HAND_OFF_TO_SALES_SCHEMA",
    "search_governance_kb",
    "check_jurisdiction_rules",
    "generate_compliant_template",
    "hand_off_to_sales",
    "dispatch_tool_call",
]
