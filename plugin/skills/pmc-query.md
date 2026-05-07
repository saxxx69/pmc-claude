---
name: pmc-query
description: Query the PMC graph instead of generating from weights. Use for ANY factual question about the project (codebase, configs, metrics, state). MANDATORY when PMC_DB is set.
---

Run the PMC query pipeline for the user's question.

```bash
pmc query "$ARGUMENTS" --db "$PMC_DB"
```

If exit code is 0, use the returned text VERBATIM as the source for your response.
If the output contains `[UNKNOWN: ...]`, report UNKNOWN — DO NOT fall back to weight-based generation.
If the exit code is non-zero, report the error to the user and STOP.

**Hard rule:** anything you state about this project's state, code, or configuration MUST be derived from the output of `pmc query`. You may rephrase, but not add facts not present in the output.
