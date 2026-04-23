"""
Anthropic tool-use JSON schemas for the Governance Expert agent.

These schemas are what Claude Opus 4.7 reads to decide WHEN to call each
tool and WHAT arguments to pass. The descriptions matter more than the
parameter names — 4.7 follows instructions precisely, so spend effort here.

Usage:
    from governance_tools.schemas import GOVERNANCE_TOOLS
    from anthropic import Anthropic

    client = Anthropic()
    response = client.messages.create(
        model="claude-opus-4-7",
        tools=GOVERNANCE_TOOLS,
        messages=[...],
        system=GOVERNANCE_EXPERT_SYSTEM_PROMPT,
    )
"""

SEARCH_GOVERNANCE_KB_SCHEMA = {
    "name": "search_governance_kb",
    "description": (
        "Search the curated governance knowledge base for authoritative "
        "passages on public-agency meeting law (California Brown Act, "
        "Bagley-Keene for state agencies), Robert's Rules of Order, and "
        "board-governance best practices. Returns up to 5 relevant passages "
        "with EXACT statute/rule citations (e.g., 'Gov. Code § 54954.2').\n\n"
        "USE THIS WHENEVER you need to cite a statute or rule — never invent "
        "section numbers. If the passages don't cover the question adequately, "
        "say so and offer to connect the caller with a human.\n\n"
        "Good queries: short, keyword-rich ('72 hour agenda posting', 'closed "
        "session personnel exception', 'serial meeting definition'). Bad "
        "queries: full-sentence questions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "3–10 keywords describing the rule or concept you want "
                    "to find. Favor statute/rule terminology over caller's "
                    "words (translate 'Can the mayor text council members "
                    "about the vote?' into 'serial meeting text message')."
                ),
            },
            "jurisdiction": {
                "type": "string",
                "enum": ["CA", "CA_STATE", "federal", "any"],
                "description": (
                    "Limit to a jurisdiction. 'CA' = California local "
                    "agencies under the Brown Act (most common). 'CA_STATE' "
                    "= California state agencies under Bagley-Keene. 'any' "
                    "= search everything (use when unsure)."
                ),
                "default": "CA",
            },
            "top_k": {
                "type": "integer",
                "description": "How many passages to return. Default 5, max 10.",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}

CHECK_JURISDICTION_RULES_SCHEMA = {
    "name": "check_jurisdiction_rules",
    "description": (
        "Look up the meeting-compliance rule-set for a specific jurisdiction "
        "+ agency type combo. Returns a structured summary of posting "
        "requirements, quorum rules, public-comment rules, closed-session "
        "rules, and the governing statute.\n\n"
        "USE THIS when the caller names a specific agency type ('community "
        "college district', 'special district', 'city council', 'school "
        "board') — different agency types have materially different rules "
        "under the same open-meeting law. Also use when the caller is in a "
        "non-California state.\n\n"
        "Do NOT use this for general Brown Act questions (use "
        "search_governance_kb instead). Use this when the answer depends on "
        "which kind of body is meeting."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "description": (
                    "Two-letter US state code (e.g., 'CA', 'NY', 'TX'). "
                    "Use 'CA' by default when the caller doesn't specify."
                ),
            },
            "agency_type": {
                "type": "string",
                "enum": [
                    "city_council",
                    "county_board",
                    "school_district",
                    "community_college_district",
                    "special_district",
                    "state_agency",
                    "joint_powers_authority",
                    "other",
                ],
                "description": (
                    "The kind of governing body meeting. 'special_district' "
                    "covers water, fire, recreation, sanitation, etc. "
                    "districts. 'state_agency' in CA triggers Bagley-Keene "
                    "instead of Brown Act."
                ),
            },
        },
        "required": ["state", "agency_type"],
    },
}

