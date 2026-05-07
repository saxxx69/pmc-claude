from __future__ import annotations
from typing import Callable, Any, Optional, Literal
from pmc.models import Node


AggFn = Literal["count", "avg", "max", "min", "sum"]


def count(nodes: list[Node]) -> int:
    return len(nodes)


def aggregate(nodes: list[Node], fn: AggFn, prop: Optional[str] = None) -> float:
    if fn == "count":
        return float(len(nodes))
    if not nodes:
        return 0.0
    if prop is None:
        raise ValueError(f"aggregate({fn}) requires a property name")
    vals: list[float] = []
    for n in nodes:
        v = n.properties.get(prop)
        if isinstance(v, (int, float)):
            vals.append(float(v))
    if not vals:
        return 0.0
    if fn == "sum":
        return sum(vals)
    if fn == "avg":
        return sum(vals) / len(vals)
    if fn == "max":
        return max(vals)
    if fn == "min":
        return min(vals)
    raise ValueError(f"unknown_agg_fn: {fn}")


def group_by(nodes: list[Node], key_fn: Callable[[Node], Any]) -> dict[Any, list[Node]]:
    out: dict[Any, list[Node]] = {}
    for n in nodes:
        k = key_fn(n)
        out.setdefault(k, []).append(n)
    return out


def reduce_best(nodes: list[Node]) -> Optional[Node]:
    """Pick highest-confidence non-deprecated node."""
    cand = [n for n in nodes if not n.deprecated]
    if not cand:
        return None
    return max(cand, key=lambda n: n.confidence)
