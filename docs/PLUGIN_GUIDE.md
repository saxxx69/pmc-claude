# PMC Claude Code Plugin Guide

## What the plugin provides

| Skill | Slash command | Purpose |
|-------|---------------|---------|
| `pmc-query` | `/pmc-query <q>` | Run the full PMC pipeline; return grounded answer |
| `pmc-plan` | `/pmc-plan <q>` | Inspect the plan without executing |
| `pmc-ingest` | `/pmc-ingest [path]` | Refresh the graph from filesystem |
| `pmc-stats` | `/pmc-stats` | Show graph statistics |
| `pmc-bootstrap` | `/pmc-bootstrap [path]` | Ingest + dataset generation |
| `pmc-assert` | `/pmc-assert <claim>` | Manual assertion (advanced) |

Plus a SessionStart hook that injects PMC awareness into every session.

## Install location

`install.sh` symlinks `plugin/` to `$CLAUDE_PLUGINS_DIR/pmc-claude`
(default: `~/.claude/plugins/pmc-claude`).

Verify:
```bash
ls -l ~/.claude/plugins/pmc-claude/plugin.json
```

## Required environment

| Var | Purpose | Default |
|-----|---------|---------|
| `PMC_DB` | Path to the SQLite memory file | (none — required) |
| `PMC_SCHEMA` | Schema path or `default` | `default` |
| `PMC_VENV` | Path to the venv | `~/.pmc-venv` |
| `ANTHROPIC_API_KEY` | For real planner/synthesizer | (offline fallback if unset) |
| `PMC_PLANNER_MODEL` | Override planner model | `claude-sonnet-4-6` |
| `PMC_SYNTH_MODEL` | Override synthesizer model | `claude-sonnet-4-6` |
| `PMC_EMBED_MODEL` | Override embedding model | `all-MiniLM-L6-v2` |
| `PMC_EMBED_MODE=fallback` | Force hash embeddings (offline) | (off) |

## CLAUDE.md integration

`bootstrap.sh` appends `templates/CLAUDE_MD_ADDON.md` to your project's
`CLAUDE.md`. This is the rule that makes Claude actually use PMC for
factual questions — without it, Claude may fall back to weight-based
recall.

## Running without an API key

PMC has full offline fallbacks:
- **Planner**: deterministic stub plan (`SELECT_APPROX → ASSERT`)
- **Synthesizer**: returns formatted assertion list verbatim
- **Embedder**: SHA-256 based pseudo-embeddings (deterministic, not
  semantically meaningful — fine for tests, suboptimal for real use)

Set `ANTHROPIC_API_KEY` to enable Claude-powered planner + synthesizer.
