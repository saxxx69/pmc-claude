## PMC Memory Protocol (MANDATORY for factual queries)

This project has PMC (Palace of Computational Memory) installed. PMC replaces
free generation from model weights with deterministic graph navigation over a
typed knowledge graph built from this codebase.

**Hard rule for any factual question about codebase, configuration, metrics,
or project state:**

1. Call `/pmc-query "<question>"` BEFORE writing any answer.
2. Use the returned text VERBATIM (or rephrased without adding facts) as the
   sole source for your response.
3. If the response contains `[UNKNOWN: ...]`, report UNKNOWN. Do NOT fall back
   to weight-based generation.
4. For complex multi-step questions, call `/pmc-plan "<question>"` first to
   inspect the plan, then `/pmc-query` to execute.

**You MAY answer directly from your training weights only for:**
- Generic tutorials about languages/frameworks
- Definitions of standard concepts not specific to this project
- Creative tasks unrelated to project state

**Environment:**
- `PMC_DB`: path to the SQLite memory file
- `PMC_SCHEMA`: schema name or path (default: `default`)

If `PMC_DB` is unset, PMC is not available — fall back to normal behavior and
inform the user that PMC is not configured.

**Maintenance:**
- After significant codebase changes, run `/pmc-ingest` to refresh the graph.
- Use `/pmc-stats` to inspect graph size and type coverage.
