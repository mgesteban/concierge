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
import re
from html import escape

from fastapi import APIRouter, Form, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.channels.tts import (
    pop_audio,
    pop_text,
    queue_text,
    register_audio,
    stream_synth,
    synthesize_static,
)
from app.voice_pipeline import (
    forget_call,
    get_turn_result,
    pop_turn,
    queue_turn,
    queue_turn_async,
    run_turn,
)

log = logging.getLogger(__name__)
router = APIRouter()


GREETING = (
    "Hello! This is the BoardBreeze concierge. I can help with governance "
    "questions, product support, pricing, or connect you with Grace. "
    "What can I help you with today?"
)
REPROMPT = "Sorry, I didn't catch that. Could you say it again?"
# Plays during /gather→/continue while Claude + synth work in the background.
# Keep this ~3 s spoken so it bridges most of the Claude time; length is
# deliberate and not filler-for-the-sake-of-it.
THINKING = "Sure — let me take a quick look at that for you."
# Spoken if the background turn times out or errors. Ends with a prompt so
# the <Gather> picks the caller's next utterance cleanly.
FALLBACK = (
    "Sorry, I'm having trouble pulling that up right now. "
    "Could you try asking again?"
)
# Spoken when the caller signals the call is over. Plays + Hangup, no
# Gather, no model round trip. Without this, "goodbye" goes through the
# chained-TwiML flow and the caller hears the THINKING filler ("let me
# take a quick look at that for you") before any farewell — jarring.
FAREWELL = "Thanks for calling BoardBreeze. Have a great day!"

# Server-side intent matcher for "the caller is wrapping up the call."
# A small keyword set is plenty for the demo and avoids the cost/latency
# of a model classification round trip. False positives here only
# truncate a call early; false negatives just keep the existing flow.
# "thanks" / "thank you" alone are NOT farewells — callers say them
# mid-call after an answer and then ask the next question. Only treat
# them as farewell when paired with bye/goodbye.
_FAREWELL_EXACT = {
    "bye", "goodbye", "good bye", "bye bye",
}
_FAREWELL_KEYWORDS = (
    "goodbye", "good bye", "bye bye", "bye now", "bye for now",
    "see you later", "see you", "see ya", "talk later",
    "talk to you later", "talk soon",
    "thanks bye", "thanks good bye", "thanks goodbye",
    "thank you bye", "thank you good bye", "thank you goodbye",
    "that's all", "thats all", "that is all",
    "that's it", "thats it", "that is it",
    "i'm done", "im done", "i am done",
    "i'm all set", "im all set", "all set",
    "we're done", "were done", "we are done",
    "have a good day", "have a nice day", "have a great day",
    "have a good one", "have a nice one", "have a great one",
    "okay bye", "ok bye", "alright bye",
    "hang up", "end the call", "end call",
    "nothing else", "no more questions", "no further questions",
)


def _is_farewell(text: str) -> bool:
    norm = text.strip().lower().rstrip(".!?,;:")
    if norm in _FAREWELL_EXACT:
        return True
    return any(kw in norm for kw in _FAREWELL_KEYWORDS)

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
    """Chained-TwiML flow:

    1. Spawn a background turn (Claude + sentence-by-sentence synth →
       complete MP3 blob).
    2. Return TwiML that immediately plays a cached "let me look that up"
       filler, then <Redirect>s to /continue/{turn_id}. Twilio fetches
       the filler from our static cache in ~100 ms and starts playing.
    3. While the filler plays (~3 s), the background turn is running.
    4. /continue waits on the Future, returns <Play>{reply}</Play><Gather/>.

    Net result: caller hears the filler ~300 ms after finishing speaking,
    then the real answer as soon as it's ready.
    """
    if not SpeechResult.strip():
        twiml = await _speak_static("reprompt", REPROMPT)
        return Response(content=twiml, media_type="application/xml")

    if _is_farewell(SpeechResult):
        try:
            cid = await run_in_threadpool(
                synthesize_static, "farewell", FAREWELL
            )
            twiml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<Response>"
                f"<Play>/twilio/voice/audio/{cid}.mp3</Play>"
                "<Hangup/>"
                "</Response>"
            )
        except Exception:
            log.exception("farewell synth failed — falling back to Polly")
            twiml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<Response>"
                f'<Say voice="Polly.Joanna">{escape(FAREWELL)}</Say>'
                "<Hangup/>"
                "</Response>"
            )
        forget_call(CallSid)
        return Response(content=twiml, media_type="application/xml")

    # Kick off the background turn FIRST so it runs while Twilio is
    # fetching and playing the filler.
    turn_id = queue_turn_async(CallSid, From, SpeechResult)

    try:
        filler_cid = await run_in_threadpool(
            synthesize_static, "thinking", THINKING
        )
    except Exception:
        # Static synth failed — skip the filler and go straight to /continue.
        # Caller hears silence until /continue lands, but at least the call
        # doesn't error. ElevenLabs is almost always available.
        log.exception("filler synth failed — no pre-reply audio")
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Redirect method="POST">/twilio/voice/continue/{turn_id}</Redirect>'
            "</Response>"
        )
        return Response(content=twiml, media_type="application/xml")

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Play>/twilio/voice/audio/{filler_cid}.mp3</Play>"
        f'<Redirect method="POST">/twilio/voice/continue/{turn_id}</Redirect>'
        "</Response>"
    )
    return Response(content=twiml, media_type="application/xml")


@router.post("/continue/{turn_id}")
async def continue_turn(
    turn_id: str,
    From: str = Form(""),
    CallSid: str = Form(""),
) -> Response:
    """Wait for the background turn to finish, return TwiML playing the
    full reply MP3 + re-opening <Gather> for the next utterance.

    Twilio gives webhook handlers ~15 s before it gives up. We cap the
    wait at 12 s to leave headroom for the HTTP response itself. If the
    turn hasn't completed by then, we play a polite fallback and let the
    caller try again.
    """
    audio = await run_in_threadpool(get_turn_result, turn_id, 12.0)
    if audio is None:
        log.warning("continue_turn: no audio for %s (timeout or missing)", turn_id)
        twiml = await _speak_static("fallback", FALLBACK)
        return Response(content=twiml, media_type="application/xml")

    cid = register_audio(audio)
    twiml = _play_twiml(f"/twilio/voice/audio/{cid}.mp3")
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
