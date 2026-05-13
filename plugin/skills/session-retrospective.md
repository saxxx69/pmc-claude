---
name: session-retrospective
description: "Analyze the current session to find wasted steps (wrong files read first, failed attempts, repeated diagnostics, suboptimal tool choices) and apply fixes to memory files and settings.json — so similar future tasks go faster. Use after completing a non-trivial task. Never touches trading logic, backend code, or system execution files."
argument-hint: "[--dry-run]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

<objective>
Analyze the current session's tool call transcript to identify wasted steps, then:
- AUTO-APPLY: ingest findings into PMC via `pmc ingest` + settings.json permission additions + hookify rules
- PROPOSE ONLY (never auto-apply): CLAUDE.cslm changes
Output a structured report of findings and actions taken.
</objective>

<context>
Args: {{args}}
- No args or --apply: find + apply safe fixes (memory, settings), propose others
- --dry-run: find + report only, apply nothing
</context>

<hard-constraints>
NEVER touch:
- backend/ or frontend/ source code (any .py, .js, .ts that runs the trading system)
- MongoDB trading collections (positions, signals, proposals, trades)
- CLAUDE.cslm (propose changes only, never write)
- Any file related to trading logic, strategies, engines, risk, execution
- Scattered .md memory files (PMC-CSLM-ONLY rule)

ONLY write to:
- PMC graph via `pmc ingest <tmpfile>` (findings as DOC nodes)
- /opt/suite-ptb/.claude/settings.json (permissions.allow only)
- /opt/suite-ptb/.claude/hookify.*.local.md (hook rules only)
</hard-constraints>

<process>

## Step 1: Find current session transcript

```bash
ls -t /root/.claude_a/.claude/projects/-opt-suite-ptb/*.jsonl 2>/dev/null | head -1
```

## Step 2: Extract tool call sequence

Parse the jsonl chronologically. Extract all tool_use entries from assistant messages.
Record: turn_index, tool_name, key_input (command / file_path / first 80 chars of old_string).

```bash
python3 - <<'PYEOF'
import json, sys
path = open('/dev/stdin').readline().strip()  # pass from step 1
with open(path) as f:
    turn = 0
    for line in f:
        try:
            obj = json.loads(line)
            msg = obj.get('message', {})
            if msg.get('role') == 'assistant':
                for c in msg.get('content', []):
                    if c.get('type') == 'tool_use':
                        name = c['name']
                        inp = c.get('input', {})
                        key = (inp.get('command') or inp.get('file_path') or
                               str(inp.get('old_string',''))[:80] or str(inp)[:80])
                        print(f"{turn}\t{name}\t{key}")
                turn += 1
        except: pass
PYEOF
```

Also read the tool RESULTS to know if a call was useful (empty result = wasted call).

## Step 3: Detect inefficiency patterns

Apply these rules to the extracted sequence:

### W1 — Wrong file first
Read(fileA) → result empty/not-found → Read(fileB) had the answer.
Example: Read(open_positions) → empty → Read(v2_open_positions) → result found.
Fix: memory note "for X queries, go to fileB directly"

### W2 — API endpoint not found → openapi.json
Bash(curl .../api/X) → 404 → Bash(curl .../openapi.json).
Fix: memory note "check /api/openapi.json before calling unknown endpoints"
Also add: Bash(curl -s http://localhost:8001/openapi.json) to settings if not present.

### W3 — Edit without prior Read
Edit(file) without a Read(file) in the preceding ~5 turns.
Fix: memory note "always Read before Edit on this file"

### W4 — Repeated identical diagnostic
Same curl/bash command appears 3+ times. Wastes time confirming state that didn't change.
Fix: propose hook rule "diagnose once, then act"

### W5 — Shell venv activation overhead
`source /opt/suite-ptb/venv/bin/activate` repeated across separate Bash calls.
Fix: memory note "use /opt/suite-ptb/venv/bin/python3 directly instead of activating venv"
Add Bash(source /opt/suite-ptb/venv/bin/activate *) to settings if not present.

### W6 — MongoDB collection name trial-and-error
python3 db['collection_A'] → empty → db['collection_B'] → result.
Fix: memory note mapping "for X data → use collection_B" in feedback_mongodb.md

### W7 — System ID case mismatch (v2 vs V2 vs v2_prop)
curl .../V2/... → not found → curl .../v2/... → found. Or similar.
Fix: memory note "system IDs are lowercase: v2, v2_prop (not V2, V2PROP)"

## Step 4: Build findings list

For each detected pattern, create a finding:
```
TIPO: W1|W2|W3|W4|W5|W6|W7
DESCRIZIONE: what happened, turn numbers
STIMA TEMPO PERSO: low|medium|high
FIX: what to do differently
TARGET: memory|settings|cslm-proposal|hook-proposal|none
```

Filter out false positives:
- Read after Edit is intentional verification → skip W3
- Same diagnostic with different result → not W4
- Be conservative: if unsure, skip

## Step 5: Apply fixes (unless --dry-run)

### For memory fixes (TARGET=memory):

Write a temporary markdown file, ingest it into PMC, then delete it:

```bash
cat > /tmp/pmc_finding_<topic>.md << 'EOF'
# <descriptive title>

<rule statement>

**Why:** <what happened in session>

**How to apply:** <concrete action>
EOF
pmc ingest /tmp/pmc_finding_<topic>.md
rm /tmp/pmc_finding_<topic>.md
```

Do NOT write to ~/.claude_a/ memory files (PMC-CSLM-ONLY rule).

### For settings fixes (TARGET=settings):

Read /opt/suite-ptb/.claude/settings.json, add to permissions.allow:
- Only read-only bash patterns (curl GET, ps, supervisorctl status, etc.)
- No interpreter wildcards (no python3 *, no bash *, no source *)
- Deduplicate against existing entries

### For CLAUDE.cslm proposals (TARGET=cslm-proposal):

Print a clearly marked proposal block:
```
━━━ CSLM PROPOSAL (requires manual confirmation) ━━━
Node type: INVESTIGATION
Label: <label>
Content: <what to add>
Command to add: pmc ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
Do NOT write to CLAUDE.cslm.

### For hook proposals (TARGET=hook-proposal):

Print a clearly marked proposal:
```
━━━ HOOK PROPOSAL (requires /hookify to apply) ━━━
Behavior to prevent: <description>
Suggested rule: <rule text>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Step 6: Output final report

```markdown
## Session Retrospective — {{date}}

### Summary
- Inefficiencies found: N
- Memory fixes applied: X
- Settings fixes applied: Y
- Proposals pending confirmation: K

### Findings

#### [W1] Wrong file first — FIXED
Turn 3→5: Read(open_positions) empty → Read(v2_open_positions) found data.
→ Written to memory/feedback_mongodb.md: "for open positions, use v2_open_positions or v2prop_open_positions"

#### [W2] API discovery waste — FIXED
Turn 7→9: curl /api/system/V2/open-positions → 404 → checked openapi.json.
→ Written to memory/feedback_api.md

[...]

### Proposals (pending confirmation)
[CSLM and hook proposals here]
```

</process>
