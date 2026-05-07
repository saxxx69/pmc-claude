#!/usr/bin/env bash
# PMC bootstrap: ingest a project, generate the synthetic dataset, and append
# the PMC protocol to its CLAUDE.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${1:-}"

if [ -z "$PROJECT" ]; then
  echo "Usage: bootstrap.sh <project-path>" >&2
  exit 2
fi

if [ ! -d "$PROJECT" ]; then
  echo "[PMC] error: project path does not exist: $PROJECT" >&2
  exit 2
fi

PROJECT="$(cd "$PROJECT" && pwd)"
DB="${PMC_DB:-$PROJECT/.pmc/m.db}"
SCHEMA="${PMC_SCHEMA:-default}"
DATASET_DIR="${PMC_DATASET_DIR:-$PROJECT/.pmc/dataset}"
GEN="${PMC_GEN_PAIRS:-2000}"
VENV="${PMC_VENV:-$HOME/.pmc-venv}"

mkdir -p "$(dirname "$DB")" "$DATASET_DIR"

if [ -f "$VENV/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
fi

echo "[PMC] ingesting $PROJECT -> $DB"
pmc ingest "$PROJECT" --db "$DB" --schema "$SCHEMA"

echo "[PMC] generating $GEN synthetic (query, plan) pairs"
pmc bootstrap "$PROJECT" --db "$DB" --schema "$SCHEMA" --gen-dataset "$GEN" --out-dir "$DATASET_DIR"

echo "[PMC] appending CLAUDE.md addon"
ADDON="$HERE/templates/CLAUDE_MD_ADDON.md"
TARGET_MD="$PROJECT/CLAUDE.md"
if [ -f "$TARGET_MD" ]; then
  if ! grep -q "PMC Memory Protocol" "$TARGET_MD"; then
    printf "\n\n" >> "$TARGET_MD"
    cat "$ADDON" >> "$TARGET_MD"
    echo "[PMC] addon appended to $TARGET_MD"
  else
    echo "[PMC] addon already present in $TARGET_MD"
  fi
else
  cp "$ADDON" "$TARGET_MD"
  echo "[PMC] CLAUDE.md created with PMC addon"
fi

cat <<EOF

[PMC] bootstrap complete

Add to your shell so Claude Code picks up PMC:
  export PMC_DB=$DB
  export PMC_SCHEMA=$SCHEMA
EOF
