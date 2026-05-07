# PMC Quickstart — From Zero to Grounded Answers in 5 Minutes

## 1. Install

```bash
git clone https://github.com/saxxx69/pmc-claude.git
cd pmc-claude
bash install.sh
```

What happens:
- Creates `~/.pmc-venv` (Python venv)
- Installs `pmc` CLI globally inside that venv
- Symlinks `plugin/` into `~/.claude/plugins/pmc-claude` (Claude Code plugin)

## 2. Bootstrap your project

```bash
bash bootstrap.sh /path/to/your/project
```

What happens:
- Walks the project tree
- Creates typed nodes (`CODE_FILE`, `FUNCTION`, `CONFIG`, `DOC`, ...)
- Creates edges (`IMPORTS`, `DEFINES`, ...)
- Generates 2000 synthetic `(query, plan)` pairs at `<project>/.pmc/dataset/`
- Appends the PMC protocol to `<project>/CLAUDE.md`

## 3. Activate

```bash
export PMC_DB=/path/to/your/project/.pmc/m.db
export PMC_SCHEMA=default
```

Add to your shell rc to make it persistent.

## 4. Use it

From a shell:
```bash
pmc query "what does main.py import?"
pmc plan  "what does main.py import?"   # show plan only
pmc stats
```

From Claude Code (after `export PMC_DB=...`):
- The session-start hook detects the DB and informs Claude
- Claude calls `/pmc-query` automatically for factual questions
- Output is grounded — every claim traces back to a source node

## 5. Verify it's working

```bash
pmc stats
```

Should show non-zero counts for `CODE_FILE`, `FUNCTION`, `DOC`, `CONFIG`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `pmc: command not found` | `source ~/.pmc-venv/bin/activate` |
| `[UNKNOWN: ...]` for everything | Run `pmc ingest <project>` first |
| HNSW errors | Falls back to brute-force; install `hnswlib` for speed |
| Embedder slow on first run | Downloads `all-MiniLM-L6-v2` (~80MB), cached after |
