from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from pmc.storage.backend import StorageBackend
from pmc.storage.hnsw_index import HNSWIndex
from pmc.embeddings.embedder import Embedder
from pmc.models import Node


def select_exact(backend: StorageBackend, type_id: str, prop: str, value: Any) -> list[Node]:
    return backend.find_by_property(type_id, prop, value)


def select_by_id(backend: StorageBackend, nid: uuid.UUID) -> Optional[Node]:
    return backend.get_node(nid)


def select_approx(
    backend: StorageBackend,
    hnsw: HNSWIndex,
    embedder: Embedder,
    query: str,
    type_filter: Optional[str] = None,
    k: int = 10,
    threshold: float = 0.5,
) -> list[tuple[Node, float]]:
    vec = embedder.encode(query)
    hits = hnsw.query(vec, k=max(k * 3, k))  # over-fetch for filtering
    out: list[tuple[Node, float]] = []
    for nid, score in hits:
        if score < threshold:
            continue
        node = backend.get_node(nid)
        if node is None or node.deprecated:
            continue
        if type_filter and node.type_id != type_filter:
            continue
        out.append((node, score))
        if len(out) >= k:
            break
    return out


def select_fresh(
    backend: StorageBackend, type_id: str, prop: str, value: Any, max_age: timedelta
) -> list[Node]:
    nodes = backend.find_by_property(type_id, prop, value)
    now = datetime.now(timezone.utc)
    out: list[Node] = []
    for n in nodes:
        ts = n.updated_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if now - ts <= max_age:
            out.append(n)
    return out
