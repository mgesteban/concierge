"""
One-shot seed script for governance_kb.

Run:
    python -m app.kb.seed_kb

What it does:
  - Loads a hand-authored set of authoritative governance chunks with
    exact statutory citations (Brown Act, Bagley-Keene, Robert's Rules).
  - Loads the BoardBreeze product FAQ from
    `BoardBreeze Comprehensive FAQ — AI Agent Knowledge Base.md` at the
    repo root, unescapes its markdown export artifacts, and chunks it
    by section. Tagged `jurisdiction='product'` so the Concierge's
    `search_product_kb` tool can target it.
  - Embeds each chunk with Voyage (voyage-3-lite, 512-dim).
  - Bulk-inserts into Supabase.

Why paraphrase instead of verbatim statutes?
  California statutes are public domain, but paraphrases retrieve better
  for conversational queries (shorter, denser, no "for purposes of this
  section" boilerplate). Keep the citation string exact — that's what the
  Governance Expert cites out loud.
"""
import os
import re
import sys
from pathlib import Path

from app.tools.governance_tools.db import get_supabase
from app.tools.governance_tools.embeddings import embed_batch


SEED_CHUNKS: list[dict] = [
    # -------- California Brown Act --------
    {
        "source": "Gov. Code § 54954.2",
        "document": "California Brown Act",
        "section_title": "Regular meeting agenda posting (72 hours)",
        "jurisdiction": "CA",
        "agency_types": [],
        "content": (
            "For regular meetings, the agency must post the agenda at "
            "least 72 hours in advance in a location freely accessible "
            "to the public AND on the agency's primary website. Each "
            "agenda item must be briefly described. The legislative "
            "body may not take action on any item not listed on the "
            "posted agenda, with narrow exceptions (emergency, "
            "subsequent need, or continuation from a prior meeting)."
        ),
    },
    {
        "source": "Gov. Code § 54956",
        "document": "California Brown Act",
        "section_title": "Special meetings (24-hour notice)",
        "jurisdiction": "CA",
        "agency_types": [],
        "content": (
            "A special meeting may be called by the presiding officer or "
            "a majority of the body. Written notice must be delivered to "
            "each member of the body and to each local newspaper, radio, "
            "and television station that has filed a written request for "
            "notice, at least 24 hours before the meeting. Only business "
            "described in the notice may be transacted; no other matter "
            "may be considered or acted upon."
        ),
    },
    {
        "source": "Gov. Code § 54956.5",
        "document": "California Brown Act",
        "section_title": "Emergency meetings",
        "jurisdiction": "CA",
        "agency_types": [],
        "content": (
            "In the case of an emergency situation (work stoppage, "
            "crippling disaster, or other activity severely impairing "
            "public health or safety, or both), an emergency meeting "
            "may be called on one hour's telephonic notice to media "
            "that have requested notice. The 24-hour notice otherwise "
            "required for special meetings does not apply, but the "
            "majority must determine that an emergency exists."
        ),
    },
    {
        "source": "Gov. Code § 54952.2",
        "document": "California Brown Act",
        "section_title": "Meeting defined; serial meetings prohibited",
        "jurisdiction": "CA",
        "agency_types": [],
        "content": (
            "A 'meeting' is any congregation of a majority of the body "
            "to hear, discuss, deliberate, or take action on any item "
            "within the body's jurisdiction. A majority of the body "
            "may not, outside an authorized meeting, use a series of "
            "communications — directly, through intermediaries, or via "
            "technology like text/email/chat — to develop a collective "
            "concurrence. This is the 'serial meeting' prohibition."
        ),
    },
    {
        "source": "Gov. Code § 54953",
        "document": "California Brown Act",
        "section_title": "Open meetings; teleconference participation",
        "jurisdiction": "CA",
        "agency_types": [],
        "content": (
            "All meetings of the legislative body must be open and "
            "public, and all persons must be permitted to attend. "
            "Members may participate by teleconference if the agency "
            "posts the address of each teleconference location, keeps "
            "each location accessible to the public, and takes roll-call "
            "votes. AB 2449 and AB 557/SB 411 provide alternate "
            "teleconference rules for 'just cause' and emergency "
            "circumstances with procedural safeguards."
        ),
    },
    {
        "source": "Gov. Code § 54954.3",
        "document": "California Brown Act",
        "section_title": "Public comment rights",
        "jurisdiction": "CA",
        "agency_types": [],
        "content": (
            "Members of the public must be given an opportunity to "
            "address the body on any agenda item before or during its "
            "consideration, and on any matter within the body's "
            "subject-matter jurisdiction during a general public-comment "
            "period. The body may adopt reasonable regulations, "
            "including total time allotted to the public-comment period "
            "and per-speaker time limits."
        ),
    },
    {
        "source": "Gov. Code § 54954.5",
        "document": "California Brown Act",
        "section_title": "Closed session agenda descriptions",
        "jurisdiction": "CA",
        "agency_types": [],
        "content": (
            "Closed session items must use the SAFE-HARBOR descriptions "
            "provided in § 54954.5 (e.g., 'CONFERENCE WITH LEGAL "
            "COUNSEL — EXISTING LITIGATION'). Using these exact labels "
            "with the required specifics (case name, negotiator "
            "identity, property address) is the intended path to "
            "compliance. Do not draft ad-hoc labels."
        ),
    },
    {
        "source": "Gov. Code § 54957",
        "document": "California Brown Act",
        "section_title": "Personnel exception (closed session)",
        "jurisdiction": "CA",
        "agency_types": [],
        "content": (
            "A closed session may be held to consider the appointment, "
            "employment, evaluation of performance, discipline, or "
            "dismissal of a public employee, or to hear complaints "
            "against an employee. The employee has a right to have the "
            "complaints or charges heard in open session, and must be "
            "given 24 hours' written notice of their right to do so."
        ),
    },
    {
        "source": "Gov. Code § 54957.1",
        "document": "California Brown Act",
        "section_title": "Reporting out from closed session",
        "jurisdiction": "CA",
        "agency_types": [],
        "content": (
            "Certain closed-session actions must be publicly reported "
            "out before adjournment. These include final approval of a "
            "real-property agreement, final action on pending "
            "litigation, and appointments/dismissals of public "
            "employees. Specific disclosures (vote tallies, case "
            "citations, employee position titles) are required for each "
            "category."
        ),
    },
    {
        "source": "Gov. Code § 54957.5",
        "document": "California Brown Act",
        "section_title": "Writings distributed to the body (agenda materials)",
        "jurisdiction": "CA",
        "agency_types": [],
        "content": (
            "Writings distributed to a majority of the legislative body "
            "in connection with an open-session agenda item are public "
            "records available for inspection during normal business "
            "hours. Materials distributed less than 72 hours before the "
            "meeting must be made available at a public office or on the "
            "agency website at the same time they are distributed to "
            "members."
        ),
    },
    {
        "source": "Gov. Code § 54960",
        "document": "California Brown Act",
        "section_title": "Enforcement and remedies",
        "jurisdiction": "CA",
        "agency_types": [],
        "content": (
            "The district attorney or any interested person may "
            "commence an action to stop or prevent Brown Act violations, "
            "to determine the applicability of the Act, or to nullify "
            "certain actions taken in violation. A written cease-and-"
            "desist demand under § 54960.2 is required before suit for "
            "past violations in most circumstances."
        ),
    },
    # -------- California Bagley-Keene (state agencies only) --------
    {
        "source": "Gov. Code § 11125(a)",
        "document": "California Bagley-Keene Open Meeting Act",
        "section_title": "10-day agenda posting (state agencies)",
        "jurisdiction": "CA_STATE",
        "agency_types": ["state_agency"],
        "content": (
            "State bodies subject to Bagley-Keene must post the meeting "
            "notice and agenda at least 10 days in advance on the "
            "agency's website and make it available in the agency's "
            "office. This is materially longer than the Brown Act's "
            "72 hours — applies ONLY to state-level boards, commissions, "
            "and committees, not local agencies."
        ),
    },
    {
        "source": "Gov. Code § 11125.4",
        "document": "California Bagley-Keene Open Meeting Act",
        "section_title": "48-hour special meeting notice (state)",
        "jurisdiction": "CA_STATE",
        "agency_types": ["state_agency"],
        "content": (
            "Bagley-Keene special meetings require 48 hours' notice — "
            "twice the Brown Act's 24. The emergency exception under "
            "Bagley-Keene is narrower and requires the body to "
            "determine prompt action is essential."
        ),
    },
    # -------- Robert's Rules (paraphrased) --------
    {
        "source": "Robert's Rules of Order, 12th ed., §4",
        "document": "Robert's Rules of Order Newly Revised (12th ed.)",
        "section_title": "Types of motions",
        "jurisdiction": "any",
        "agency_types": [],
        "content": (
            "Robert's Rules recognizes four classes of motions: main "
            "motions (bring business before the body), subsidiary "
            "motions (modify or dispose of the motion under "
            "consideration — amend, refer, postpone, lay on the table), "
            "privileged motions (unrelated urgent matters — recess, "
            "adjourn, raise a question of privilege), and incidental "
            "motions (procedural — point of order, appeal, division of "
            "the assembly). Only one main motion is on the floor at a "
            "time."
        ),
    },
    {
        "source": "Robert's Rules of Order, 12th ed., §3",
        "document": "Robert's Rules of Order Newly Revised (12th ed.)",
        "section_title": "Quorum",
        "jurisdiction": "any",
        "agency_types": [],
        "content": (
            "A quorum is the minimum number of members who must be "
            "present for business to be validly transacted. If the "
            "bylaws or controlling statute specify a quorum, that "
            "controls; otherwise Robert's Rules defaults to a majority "
            "of the members. Business conducted without a quorum is "
            "generally invalid and may be challenged."
        ),
    },
    {
        "source": "Robert's Rules of Order, 12th ed., §48",
        "document": "Robert's Rules of Order Newly Revised (12th ed.)",
        "section_title": "Minutes of the meeting",
        "jurisdiction": "any",
        "agency_types": [],
        "content": (
            "Minutes record what was DONE, not what was said. Each "
            "motion should be recorded with its exact wording, the name "
            "of the member who moved and seconded it, and the result of "
            "the vote. Points of order and appeals and their rulings "
            "are recorded. Discussion content is ordinarily summarized, "
            "not transcribed, unless the body orders otherwise."
        ),
    },
    {
        "source": "Robert's Rules of Order, 12th ed., §44",
        "document": "Robert's Rules of Order Newly Revised (12th ed.)",
        "section_title": "Voting thresholds",
        "jurisdiction": "any",
        "agency_types": [],
        "content": (
            "Standard votes: a majority vote is more than half of the "
            "votes cast (abstentions not counted). A two-thirds vote "
            "is required to close debate (previous question), suspend "
            "the rules, amend previously-adopted bylaws, or rescind "
            "without notice. Special thresholds may be set by bylaws "
            "or governing statute and override Robert's defaults."
        ),
    },
    # -------- Agency-type-specific notes --------
    {
        "source": "Ed. Code § 35144 et seq.",
        "document": "California Education Code (school districts)",
        "section_title": "School district board meetings",
        "jurisdiction": "CA",
        "agency_types": ["school_district"],
        "content": (
            "School district governing boards meet per the Education "
            "Code in addition to the Brown Act. Regular meetings are "
            "typically held at the district office within the district. "
            "Closed sessions for certificated employee discipline have "
            "additional notice requirements under Ed. Code § 44929.21 "
            "et seq., and student expulsion hearings under § 48918 have "
            "their own procedural framework."
        ),
    },
    {
        "source": "Ed. Code § 70902 and Title 5 CCR § 53200",
        "document": "California Ed. Code + Title 5 (community college districts)",
        "section_title": "CCD shared governance",
        "jurisdiction": "CA",
        "agency_types": ["community_college_district"],
        "content": (
            "Community college district boards are Brown Act "
            "'legislative bodies'. In addition to Brown Act compliance, "
            "CCD boards must follow Title 5 CCR § 53200 et seq. shared-"
            "governance rules: Academic Senate consultation is required "
            "on academic and professional matters (curriculum, degree "
            "requirements, grading policies, educational program "
            "development, etc.), and those items should be staged on "
            "the agenda accordingly."
        ),
    },
    {
        "source": "Gov. Code § 54952(a)",
        "document": "California Brown Act",
        "section_title": "Special districts are covered",
        "jurisdiction": "CA",
        "agency_types": ["special_district"],
        "content": (
            "Independent special districts (water, fire, recreation, "
            "sanitation, healthcare, etc.) are 'local agencies' whose "
            "governing bodies are 'legislative bodies' under Gov. Code "
            "§ 54952(a), placing them squarely under the Brown Act. "
            "Standing committees of a special-district board with "
            "continuing subject-matter jurisdiction are ALSO subject "
            "to the Brown Act, even if they do not include a quorum."
        ),
    },
]


