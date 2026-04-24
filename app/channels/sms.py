"""Twilio SMS webhook.

Inbound SMS → one CMA session turn → TwiML reply. The same session is
reused across SMS threads for the same caller (keyed on `From` phone
number in Supabase), so multi-day memory works automatically:
caller texts Monday, texts again Thursday, agent remembers.
"""
from fastapi import APIRouter, Form, Response
from fastapi.concurrency import run_in_threadpool

from app.managed_agents.client import handle_message

router = APIRouter()


@router.post("/inbound")
async def inbound_sms(
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...),
) -> Response:
    reply_text = await run_in_threadpool(
        handle_message, From, Body, "sms"
    )

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
        .replace("'", "&apos;")
    )
