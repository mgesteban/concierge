"""
Environment-backed settings for BoardBreeze Concierge.

Loads from .env in dev and from process env in production. Every subsystem
(Twilio webhooks, Supabase client, Anthropic client) pulls config from here
rather than os.environ directly — so we have one audit point for secrets.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""

    supabase_url: str = ""
    supabase_service_key: str = ""

    voyage_api_key: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""

    grace_phone_number: str = ""
    grace_email: str = ""

    public_base_url: str = ""
    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
