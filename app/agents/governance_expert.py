"""
Governance Expert agent — cite-backed advisor on public-agency meeting law.

This module is the production entry point for the Governance Expert. The
reference implementation lives in _governance_reference_loop.py (kept for
readability); this module wraps that loop and applies the 4.7-tuned prompt
nuances from playbook §8.6 (conditional language over blanket NEVER/ALWAYS).

Future (Thursday): wrap every statutory answer in verify_citation(...) per
playbook §16.5 before the reply reaches the caller.
"""
from app.agents._governance_reference_loop import run_governance_expert_turn

__all__ = ["run_governance_expert_turn"]
