"""
Tool 2: check_jurisdiction_rules

Structured rule-set lookup by (state, agency_type). Returns the key
compliance rules as a structured dict the agent can present cleanly.

Data source: California Government Code (Brown Act §§ 54950-54963,
Bagley-Keene §§ 11120-11132), California Education Code § 35144 et seq.
Other states are STUBBED — extend as needed. The stub response is honest:
it acknowledges we don't have deep coverage yet rather than guessing.
"""
from typing import Any


# ---------------------------------------------------------------------------
# The rules database.
# Structure: RULES[state][agency_type] = { ...rule dict... }
# "_default" under a state means "this agency type inherits state defaults".
# ---------------------------------------------------------------------------

_CA_BROWN_ACT_DEFAULT: dict[str, Any] = {
    "governing_statute": "California Brown Act (Gov. Code §§ 54950–54963)",
    "regular_meeting_agenda_posting": {
        "notice_hours": 72,
        "rule": (
            "Post the agenda at least 72 hours before a regular meeting in "
            "a location freely accessible to the public and on the agency's "
            "primary website."
        ),
        "citation": "Gov. Code § 54954.2(a)(1)",
    },
    "special_meeting_notice": {
        "notice_hours": 24,
        "rule": (
            "Deliver written notice to each member of the legislative body "
            "and to each local newspaper/broadcaster that has requested "
            "notice, at least 24 hours before the special meeting. Only "
            "agenda items listed in the notice may be discussed."
        ),
        "citation": "Gov. Code § 54956",
    },
    "emergency_meeting_notice": {
        "rule": (
            "For emergencies (work stoppage, crippling disaster, etc.), "
            "one hour's notice may be given to media that have requested "
            "notice. No 24-hour requirement applies."
        ),
        "citation": "Gov. Code § 54956.5",
    },
    "public_comment": {
        "rule": (
            "Members of the public must be allowed to address the body on "
            "any agenda item before or during its consideration, AND on "
            "any matter within the body's subject-matter jurisdiction "
            "during a general public-comment period."
        ),
        "citation": "Gov. Code § 54954.3",
    },
    "serial_meetings_prohibited": {
        "rule": (
            "A majority of the body may not, OUTSIDE an open meeting, use "
            "direct communication, intermediaries, or technology (text, "
            "email, chat) to develop a collective concurrence on an item "
            "within the body's jurisdiction."
        ),
        "citation": "Gov. Code § 54952.2(b)",
    },
    "closed_session_allowed_topics": {
        "rule": (
            "Closed sessions are limited to specific statutory topics: "
            "pending litigation (§ 54956.9), personnel matters (§ 54957), "
            "labor negotiations (§ 54957.6), real property negotiations "
            "(§ 54956.8), public security (§ 54957(a)), and license "
            "applicant cases. Anything outside these categories must be "
            "in open session."
        ),
        "citation": "Gov. Code §§ 54956.7–54957.8",
    },
    "closed_session_reporting": {
        "rule": (
            "Certain closed-session actions (final action on litigation, "
            "appointment/discipline of employees, approval of real-property "
            "agreements) must be publicly reported out before adjournment."
        ),
        "citation": "Gov. Code § 54957.1",
    },
    "remote_participation": {
        "rule": (
            "Teleconference participation is permitted under the standard "
            "rules (§ 54953(b): post address of each teleconference "
            "location, keep each location open to public). AB 2449 (in "
            "effect through Jan 1, 2026) and AB 557/SB 411 updates allow "
            "limited 'just cause' remote attendance without posting the "
            "remote location, subject to procedural requirements."
        ),
        "citation": "Gov. Code § 54953(b), (f)",
    },
    "quorum": {
        "rule": (
            "Default: majority of the total authorized membership of the "
            "body constitutes a quorum. Check your enabling statute / "
            "bylaws for any higher threshold."
        ),
        "citation": "Common-law default; see agency enabling statute",
    },
    "minutes_retention": {
        "rule": (
            "Minutes must be kept for open sessions. Closed-session minute "
            "books, where kept, are confidential except as to a court in "
            "camera review."
        ),
        "citation": "Gov. Code § 54957.2 (minute book for closed sessions)",
    },
}

_CA_SCHOOL_DISTRICT_OVERLAY: dict[str, Any] = {
    **_CA_BROWN_ACT_DEFAULT,
    "governing_statute": (
        "California Brown Act (Gov. Code §§ 54950–54963) PLUS "
        "Education Code provisions specific to school district boards "
        "(Ed. Code §§ 35140–35178)."
    ),
    "agency_specific_notes": [
        (
            "School district boards must hold regular meetings in a location "
            "within the district boundaries unless an emergency or other "
            "specific Ed. Code exception applies."
        ),
        (
            "Public employee discipline/dismissal closed sessions for "
            "certificated employees have additional Ed. Code notice "
            "requirements (see Ed. Code § 44929.21 et seq.)."
        ),
        (
            "Student expulsion hearings are governed by Ed. Code § 48918 "
            "and have their own procedural rules layered on Brown Act."
        ),
    ],
}

_CA_CCD_OVERLAY: dict[str, Any] = {
    **_CA_BROWN_ACT_DEFAULT,
    "governing_statute": (
        "California Brown Act (Gov. Code §§ 54950–54963) PLUS Education "
        "Code provisions for community college districts (Ed. Code "
        "§§ 70900 et seq., and Title 5 CCR regulations)."
    ),
    "agency_specific_notes": [
        (
            "Community college district boards are 'legislative bodies' "
            "under Gov. Code § 54952 and fully subject to the Brown Act."
        ),
        (
            "CCDs have shared-governance obligations under Title 5 CCR "
            "§ 53200 et seq. that affect how certain academic/professional "
            "matters come before the board (agenda structure often reflects "
            "Academic Senate consultation)."
        ),
        (
            "Collective-bargaining and personnel closed sessions follow "
            "Gov. Code § 54957.6 and Ed. Code provisions for academic "
            "employees."
        ),
    ],
}

