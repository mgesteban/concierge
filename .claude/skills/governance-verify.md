---
name: governance-verify
description: Run a drafted Governance Expert answer through the verify_citation layer before it ships. Use when reviewing an agent reply that contains statutory citations. Playbook §16.5.
---

# /governance-verify

Before any Governance Expert answer with a statutory citation ships to a
caller OR into the demo video, run it through this verification pattern.

## Input

A drafted agent reply containing one or more citations (e.g., "Gov. Code
§ 54954.2", "Cal. Ed. Code § 72000", "Robert's Rules §24").

## Steps

1. Extract every distinct citation from the reply as `(citation, claim)`
   pairs — each cited statute is paired with the specific 1–2 sentence
   claim being attached to it.
2. For each pair, call `verify_citation(citation, claim)` (currently in
   `app/tools/verify_citation.py`).
3. If every citation returns `verified: True`, emit the reply unchanged.
4. If any citation fails:
   - Rewrite the reply using only verified material.
   - If nothing remains verifiable, emit the hedged fallback:
     "I'm not certain on the specific section — let me connect you with
     someone who can confirm."
5. Emit a verification audit table for the review log:

   | Citation | Claim | Verified | Reason |
   | -------- | ----- | -------- | ------ |

## When to use

- Before recording the Governance Expert's line in the demo video.
- When Grace pastes a draft agent reply and asks "is this safe to ship?"
- When expanding the KB — run the 10-pair golden test set afterward.

## Don'ts

- Don't skip verification because "the citation looks right" — that's
  exactly how hallucinated-but-plausible citations reach callers.
- Don't trust the agent's confidence level. The verifier is the source
  of truth.
