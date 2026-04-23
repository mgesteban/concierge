"""
Tool 3: generate_compliant_template

Returns Brown-Act-ready (or Bagley-Keene) templates with:
  - required legal boilerplate (ADA, public comment, posting attestation)
  - clearly-marked {{placeholders}} the caller fills in
  - compliance_checklist: the non-skippable items

Templates are authored to the current (2026) state of California law. Review
when AB 2449's sunset hits in Jan 2026 — AB 557 / SB 411 extensions may apply.
"""
from typing import Any


# ---------------------------------------------------------------------------
# Templates — Brown Act
# ---------------------------------------------------------------------------

_REGULAR_MEETING_AGENDA_BROWN_ACT = """\
{{AGENCY_NAME}}
{{BODY_NAME}} — REGULAR MEETING AGENDA

Meeting Date:    {{DATE}}
Meeting Time:    {{TIME}}
Meeting Location: {{LOCATION_ADDRESS}}
{{#TELECONFERENCE_LOCATIONS}}Teleconference Location(s): {{TELECONFERENCE_LOCATIONS}}{{/TELECONFERENCE_LOCATIONS}}

PUBLIC PARTICIPATION
Members of the public may address the {{BODY_NAME}} on any item on this
agenda before or during its consideration. The public may also address
the body during the General Public Comment item on any matter within the
body's subject-matter jurisdiction. (Gov. Code § 54954.3.)

ACCESSIBILITY / ADA
In compliance with the Americans with Disabilities Act, if you need
special assistance to participate in this meeting, please contact
{{ADA_CONTACT_NAME}} at {{ADA_CONTACT_PHONE}} at least 48 hours before the
meeting to allow the agency to make reasonable arrangements.

WRITINGS DISTRIBUTED TO THE BODY
Writings distributed to a majority of the {{BODY_NAME}} in connection with
an open-session agenda item less than 72 hours before the meeting are
available for public inspection at {{PUBLIC_INSPECTION_ADDRESS}} during
regular business hours. (Gov. Code § 54957.5.)

—————————————————————————————————————
1. CALL TO ORDER / ROLL CALL
2. PLEDGE OF ALLEGIANCE (optional)
3. APPROVAL OF AGENDA
4. GENERAL PUBLIC COMMENT
   (Each speaker limited to {{PUBLIC_COMMENT_MINUTES}} minutes.)
5. CONSENT CALENDAR
   All matters listed under Consent Calendar are considered routine and
   will be acted upon by one motion unless a member or member of the
   public requests separate action.
   5.1 {{CONSENT_ITEM_1}}
   5.2 {{CONSENT_ITEM_2}}
6. REGULAR AGENDA ITEMS
   6.1 {{REGULAR_ITEM_1_TITLE}}
       (Recommended action: {{REGULAR_ITEM_1_RECOMMENDED_ACTION}})
   6.2 {{REGULAR_ITEM_2_TITLE}}
7. REPORTS AND COMMUNICATIONS
8. CLOSED SESSION (if applicable — use closed_session_agenda template)
9. ADJOURNMENT

—————————————————————————————————————
POSTING ATTESTATION
I, {{POSTING_CLERK_NAME}}, {{POSTING_CLERK_TITLE}}, hereby certify that on
{{POSTING_DATE}} at {{POSTING_TIME}}, this agenda was posted at
{{POSTING_LOCATION}} (a location freely accessible to the public) and on
the agency's website at {{AGENCY_WEBSITE}}, at least 72 hours before the
meeting as required by Government Code § 54954.2.
"""

_SPECIAL_MEETING_NOTICE = """\
{{AGENCY_NAME}}
NOTICE AND AGENDA — SPECIAL MEETING OF {{BODY_NAME}}

NOTICE IS HEREBY GIVEN that a special meeting of the {{BODY_NAME}} will
be held:

Date:     {{DATE}}
Time:     {{TIME}}
Location: {{LOCATION_ADDRESS}}

BUSINESS TO BE TRANSACTED
Only the following matter(s) shall be considered. No other business may
be transacted at this special meeting (Gov. Code § 54956).

1. {{AGENDA_ITEM_1_TITLE}}
   (Recommended action: {{AGENDA_ITEM_1_RECOMMENDED_ACTION}})
{{#AGENDA_ITEM_2_TITLE}}
2. {{AGENDA_ITEM_2_TITLE}}
{{/AGENDA_ITEM_2_TITLE}}

PUBLIC COMMENT
Members of the public shall be given an opportunity to address the body
on each item on this agenda before or during its consideration.
(Gov. Code § 54954.3.)

ACCESSIBILITY / ADA
[ADA language — see regular agenda template.]

—————————————————————————————————————
NOTICE DELIVERY ATTESTATION
I, {{POSTING_CLERK_NAME}}, hereby certify that on {{NOTICE_DELIVERY_DATE}}
at {{NOTICE_DELIVERY_TIME}} — at least 24 hours before this special
meeting — written notice of this meeting was delivered to each member of
the {{BODY_NAME}} and to each local newspaper of general circulation,
radio, and television station that had requested notice in writing,
as required by Government Code § 54956. Notice was also posted at
{{POSTING_LOCATION}} and on the agency website.
"""

