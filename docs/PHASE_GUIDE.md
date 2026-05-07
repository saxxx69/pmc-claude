# PMC Phase Guide

PMC ships in three phases. v0.1.0 covers Phase 0 and Phase 1 fully; Phase 2
is on the v0.2.0 roadmap.

## Phase 0 — Cold Start (works on install)

- Planner: few-shot prompting, no training
- Synthesizer: invariant prompt template + Claude API call
- Quality: ~60–70% plan correctness on simple/multi-hop queries
- Latency: ~1–3 s per query

What you need: any project, an `ANTHROPIC_API_KEY`, and ~5 minutes for
ingestion + bootstrap.

## Phase 1 — Warm Start (after some usage)

- Same architecture as Phase 0
- Plus: a growing dataset of `(query, plan)` pairs accumulated from real
  usage, stored under `<project>/.pmc/dataset/`
- Plus: corrections from `/pmc-plan` reviews when the user adjusts plans
- Quality: ~80% plan correctness on the kinds of queries seen in dataset

The dataset is generated automatically by the bootstrap step (synthetic
backward-traversal pairs). You graduate to Phase 1 once you have ~5000
real-usage pairs.

## Phase 2 — Trained Planner (v0.2.0+)

- Planner is fine-tuned on the accumulated dataset
- Quality: ~90–95% plan correctness
- Latency: shorter — no need for few-shot examples in every prompt

This requires a fine-tuning loop — out of scope for v0.1.0. The dataset
format produced by `pmc bootstrap` is already compatible with standard
fine-tuning pipelines.

## Coverage thresholds

| Threshold | What it means |
|-----------|---------------|
| ≥ 500 nodes | minimum for synthetic dataset to be diverse enough |
| ≥ 10 nodes per type | each TypeID has enough examples |
| ≥ 2 edges per node avg | graph is well-connected, not just a list |

`pmc stats` reports these. If you fall below, run `pmc ingest` again or
extend the schema with more types.