# ---------------------------------------------------------------------------
# BoardBreeze FAQ loader (product KB)
# ---------------------------------------------------------------------------
# The FAQ markdown is an export from a tool that escaped most punctuation
# (\#, \*, \., \(, \), etc.). We strip those before chunking so the
# embeddings see clean prose.
#
# Sections 24 (User Database) and 25 (Onboarding Emails Already Sent) are
# excluded — they contain subscriber PII we don't want a phone agent
# reading aloud. Section 27 (Blog Content Available) is excluded because
# it's a long list of blog post titles that adds retrieval noise without
# helping callers.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
FAQ_PATH = REPO_ROOT / "BoardBreeze Comprehensive FAQ — AI Agent Knowledge Base.md"

PRODUCT_SECTION_SKIP = {24, 25, 27}
SUBCHUNK_THRESHOLD_CHARS = 1800  # split sections larger than this on `### `

_FAQ_ESCAPE_RE = re.compile(r"\\([^a-zA-Z0-9])")
_FAQ_SECTION_RE = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)
_FAQ_SUBSECTION_RE = re.compile(r"^### (.+)$", re.MULTILINE)


def _faq_unescape(text: str) -> str:
    # The export double-escapes some chars (e.g. "1\\." for a list number).
    # Loop until the substitution converges so both layers come off.
    while True:
        new = _FAQ_ESCAPE_RE.sub(r"\1", text)
        if new == text:
            return new
        text = new