_EMERGENCY_MEETING_NOTICE = """\
{{AGENCY_NAME}}
NOTICE — EMERGENCY MEETING OF {{BODY_NAME}}

Pursuant to Government Code § 54956.5, a majority of the {{BODY_NAME}} has
determined that a work stoppage, crippling disaster, or other activity
severely impairing public health, safety, or both exists, and that an
emergency meeting is required.

Nature of Emergency: {{EMERGENCY_DESCRIPTION}}

Date:     {{DATE}}
Time:     {{TIME}}
Location: {{LOCATION_ADDRESS}}

ITEMS TO BE CONSIDERED
1. {{EMERGENCY_ITEM_1}}

NOTICE DELIVERY
One hour telephonic notice has been given to each local newspaper of
general circulation, radio, and television station that has requested
notice in writing, as permitted by Gov. Code § 54956.5(b)(1).

{{POSTING_CLERK_NAME}}
{{POSTING_CLERK_TITLE}}
{{POSTING_DATETIME}}
"""

_CLOSED_SESSION_AGENDA = """\
{{AGENCY_NAME}}
{{BODY_NAME}} — CLOSED SESSION AGENDA

Date:     {{DATE}}
Time:     {{TIME}}
Location: {{LOCATION_ADDRESS}} (closed session)

The {{BODY_NAME}} will meet in closed session to consider the following
matter(s). Each item below describes the closed-session topic with the
specificity required by Gov. Code § 54954.5.

—————————————————————————————————————
{{#LITIGATION_PENDING}}
CONFERENCE WITH LEGAL COUNSEL — EXISTING LITIGATION
Government Code § 54956.9(d)(1)
Case Name / Court:  {{CASE_NAME}} — {{COURT_AND_CASE_NUMBER}}
{{/LITIGATION_PENDING}}

{{#LITIGATION_ANTICIPATED}}
CONFERENCE WITH LEGAL COUNSEL — ANTICIPATED LITIGATION
Significant exposure to litigation pursuant to Gov. Code § 54956.9(d)(2):
{{NUMBER_OF_POTENTIAL_CASES}} case(s). Facts and circumstances are
privileged unless the body elects to disclose them.
{{/LITIGATION_ANTICIPATED}}

{{#PUBLIC_EMPLOYEE_PERFORMANCE}}
PUBLIC EMPLOYEE PERFORMANCE EVALUATION
Government Code § 54957(b)(1)
Title: {{POSITION_TITLE}}
{{/PUBLIC_EMPLOYEE_PERFORMANCE}}

{{#LABOR_NEGOTIATIONS}}
CONFERENCE WITH LABOR NEGOTIATORS
Government Code § 54957.6
Agency designated representatives: {{DESIGNATED_REPS}}
Employee organization(s):          {{BARGAINING_UNITS}}
{{/LABOR_NEGOTIATIONS}}

{{#REAL_PROPERTY}}
CONFERENCE WITH REAL PROPERTY NEGOTIATORS
Government Code § 54956.8
Property:                {{PROPERTY_DESCRIPTION}}
Agency negotiator(s):    {{AGENCY_NEGOTIATORS}}
Negotiating parties:     {{OTHER_PARTIES}}
Under negotiation:       {{PRICE_AND_TERMS_OF_PAYMENT}}
{{/REAL_PROPERTY}}

—————————————————————————————————————
RECONVENE TO OPEN SESSION
Any reportable action taken in closed session will be announced in open
session as required by Gov. Code § 54957.1 before adjournment.

POSTING ATTESTATION
[As in regular agenda — 72 hours, posting location, website URL.]
"""

_CONSENT_AGENDA = """\
{{AGENCY_NAME}}
{{BODY_NAME}} — CONSENT CALENDAR
(Attached to or embedded in the {{DATE}} Regular Meeting Agenda)

All matters listed under this Consent Calendar are considered routine and
will be enacted by ONE motion unless, prior to the vote, a member of the
body or a member of the public requests that an item be removed for
separate discussion and action.

Each removed item will be considered separately immediately following
approval of the remaining Consent Calendar items.

—————————————————————————————————————
C-1  Approval of Minutes: {{MINUTES_DATE}} regular meeting
C-2  Warrant / Check Register for {{PAYROLL_PERIOD}}
     (Total: ${{WARRANT_TOTAL}})
C-3  Acceptance of monthly financial report for {{FINANCIAL_PERIOD}}
C-4  {{ROUTINE_CONTRACT_RENEWAL}}
C-5  {{PERSONNEL_ROUTINE_APPOINTMENT}}
{{#ADDITIONAL_CONSENT_ITEMS}}
C-6  {{ADDITIONAL_CONSENT_ITEMS}}
{{/ADDITIONAL_CONSENT_ITEMS}}

Recommended Action: Approve the Consent Calendar as presented.
"""

