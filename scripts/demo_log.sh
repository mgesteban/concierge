#!/usr/bin/env bash
# Demo-friendly tail of the voice/SMS server log.
#
# Strips out HTTP-access noise and the ElevenLabs request line every synth
# emits, then color-codes the events that matter on screen during a recording:
#
#   📞  inbound / call lifecycle
#   👂  caller utterance picked up by Twilio
#   🔎  governance-KB search via Supabase RPC
#   🛒  product-KB search via Supabase RPC (same RPC, jurisdiction='product')
#   ✅  verify_citation (anti-hallucination gate)
#   🚨  escalate_to_grace (Twilio SMS to Grace)
#   💬  the actual sentence we sent to ElevenLabs
#   🎧  full reply MP3 ready
#   👋  call ended
#
# Run in a terminal next to the phone. Looks great on camera if you record.
#
# Usage:  ./scripts/demo_log.sh           # tail live
#         ./scripts/demo_log.sh -n 200    # show last 200 matching lines first
LOG=${LOG:-/tmp/uvicorn.log}

# tput-style colors; degrade to no-op if stdout isn't a terminal.
if [ -t 1 ]; then
  C_DIM=$'\033[2m'
  C_RESET=$'\033[0m'
  C_GREEN=$'\033[1;32m'
  C_BLUE=$'\033[1;34m'
  C_YELLOW=$'\033[1;33m'
  C_RED=$'\033[1;31m'
  C_CYAN=$'\033[1;36m'
  C_MAGENTA=$'\033[1;35m'
  C_WHITE=$'\033[1;37m'
else
  C_DIM= C_RESET= C_GREEN= C_BLUE= C_YELLOW= C_RED= C_CYAN= C_MAGENTA= C_WHITE=
fi

format() {
  awk -v dim="$C_DIM" -v rst="$C_RESET" \
      -v green="$C_GREEN" -v blue="$C_BLUE" -v yellow="$C_YELLOW" \
      -v red="$C_RED" -v cyan="$C_CYAN" -v magenta="$C_MAGENTA" \
      -v white="$C_WHITE" '
    # ---- DROP NOISE ----------------------------------------------------
    /uvicorn\.access/                                        { next }
    /^INFO:[[:space:]]+[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/       { next }
    /api\.elevenlabs\.io/                                    { next }
    /Started server process|Application startup|Application shutdown/ { next }
    /Started reloader process|Finished server process/       { next }
    /Shutting down|WatchFiles detected/                      { next }
    /Waiting for application/                                { next }
    /GET \/health/                                           { next }

    # ---- SHRINK TIMESTAMP TO HH:MM:SS ----------------------------------
    {
      ts = ""
      if (match($0, /[0-9]{4}-[0-9]{2}-[0-9]{2} ([0-9]{2}:[0-9]{2}:[0-9]{2})/, a)) {
        ts = a[1]
        sub(/^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]+ /, "")
      }
    }

    # ---- HIGHLIGHTS ----------------------------------------------------
    /forgot call/ {
      sub(/.*forgot call /, "")
      printf "%s%s%s  %s👋  call ended%s  %s%s%s\n", dim, ts, rst, magenta, rst, dim, $0, rst
      next
    }

    # voice_pipeline lines carry most of the demo-visible state.
    /voice_pipeline: stream open/ {
      printf "%s%s%s  %s📞  turn started%s  %s\n", dim, ts, rst, blue, rst, $0
      next
    }
    /voice turn complete/ {
      printf "%s%s%s  %s🎧  reply ready%s  %s\n", dim, ts, rst, green, rst, $0
      next
    }
    /synth sentence:|synth trailing:/ {
      sub(/.*synth (sentence|trailing): /, "")
      printf "%s%s%s  %s💬 %s%s\n", dim, ts, rst, white, $0, rst
      next
    }

    # KB hits — match_governance_kb is shared between governance + product.
    /rpc\/match_governance_kb/ {
      printf "%s%s%s  %s🔎  KB search%s  %s\n", dim, ts, rst, cyan, rst, $0
      next
    }
    /search_product_kb|jurisdiction.*product/ {
      printf "%s%s%s  %s🛒  product KB%s  %s\n", dim, ts, rst, cyan, rst, $0
      next
    }

    # verify_citation gate (the anti-hallucination layer)
    /verify_citation/ {
      printf "%s%s%s  %s✅  verify_citation%s  %s\n", dim, ts, rst, yellow, rst, $0
      next
    }

    # escalation paging
    /escalate_to_grace/ {
      printf "%s%s%s  %s🚨  escalate%s  %s\n", dim, ts, rst, red, rst, $0
      next
    }

    # caller utterance arriving (Twilio gather request body — not in log
    # by default, but we leave a hook here in case we add it later)
    /SpeechResult=/ {
      sub(/.*SpeechResult=/, "")
      printf "%s%s%s  %s👂  caller said%s  %s\n", dim, ts, rst, blue, rst, $0
      next
    }

    # tts queued / cached / registered — interesting but quiet
    /tts registered bytes|tts static-cached|tts queued/ {
      printf "%s%s%s  %s🔊  %s%s\n", dim, ts, rst, dim, $0, rst
      next
    }

    # Anthropic Messages API hits — keep, useful for "is the model thinking"
    /api\.anthropic\.com\/v1\/messages/ {
      printf "%s%s%s  %s🧠  model call%s\n", dim, ts, rst, dim, rst
      next
    }

    # Anything left over — print dim so it doesn’t fight for attention.
    {
      printf "%s%s  %s%s\n", dim, ts ? ts " " : "", $0, rst
    }
  '
}

if [ "$1" = "-n" ] && [ -n "$2" ]; then
  tail -n "$2" "$LOG" | format
  exit 0
fi

# Live mode: stream forever.
tail -F "$LOG" | format
