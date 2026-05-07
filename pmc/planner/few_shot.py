from __future__ import annotations
import json
from pmc.planner.plan import Plan, Step
from pmc.schema.types import Schema


# A small set of few-shot examples. Phase 0 planner relies on these.
FEW_SHOT_EXAMPLES: list[dict] = [
    {
        "query": "what is the path of shadow_engine?",
        "plan": Plan(
            query="what is the path of shadow_engine?",
            intent="retrieval",
            steps=[
                Step(step_id="s1", op="SELECT_APPROX",
                     args={"query": "shadow_engine", "type_filter": "CODE_FILE", "k": 1, "threshold": 0.35},
                     output_binding="$n", expected_type="(NodeID,score)[]"),
                Step(step_id="s2", op="ASSERT",
                     args={"claim": "shadow_engine path", "sources": "$n", "confidence_threshold": 0.7},
                     output_binding="$a", depends_on=["s1"]),
            ],
            synthesis={"rule": "assert_only", "inputs": ["$a"]},
        ).model_dump(mode="json"),
    },
    {
        "query": "which functions are defined in shadow_engine?",
        "plan": Plan(
            query="which functions are defined in shadow_engine?",
            intent="retrieval",
            steps=[
                Step(step_id="s1", op="SELECT_APPROX",
                     args={"query": "shadow_engine", "type_filter": "CODE_FILE", "k": 1, "threshold": 0.35},
                     output_binding="$f", expected_type="(NodeID,score)[]"),
                Step(step_id="s2", op="TRAVERSE",
                     args={"node": "$f", "rel": "DEFINES", "direction": "out"},
                     output_binding="$funcs", depends_on=["s1"]),
                Step(step_id="s3", op="ASSERT",
                     args={"claim": "functions in shadow_engine", "sources": "$funcs", "confidence_threshold": 0.6},
                     output_binding="$a", depends_on=["s2"]),
            ],
            synthesis={"rule": "assert_only", "inputs": ["$a"]},
        ).model_dump(mode="json"),
    },
    {
        "query": "is there a config governing risk thresholds?",
        "plan": Plan(
            query="is there a config governing risk thresholds?",
            intent="retrieval",
            steps=[
                Step(step_id="s1", op="SELECT_APPROX",
                     args={"query": "risk threshold config", "type_filter": "CONFIG", "k": 5, "threshold": 0.35},
                     output_binding="$c", expected_type="(NodeID,score)[]",
                     on_empty={"policy": "HALT"}),
                Step(step_id="s2", op="ASSERT",
                     args={"claim": "risk threshold configs", "sources": "$c", "confidence_threshold": 0.6},
                     output_binding="$a", depends_on=["s1"]),
            ],
            synthesis={"rule": "assert_only", "inputs": ["$a"]},
        ).model_dump(mode="json"),
    },
]


def build_prompt(query: str, schema: Schema, examples_n: int = 3) -> str:
    schema_compact = {
        "types": {
            t: {
                "properties": list(td.properties.keys()),
                "relations": {r: rd.target_type for r, rd in td.relations_out.items()},
            }
            for t, td in schema.types.items()
        }
    }
    examples_txt = "\n\n".join(
        f"QUERY: {ex['query']}\nPLAN:\n{json.dumps(ex['plan'], indent=2, default=str)}"
        for ex in FEW_SHOT_EXAMPLES[:examples_n]
    )
    return f"""You are the PMC planner. Produce a JSON Plan that answers the QUERY using ONLY operations from the catalog.

SCHEMA (compact):
{json.dumps(schema_compact, indent=2)}

OPERATIONS CATALOG:
SELECT_EXACT(type, property, value) | SELECT_APPROX(query, type_filter, k, threshold) | SELECT_BY_ID(id) | SELECT_FRESH(type, property, value, max_age)
TRAVERSE(node, rel, direction in[out,in,both]) | EXPAND(nodes, rel_types, max_hops, direction) | PATH_FIND(source, target, rel_types) | SUBGRAPH(root, depth, rel_types)
INTERSECT(a, b) | UNION(a, b) | DIFFERENCE(a, b)
FILTER(input, condition) | RANK(input, score_fn) | SORT(input, key, order) | TOP_K(input, k)
COUNT(input) | AGGREGATE(input, fn, prop) | GROUP(input, key) | REDUCE(input)
ASSERT(claim, sources, confidence_threshold) | INFER(rule_id) | CONTRADICT(a, b) | CHECK_COVERAGE(topic)

RULES:
- Each Step has: step_id, op, args, output_binding starting with "$", expected_type, depends_on.
- Reference outputs of previous steps via $bindings in args.
- Always end with at least one ASSERT step. The final synthesis.inputs MUST list the ASSERT bindings.
- If the query cannot be answered from the schema, output a Plan whose final step is ASSERT with an empty source list (it will return UNKNOWN).
- Output ONLY a single valid JSON object matching the Plan schema. No prose, no markdown.

EXAMPLES:
{examples_txt}

QUERY: {query}
PLAN:"""
