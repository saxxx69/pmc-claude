from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, Union
from dataclasses import dataclass, field

from pmc.storage.backend import StorageBackend
from pmc.models import Assertion, Unknown


@dataclass
class CoverageReport:
    verdict: str  # COVERED | PARTIAL | SPARSE | UNKNOWN
    score: float
    matched_count: int
    confidence_avg: float
    gaps: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        return (f"verdict={self.verdict} score={self.score:.2f} "
                f"matched={self.matched_count} conf_avg={self.confidence_avg:.2f}")


@dataclass
class ContradictionReport:
    node_a: uuid.UUID
    node_b: uuid.UUID
    reason: str


def assert_claim(
    backend: StorageBackend,
    claim: str,
    source_node_ids: list[uuid.UUID],
    confidence_threshold: float = 0.7,
    plan_step_id: Optional[str] = None,
) -> Union[uuid.UUID, Unknown]:
    if not source_node_ids:
        return Unknown("no_sources")
    sources = [backend.get_node(i) for i in source_node_ids]
    if any(s is None for s in sources):
        return Unknown("source_missing")
    if any(s.deprecated for s in sources):  # type: ignore[union-attr]
        return Unknown("source_deprecated")
    agg = min(s.confidence for s in sources)  # type: ignore[union-attr]
    if agg < confidence_threshold:
        return Unknown(f"below_threshold: {agg:.2f}<{confidence_threshold:.2f}")
    aid = uuid.uuid4()
    a = Assertion(
        id=aid, claim=claim, source_node_ids=source_node_ids,
        confidence=agg, created_at=datetime.now(timezone.utc),
        plan_step_id=plan_step_id,
    )
    backend.insert_assertion(a)
    return aid


def contradict(backend: StorageBackend, node_a: uuid.UUID, node_b: uuid.UUID) -> Optional[ContradictionReport]:
    a = backend.get_node(node_a)
    b = backend.get_node(node_b)
    if not a or not b or a.type_id != b.type_id:
        return None
    # naive: same identifying property with different value
    keys = set(a.properties.keys()) & set(b.properties.keys())
    for k in keys:
        if a.properties[k] != b.properties[k]:
            return ContradictionReport(node_a, node_b, f"differ_on:{k}")
    return None


def check_coverage(
    backend: StorageBackend, hnsw, embedder, topic: str, k: int = 20, threshold: float = 0.3
) -> CoverageReport:
    from pmc.operations.retrieval import select_approx
    hits = select_approx(backend, hnsw, embedder, topic, k=k, threshold=threshold)
    if not hits:
        return CoverageReport(verdict="UNKNOWN", score=0.0, matched_count=0, confidence_avg=0.0,
                              gaps=[f"no_matches_above_threshold:{threshold}"])
    confs = [n.confidence for n, _ in hits]
    conf_avg = sum(confs) / len(confs)
    score = min(1.0, len(hits) / k) * conf_avg
    verdict = "COVERED" if score >= 0.7 else ("PARTIAL" if score >= 0.4 else "SPARSE")
    return CoverageReport(verdict=verdict, score=score, matched_count=len(hits),
                          confidence_avg=conf_avg)


def infer(backend: StorageBackend, schema, rule_id: str) -> list[tuple[uuid.UUID, float]]:
    """Forward-chain a single rule. Returns list of (target_node_id, confidence).

    For v0.1.0 the inference returns a synthetic "virtual" relation result
    without writing back to the graph. Callers consume the (node, conf) pairs
    as inferred facts.
    """
    rule = next((r for r in schema.inference_rules if r.get("rule_id") == rule_id), None)
    if rule is None:
        return []
    pat = rule["pattern"]
    if len(pat) != 2:
        return []  # only 2-step transitive patterns supported in v0.1
    rel1 = pat[0]["rel"]
    rel2 = pat[1]["rel"]
    out: list[tuple[uuid.UUID, float]] = []
    for a in backend.all_nodes():
        for e1 in backend.get_edges_out(a.id, rel1):
            for e2 in backend.get_edges_out(e1.target, rel2):
                conf = min(e1.confidence, e2.confidence) * 0.9
                out.append((e2.target, conf))
    return out
