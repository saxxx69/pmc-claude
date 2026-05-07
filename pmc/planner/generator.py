from __future__ import annotations
import json
import os
from typing import Optional

from pmc.planner.plan import Plan, Step
from pmc.planner.few_shot import build_prompt
from pmc.schema.types import Schema


class PlannerError(Exception):
    pass


def _call_claude(prompt: str, model: Optional[str] = None) -> str:
    """Call Claude API. Falls back to a deterministic stub plan when no
    ANTHROPIC_API_KEY is configured (offline/test mode)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _stub_plan(prompt)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model or os.environ.get("PMC_PLANNER_MODEL", "claude-sonnet-4-6"),
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text  # type: ignore[union-attr]
    except Exception as e:
        raise PlannerError(f"claude_api_failed: {e}") from e


def _stub_plan(prompt: str) -> str:
    """Offline fallback: extract the QUERY line from the prompt and produce
    a generic SELECT_APPROX → ASSERT plan."""
    query = ""
    for line in prompt.splitlines():
        if line.startswith("QUERY: "):
            query = line[len("QUERY: "):]
    p = Plan(
        query=query or "unknown",
        intent="retrieval",
        steps=[
            Step(step_id="s1", op="SELECT_APPROX",
                 args={"query": query or "unknown", "k": 5, "threshold": 0.4},
                 output_binding="$n", expected_type="(NodeID,score)[]",
                 on_empty={"policy": "CONTINUE"}),
            Step(step_id="s2", op="ASSERT",
                 args={"claim": query, "sources": "$n", "confidence_threshold": 0.5},
                 output_binding="$a", depends_on=["s1"]),
        ],
        synthesis={"rule": "assert_only", "inputs": ["$a"]},
    )
    return p.model_dump_json()


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # strip code fences
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    # find first { ... last }
    i = text.find("{")
    j = text.rfind("}")
    if i == -1 or j == -1 or j < i:
        raise PlannerError("no_json_object_in_response")
    return text[i:j + 1]


def generate_plan(query: str, schema: Schema) -> Plan:
    prompt = build_prompt(query, schema)
    raw = _call_claude(prompt)
    payload = _extract_json(raw)
    try:
        return Plan.model_validate_json(payload)
    except Exception as e:
        raise PlannerError(f"plan_parse_failed: {e}") from e
