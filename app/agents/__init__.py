"""Historical reference only.

The production Concierge lives in `app/managed_agents/` and runs on
Claude Managed Agents with a single-agent-plus-tools architecture
(see notes/cohen-managed-agents.md for why).

This package keeps `_governance_reference_loop.py` — a self-contained
Brown Act Q&A loop written Wednesday against the raw Claude API —
because it makes the v0→v1 evolution of the project legible. Nothing
imports it at runtime.
"""
