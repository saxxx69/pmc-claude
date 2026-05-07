# PMC Schema Guide

The schema `T` defines the type system for `m`. Without a schema, no
operation is type-safe.

## File format

JSON, validated by `pmc.schema.types.Schema`. See [`schema/default.json`](../schema/default.json).

```json
{
  "schema_id": "my-domain",
  "version": "1.0.0",
  "types": {
    "MY_TYPE": {
      "extends": "ENTITY",
      "properties": {
        "name": {"type": "string", "required": true},
        "value": {"type": "float"}
      },
      "relations_out": {
        "RELATES_TO": {"target_type": "MY_TYPE", "cardinality": "many"}
      },
      "freshness": {"half_life": "24h"}
    }
  },
  "inference_rules": [],
  "conflict_resolution_policy": {}
}
```

## Property types

| Type | Validation |
|------|-----------|
| `string` | any Python str |
| `int` / `float` | numeric |
| `bool` | true/false |
| `enum` | must be in `enum_values` |
| `timestamp` | ISO 8601 |
| `ref` | UUID pointing to another node |

## Inheritance

`extends` walks the chain on type checks. Use `ENTITY` as the abstract root
for nodes that should appear in generic searches.

## Adding a custom schema

1. Copy `schema/default.json` → `schema/my_domain.json`
2. Add types
3. Run with `pmc ingest <project> --schema schema/my_domain.json`
4. Set `PMC_SCHEMA=schema/my_domain.json` in your environment

## Inference rules

Two-step transitive patterns are supported in v0.1.0:

```json
{
  "rule_id": "transitive_imports",
  "pattern": [
    {"from": "A", "rel": "IMPORTS", "to": "B"},
    {"from": "B", "rel": "IMPORTS", "to": "C"}
  ],
  "conclusion": {"from": "A", "rel": "TRANSITIVELY_DEPENDS_ON", "to": "C"},
  "confidence_fn": "min(conf_edge1, conf_edge2) * 0.9"
}
```

More complex multi-step rules are out of scope for v0.1 and planned for v0.2.

## Schema migration

When `T` changes incompatibly (e.g., remove a type), bump `version` and run
re-ingestion. v0.1.0 has no in-place migration tool — re-ingestion is the
sanctioned path.
