"""
Twilio Voice webhooks.

Two-stage strategy (per playbook §7.1 — "Shipping > perfect"):

  Stage 1 (today): <Gather> + <Say>. Twilio transcribes one turn, posts it
    back to us, we return TwiML with the reply spoken via Polly/ElevenLabs.
    Latency is ~3–5s/turn — not magical but works end-to-end on day one.

  Stage 2 (Thu/Fri): swap to Twilio Media Streams + Deepgram (STT) +
    ElevenLabs (TTS) for real-time streaming. Target <1s perceived latency.

Both stages share the same Concierge supervisor — only the transport changes.
"""
from fastapi import APIRouter, Form, Response

from app.agents.concierge import run_concierge_turn

router = APIRouter()


@router.post("/inbound")
async def inbound_call(From: str = Form(...), CallSid: str = Form(...)) -> Response:
    """First touch: greet, then hand to /gather for the first turn."""
    greeting = (
        "Hi, this is BoardBreeze's AI concierge. I can help with governance "
        "questions, product support, or connect you with Grace. What's going on?"
    )
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say voice="Polly.Joanna">{greeting}</Say>'
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
    """One caller turn → one agent turn → speak reply, then gather again."""
    if not SpeechResult.strip():
        # Silence — re-prompt.
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

    reply_text = await run_concierge_turn(
        caller_id=From,
        channel="voice",
        caller_message=SpeechResult,
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
