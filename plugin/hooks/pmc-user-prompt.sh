#!/usr/bin/env bash
# PMC UserPromptSubmit hook — graph pre-flight + conversation context
#
# Fires before Claude sees the user's message. Injects TWO blocks:
#
#   1. PMC graph answer (deterministic) — same as before
#   2. Conversation context (recent turns + semantically related past turns)
#      — this is what makes the context window effectively infinite.
#
# With both blocks, Claude enters each turn knowing:
#   - What the graph says about the current question (facts, code, config)
#   - What was discussed recently in this session
#   - What was discussed in past sessions on related topics
#
# All of this costs ~1-3k tokens per turn instead of accumulating the full
# transcript (which would overflow the 1M context window after ~20 turns
# of rich coding conversation).
#
# Environment variables:
#   PMC_DB            — path to SQLite db (required)
#   PMC_SCHEMA        — schema name (default: "default")
#   PMC_VENV          — Python venv path (optional)
#   CLAUDE_SESSION_ID — stable session identifier (injected by Claude Code)
#   PMC_RECENT_TURNS  — how many recent turns to inject (default: 6)
#   PMC_SEMANTIC_TURNS — how many past-session turns to inject (default: 4)

set -e

# ── guards ───────────────────────────────────────────────────────────────────
if [ -z "${PMC_DB:-}" ] || [ ! -f "$PMC_DB" ]; then
    exit 0
fi

if [ -n "${PMC_VENV:-}" ] && [ -f "$PMC_VENV/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$PMC_VENV/bin/activate"
fi

# ── parse user prompt ────────────────────────────────────────────────────────
input=$(cat)
user_prompt=$(echo "$input" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('user_prompt', ''))
except:
    print('')
" 2>/dev/null)

if [ -z "$user_prompt" ] || [ "${#user_prompt}" -lt 5 ]; then
    exit 0
fi

SESSION_ID="${CLAUDE_SESSION_ID:-unknown-session}"

# ── block 0: checkpoint recovery (post-auto-clear) ───────────────────────────
checkpoint_context=$(pmc checkpoint-context \
    --db "$PMC_DB" \
    --schema "${PMC_SCHEMA:-default}" \
    --max-age 120 \
    2>/dev/null || true)

# ── block 1: PMC graph pre-flight ────────────────────────────────────────────
graph_result=$(pmc query "$user_prompt" \
    --db "$PMC_DB" \
    --schema "${PMC_SCHEMA:-default}" \
    2>/dev/null)

# ── block 2: conversation context ────────────────────────────────────────────
conv_context=$(pmc conversation-context "$user_prompt" \
    --db "$PMC_DB" \
    --schema "${PMC_SCHEMA:-default}" \
    --session-id "$SESSION_ID" \
    --recent "${PMC_RECENT_TURNS:-6}" \
    --semantic "${PMC_SEMANTIC_TURNS:-4}" \
    2>/dev/null || true)

# ── emit system-reminder ─────────────────────────────────────────────────────
# Only emit if at least one block has content.
has_graph=false
has_conv=false

if [ -n "$graph_result" ] && ! echo "$graph_result" | grep -q '^\[UNKNOWN'; then
    has_graph=true
fi
if [ -n "$conv_context" ]; then
    has_conv=true
fi

has_checkpoint=false
if [ -n "$checkpoint_context" ]; then
    has_checkpoint=true
fi

if ! $has_graph && ! $has_conv && ! $has_checkpoint; then
    exit 0
fi

echo "<system-reminder>"

if $has_checkpoint; then
    echo "[PMC CHECKPOINT RESTORED — previous session context]"
    echo "$checkpoint_context"
    echo ""
fi

if $has_graph; then
    echo "[PMC pre-flight — graph answer]"
    echo "$graph_result"
    echo "Use this answer VERBATIM. Do NOT add facts not present above."
    echo ""
fi

if $has_conv; then
    echo "$conv_context"
    echo ""
fi

echo "</system-reminder>"
