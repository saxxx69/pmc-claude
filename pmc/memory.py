from __future__ import annotations
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from pmc.storage.sqlite import SQLiteBackend
from pmc.storage.hnsw_index import HNSWIndex
from pmc.embeddings.embedder import Embedder
from pmc.schema.loader import load_schema
from pmc.schema.types import Schema
from pmc.planner.generator import generate_plan
from pmc.planner.validator import validate_plan
from pmc.executor.runner import Executor, ExecutionResult
from pmc.verifier.checker import verify, VerificationReport
from pmc.synthesis.synthesizer import synthesize
from pmc.operations.reasoning import (
    assert_claim, check_coverage, CoverageReport,
)
from pmc.ingestion.pipeline import ingest_filesystem, IngestReport


@dataclass
class QueryResult:
    status: str
    text: str
    plan_id: Optional[uuid.UUID] = None
    assertions: list[uuid.UUID] = field(default_factory=list)
    verification: Optional[VerificationReport] = None
    coverage: Optional[CoverageReport] = None
    trace: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class PMCMemory:
    def __init__(self, db_path: str, schema: Schema):
        self.db_path = db_path
        self.backend = SQLiteBackend(db_path)
        self.backend.init_schema()
        self.schema = schema
        self.embedder = Embedder()
        self.hnsw = HNSWIndex(
            dim=self.embedder.dim,
            capacity=int(os.environ.get("PMC_HNSW_CAPACITY", "20000")),
            persist_path=os.path.join(os.path.dirname(db_path) or ".", "hnsw.bin"),
        )
        self._rehydrate_index()

    @classmethod
    def create(cls, db_path: str, schema: Union[str, Path] = "default") -> "PMCMemory":
        Path(os.path.dirname(db_path) or ".").mkdir(parents=True, exist_ok=True)
        s = load_schema(schema) if not isinstance(schema, Schema) else schema
        return cls(db_path, s)

    @classmethod
    def open(cls, db_path: str, schema: Union[str, Path] = "default") -> "PMCMemory":
        return cls.create(db_path, schema)

    def _rehydrate_index(self) -> None:
        for n in self.backend.all_nodes():
            if n.embedding:
                self.hnsw.add(n.id, n.embedding)

    # -------- ingestion --------
    def ingest(self, source: str, kind: str = "filesystem") -> IngestReport:
        if kind != "filesystem":
            raise NotImplementedError(f"unsupported_kind:{kind}")
        rep = ingest_filesystem(self.backend, self.hnsw, self.embedder, source)
        return rep

    # -------- query path --------
    def plan(self, query: str):
        p = generate_plan(query, self.schema)
        report = validate_plan(p, self.schema)
        return p, report

    def execute(self, plan) -> ExecutionResult:
        ex = Executor(self.backend, self.hnsw, self.embedder, self.schema)
        return ex.execute(plan)

    def query(self, c: str) -> QueryResult:
        try:
            plan, vrep = self.plan(c)
        except Exception as e:
            return QueryResult(status="FAILED", text=f"[UNKNOWN: planner_error: {e}]",
                               errors=[str(e)])
        if not vrep.ok:
            return QueryResult(status="FAILED",
                               text=f"[UNKNOWN: invalid_plan: {vrep.errors}]",
                               errors=vrep.errors)
        result = self.execute(plan)
        verification = verify(self.backend, result)
        coverage = check_coverage(self.backend, self.hnsw, self.embedder, c)
        text = synthesize(self.backend, c, result.assertions, coverage=coverage)
        return QueryResult(
            status=result.status, text=text,
            plan_id=plan.plan_id, assertions=result.assertions,
            verification=verification, coverage=coverage,
            trace=result.trace, errors=result.errors,
        )

    def assert_(self, claim: str, sources: list[uuid.UUID],
                confidence_threshold: float = 0.7):
        return assert_claim(self.backend, claim, sources, confidence_threshold)

    def check_coverage(self, topic: str) -> CoverageReport:
        return check_coverage(self.backend, self.hnsw, self.embedder, topic)

    def stats(self) -> dict:
        type_counts: dict[str, int] = {}
        for t in self.schema.types:
            type_counts[t] = self.backend.count_by_type(t)
        return {
            "db_path": self.db_path,
            "schema_id": self.schema.schema_id,
            "schema_version": self.schema.version,
            "node_counts_by_type": type_counts,
            "total_nodes": sum(type_counts.values()),
        }

    def close(self) -> None:
        try:
            self.hnsw.save()
        except Exception:
            pass
        self.backend.close()
