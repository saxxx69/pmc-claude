# PMC — Palace of Computational Memory

> A graph-grounded, traceable memory layer for Claude. Replaces weight-based
> factual recall with deterministic navigation over a typed knowledge graph
> built from your codebase.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

---

## Why

LLMs answer factual questions about a project by sampling from training-data
patterns. For closed domains (your codebase, your configs, your metrics)
this produces hallucinations. **PMC fixes it by:**

1. Building a typed graph `m = (N, E, C, T, I, U, P)` from your project.
2. Producing an explicit **plan** `s` (a sequence of typed operations) for
   each query, instead of generating an answer directly.
3. Executing the plan deterministically — every output claim is traceable
   to a `NodeID → ContentID → ProvenanceRecord`.
4. Synthesizing the final response under a constraint: **only verified
   assertions can appear in the output**. No assertion → `[UNKNOWN]`.

The PMC error model:

> The system cannot hallucinate. It can only fail to navigate.

## Install

```bash
git clone https://github.com/saxxx69/pmc-claude.git
cd pmc-claude
bash install.sh
```

The installer creates a venv at `~/.pmc-venv`, installs the `pmc` CLI, and
symlinks the Claude Code plugin into `~/.claude/plugins/pmc-claude`.

## LLM backend (auto-detected)

PMC works out of the box if **any** of these is true on your machine:

1. The `claude` CLI is installed and signed in → uses your **Claude Code
   subscription** (no API key needed)
2. `ANTHROPIC_API_KEY` is exported → uses the Anthropic SDK directly
3. Neither → fully offline fallback (deterministic stub planner +
   assertion-list synthesis; useful for tests and CI)

In all three modes, the no-hallucination invariant holds: every output
claim traces back to a node in `m`.

## Bootstrap a project

```bash
bash bootstrap.sh /path/to/your/project
```

This ingests the entire project tree into a SQLite graph, generates the
synthetic Phase-0 dataset (2000 query/plan pairs by default), and appends
the PMC protocol to the project's `CLAUDE.md`.

After bootstrap, export:

```bash
export PMC_DB=/path/to/your/project/.pmc/m.db
export PMC_SCHEMA=default
```

The Claude Code session-start hook then activates PMC for every session in
that project.

## Query directly

```bash
pmc query "what does shadow_engine.py import?"
pmc plan  "what does shadow_engine.py import?"   # show plan only
pmc stats
```

## Architecture

| Layer | What it does |
|-------|--------------|
| `pmc.models` | Node, Edge, Content, Provenance, Uncertainty, Assertion |
| `pmc.storage` | SQLite backend + HNSW ANN index |
| `pmc.schema` | Type system T (loader + validator) |
| `pmc.operations` | All 24 ops: SELECT, TRAVERSE, EXPAND, INTERSECT, ASSERT, INFER, … |
| `pmc.planner` | Few-shot `P(s\|c, T)` planner that emits Plan JSON |
| `pmc.executor` | Deterministic step runner with type checks + tracer |
| `pmc.verifier` | 6-check validation (completeness, consistency, provenance, freshness, coverage, confidence) |
| `pmc.synthesis` | Assert-only synthesizer with invariant prompt template |
| `pmc.ingestion` | Filesystem connector → typed graph |
| `pmc.dataset` | Backward-traversal dataset generator (Phase 0/1) |
| `pmc.cli` | `pmc` command group |

## Phases

- **Phase 0** (cold start): Few-shot planner. Works the moment you install.
- **Phase 1** (warm start): Dataset accumulates from real usage; corrections
  feed back as gold pairs.
- **Phase 2** (trained planner): Fine-tuned planner replaces few-shot. Out
  of scope for v0.1.0 — see `docs/PHASE_GUIDE.md`.

## Documentation

- [QUICKSTART.md](docs/QUICKSTART.md)
- [SCHEMA_GUIDE.md](docs/SCHEMA_GUIDE.md)
- [OPERATIONS_REF.md](docs/OPERATIONS_REF.md)
- [PLUGIN_GUIDE.md](docs/PLUGIN_GUIDE.md)
- [PHASE_GUIDE.md](docs/PHASE_GUIDE.md)
- [DATASET_GUIDE.md](docs/DATASET_GUIDE.md)

## License

MIT. See [LICENSE](LICENSE).
