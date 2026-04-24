"""
FastAPI entrypoint for BoardBreeze Concierge.

Mounts Twilio webhooks (voice + SMS) and a health check. Twilio posts inbound
messages/calls to these endpoints; the Concierge Managed Agent responds.

Run locally:
    .venv/bin/uvicorn app.main:app --reload --port 8000
"""
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

# Load .env from repo root so tools, SDKs, and clients find their secrets
# regardless of how uvicorn was invoked. Safe to call; if a var is already
# set in the environment, we don't override it.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Surface our own loggers (app.*) alongside uvicorn's. Without this the
# voice pipeline's sentence-timing info is invisible because FastAPI's
# default uvicorn config only configures uvicorn.* loggers.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

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
