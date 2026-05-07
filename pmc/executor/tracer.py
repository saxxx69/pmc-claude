from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StepTrace:
    step_id: str
    op: str
    output_binding: str
    result_summary: str
    wall_time_ms: int
    error: Optional[str] = None


@dataclass
class Tracer:
    steps: list[StepTrace] = field(default_factory=list)
    total_wall_time_ms: int = 0

    def record(
        self, step_id: str, op: str, output_binding: str, value: Any,
        wall_time_ms: int, error: Optional[str] = None,
    ) -> None:
        summary = _summarize(value)
        self.steps.append(
            StepTrace(step_id=step_id, op=op, output_binding=output_binding,
                      result_summary=summary, wall_time_ms=wall_time_ms, error=error)
        )
        self.total_wall_time_ms += wall_time_ms

    def to_dict(self) -> dict:
        return {
            "total_wall_time_ms": self.total_wall_time_ms,
            "steps": [vars(s) for s in self.steps],
        }


def _summarize(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, list):
        return f"list(len={len(value)})"
    if isinstance(value, dict):
        return f"dict(keys={list(value.keys())[:3]})"
    s = repr(value)
    return s if len(s) < 120 else s[:117] + "..."
