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


def _convert(text: str) -> Iterator[bytes]:
    """Raw ElevenLabs streaming synth. Yields MP3 chunks as they arrive."""
    return _client().text_to_speech.convert(
        voice_id=os.environ["ELEVENLABS_VOICE_ID"],
        text=text,
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
