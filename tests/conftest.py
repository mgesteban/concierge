"""
Stub heavy deps so the test suite runs offline with no keys.

Pytest auto-discovers conftest.py. This must run BEFORE any governance_tools
imports are resolved in tests.
"""
import sys
from unittest.mock import MagicMock

# Stub optional deps. Real implementations are only exercised in integration
# tests (not included here — you'd gate those behind `@pytest.mark.integration`
# and an env-var check).
for mod in ("voyageai", "supabase", "anthropic"):
    sys.modules.setdefault(mod, MagicMock())
