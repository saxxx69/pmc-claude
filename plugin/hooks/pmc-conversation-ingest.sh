#!/usr/bin/env bash
# PMC PostToolUse hook — conversation ingest
#
# Fires after every tool use. Detects when Claude has finished generating
# a response (tool_name == "unknown" / stop event) and ingests both the
# user prompt and the assistant reply as CONVERSATION_TURN nodes into PMC.
#
# Environment variables consumed:
#   PMC_DB           — path to the SQLite database (required)
#   PMC_SCHEMA       — schema name (default: "default")
#   PMC_VENV         — path to the Python venv containing pmc (optional)
#   CLAUDE_SESSION_ID — injected by Claude Code (stable per session)
#
# How it works:
#   1. Reads JSON from stdin (Claude Code hook payload).
#   2. Extracts tool_name, user_prompt, assistant_response.
#   3. Calls `pmc converse-ingest` with the two turns.
#   4. Runs in background (non-blocking) — zero latency added to Claude.
#
# The turn_index is derived from the current count of turns in the session
# (handled inside `pmc converse-ingest` itself — this script just passes
# the raw messages).

set -e

# ── guards ──────────────────────────────────────────────────────────────────
if [ -z "${PMC_DB:-}" ] || [ ! -f "$PMC_DB" ]; then
    exit 0
fi

if [ -n "${PMC_VENV:-}" ] && [ -f "$PMC_VENV/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$PMC_VENV/bin/activate"
fi

# ── parse hook payload ───────────────────────────────────────────────────────
input=$(cat)

tool_name=$(echo "$input" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('tool_name', ''))
except:
    print('')
" 2>/dev/null)

# Only fire on the stop/response event, not on intermediate tool calls
# (Write, Read, Bash etc. are handled by pmc-auto-ingest.sh separately).
# Claude Code emits tool_name="" or tool_name="__response__" at turn end.
if [ -n "$tool_name" ] && [ "$tool_name" != "__response__" ]; then
    exit 0
fi

user_prompt=$(echo "$input" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('user_prompt', ''))
except:
    print('')
" 2>/dev/null)

assistant_response=$(echo "$input" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('assistant_response', ''))
except:
    print('')
" 2>/dev/null)

# Nothing to ingest if both are empty
if [ -z "$user_prompt" ] && [ -z "$assistant_response" ]; then
    exit 0
fi

# ── ingest in background ─────────────────────────────────────────────────────
SESSION_ID="${CLAUDE_SESSION_ID:-unknown-session}"
PROJECT="${PMC_PROJECT:-}"

(
    pmc converse-ingest \
        --db "$PMC_DB" \
        --schema "${PMC_SCHEMA:-default}" \
        --session-id "$SESSION_ID" \
        --project "$PROJECT" \
        --user-text "$user_prompt" \
        --assistant-text "$assistant_response" \
        2>/dev/null
) &

exit 0
