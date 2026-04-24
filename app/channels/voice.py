"""Twilio Voice webhooks — day-one pipeline.

Flow: Twilio <Gather input=speech> → FastAPI → CMA session → TwiML <Say>.
Latency is ~3–5 s/turn; good enough to demo the end-to-end loop.

Friday upgrade (per playbook §7.1): Twilio Media Streams + Deepgram STT
+ ElevenLabs TTS for sub-second perceived latency. Same CMA session
layer underneath — only the transport changes.
"""
from fastapi import APIRouter, Form, Response
from fastapi.concurrency import run_in_threadpool

from app.managed_agents.client import handle_message

router = APIRouter()


GREETING = (
    "Hi, this is BoardBreeze's AI concierge. I can help with governance "
    "questions, product support, or connect you with Grace. What's going on?"
)


@router.post("/inbound")
async def inbound_call(
    From: str = Form(...), CallSid: str = Form(...)
) -> Response:
    """First touch: greet, then gather the caller's first utterance."""
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say voice="Polly.Joanna">{GREETING}</Say>'
        '<Gather input="speech" action="/twilio/voice/gather" '
        'speechTimeout="auto" language="en-US"/>'
        "</Response>"
    )
    return Response(content=twiml, media_type="application/xml")


@router.post("/gather")
async def gather(
    From: str = Form(...),
    CallSid: str = Form(...),
    SpeechResult: str = Form(""),
) -> Response:
    """One caller turn → one CMA turn → speak reply → gather again."""
    if not SpeechResult.strip():
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            '<Say voice="Polly.Joanna">Sorry, I didn\'t catch that. '
            "Could you say it again?</Say>"
            '<Gather input="speech" action="/twilio/voice/gather" '
            'speechTimeout="auto" language="en-US"/>'
            "</Response>"
        )
        return Response(content=twiml, media_type="application/xml")

    reply_text = await run_in_threadpool(
        handle_message, From, SpeechResult, "voice"
    )

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say voice="Polly.Joanna">{_xml_escape(reply_text)}</Say>'
        '<Gather input="speech" action="/twilio/voice/gather" '
        'speechTimeout="auto" language="en-US"/>'
        "</Response>"
    )
    return Response(content=twiml, media_type="application/xml")


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