_MEETING_MINUTES = """\
{{AGENCY_NAME}}
MINUTES — {{BODY_NAME}} {{MEETING_TYPE}} MEETING

Date:     {{DATE}}
Time Convened: {{TIME_CONVENED}}
Time Adjourned: {{TIME_ADJOURNED}}
Location: {{LOCATION_ADDRESS}}

MEMBERS PRESENT
{{MEMBERS_PRESENT}}

MEMBERS ABSENT
{{MEMBERS_ABSENT}}

STAFF PRESENT
{{STAFF_PRESENT}}

—————————————————————————————————————
1. CALL TO ORDER
   {{CHAIR_NAME}} called the meeting to order at {{TIME_CONVENED}} and led
   the Pledge of Allegiance.

2. APPROVAL OF AGENDA
   Motion: Moved by {{MOVED_BY}}, seconded by {{SECONDED_BY}}, to approve
   the agenda as presented. AYES: {{AYES}}. NOES: {{NOES}}. ABSENT:
   {{ABSENT}}. Motion carried.

3. PUBLIC COMMENT
   {{PUBLIC_COMMENT_SUMMARY}} (Individual comments summarized; full
   recording retained per agency records policy.)

4. CONSENT CALENDAR
   Items C-1 through C-{{CONSENT_LAST}} approved by unanimous motion
   ({{MOVED_BY}} / {{SECONDED_BY}}).

5. REGULAR AGENDA ITEMS
   5.1  {{ITEM_5_1_TITLE}}
        Discussion: {{ITEM_5_1_DISCUSSION_SUMMARY}}
        Motion: Moved by {{ITEM_5_1_MOVED_BY}}, seconded by
        {{ITEM_5_1_SECONDED_BY}}, to {{ITEM_5_1_ACTION}}.
        Roll call vote —
          AYES: {{ITEM_5_1_AYES}}
          NOES: {{ITEM_5_1_NOES}}
          ABSTAIN: {{ITEM_5_1_ABSTAIN}}
        Motion {{ITEM_5_1_OUTCOME}}.

6. CLOSED SESSION REPORT OUT (if applicable)
   {{CLOSED_SESSION_REPORT_OR_NONE}}

7. ADJOURNMENT
   The meeting adjourned at {{TIME_ADJOURNED}}.

—————————————————————————————————————
Respectfully submitted,

{{CLERK_NAME}}, {{CLERK_TITLE}}

Approved by {{BODY_NAME}} on: {{APPROVAL_DATE}}
"""

_ANNUAL_MEETING_CALENDAR_NOTICE = """\
{{AGENCY_NAME}}
{{BODY_NAME}} — {{YEAR}} REGULAR MEETING CALENDAR

Pursuant to the {{BODY_NAME}}'s bylaws and Government Code § 54954, the
{{BODY_NAME}} hereby establishes the following schedule of regular
meetings for the calendar year {{YEAR}}.

All regular meetings will be held at {{DEFAULT_LOCATION}} at
{{DEFAULT_TIME}} unless otherwise noticed.

{{MEETING_DATES_LIST}}

Agendas for each regular meeting will be posted at least 72 hours in
advance at {{POSTING_LOCATION}} and on the agency website at
{{AGENCY_WEBSITE}}, as required by Gov. Code § 54954.2.

Adopted this {{ADOPTION_DATE}} by action of the {{BODY_NAME}}.
"""


# ---------------------------------------------------------------------------
# Compliance checklists — the "you cannot skip these" summary per template.
# Surfaced alongside the template so the agent can coach the caller.
# ---------------------------------------------------------------------------

