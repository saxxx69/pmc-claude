from __future__ import annotations
import uuid
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


OpName = Literal[
    "SELECT_EXACT", "SELECT_APPROX", "SELECT_BY_ID", "SELECT_FRESH",
    "TRAVERSE", "EXPAND", "PATH_FIND", "SUBGRAPH",
    "INTERSECT", "UNION", "DIFFERENCE",
    "FILTER", "RANK", "SORT", "TOP_K",
    "COUNT", "AGGREGATE", "GROUP", "REDUCE",
    "ASSERT", "INFER", "CONTRADICT", "CHECK_COVERAGE",
    "GET_TYPE", "CHECK_TYPE", "GET_PROVENANCE", "IS_FRESH",
]


class Step(BaseModel):
    step_id: str
    op: OpName
    args: dict[str, Any] = Field(default_factory=dict)
    output_binding: str
    expected_type: str = ""
    on_empty: dict[str, Any] = Field(default_factory=lambda: {"policy": "HALT"})
    on_type_error: Literal["HALT", "CONTINUE"] = "HALT"
    constraints: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    label: str = ""


class Plan(BaseModel):
    plan_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    schema_version: str = "1.0"
    query: str
    intent: Literal["retrieval", "reasoning", "inference", "synthesis", "hybrid"] = "retrieval"
    decomposition: list[str] = Field(default_factory=list)
    steps: list[Step]
    execution: dict[str, Any] = Field(default_factory=lambda: {
        "mode": "sequential", "max_nodes_visited": 500, "timeout_ms": 10000
    })
    synthesis: dict[str, Any] = Field(default_factory=lambda: {
        "rule": "assert_only", "unknown_policy": "report_gap",
        "min_aggregate_confidence": 0.6,
    })
