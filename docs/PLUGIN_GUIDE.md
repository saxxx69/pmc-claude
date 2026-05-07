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
| `ANTHROPIC_API_KEY` | API-key backend (paid via Anthropic API) | (optional) |
| `PMC_LLM_BACKEND` | Force backend: `claude-cli`, `anthropic`, `fallback` | (auto-detect) |
| `PMC_LLM_TIMEOUT_SEC` | Per-call timeout for `claude-cli` backend | `120` |
| `PMC_PLANNER_MODEL` | Override planner model | `claude-sonnet-4-6` |
| `PMC_SYNTH_MODEL` | Override synthesizer model | `claude-sonnet-4-6` |
| `PMC_EMBED_MODEL` | Override embedding model | `all-MiniLM-L6-v2` |
| `PMC_EMBED_MODE=fallback` | Force hash embeddings (offline) | (off) |

## LLM backend selection

PMC auto-detects the best available backend:

1. `PMC_LLM_BACKEND` if set (explicit override)
2. `anthropic` SDK if `ANTHROPIC_API_KEY` is exported
3. `claude-cli` if the `claude` binary is on PATH — **uses your Claude Code
   subscription, no API key needed**
4. `fallback` (deterministic stub plan + assertion-list synthesis)

This means: **if you have Claude Code installed and signed in, PMC works
out of the box** without any extra credentials. The planner and
synthesizer call `claude -p` as subprocesses, billed against your
subscription.

## CLAUDE.md integration

`bootstrap.sh` appends `templates/CLAUDE_MD_ADDON.md` to your project's
`CLAUDE.md`. This is the rule that makes Claude actually use PMC for
factual questions — without it, Claude may fall back to weight-based
recall.

## Running without an API key

If you have **Claude Code** installed and signed in, you get full quality
for free — PMC will detect the `claude` CLI and route planner +
synthesizer calls through your subscription.

If neither `claude` CLI nor `ANTHROPIC_API_KEY` is available, PMC falls
back to:
- **Planner**: deterministic stub plan (`SELECT_APPROX → ASSERT`)
- **Synthesizer**: returns formatted assertion list verbatim
- **Embedder**: SHA-256 based pseudo-embeddings (deterministic, not
  semantically meaningful — fine for tests, suboptimal for real use)

The hallucination-free invariant is preserved in every mode: even on
fallback, every output claim still traces back to a node in `m`.
