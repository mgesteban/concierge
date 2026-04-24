"""ElevenLabs TTS for the voice channel.

Day-one pattern: synthesize each reply to MP3, cache in-process keyed
by a short UUID, serve to Twilio via `<Play>/twilio/voice/audio/{cid}.mp3</Play>`.
Twilio fetches the URL over our ngrok tunnel and streams audio to the
caller. Cache entries are one-shot — popped on fetch.

Uses `eleven_flash_v2_5` for ~200ms time-to-first-byte; quality trade is
fine for voice-channel use and we can swap to v3 on Friday if we want.

Friday upgrade (per playbook §7.1): replace this with real-time
streaming via Twilio Media Streams — ElevenLabs emits audio chunks as
Claude generates tokens, Twilio plays them in-flight. Sub-second
perceived latency, no 15s webhook ceiling.
"""
from __future__ import annotations

import logging
import os
import uuid
from functools import lru_cache
from threading import Lock

from elevenlabs.client import ElevenLabs

log = logging.getLogger(__name__)

_CACHE: dict[str, bytes] = {}
_LOCK = Lock()

# Keep the cache bounded so a stuck synthesis doesn't pin memory forever.
_MAX_ENTRIES = 64

# Cheap static-greeting cache so the first "Hi this is BoardBreeze..."
# doesn't hit ElevenLabs on every call.
_STATIC_CACHE: dict[str, bytes] = {}


@lru_cache(maxsize=1)
def _client() -> ElevenLabs:
    return ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])


def _synthesize_bytes(text: str) -> bytes:
    """Call ElevenLabs and return full MP3 bytes."""
    chunks = _client().text_to_speech.convert(
        voice_id=os.environ["ELEVENLABS_VOICE_ID"],
        text=text,
        model_id="eleven_flash_v2_5",   # low-latency model
        output_format="mp3_22050_32",   # small + Twilio-compatible
    )
    return b"".join(chunks)


def synthesize(text: str) -> str:
    """Synthesize text, cache, return cache id for the Play URL."""
    audio = _synthesize_bytes(text)
    cid = uuid.uuid4().hex
    with _LOCK:
        if len(_CACHE) >= _MAX_ENTRIES:
            # Drop oldest half to avoid unbounded growth.
            for k in list(_CACHE)[: _MAX_ENTRIES // 2]:
                _CACHE.pop(k, None)
        _CACHE[cid] = audio
    log.info("tts cached %s (%d bytes, %d chars)", cid, len(audio), len(text))
    return cid


def synthesize_static(key: str, text: str) -> str:
    """Synthesize once per process, reuse forever. Caller passes a stable key."""
    with _LOCK:
        cached = _STATIC_CACHE.get(key)
    if cached is None:
        cached = _synthesize_bytes(text)
        with _LOCK:
            _STATIC_CACHE[key] = cached
        log.info("tts static-cached %s (%d bytes)", key, len(cached))
    # Register under a fresh one-shot id so our pop_audio flow still works.
    cid = uuid.uuid4().hex
    with _LOCK:
        _CACHE[cid] = cached
    return cid


def pop_audio(cid: str) -> bytes | None:
    with _LOCK:
        return _CACHE.pop(cid, None)