_CHECKLISTS: dict[str, list[str]] = {
    "regular_meeting_agenda": [
        "Post at least 72 hours before the meeting (Gov. Code § 54954.2).",
        "Post BOTH at a physically-accessible location AND on the agency website.",
        "Include a brief general description of each item — no surprise action items.",
        "Include the ADA accommodation contact info.",
        "Include the 'writings distributed to the body' public inspection notice.",
        "Retain the signed posting attestation in the agency records.",
    ],
    "special_meeting_notice": [
        "Deliver written notice to every body member AND every requesting media outlet at least 24 hours before the meeting (Gov. Code § 54956).",
        "ONLY items listed in the notice may be discussed — no 'other business'.",
        "Public comment required on every listed item.",
        "Retain delivery / posting attestation for each recipient.",
    ],
    "emergency_meeting_notice": [
        "Use ONLY for genuine emergencies (work stoppage, crippling disaster) under Gov. Code § 54956.5 — misuse voids the meeting.",
        "One-hour telephonic notice to requesting media is the floor, not the ceiling — notify everyone you reasonably can.",
        "Minutes/recording requirements are stricter for emergency meetings; confirm your agency's retention policy.",
    ],
    "closed_session_agenda": [
        "Each closed-session item must use the specific description required by Gov. Code § 54954.5 for its category (don't write your own labels).",
        "Include the statutory citation on each item.",
        "Only the enumerated closed-session categories (§§ 54956.7–54957.8) are permitted.",
        "Report out any reportable action in open session before adjournment (Gov. Code § 54957.1).",
    ],
    "consent_agenda": [
        "Each item must still be individually listed — not grouped into a vague 'routine matters' line.",
        "Any member OR member of the public may request removal for separate discussion.",
        "Consent items are still subject to the 72-hour posting rule.",
    ],
    "meeting_minutes": [
        "Record motions, movers, seconders, and roll-call votes on each substantive action.",
        "Summarize public comment (full verbatim not required unless your bylaws say so).",
        "Report out any closed-session reportable actions.",
        "Approve at the next regular meeting — minutes are not official until approved.",
    ],
    "annual_meeting_calendar_notice": [
        "Adopted by action of the body — not by the clerk alone.",
        "Publishing the annual calendar does NOT replace the 72-hour agenda posting for each meeting.",
        "If the agency changes the date/time of a regular meeting, re-post the amended calendar.",
    ],
}


TEMPLATES: dict[tuple[str, str], str] = {
    # (template_type, jurisdiction) -> template string
    ("regular_meeting_agenda", "CA_BROWN_ACT"): _REGULAR_MEETING_AGENDA_BROWN_ACT,
    ("special_meeting_notice", "CA_BROWN_ACT"): _SPECIAL_MEETING_NOTICE,
    ("emergency_meeting_notice", "CA_BROWN_ACT"): _EMERGENCY_MEETING_NOTICE,
    ("closed_session_agenda", "CA_BROWN_ACT"): _CLOSED_SESSION_AGENDA,
    ("consent_agenda", "CA_BROWN_ACT"): _CONSENT_AGENDA,
    ("meeting_minutes", "CA_BROWN_ACT"): _MEETING_MINUTES,
    ("annual_meeting_calendar_notice", "CA_BROWN_ACT"): _ANNUAL_MEETING_CALENDAR_NOTICE,
    # Bagley-Keene can reuse the Brown Act ones for now with a note, or be
    # filled in with state-specific variants. Stubbed for hackathon.
}


def generate_compliant_template(
    template_type: str,
    jurisdiction: str = "CA_BROWN_ACT",
    agency_type: str | None = None,
) -> dict[str, Any]:
    """
    Return a structured response:
        {
          "template_type": str,
          "jurisdiction": str,
          "template": str,                 # the actual template body
          "placeholders": list[str],       # parsed {{...}} names
          "compliance_checklist": list[str],
          "notes": list[str],              # agency-type-specific notes
        }
    """
    key = (template_type, jurisdiction)
    template = TEMPLATES.get(key)

    if template is None:
        return {
            "template_type": template_type,
            "jurisdiction": jurisdiction,
            "error": (
                f"No template available for "
                f"{template_type=} / {jurisdiction=}. "
                "Available: "
                f"{sorted({t for t, _ in TEMPLATES})}"
            ),
        }

    # Parse unique placeholder names for convenience (agent can enumerate
    # what the caller needs to fill in).
    import re

    raw_placeholders = re.findall(r"\{\{([A-Z_0-9]+)\}\}", template)
    placeholders = sorted(set(raw_placeholders))

    notes: list[str] = []
    if agency_type == "school_district":
        notes.append(
            "School district boards: layer Ed. Code § 35144 et seq. and "
            "student-matter procedures (e.g., Ed. Code § 48918 for "
            "expulsion hearings) on top of this Brown Act template."
        )
    elif agency_type == "community_college_district":
        notes.append(
            "CCD boards: ensure items subject to shared governance "
            "(Title 5 CCR § 53200 et seq.) are appropriately identified "
            "and preceded by Academic Senate consultation where required."
        )
    elif agency_type == "special_district":
        notes.append(
            "Special districts: check your enabling statute (Water Code, "
            "Health & Safety Code, Public Resources Code, etc.) for any "
            "district-specific notice requirements beyond Brown Act."
        )

    return {
        "template_type": template_type,
        "jurisdiction": jurisdiction,
        "agency_type": agency_type,
        "template": template,
        "placeholders": placeholders,
        "compliance_checklist": _CHECKLISTS.get(template_type, []),
        "notes": notes,
    }
