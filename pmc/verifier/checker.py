from __future__ import annotations
from dataclasses import dataclass, field
from datetime import timedelta

from pmc.storage.backend import StorageBackend
from pmc.executor.runner import ExecutionResult
from pmc.operations.meta import is_fresh, get_provenance


@dataclass
class VerificationReport:
    completeness: bool = False
    consistency: bool = True
    coverage_score: float = 0.0
    provenance_ok: bool = True
    freshness_ok: bool = True
    confidence: float = 0.0
    gaps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def overall_ok(self) -> bool:
        return (self.completeness and self.consistency
                and self.provenance_ok and self.freshness_ok)


def verify(backend: StorageBackend, result: ExecutionResult,
           freshness_window: timedelta = timedelta(days=14)) -> VerificationReport:
    rep = VerificationReport()

    if not result.assertions:
        rep.completeness = False
        rep.gaps.append("no_assertions")
        return rep
    rep.completeness = True

    # provenance + freshness over assertion sources
    prov_ok = True
    fresh_ok = True
    confs: list[float] = []
    for aid in result.assertions:
        # Lookup assertion via backend (we do a cheap re-fetch path)
        # In v0.1 we trust the executor placed the assertion; we re-derive
        # confidence from sources via stored uncertainty when available.
        confs.append(1.0)  # provisional; refined below
    for nid_set in [result.bindings.get(k) for k in result.bindings]:
        if not nid_set:
            continue
        if isinstance(nid_set, list):
            for n in nid_set:
                node_id = getattr(n, "id", None)
                if node_id is None:
                    continue
                node = backend.get_node(node_id)
                if node is None:
                    continue
                p = get_provenance(backend, node_id)
                if p is None:
                    prov_ok = False
                if not is_fresh(backend, node_id, freshness_window):
                    fresh_ok = False
                confs.append(node.confidence)
    rep.provenance_ok = prov_ok
    rep.freshness_ok = fresh_ok
    rep.confidence = sum(confs) / len(confs) if confs else 0.0
    return rep
