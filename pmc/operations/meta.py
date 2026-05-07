from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from pmc.storage.backend import StorageBackend
from pmc.models import ProvenanceRecord, UncertaintyRecord


def get_type(backend: StorageBackend, node_id: uuid.UUID) -> Optional[str]:
    n = backend.get_node(node_id)
    return n.type_id if n else None


def check_type(backend: StorageBackend, node_id: uuid.UUID, type_id: str) -> bool:
    return get_type(backend, node_id) == type_id


def get_provenance(backend: StorageBackend, node_id: uuid.UUID) -> Optional[ProvenanceRecord]:
    n = backend.get_node(node_id)
    if not n:
        return None
    return backend.get_provenance(n.provenance_id)


def get_confidence(backend: StorageBackend, node_id: uuid.UUID) -> Optional[UncertaintyRecord]:
    return backend.get_uncertainty(node_id)


def is_fresh(backend: StorageBackend, node_id: uuid.UUID, max_age: timedelta) -> bool:
    n = backend.get_node(node_id)
    if not n:
        return False
    ts = n.updated_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts) <= max_age


def is_deprecated(backend: StorageBackend, node_id: uuid.UUID) -> bool:
    n = backend.get_node(node_id)
    return bool(n and n.deprecated)


def get_contradictions(backend: StorageBackend, node_id: uuid.UUID) -> list[uuid.UUID]:
    u = backend.get_uncertainty(node_id)
    return list(u.contradiction_set) if u else []
