#!/usr/bin/env bash
# PMC Stop hook — ingest last exchange (user + assistant) into PMC graph
#
# Fires after every complete Claude response via the Stop event.
# Reads the Stop payload (session_id, last_assistant_message, transcript_path)
# and ingests the last user+assistant turn as CONVERSATION_TURN nodes.

set -e

if [ -z "${PMC_DB:-}" ] || [ ! -f "$PMC_DB" ]; then
    exit 0
fi

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

# Extract last user message from JSONL transcript
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

# Nothing to ingest
if [ -z "$assistant_text" ] && [ -z "$user_text" ]; then
    exit 0
fi

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

exit 0
