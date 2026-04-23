"""
FastAPI entrypoint for BoardBreeze Concierge.

Mounts Twilio webhooks (voice + SMS) and a health check. Twilio posts inbound
messages/calls to these endpoints; the Concierge supervisor decides which
specialist handles the turn.

Run locally:
    uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI

from app.channels.sms import router as sms_router
from app.channels.voice import router as voice_router

app = FastAPI(
    title="BoardBreeze Concierge",
    description=(
        "Multi-agent voice + SMS support, governance advisor, and sales "
        "closer for appboardbreeze.com. Powered by Claude Opus 4.7 with "
        "Managed Agents."
    ),
    version="0.1.0",
)

app.include_router(sms_router, prefix="/twilio/sms", tags=["sms"])
app.include_router(voice_router, prefix="/twilio/voice", tags=["voice"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "BoardBreeze Concierge",
        "status": "live",
        "repo": "https://github.com/mgesteban/concierge",
    }
