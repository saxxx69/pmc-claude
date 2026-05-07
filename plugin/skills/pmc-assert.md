---
name: pmc-assert
description: Manually create a grounded assertion in PMC. Source node IDs must be provided.
---

```bash
pmc assert "$CLAIM" --sources "$SOURCE_IDS" --db "$PMC_DB"
```

Use only when you have explicit, verified source node IDs. Otherwise prefer `pmc query`, which produces assertions automatically.
