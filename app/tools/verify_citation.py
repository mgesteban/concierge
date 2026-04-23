"""
verify_citation — the anti-hallucination layer for the Governance Expert.

Playbook §16.5: no statutory citation reaches a caller until this tool has
confirmed (a) the cited section exists in our curated KB, and (b) the
section's actual text supports the claim being made.

The shape of a call:

    verify_citation(
        citation="Gov. Code § 54954.2",
        claim="Local agencies must post the meeting agenda at least 72 "
              "hours before a regular meeting.",
    )
    → {
        "verified": True,
        "actual_text": "Each legislative body of a local agency...",
        "suggested_rewrite": None,
      }

When verification fails, the caller-facing agent is instructed (via the
Governance Expert system prompt) to rewrite the answer using only verified
material — or to say "I'm not certain on the specific section — let me
connect you with someone who can confirm."

Thursday work: wire this into the Governance Expert's tool list and the
reference loop so every tool_use that cites a statute is automatically
verified before the agent's final text reaches Twilio.

Saturday work: build the 10-pair golden test set and tune until false-pass
rate is zero. (False-fail is fine — over-cautious is the right failure mode
for a regulated domain.)
"""
from __future__ import annotations

from typing import TypedDict


class VerifyResult(TypedDict):
    verified: bool
    actual_text: str | None
    suggested_rewrite: str | None
    reason: str


VERIFY_CITATION_SCHEMA = {
    "name": "verify_citation",
    "description": (
        "Verify that a statutory citation is real AND that its actual text "
        "supports the specific claim being made. MUST be called before any "
        "reply that cites a statute reaches the caller.\n\n"
        "Returns {verified: bool, actual_text: str, suggested_rewrite: str, "
        "reason: str}. If verified is False, rewrite the claim using only "
        "verified material — or say 'I'm not certain on the specific "
        "section' and offer a human callback. Do not read the failed "
        "citation aloud."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "citation": {
                "type": "string",
                "description": (
                    "The exact citation string you plan to read aloud — "
                    "e.g., 'Gov. Code § 54954.2', 'Cal. Ed. Code § 72000', "
                    "'Robert's Rules, §24'. Use the canonical form from "
                    "search_governance_kb, not your own paraphrase."
                ),
            },
            "claim": {
                "type": "string",
                "description": (
                    "The specific legal claim you're attaching to this "
                    "citation, in one or two sentences. Example: 'Local "
                    "agencies must post the meeting agenda at least 72 "
                    "hours before a regular meeting.'"
                ),
            },
        },
        "required": ["citation", "claim"],
    },
}


def verify_citation(citation: str, claim: str) -> VerifyResult:
    """
    Placeholder implementation — returns unverified so the Governance Expert
    is forced to hedge until the real verifier lands Thursday.

    Thursday implementation:
      1. Look up `citation` in governance_kb (exact-match on `source`).
      2. If not found, return {verified: False, reason: 'citation not in KB'}.
      3. If found, call a small Claude classifier: "Does this passage
         support the claim? {yes|no|partial}, with 1-sentence reason."
      4. Return {verified: yes/partial, actual_text, suggested_rewrite}.
    """
    _ = citation, claim
    return {
        "verified": False,
        "actual_text": None,
        "suggested_rewrite": None,
        "reason": (
            "verify_citation stub — Thursday milestone. Hedge and offer a "
            "human callback rather than reading the citation aloud."
        ),
    }
