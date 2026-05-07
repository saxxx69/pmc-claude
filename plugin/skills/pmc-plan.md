---
name: pmc-plan
description: Generate the PMC plan for a query WITHOUT executing it. Useful to inspect the planner's approach.
---

```bash
pmc plan "$ARGUMENTS" --db "$PMC_DB"
```

Show the JSON plan to the user. Do not interpret or summarize beyond what the plan literally says.
