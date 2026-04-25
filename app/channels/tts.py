"""ElevenLabs TTS for the voice channel.

Two paths:

1. **Dynamic replies** (per-caller, per-turn): text is registered via
   `queue_text()` which returns a cid. When Twilio fetches
   `/twilio/voice/audio/{cid}.mp3`, the handler pops the text and returns
   a streaming MP3 response — ElevenLabs chunks are piped straight
   through to Twilio as they arrive, instead of being buffered into a
   full file first. This saves the ~1–1.5 s it would otherwise take to
   complete the full synth before Twilio receives byte zero.

2. **Static prompts** (greeting, reprompt): synthesize once per process
   into `_STATIC_CACHE`, then hand Twilio a fresh cid backed by the
   cached bytes via `_CACHE`. No streaming needed — we already have the
   full MP3 in memory, and static prompts change rarely.

Uses `eleven_flash_v2_5` for ~200 ms time-to-first-byte.

Next upgrade (playbook §7.1): Twilio Media Streams bidirectional
WebSocket — feed CMA tokens into ElevenLabs input streaming as soon as
they're generated, so synth begins mid-Claude-sentence and perceived
latency drops into the sub-second range.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from collections.abc import Iterator
from functools import lru_cache
from threading import Lock

from elevenlabs.client import ElevenLabs

log = logging.getLogger(__name__)

# Byte cache for static prompts (greeting/reprompt) — one-shot cids.
_CACHE: dict[str, bytes] = {}

# Text cache for dynamic replies — synthesis happens when Twilio fetches
# the /audio URL, not when we register the text. Pop on fetch.
_TEXT_CACHE: dict[str, str] = {}

_LOCK = Lock()

# Keep the caches bounded so stuck entries don't pin memory forever.
_MAX_ENTRIES = 64

# Process-lifetime cache of synthesized static prompts.
_STATIC_CACHE: dict[str, bytes] = {}

_MODEL_ID = "eleven_flash_v2_5"
_OUTPUT_FORMAT = "mp3_22050_32"


@lru_cache(maxsize=1)
def _client() -> ElevenLabs:
    return ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])


def _prune(cache: dict) -> None:
    if len(cache) >= _MAX_ENTRIES:
        for k in list(cache)[: _MAX_ENTRIES // 2]:
            cache.pop(k, None)


# ---------------------------------------------------------------------------
# Pre-synth text normalization
# ---------------------------------------------------------------------------
# ElevenLabs Flash v2.5 mispronounces multi-digit dollar amounts ("$99",
# "$499") often enough to be a real demo problem — they come out blurred
# or run together. The KB has prices stored as "$29.99/month" verbatim,
# and the Concierge tends to read them straight back, so we have to
# normalize before synth rather than rely on the model. Spelled-out
# numbers ("ninety-nine dollars") synthesize cleanly.
# ---------------------------------------------------------------------------

_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
_TENS = (
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
)


def _int_to_words(n: int) -> str:
    """Render 0..9999 as English words. Outside that range, fall back to
    the digit string — the Concierge doesn't quote larger numbers in the
    demo path."""
    if n < 0:
        return f"minus {_int_to_words(-n)}"
    if n < 20:
        return _ONES[n]
    if n < 100:
        if n % 10 == 0:
            return _TENS[n // 10]
        return f"{_TENS[n // 10]}-{_ONES[n % 10]}"
    if n < 1000:
        head = f"{_ONES[n // 100]} hundred"
        rest = n % 100
        return head if rest == 0 else f"{head} {_int_to_words(rest)}"
    if n < 10000:
        head = f"{_ONES[n // 1000]} thousand"
        rest = n % 1000
        return head if rest == 0 else f"{head} {_int_to_words(rest)}"
    return str(n)


# $X.YY → "X dollars and YY cents" (or "X dollars" when YY == 0)
_MONEY_DECIMAL_RE = re.compile(r"\$\s*(\d+)\.(\d{2})\b")
# $X → "X dollars"
_MONEY_INTEGER_RE = re.compile(r"\$\s*(\d+)\b")


def _normalize_money(text: str) -> str:
    def _decimal(m: re.Match) -> str:
        dollars = int(m.group(1))
        cents = int(m.group(2))
        if cents == 0:
            return f"{_int_to_words(dollars)} dollars"
        return (
            f"{_int_to_words(dollars)} dollars and "
            f"{_int_to_words(cents)} cents"
        )

    text = _MONEY_DECIMAL_RE.sub(_decimal, text)
    text = _MONEY_INTEGER_RE.sub(
        lambda m: f"{_int_to_words(int(m.group(1)))} dollars", text,
    )
    return text


# "$99/month" → "$99 per month" (natural speech instead of literal "slash").
# Run before money normalization so the dollar regex still matches.
_PER_MONTH_RE = re.compile(r"/\s*month\b", re.IGNORECASE)


def normalize_for_speech(text: str) -> str:
    """Pre-synth cleanup. Currently: dollar amounts → words and
    "/month" → " per month". Extend here when other speak-as-words
    patterns surface."""
    text = _PER_MONTH_RE.sub(" per month", text)
    return _normalize_money(text)


def _convert(text: str) -> Iterator[bytes]:
    """Raw ElevenLabs streaming synth. Yields MP3 chunks as they arrive."""
    return _client().text_to_speech.convert(
        voice_id=os.environ["ELEVENLABS_VOICE_ID"],
        text=normalize_for_speech(text),
        model_id=_MODEL_ID,
        output_format=_OUTPUT_FORMAT,
    )


def _synthesize_bytes(text: str) -> bytes:
    """Buffer a full synth into bytes. Used only for static prompts we
    want to cache process-wide."""
    return b"".join(_convert(text))


# ---------------------------------------------------------------------------
# Dynamic replies — register text, stream synth on fetch
# ---------------------------------------------------------------------------

def queue_text(text: str) -> str:
    """Register reply text for streaming synth; return cid for the <Play> URL.

    Synthesis is deferred — it starts when Twilio actually fetches the
    /audio/{cid}.mp3 URL. This overlaps synth time with Twilio's fetch
    and playback, instead of making Twilio wait for a complete MP3.
    """
    cid = uuid.uuid4().hex
    with _LOCK:
        _prune(_TEXT_CACHE)
        _TEXT_CACHE[cid] = text
    log.info("tts queued %s (%d chars)", cid, len(text))
    return cid


def pop_text(cid: str) -> str | None:
    with _LOCK:
        return _TEXT_CACHE.pop(cid, None)


def stream_synth(text: str) -> Iterator[bytes]:
    """Iterator of MP3 chunks direct from ElevenLabs. For use inside a
    StreamingResponse."""
    return _convert(text)


# ---------------------------------------------------------------------------
# Static prompts — synthesize once, reuse forever
# ---------------------------------------------------------------------------

def synthesize_static(key: str, text: str) -> str:
    """Synthesize once per process, reuse forever. Caller passes a stable key."""
    with _LOCK:
        cached = _STATIC_CACHE.get(key)
    if cached is None:
        cached = _synthesize_bytes(text)
        with _LOCK:
            _STATIC_CACHE[key] = cached
        log.info("tts static-cached %s (%d bytes)", key, len(cached))
    cid = uuid.uuid4().hex
    with _LOCK:
        _prune(_CACHE)
        _CACHE[cid] = cached
    return cid


def pop_audio(cid: str) -> bytes | None:
    with _LOCK:
        return _CACHE.pop(cid, None)


def register_audio(audio: bytes) -> str:
    """Register pre-computed MP3 bytes for one-shot fetch via /audio/{cid}.mp3.

    Used by the chained-TwiML voice flow: the background turn synthesizes
    the full reply into a single MP3 blob, hands the bytes to this
    function, and embeds the returned cid in the <Play> URL it sends to
    Twilio. Twilio fetches once, plays the whole MP3 straight through —
    no mid-stream buffering ambiguity.
    """
    cid = uuid.uuid4().hex
    with _LOCK:
        _prune(_CACHE)
        _CACHE[cid] = audio
    log.info("tts registered bytes %s (%d bytes)", cid, len(audio))
    return cid