def _faq_split_section(num: int, title: str, body: str) -> list[dict]:
    body = re.sub(r"\n---\s*$", "", body).strip()
    if not body:
        return []

    base = {
        "source": f"BoardBreeze FAQ §{num}",
        "document": "BoardBreeze Product FAQ",
        "jurisdiction": "product",
        "agency_types": [],
    }

    if (
        len(body) < SUBCHUNK_THRESHOLD_CHARS
        or not _FAQ_SUBSECTION_RE.search(body)
    ):
        return [{**base, "section_title": title, "content": body}]

    parts: list[dict] = []
    matches = list(_FAQ_SUBSECTION_RE.finditer(body))
    if matches[0].start() > 0:
        prelude = body[: matches[0].start()].strip()
        if prelude:
            parts.append({**base, "section_title": title, "content": prelude})
    for i, m in enumerate(matches):
        sub_title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sub_body = body[start:end].strip()
        if sub_body:
            parts.append(
                {
                    **base,
                    "section_title": f"{title} — {sub_title}",
                    "content": sub_body,
                }
            )
    return parts


def load_faq_chunks() -> list[dict]:
    if not FAQ_PATH.exists():
        print(f"FAQ source not found at {FAQ_PATH} — skipping product KB.")
        return []

    raw = _faq_unescape(FAQ_PATH.read_text(encoding="utf-8"))
    headings = list(_FAQ_SECTION_RE.finditer(raw))
    chunks: list[dict] = []
    for i, m in enumerate(headings):
        num = int(m.group(1))
        if num in PRODUCT_SECTION_SKIP:
            continue
        title = m.group(2).strip()
        body_start = m.end()
        body_end = (
            headings[i + 1].start() if i + 1 < len(headings) else len(raw)
        )
        chunks.extend(_faq_split_section(num, title, raw[body_start:body_end]))
    return chunks


def main() -> int:
    governance = SEED_CHUNKS
    product = load_faq_chunks()
    all_chunks = governance + product
    print(
        f"Seeding {len(governance)} governance + {len(product)} product "
        f"chunks = {len(all_chunks)} total..."
    )
    supabase = get_supabase()

    texts = [c["content"] for c in all_chunks]
    embeddings = embed_batch(texts, input_type="document")

    rows = [{**c, "embedding": e} for c, e in zip(all_chunks, embeddings)]

    # Wipe + reinsert so this script is idempotent.
    supabase.table("governance_kb").delete().gt(
        "created_at", "1970-01-01"
    ).execute()
    supabase.table("governance_kb").insert(rows).execute()

    print(f"Inserted {len(rows)} rows. Running analyze...")
    # Supabase-py doesn't support ANALYZE via table methods — you can run
    # "analyze governance_kb;" manually in SQL editor once.
    print("Done. Run `analyze governance_kb;` in Supabase SQL editor once.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