_CA_SPECIAL_DISTRICT_OVERLAY: dict[str, Any] = {
    **_CA_BROWN_ACT_DEFAULT,
    "governing_statute": (
        "California Brown Act (Gov. Code §§ 54950–54963). Agency also "
        "subject to its enabling statute (varies by district type — "
        "water, fire, recreation, sanitation, etc.)."
    ),
    "agency_specific_notes": [
        (
            "Independent special districts are squarely within the Brown "
            "Act as 'legislative bodies of a local agency' (Gov. Code "
            "§ 54952(a))."
        ),
        (
            "Subsidiary bodies (standing committees with continuing subject-"
            "matter jurisdiction) are ALSO subject to Brown Act. Ad hoc "
            "committees of less than a quorum generally are NOT."
        ),
        (
            "Check your district's enabling statute (Water Code, Health & "
            "Safety Code, Public Resources Code, etc.) for elections, "
            "officer terms, and any heightened notice requirements."
        ),
    ],
}

_CA_BAGLEY_KEENE: dict[str, Any] = {
    "governing_statute": "California Bagley-Keene Open Meeting Act (Gov. Code §§ 11120–11132)",
    "regular_meeting_agenda_posting": {
        "notice_hours": 240,  # 10 days
        "rule": (
            "Post the agenda at least 10 days before a regular meeting on "
            "the agency's website and in the agency's office."
        ),
        "citation": "Gov. Code § 11125(a)",
    },
    "special_meeting_notice": {
        "notice_hours": 48,
        "rule": (
            "Deliver written notice to each body member and requesting "
            "parties at least 48 hours before the special meeting."
        ),
        "citation": "Gov. Code § 11125.4",
    },
    "public_comment": {
        "rule": (
            "Members of the public must be allowed to address the body on "
            "each agenda item. Bagley-Keene does not require a general "
            "non-agenda public comment period (unlike Brown Act)."
        ),
        "citation": "Gov. Code § 11125.7",
    },
    "closed_session_allowed_topics": {
        "rule": (
            "Narrower than Brown Act. Closed sessions permitted for "
            "pending litigation, personnel, license applicant, threats to "
            "public services, and a few other enumerated categories."
        ),
        "citation": "Gov. Code §§ 11126",
    },
    "agency_specific_notes": [
        (
            "Bagley-Keene applies to STATE boards, commissions, and "
            "committees — not local agencies. If the caller is a city, "
            "county, school district, CCD, or special district, they're "
            "under Brown Act, not Bagley-Keene."
        )
    ],
}


RULES: dict[str, dict[str, Any]] = {
    "CA": {
        "_default": _CA_BROWN_ACT_DEFAULT,
        "city_council": _CA_BROWN_ACT_DEFAULT,
        "county_board": _CA_BROWN_ACT_DEFAULT,
        "school_district": _CA_SCHOOL_DISTRICT_OVERLAY,
        "community_college_district": _CA_CCD_OVERLAY,
        "special_district": _CA_SPECIAL_DISTRICT_OVERLAY,
        "joint_powers_authority": _CA_BROWN_ACT_DEFAULT,
        "state_agency": _CA_BAGLEY_KEENE,
        "other": _CA_BROWN_ACT_DEFAULT,
    },
    # Stubs for other states — honest "we don't have deep data yet" response
    # rather than guessing. Extend these with real research when you expand.
    "NY": {
        "_default": {
            "governing_statute": "New York Open Meetings Law (Public Officers Law §§ 100–111)",
            "_stub": True,
            "pointer": (
                "Our deep ruleset coverage is currently California-only. "
                "For NY specifics, consult the NY Committee on Open "
                "Government (opengovernment.ny.gov) or agency counsel."
            ),
        }
    },
    "TX": {
        "_default": {
            "governing_statute": "Texas Open Meetings Act (Gov. Code Ch. 551)",
            "_stub": True,
            "pointer": (
                "Our deep ruleset coverage is currently California-only. "
                "For TX specifics, consult the Texas Attorney General's "
                "Open Meetings Handbook or agency counsel."
            ),
        }
    },
    "FL": {
        "_default": {
            "governing_statute": "Florida Sunshine Law (§ 286.011, Fla. Stat.)",
            "_stub": True,
            "pointer": (
                "Our deep ruleset coverage is currently California-only. "
                "For FL specifics, consult the Florida Attorney General's "
                "Sunshine Manual or agency counsel."
            ),
        }
    },
}


def check_jurisdiction_rules(state: str, agency_type: str) -> dict[str, Any]:
    """
    Return the structured rule-set for (state, agency_type).

    If we don't have deep coverage for the state, returns a stub with
    a pointer and an explicit `_stub: True` flag so the agent knows to
    caveat its response and offer a human callback instead of bluffing.
    """
    state = (state or "").upper()
    agency_type = (agency_type or "other").lower()

    state_rules = RULES.get(state)
    if state_rules is None:
        return {
            "state": state,
            "agency_type": agency_type,
            "_stub": True,
            "message": (
                f"We don't have a structured ruleset for {state!r} yet. "
                "California is fully covered; other states return general "
                "pointers only. Recommend connecting the caller with "
                "counsel in their jurisdiction."
            ),
        }

    rules = state_rules.get(agency_type) or state_rules["_default"]
    return {
        "state": state,
        "agency_type": agency_type,
        **rules,
    }
