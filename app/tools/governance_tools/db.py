"""
Supabase client. Module-level singleton so we don't re-initialize per call.

Env vars required:
    SUPABASE_URL            — your project URL
    SUPABASE_SERVICE_KEY    — service role key (server-side only, NEVER ship to browser)
"""
import os
from functools import lru_cache
from supabase import create_client, Client


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)
