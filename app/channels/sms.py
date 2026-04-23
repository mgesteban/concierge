"""
Twilio SMS webhook.

Twilio POSTs inbound messages to /twilio/sms/inbound. We respond with TwiML
(Twilio's XML dialect); the <Message> element is what the caller receives.

The flow:
  1. Twilio posts the inbound body + From number.
  2. We load or create a conversation_state row (keyed by caller_id).
  3. The Concierge supervisor picks the right specialist for this turn.
  4. We run one agent turn and return the reply as TwiML.

Multi-day SMS memory lives in Supabase — see §6.3 of the playbook.
"""
from fastapi import APIRouter, Form, Response

from app.agents.concierge import run_concierge_turn

router = APIRouter()


@router.post("/inbound")
async def inbound_sms(
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...),
) -> Response:
    reply_text = await run_concierge_turn(
        caller_id=From,
        channel="sms",
        caller_message=Body,
    )

    # TwiML response. Twilio sends this exact string back to the caller.
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Message>{_xml_escape(reply_text)}</Message>"
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
