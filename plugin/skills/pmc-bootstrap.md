---
name: pmc-bootstrap
description: One-shot bootstrap — ingests a project and generates the synthetic dataset (Phase 0 → Phase 1 transition).
---

```bash
TARGET="${ARGUMENTS:-$(pwd)}"
pmc bootstrap "$TARGET" --db "$PMC_DB" --gen-dataset 5000
```

Reports nodes/edges ingested + dataset splits (train/val/test) generated.
