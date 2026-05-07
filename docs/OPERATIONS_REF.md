# PMC Operations Reference

All operations available in the planner DSL. Each Step's `op` field must be
one of these names. The executor dispatches via `pmc/executor/runner.py:_dispatch`.

## Retrieval

| Op | Args | Returns |
|----|------|---------|
| `SELECT_EXACT` | `type`, `property`, `value` | `Node[]` |
| `SELECT_APPROX` | `query`, `type_filter?`, `k`, `threshold` | `Node[]` |
| `SELECT_BY_ID` | `id` | `Node\|null` |
| `SELECT_FRESH` | `type`, `property`, `value`, `max_age_sec` | `Node[]` |

## Navigation

| Op | Args | Returns |
|----|------|---------|
| `TRAVERSE` | `node`, `rel`, `direction ∈ {out,in,both}` | `Node[]` |
| `EXPAND` | `nodes`, `rel_types?`, `max_hops`, `direction` | `Node[]` |
| `PATH_FIND` | `source`, `target`, `rel_types?` | `NodeID[][]` |
| `SUBGRAPH` | `root`, `depth`, `rel_types?` | `(Node[], Edge[])` |

## Sets

| Op | Args | Returns |
|----|------|---------|
| `INTERSECT` | `a`, `b` | `Node[]` |
| `UNION` | `a`, `b` | `Node[]` |
| `DIFFERENCE` | `a`, `b` | `Node[]` |

## Filter / Rank

| Op | Args | Returns |
|----|------|---------|
| `FILTER` | `input`, `condition` | `Node[]` |
| `TOP_K` | `input`, `k` | `Node[]` |

`condition` DSL: `<lhs> <op> <rhs>` where:
- `lhs ∈ {label, type_id, confidence, deprecated, properties.<key>}`
- `op ∈ {==, !=, <=, >=, <, >}`
- `rhs`: quoted string, number, or `true`/`false`

## Aggregation

| Op | Args | Returns |
|----|------|---------|
| `COUNT` | `input` | `int` |
| `AGGREGATE` | `input`, `fn ∈ {avg,max,min,sum}`, `prop` | `float` |
| `REDUCE` | `input` | `Node\|null` |

## Reasoning

| Op | Args | Returns |
|----|------|---------|
| `ASSERT` | `claim`, `sources`, `confidence_threshold` | `AssertionID \| Unknown` |
| `INFER` | `rule_id` | `(NodeID, conf)[]` |
| `CONTRADICT` | `a`, `b` | `ContradictionReport \| null` |
| `CHECK_COVERAGE` | `topic` | `CoverageReport` |

## Bindings

Step outputs use `output_binding` (must start with `$`). Reference earlier
outputs in `args` by writing the binding name as a string, e.g.:

```json
{"node": "$n_root", "rel": "DEFINES"}
```

The executor recursively resolves `$bindings` in `args` before dispatching.

## Type safety

The plan validator (`pmc.planner.validator.validate_plan`) checks:
- `op` is in catalog
- `step_id` unique, `output_binding` starts with `$`
- `depends_on` references earlier steps (no forward deps)
- `SELECT_EXACT.type` exists in schema
- `TRAVERSE.rel` is set
- Plan ends with at least one `ASSERT`
- `synthesis.inputs` resolve to bound outputs

## Error policies

Each Step has:
- `on_empty: {policy: HALT|CONTINUE|FALLBACK, fallback_step?}`
- `on_type_error: HALT|CONTINUE`
- `constraints: {require_fresh, max_age, min_confidence}`
