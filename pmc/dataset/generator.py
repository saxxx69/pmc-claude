from __future__ import annotations
import random
import uuid
from typing import Optional

from pmc.storage.backend import StorageBackend
from pmc.planner.plan import Plan, Step


def _random_walk(backend: StorageBackend, max_hops: int = 3) -> list[uuid.UUID]:
    nodes = backend.all_nodes()
    if not nodes:
        return []
    start = random.choice(nodes)
    path: list[uuid.UUID] = [start.id]
    cur = start.id
    for _ in range(max_hops):
        edges = backend.get_edges_out(cur)
        if not edges:
            break
        e = random.choice(edges)
        cur = e.target
        path.append(cur)
    return path


def _query_from_path(backend: StorageBackend, path: list[uuid.UUID]) -> str:
    if not path:
        return "what is in m?"
    head = backend.get_node(path[0])
    tail = backend.get_node(path[-1])
    if head and tail and head.id != tail.id:
        return f"how is {head.label} related to {tail.label}?"
    return f"what is {head.label if head else 'the entity'}?"


def _path_to_plan(backend: StorageBackend, path: list[uuid.UUID]) -> Plan:
    head = backend.get_node(path[0])
    if head is None:
        raise ValueError("empty_path")
    steps: list[Step] = [
        Step(step_id="s1", op="SELECT_BY_ID",
             args={"id": str(head.id)},
             output_binding="$h", expected_type="Node"),
    ]
    if len(path) == 1:
        steps.append(Step(step_id="s2", op="ASSERT",
                          args={"claim": _query_from_path(backend, path),
                                "sources": "$h", "confidence_threshold": 0.6},
                          output_binding="$a", depends_on=["s1"]))
    else:
        cur_binding = "$h"
        for i in range(len(path) - 1):
            edges = backend.get_edges_out(path[i])
            rel = next((e.type_id for e in edges if e.target == path[i + 1]), None)
            if rel is None:
                continue
            sid = f"s{i + 2}"
            steps.append(Step(step_id=sid, op="TRAVERSE",
                              args={"node": cur_binding, "rel": rel, "direction": "out"},
                              output_binding=f"$n{i}", depends_on=[steps[-1].step_id]))
            cur_binding = f"$n{i}"
        steps.append(Step(step_id="sa", op="ASSERT",
                          args={"claim": _query_from_path(backend, path),
                                "sources": cur_binding, "confidence_threshold": 0.6},
                          output_binding="$a", depends_on=[steps[-1].step_id]))
    return Plan(query=_query_from_path(backend, path), steps=steps,
                synthesis={"rule": "assert_only", "inputs": ["$a"]})


def generate_pairs(backend: StorageBackend, n: int = 100,
                   seed: Optional[int] = None) -> list[tuple[str, Plan]]:
    if seed is not None:
        random.seed(seed)
    pairs: list[tuple[str, Plan]] = []
    attempts = 0
    while len(pairs) < n and attempts < n * 10:
        attempts += 1
        path = _random_walk(backend, max_hops=random.randint(1, 3))
        if not path:
            break
        try:
            plan = _path_to_plan(backend, path)
            pairs.append((plan.query, plan))
        except Exception:
            continue
    return pairs
