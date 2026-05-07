from __future__ import annotations
from pmc.models import Node


def intersect_nodes(a: list[Node], b: list[Node]) -> list[Node]:
    bids = {n.id for n in b}
    return [n for n in a if n.id in bids]


def union_nodes(a: list[Node], b: list[Node]) -> list[Node]:
    seen: set = set()
    out: list[Node] = []
    for n in a + b:
        if n.id not in seen:
            seen.add(n.id)
            out.append(n)
    return out


def difference_nodes(a: list[Node], b: list[Node]) -> list[Node]:
    bids = {n.id for n in b}
    return [n for n in a if n.id not in bids]
