"""Twilio Voice webhooks — day-one pipeline with ElevenLabs TTS.

Flow:
  Twilio <Gather input=speech>     → we receive transcribed text
  → handle_message via CMA session → Claude reply
  → ElevenLabs synth to MP3        → cached in-process
  → TwiML <Play>/audio/{cid}.mp3   → Twilio fetches and streams

If ElevenLabs synthesis fails (quota, rate limit, outage), we degrade to
a Polly <Say> TwiML for the same text — voice quality drops but the call
stays up. Errors are logged so the ElevenLabs config can be fixed
without paging anyone.

Latency today is ~9–12s end-to-end on Brown Act questions (Opus 4.7 is
thorough but not instant). Replies that exceed Twilio's ~15s webhook
timeout play "application error" instead of the real reply — mostly hit
on escalation paths that use two tool round-trips.

Friday upgrade (playbook §7.1): Twilio Media Streams + Deepgram (STT) +
ElevenLabs streaming TTS. Audio starts playing after the first Claude
token, so perceived latency is sub-second and the 15s ceiling goes away.
Same handle_message underneath — only the transport changes.
"""
import logging
from html import escape

from fastapi import APIRouter, Form, Response
from fastapi.concurrency import run_in_threadpool

from app.channels.tts import pop_audio, synthesize, synthesize_static
from app.managed_agents.client import handle_message

log = logging.getLogger(__name__)
router = APIRouter()


GREETING = (
    "Hi, this is BoardBreeze's AI concierge. I can help with governance "
    "questions, product support, or connect you with Grace. What's going on?"
)
REPROMPT = "Sorry, I didn't catch that. Could you say it again?"

_GATHER = (
    '<Gather input="speech" action="/twilio/voice/gather" '
    'speechTimeout="auto" language="en-US"/>'
)


def _play_twiml(cid: str, gather: bool = True) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Play>/twilio/voice/audio/{cid}.mp3</Play>'
        f"{_GATHER if gather else ''}"
        "</Response>"
    )


def _say_twiml(text: str, gather: bool = True) -> str:
    """Fallback TwiML when ElevenLabs synth fails — Polly voice, but audible."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say voice="Polly.Joanna">{escape(text)}</Say>'
        f"{_GATHER if gather else ''}"
        "</Response>"
    )


async def _speak(text: str, static_key: str | None = None) -> str:
    """Synthesize via ElevenLabs, fall back to Polly Say on failure."""
    try:
        if static_key is not None:
            cid = await run_in_threadpool(synthesize_static, static_key, text)
        else:
            cid = await run_in_threadpool(synthesize, text)
        return _play_twiml(cid)
    except Exception:
        log.exception("ElevenLabs TTS failed — falling back to Polly Say")
        return _say_twiml(text)


@router.post("/inbound")
async def inbound_call(
    From: str = Form(...), CallSid: str = Form(...)
) -> Response:
    """First touch: greet, then gather the caller's first utterance."""
    twiml = await _speak(GREETING, static_key="greeting")
    return Response(content=twiml, media_type="application/xml")


@router.post("/gather")
async def gather(
    From: str = Form(...),
    CallSid: str = Form(...),
    SpeechResult: str = Form(""),
) -> Response:
    """One caller turn → one CMA turn → speak reply → gather again."""
    if not SpeechResult.strip():
        twiml = await _speak(REPROMPT, static_key="reprompt")
        return Response(content=twiml, media_type="application/xml")

    reply_text = await run_in_threadpool(
        handle_message, From, SpeechResult, "voice"
    )
    twiml = await _speak(reply_text)
    return Response(content=twiml, media_type="application/xml")


@router.get("/audio/{cid}.mp3")
async def serve_audio(cid: str) -> Response:
    """Twilio fetches the MP3 here. One-shot cache — entry is popped on fetch."""
    audio = pop_audio(cid)
    if audio is None:
        return Response(status_code=404)
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )
