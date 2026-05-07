#!/usr/bin/env bash
# PMC Claude Code SessionStart hook
# Injects PMC schema awareness into Claude's context at session start.
set -e

if [ -z "${PMC_DB:-}" ]; then
  exit 0
fi

if [ ! -f "$PMC_DB" ]; then
  exit 0
fi

cat <<EOF
<system-reminder>
PMC (Palace of Computational Memory) is active for this session.
Database: $PMC_DB
Schema: ${PMC_SCHEMA:-default}

For ANY factual question about this project's code, configuration, metrics,
or state, you MUST use the /pmc-query skill BEFORE generating an answer.
You may answer from your weights ONLY for: tutorials, generic concepts,
or creative tasks unrelated to project state.

Stats:
$(pmc stats --db "$PMC_DB" --schema-only 2>/dev/null || echo "(stats unavailable)")
</system-reminder>
EOF
