"""
pmc.operations.semantic_linking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Auto-link a freshly inserted node to its nearest neighbours in the HNSW index.

Called after every ``hnsw.add()`` so new nodes are immediately wired into the
semantic graph.  Produces ``SIMILAR_TO`` edges (weight = cosine similarity).

Usage
-----
::

    n_edges = link_to_neighbors(
        node_id=node.id,
        embedding=emb,
        backend=backend,
        hnsw=hnsw,
        run_id=report.pipeline_run_id,
    )
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pmc.models import Edge, ProvenanceRecord, SourceType, TrustLevel
from pmc.storage.backend import StorageBackend
from pmc.storage.hnsw_index import HNSWIndex

REL_SIMILAR_TO = "SIMILAR_TO"

_DEFAULT_TOP_K = 5
_DEFAULT_THRESHOLD = 0.65


def _now() -> datetime:
    return datetime.now(timezone.utc)


def link_to_neighbors(
    node_id: uuid.UUID,
    embedding: list[float],
    backend: StorageBackend,
    hnsw: HNSWIndex,
    top_k: int = _DEFAULT_TOP_K,
    threshold: float = _DEFAULT_THRESHOLD,
    rel_type: str = REL_SIMILAR_TO,
    run_id: Optional[uuid.UUID] = None,
) -> int:
    """Query HNSW for top-k neighbours and insert directed similarity edges.

    Only creates edges when cosine similarity >= *threshold*.  Skips self-loops
    and edges that already exist (idempotent on re-ingest).

    Returns the number of new edges created.
    """
    hits = hnsw.query(embedding, k=top_k + 1)  # +1 to exclude self

    existing_targets = {e.target for e in backend.get_edges_out(node_id, rel_type)}

    created = 0
    effective_run_id = run_id or uuid.uuid4()

    for neighbor_id, score in hits:
        if neighbor_id == node_id:
            continue
        if score < threshold:
            continue
        if neighbor_id in existing_targets:
            continue

        prov = ProvenanceRecord(
            id=uuid.uuid4(),
            source_type=SourceType.INFERENCE,
            source_uri=f"semantic_linking:{node_id}",
            extracted_by="pmc.operations.semantic_linking",
            extracted_at=_now(),
            pipeline_run_id=effective_run_id,
            trust_level=TrustLevel.UNVERIFIED,
        )
        backend.insert_provenance(prov)
        backend.insert_edge(Edge(
            id=uuid.uuid4(),
            source=node_id,
            target=neighbor_id,
            type_id=rel_type,
            weight=round(score, 4),
            confidence=round(score, 4),
            provenance_id=prov.id,
            created_at=_now(),
        ))
        existing_targets.add(neighbor_id)
        created += 1

    return created
