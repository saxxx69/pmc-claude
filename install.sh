#!/usr/bin/env bash
# PMC install script. Creates a venv, installs pmc-claude, and links the
# Claude Code plugin if a plugins directory is detected.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
VENV="${PMC_VENV:-$HOME/.pmc-venv}"
PLUGIN_DIR="${CLAUDE_PLUGINS_DIR:-$HOME/.claude/plugins}"

echo "[PMC] python: $PYTHON"
echo "[PMC] venv:   $VENV"
echo "[PMC] plugins:$PLUGIN_DIR"

if [ ! -d "$VENV" ]; then
  echo "[PMC] creating venv"
  "$PYTHON" -m venv "$VENV"
fi

# shellcheck disable=SC1091
"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install -e "$HERE"

if [ ! -d "$PLUGIN_DIR" ]; then
  mkdir -p "$PLUGIN_DIR"
fi

LINK="$PLUGIN_DIR/pmc-claude"
if [ -L "$LINK" ] || [ -e "$LINK" ]; then
  rm -rf "$LINK"
fi
ln -s "$HERE/plugin" "$LINK"

# Install skill symlink into ~/.claude_a/skills (or CLAUDE_CONFIG_DIR/skills)
CLAUDE_CONFIG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SKILLS_DIR="$CLAUDE_CONFIG/skills/session-retrospective"
mkdir -p "$SKILLS_DIR"
cp "$HERE/plugin/skills/session-retrospective.md" "$SKILLS_DIR/SKILL.md"
echo "[PMC] skill installed: session-retrospective → $SKILLS_DIR/SKILL.md"

cat <<EOF

[PMC] install complete

Next steps:
  1) Activate the venv (or add it to your PATH):
       source $VENV/bin/activate
  2) Bootstrap a project:
       bash $HERE/bootstrap.sh /path/to/your/project
  3) Export PMC_DB in your shell so Claude Code picks up the database:
       export PMC_DB=/path/to/your/project/.pmc/m.db
EOF
