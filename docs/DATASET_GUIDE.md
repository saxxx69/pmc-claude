# PMC Dataset Guide

PMC v0.1.0 generates `(query, plan)` training pairs from `m` itself, via
backward traversal. No human annotation is required for Phase 0/1.

## Format

Each pair is a JSON line:

```json
{
  "query": "how is main.py related to utils.py?",
  "plan": {
    "plan_id": "...",
    "steps": [
      {"step_id": "s1", "op": "SELECT_BY_ID", "args": {"id": "..."}, "output_binding": "$h"},
      {"step_id": "s2", "op": "TRAVERSE", "args": {"node": "$h", "rel": "IMPORTS"}, "output_binding": "$n0"},
      {"step_id": "sa", "op": "ASSERT", "args": {"claim": "...", "sources": "$n0"}, "output_binding": "$a"}
    ],
    "synthesis": {"rule": "assert_only", "inputs": ["$a"]}
  }
}
```

## How it's generated

`pmc.dataset.generator`:
1. Pick a random node in `m`.
2. Walk 1–3 hops along outgoing edges.
3. Synthesize a natural-language query from the path's endpoints.
4. Convert the path into a Plan: `SELECT_BY_ID → TRAVERSE* → ASSERT`.
5. Validate the plan against the schema (discard if invalid).

## Splits

Default ratios: 70% train / 15% val / 15% test. Random shuffle with seed 42
for reproducibility.

```bash
pmc bootstrap /path/to/project --gen-dataset 5000
```

Produces `<project>/.pmc/dataset/{train,val,test}.jsonl`.

## What's missing for Phase 2

Real (c, s) pairs annotated by humans for:
- Negative queries (expected output: `[UNKNOWN]`)
- Aggregation queries
- Inference queries (multi-rule)
- Complex hybrid queries

The Phase 2 dataset will mix synthetic pairs (60%) with human-annotated
pairs from real usage (~30%) and adapted public datasets (~10%, from
WebQSP / Spider / HotpotQA after format conversion).

## Quality control

When using the dataset for fine-tuning:
- Filter to pairs where `validate_plan` returns `ok=True`
- Drop pairs where the executor errors at any step
- Stratify by `step_count` (1, 2, 3+) to ensure depth diversity
