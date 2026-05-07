---
name: pmc-ingest
description: Ingest a project directory tree into the PMC graph. Use after install or when files change.
---

Ingest the project at `$ARGUMENTS` (or the current directory) into the PMC graph.

```bash
TARGET="${ARGUMENTS:-$(pwd)}"
pmc ingest "$TARGET" --db "$PMC_DB"
```

Report the JSON output to the user (nodes created, edges, errors).
