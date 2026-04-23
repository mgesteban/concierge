"""
Supabase client singleton.

The governance_tools package has its own client in app/tools/governance_tools/db.py —
this module is the Concierge's equivalent for conversation_state, messages,
leads, and tickets tables.

Kept separate so that agent-level tools don't accidentally reach into
conversation-level persistence (and vice versa).
"""
from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)
