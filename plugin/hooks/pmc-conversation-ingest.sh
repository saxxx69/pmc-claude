#!/usr/bin/env bash
# PMC Stop hook — ingest last exchange + auto-clear trigger at 80% context
#
# Fires after every complete Claude response via the Stop event.
# 1. Ingests last user+assistant turn as CONVERSATION_TURN nodes.
# 2. Measures transcript JSONL size as proxy for context usage.
# 3. At 80% (TRANSCRIPT_LIMIT_BYTES), saves CHECKPOINT to PMC and
#    writes /tmp/pmc-restart-needed for pmc-session-monitor to act on.

set -e

if [ -z "${PMC_DB:-}" ] || [ ! -f "$PMC_DB" ]; then
    exit 0
fi

# ── Context threshold (bytes): 600KB ≈ 80% of 200k token context window ──────
TRANSCRIPT_LIMIT_BYTES="${PMC_TRANSCRIPT_LIMIT:-614400}"

input=$(cat)

session_id=$(echo "$input" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('session_id', 'unknown'))
except:
    print('unknown')
" 2>/dev/null)

assistant_text=$(echo "$input" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('last_assistant_message', ''))
except:
    print('')
" 2>/dev/null)

transcript_path=$(echo "$input" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('transcript_path', ''))
except:
    print('')
" 2>/dev/null)

# ── Extract last user message from JSONL transcript ───────────────────────────
user_text=""
if [ -f "$transcript_path" ]; then
    user_text=$(python3 << PYEOF
import json, sys

path = "$transcript_path"
entries = []
with open(path) as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass

for e in reversed(entries):
    if e.get('type') != 'user':
        continue
    msg = e.get('message', {})
    if isinstance(msg, str):
        try:
            msg = json.loads(msg)
        except Exception:
            continue
    if not isinstance(msg, dict):
        continue
    content = msg.get('content', '')
    if isinstance(content, list):
        parts = [c.get('text', '') for c in content if isinstance(c, dict) and c.get('type') == 'text']
        content = ' '.join(parts)
    content = str(content).strip()
    if content:
        print(content[:2000])
        break
PYEOF
    )
fi

# ── Ingest turn ───────────────────────────────────────────────────────────────
if [ -n "$assistant_text" ] || [ -n "$user_text" ]; then
    (
        pmc converse-ingest \
            --db "$PMC_DB" \
            --schema "${PMC_SCHEMA:-default}" \
            --session-id "$session_id" \
            --project "${PMC_PROJECT:-}" \
            --user-text "$user_text" \
            --assistant-text "$assistant_text" \
            2>/dev/null
    ) &
fi

# ── Context size check ────────────────────────────────────────────────────────
if [ ! -f "$transcript_path" ]; then
    exit 0
fi

transcript_size=$(stat -c%s "$transcript_path" 2>/dev/null || echo 0)

if [ "$transcript_size" -gt "$TRANSCRIPT_LIMIT_BYTES" ]; then
    # Save checkpoint (synchronous)
    pmc checkpoint \
        --db "$PMC_DB" \
        --schema "${PMC_SCHEMA:-default}" \
        --session-id "$session_id" \
        --project "${PMC_PROJECT:-}" \
        2>/dev/null || true

    # Cooldown: don't trigger twice in the same session
    COOLDOWN_FILE="/tmp/pmc-autoclear-${session_id}.lock"
    if [ -f "$COOLDOWN_FILE" ]; then
        exit 0
    fi
    touch "$COOLDOWN_FILE"

    # Find Claude Code's PTY — look for the `claude` binary (exact match), not node
    CLAUDE_PID=$(pgrep -x "claude" 2>/dev/null | grep -v $$ | head -1)

    if [ -n "$CLAUDE_PID" ]; then
        CLAUDE_PTY=$(readlink /proc/"$CLAUDE_PID"/fd/1 2>/dev/null || echo "")
        if [[ "$CLAUDE_PTY" == /dev/pts/* ]]; then
            sleep 1
            printf "/clear\n" > "$CLAUDE_PTY"
            sleep 3
            printf "[PMC AUTO-RESUME] Continua dalla sessione precedente — checkpoint caricato da PMC.\n" > "$CLAUDE_PTY"
        fi
    fi
fi

exit 0
