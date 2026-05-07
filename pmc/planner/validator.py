from __future__ import annotations
from dataclasses import dataclass, field

from pmc.planner.plan import Plan
from pmc.schema.types import Schema


VALID_OPS = {
    "SELECT_EXACT", "SELECT_APPROX", "SELECT_BY_ID", "SELECT_FRESH",
    "TRAVERSE", "EXPAND", "PATH_FIND", "SUBGRAPH",
    "INTERSECT", "UNION", "DIFFERENCE",
    "FILTER", "RANK", "SORT", "TOP_K",
    "COUNT", "AGGREGATE", "GROUP", "REDUCE",
    "ASSERT", "INFER", "CONTRADICT", "CHECK_COVERAGE",
    "GET_TYPE", "CHECK_TYPE", "GET_PROVENANCE", "IS_FRESH",
}


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_plan(plan: Plan, schema: Schema) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    bindings: set[str] = set()
    seen: set[str] = set()
    for step in plan.steps:
        if step.op not in VALID_OPS:
            errors.append(f"unknown_op:{step.op}@{step.step_id}")
            continue
        if step.step_id in seen:
            errors.append(f"duplicate_step_id:{step.step_id}")
        seen.add(step.step_id)
        if not step.output_binding.startswith("$"):
            errors.append(f"binding_must_start_with_$:{step.step_id}")
        for dep in step.depends_on:
            if dep not in seen and dep != step.step_id:
                # depends_on must reference an earlier step
                errors.append(f"forward_dependency:{step.step_id}->{dep}")
        # type-aware checks
        if step.op == "SELECT_EXACT":
            t = step.args.get("type")
            if t and t not in schema.types:
                errors.append(f"unknown_type_in_select:{t}@{step.step_id}")
        if step.op == "TRAVERSE":
            rel = step.args.get("rel")
            if not rel:
                errors.append(f"traverse_missing_rel:{step.step_id}")
        bindings.add(step.output_binding)

    # Plan must end with ASSERT bound to synthesis.inputs
    asserts = [s for s in plan.steps if s.op == "ASSERT"]
    if not asserts:
        errors.append("missing_terminal_assert")
    syn_inputs = plan.synthesis.get("inputs") or [a.output_binding for a in asserts]
    for inp in syn_inputs:
        if inp not in bindings:
            errors.append(f"synthesis_input_not_bound:{inp}")

    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)
