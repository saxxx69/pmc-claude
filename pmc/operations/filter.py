from __future__ import annotations
from typing import Callable, Any, Literal
from pmc.models import Node


def filter_pred(nodes: list[Node], predicate: Callable[[Node], bool]) -> list[Node]:
    return [n for n in nodes if predicate(n)]


def rank(nodes: list[Node], score_fn: Callable[[Node], float]) -> list[tuple[Node, float]]:
    scored = [(n, score_fn(n)) for n in nodes]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def sort_nodes(
    nodes: list[Node], key_fn: Callable[[Node], Any], order: Literal["asc", "desc"] = "asc"
) -> list[Node]:
    return sorted(nodes, key=key_fn, reverse=(order == "desc"))


def top_k(nodes: list[Node], k: int) -> list[Node]:
    return nodes[:k]
