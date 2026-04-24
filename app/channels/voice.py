"""Twilio Voice webhooks — streaming voice pipeline.

Flow:
  Twilio <Gather input=speech>    → SpeechResult
  → /gather queues the turn, returns <Play>/reply/{cid}.mp3 immediately
  → Twilio fetches /reply/{cid}.mp3 and plays bytes as they arrive
  → Inside that request:
      - drive a direct Claude Messages API stream (tools + history)
      - split Claude's tokens into sentences
      - fire ElevenLabs synth on each complete sentence
      - yield MP3 chunks straight back to Twilio

The /gather handler does NOT wait for the reply — it returns TwiML in
milliseconds with a <Play> URL. Twilio fetches that URL, we hold the
HTTP response open, and audio flows as Claude + ElevenLabs produce it.
Caller hears the first sentence ~1–2 s after they finish speaking,
instead of ~5–7 s with the buffered CMA path.

CMA is retained for SMS (see app/managed_agents/) because text doesn't
need token-level streaming and CMA's built-in session memory is free.
Voice uses the direct Messages API for latency.
"""
import logging
from html import escape

from fastapi import APIRouter, Form, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.channels.tts import (
    pop_audio,
    pop_text,
    queue_text,
    stream_synth,
    synthesize_static,
)
from app.voice_pipeline import forget_call, pop_turn, queue_turn, run_turn

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


def _play_twiml(play_path: str, gather: bool = True) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Play>{play_path}</Play>"
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


async def _speak_static(key: str, text: str) -> str:
    """TwiML for static prompts (greeting/reprompt). Synthesized once per
    process, served from memory. Falls back to Polly on TTS failure."""
    try:
        cid = await run_in_threadpool(synthesize_static, key, text)
        return _play_twiml(f"/twilio/voice/audio/{cid}.mp3")
    except Exception:
        log.exception("ElevenLabs static synth failed — falling back to Polly")
        return _say_twiml(text)


@router.post("/inbound")
async def inbound_call(
    From: str = Form(...), CallSid: str = Form(...)
) -> Response:
    """First touch: greet, then gather the caller's first utterance."""
    twiml = await _speak_static("greeting", GREETING)
    return Response(content=twiml, media_type="application/xml")


@router.post("/gather")
async def gather(
    From: str = Form(...),
    CallSid: str = Form(...),
    SpeechResult: str = Form(""),
) -> Response:
    """Queue the turn, return TwiML immediately pointing at /reply."""
    if not SpeechResult.strip():
        twiml = await _speak_static("reprompt", REPROMPT)
        return Response(content=twiml, media_type="application/xml")

    cid = queue_turn(CallSid, From, SpeechResult)
    twiml = _play_twiml(f"/twilio/voice/reply/{cid}.mp3")
    return Response(content=twiml, media_type="application/xml")


@router.post("/status")
async def call_status(
    CallSid: str = Form(...), CallStatus: str = Form(""),
) -> Response:
    """Twilio fires this on call status changes. On completion, drop
    the in-memory history for this CallSid so we don't leak memory."""
    if CallStatus in ("completed", "failed", "busy", "no-answer", "canceled"):
        forget_call(CallSid)
        log.info("forgot call %s (%s)", CallSid, CallStatus)
    return Response(status_code=204)


@router.get("/reply/{cid}.mp3")
def reply_stream(cid: str) -> Response:
    """Twilio fetches this URL for a dynamic reply. We drive the Claude
    turn (streaming Messages API) and pipe ElevenLabs MP3 chunks back as
    each sentence completes. Sync generator: FastAPI handles it in a
    worker thread, so blocking Anthropic/ElevenLabs HTTP calls are fine."""
    turn = pop_turn(cid)
    if turn is None:
        return Response(status_code=404)

    def _iter():
        try:
            yield from run_turn(
                call_sid=turn["call_sid"],
                phone=turn["phone"],
                user_text=turn["user_text"],
            )
        except Exception:
            log.exception("voice reply stream failed mid-flight")

    return StreamingResponse(
        _iter(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/audio/{cid}.mp3")
async def serve_audio(cid: str) -> Response:
    """Static / queued-text audio. Used by the greeting + reprompt paths
    (static cache) and any legacy queue_text consumers. The main dynamic
    reply flow uses /reply/{cid}.mp3 above."""
    audio = pop_audio(cid)
    if audio is not None:
        return Response(
            content=audio,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )
    text = pop_text(cid)
    if text is not None:
        def _iter():
            try:
                for chunk in stream_synth(text):
                    if chunk:
                        yield chunk
            except Exception:
                log.exception("ElevenLabs streaming synth failed mid-flight")

        return StreamingResponse(
            _iter(),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )
    return Response(status_code=404)