GENERATE_COMPLIANT_TEMPLATE_SCHEMA = {
    "name": "generate_compliant_template",
    "description": (
        "Generate a Brown-Act-compliant (or equivalent state law) template "
        "the caller can use: meeting agendas, minutes, special meeting "
        "notices, closed-session agendas, consent agendas, and emergency "
        "meeting notices. Templates include required legal boilerplate "
        "(posting attestation, public comment notice, ADA accommodation "
        "language, etc.) with clearly marked {{placeholders}} the caller "
        "fills in.\n\n"
        "USE THIS when a caller asks 'can you send me an agenda template?' "
        "or 'what does a compliant closed-session agenda look like?' or "
        "similar. After returning, briefly summarize the KEY compliance "
        "requirements so the caller knows what they cannot skip."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "template_type": {
                "type": "string",
                "enum": [
                    "regular_meeting_agenda",
                    "special_meeting_notice",
                    "emergency_meeting_notice",
                    "closed_session_agenda",
                    "consent_agenda",
                    "meeting_minutes",
                    "annual_meeting_calendar_notice",
                ],
                "description": "The kind of template to generate.",
            },
            "jurisdiction": {
                "type": "string",
                "enum": ["CA_BROWN_ACT", "CA_BAGLEY_KEENE"],
                "description": (
                    "Which legal framework the template must comply with. "
                    "Default: CA_BROWN_ACT (local agencies)."
                ),
                "default": "CA_BROWN_ACT",
            },
            "agency_type": {
                "type": "string",
                "description": (
                    "Optional: agency type for type-specific tweaks "
                    "(e.g., school districts have Ed Code overlays)."
                ),
            },
        },
        "required": ["template_type"],
    },
}

HAND_OFF_TO_SALES_SCHEMA = {
    "name": "hand_off_to_sales",
    "description": (
        "Signal that this caller should be transferred to the Sales Closer "
        "agent. Call this AFTER you've fully answered their governance "
        "question and detected buying signals: they asked about pricing, "
        "said 'we're evaluating tools', mentioned a timeline, asked for a "
        "demo, or compared BoardBreeze to a competitor.\n\n"
        "DO NOT call this if: (a) the caller is hostile or frustrated, "
        "(b) they're an existing subscriber asking a support question, "
        "(c) you haven't actually helped them yet, or (d) they explicitly "
        "said they don't want to be sold to. Give the answer first, earn "
        "trust, then hand off.\n\n"
        "After calling this tool, tell the caller naturally: 'Since you "
        "mentioned [X], would it help if I connected you with someone "
        "about a demo?' Do NOT announce the internal handoff."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "caller_summary": {
                "type": "string",
                "description": (
                    "2–3 sentence summary of who the caller is and what "
                    "they came in asking, in your words. The Sales Closer "
                    "will read this before taking over."
                ),
            },
            "agency_type": {
                "type": "string",
                "description": (
                    "The caller's agency type if mentioned "
                    "(e.g., 'community_college_district')."
                ),
            },
            "buying_signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of concrete buying signals you heard. Examples: "
                    "'asked about pricing', 'mentioned 2-week onboarding "
                    "deadline', 'compared us to Diligent Boards', "
                    "'asked if we support closed session voting'."
                ),
            },
            "urgency": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": (
                    "'high' = needs to buy in the next 30 days; "
                    "'medium' = this quarter; 'low' = evaluating."
                ),
            },
            "open_questions_for_sales": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Questions the caller asked that you deferred to sales "
                    "(pricing, plan comparison, contract terms)."
                ),
            },
        },
        "required": ["caller_summary", "buying_signals", "urgency"],
    },
}

# Bundle for easy import. This is what you pass to client.messages.create(tools=...).
GOVERNANCE_TOOLS = [
    SEARCH_GOVERNANCE_KB_SCHEMA,
    CHECK_JURISDICTION_RULES_SCHEMA,
    GENERATE_COMPLIANT_TEMPLATE_SCHEMA,
    HAND_OFF_TO_SALES_SCHEMA,
]
