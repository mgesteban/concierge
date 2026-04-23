"""
Fast offline tests for the pure-Python tools.

These stub out Supabase so you can run them with zero env setup:
    python -m pytest tests/
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.governance_tools import (
    check_jurisdiction_rules,
    generate_compliant_template,
    dispatch_tool_call,
)


# ---------------------------------------------------------------------------
# check_jurisdiction_rules — pure function, no stubs needed
# ---------------------------------------------------------------------------
def test_ca_brown_act_default():
    result = check_jurisdiction_rules("CA", "city_council")
    assert "Brown Act" in result["governing_statute"]
    assert result["regular_meeting_agenda_posting"]["notice_hours"] == 72
    assert "54954.2" in result["regular_meeting_agenda_posting"]["citation"]


def test_ca_ccd_has_ed_code_overlay():
    result = check_jurisdiction_rules("CA", "community_college_district")
    notes = result["agency_specific_notes"]
    assert any("Title 5" in n or "Academic Senate" in n for n in notes)


def test_ca_state_agency_is_bagley_keene():
    result = check_jurisdiction_rules("CA", "state_agency")
    assert "Bagley-Keene" in result["governing_statute"]
    # 10 days = 240 hours — materially stricter than Brown Act's 72
    assert result["regular_meeting_agenda_posting"]["notice_hours"] == 240


def test_non_ca_state_returns_stub():
    result = check_jurisdiction_rules("NY", "city_council")
    assert result["_stub"] is True
    assert "pointer" in result


def test_unknown_state_is_graceful():
    result = check_jurisdiction_rules("ZZ", "city_council")
    assert result["_stub"] is True


# ---------------------------------------------------------------------------
# generate_compliant_template — pure function
# ---------------------------------------------------------------------------
def test_regular_agenda_contains_ada_and_72hr():
    result = generate_compliant_template("regular_meeting_agenda")
    assert "ADA" in result["template"]
    assert "72 hours" in result["template"]
    assert "54954.2" in result["template"]
    # Checklist has the non-skippable items
    assert len(result["compliance_checklist"]) >= 4


def test_closed_session_agenda_uses_safe_harbor_labels():
    result = generate_compliant_template("closed_session_agenda")
    # safe-harbor labels from § 54954.5
    assert "CONFERENCE WITH LEGAL COUNSEL" in result["template"]
    assert "54956.9" in result["template"]


def test_minutes_template_records_votes():
    result = generate_compliant_template("meeting_minutes")
    assert "AYES" in result["template"]
    assert "Moved by" in result["template"]


def test_ccd_agency_adds_title_5_note():
    result = generate_compliant_template(
        "regular_meeting_agenda",
        agency_type="community_college_district",
    )
    assert any("Title 5" in n for n in result["notes"])


def test_unknown_template_type_errors_cleanly():
    result = generate_compliant_template("made_up_template")
    assert "error" in result


def test_placeholders_are_extracted():
    result = generate_compliant_template("regular_meeting_agenda")
    # Smoke check a few placeholders that should definitely be there
    assert "AGENCY_NAME" in result["placeholders"]
    assert "DATE" in result["placeholders"]
    assert "POSTING_CLERK_NAME" in result["placeholders"]


# ---------------------------------------------------------------------------
# hand_off_to_sales — stubs Supabase
# ---------------------------------------------------------------------------
def test_handoff_writes_and_returns_signal():
    fake_supabase = MagicMock()
    # Configure chained mock so .table(...).insert(...).execute() works
    fake_supabase.table.return_value.insert.return_value.execute.return_value = None
    fake_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = None

    with patch("governance_tools.handoff.get_supabase", return_value=fake_supabase):
        result = dispatch_tool_call(
            "hand_off_to_sales",
            {
                "caller_summary": "CCD board secretary in Riverside",
                "buying_signals": ["asked about pricing", "2-week timeline"],
                "urgency": "high",
                "agency_type": "community_college_district",
                "open_questions_for_sales": ["annual cost"],
            },
            session_id="test-session-123",
        )

    assert result["handoff"] is True
    assert result["next_agent"] == "sales_closer"
    assert "handoff_id" in result
    assert result["package"]["urgency"] == "high"

    # Verify the DB writes happened
    assert fake_supabase.table.call_count >= 2  # handoffs + conversation_state


# ---------------------------------------------------------------------------
# dispatch_tool_call routing
# ---------------------------------------------------------------------------
def test_dispatch_unknown_tool_raises():
    import pytest

    with pytest.raises(KeyError):
        dispatch_tool_call("not_a_real_tool", {}, session_id="x")
