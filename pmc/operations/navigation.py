from __future__ import annotations
import uuid
from typing import Optional, Literal
from collections import deque

from pmc.storage.backend import StorageBackend
from pmc.models import Node, Edge

Direction = Literal["out", "in", "both"]


def _edges(backend: StorageBackend, nid: uuid.UUID, rel: Optional[str], direction: Direction) -> list[Edge]:
    if direction == "out":
        return backend.get_edges_out(nid, rel)
    if direction == "in":
        return backend.get_edges_in(nid, rel)
    return backend.get_edges_out(nid, rel) + backend.get_edges_in(nid, rel)


def _other_end(edge: Edge, nid: uuid.UUID) -> uuid.UUID:
    return edge.target if edge.source == nid else edge.source


def traverse(
    backend: StorageBackend, node_id: uuid.UUID, rel_type: str, direction: Direction = "out"
) -> list[Node]:
    edges = _edges(backend, node_id, rel_type, direction)
    out: list[Node] = []
    for e in edges:
        nxt = _other_end(e, node_id)
        n = backend.get_node(nxt)
        if n is not None and not n.deprecated:
            out.append(n)
    return out


def expand(
    backend: StorageBackend,
    node_ids: list[uuid.UUID],
    rel_types: Optional[list[str]],
    max_hops: int,
    direction: Direction = "out",
) -> list[Node]:
    visited: set[uuid.UUID] = set(node_ids)
    frontier: list[uuid.UUID] = list(node_ids)
    for _ in range(max_hops):
        next_frontier: list[uuid.UUID] = []
        for nid in frontier:
            rels = rel_types or [None]  # type: ignore[list-item]
            for rel in rels:
                for e in _edges(backend, nid, rel, direction):
                    other = _other_end(e, nid)
                    if other not in visited:
                        visited.add(other)
                        next_frontier.append(other)
        frontier = next_frontier
        if not frontier:
            break
    out: list[Node] = []
    for nid in visited:
        if nid in node_ids:
            continue
        n = backend.get_node(nid)
        if n is not None and not n.deprecated:
            out.append(n)
    return out


def path_find(
    backend: StorageBackend,
    source: uuid.UUID,
    target: uuid.UUID,
    rel_types: Optional[list[str]] = None,
    max_hops: int = 6,
) -> list[list[uuid.UUID]]:
    """BFS shortest-path enumeration. Returns up to a few shortest paths."""
    if source == target:
        return [[source]]
    rels = rel_types or [None]  # type: ignore[list-item]
    parents: dict[uuid.UUID, list[uuid.UUID]] = {source: []}
    queue: deque = deque([(source, 0)])
    visited: set[uuid.UUID] = {source}
    found_depth: Optional[int] = None
    while queue:
        nid, depth = queue.popleft()
        if found_depth is not None and depth > found_depth:
            break
        if depth >= max_hops:
            continue
        for rel in rels:
            for e in backend.get_edges_out(nid, rel):
                nxt = e.target
                if nxt == target:
                    parents.setdefault(nxt, []).append(nid)
                    found_depth = depth + 1
                    continue
                if nxt not in visited:
                    visited.add(nxt)
                    parents.setdefault(nxt, []).append(nid)
                    queue.append((nxt, depth + 1))
    if target not in parents:
        return []

    # reconstruct paths
    paths: list[list[uuid.UUID]] = []

    def _walk(node: uuid.UUID, acc: list[uuid.UUID]) -> None:
        if node == source:
            paths.append([source] + acc)
            return
        for p in parents.get(node, []):
            _walk(p, [node] + acc)

    _walk(target, [])
    return paths


def subgraph(
    backend: StorageBackend, root: uuid.UUID, depth: int, rel_types: Optional[list[str]] = None
) -> tuple[list[Node], list[Edge]]:
    visited: set[uuid.UUID] = {root}
    frontier: list[uuid.UUID] = [root]
    edges: list[Edge] = []
    rels = rel_types or [None]  # type: ignore[list-item]
    for _ in range(depth):
        nxt: list[uuid.UUID] = []
        for nid in frontier:
            for rel in rels:
                for e in backend.get_edges_out(nid, rel):
                    edges.append(e)
                    if e.target not in visited:
                        visited.add(e.target)
                        nxt.append(e.target)
        frontier = nxt
        if not frontier:
            break
    nodes = [backend.get_node(n) for n in visited]
    return [n for n in nodes if n is not None], edges
