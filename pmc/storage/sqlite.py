from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from pmc.models import (
    Node, Edge, Content, ProvenanceRecord, UncertaintyRecord, Assertion,
    SourceType, TrustLevel,
)
from pmc.storage.backend import StorageBackend


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _emb_to_blob(emb: list[float]) -> bytes:
    return np.asarray(emb, dtype=np.float32).tobytes() if emb else b""


def _blob_to_emb(b: Optional[bytes]) -> list[float]:
    if not b:
        return []
    return np.frombuffer(b, dtype=np.float32).tolist()


def _dt(s: Optional[str]) -> Optional[datetime]:
    if s is None:
        return None
    return datetime.fromisoformat(s)


class SQLiteBackend(StorageBackend):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self.conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS provenance (
              id TEXT PRIMARY KEY,
              source_type TEXT NOT NULL,
              source_uri TEXT NOT NULL,
              extracted_by TEXT NOT NULL,
              extracted_at TEXT NOT NULL,
              raw_content_id TEXT,
              pipeline_run_id TEXT,
              trust_level TEXT NOT NULL DEFAULT 'unverified'
            );

            CREATE TABLE IF NOT EXISTS contents (
              id TEXT PRIMARY KEY,
              format TEXT NOT NULL,
              data BLOB NOT NULL,
              hash TEXT NOT NULL,
              encoding TEXT NOT NULL DEFAULT 'utf-8',
              source_uri TEXT,
              extracted_at TEXT NOT NULL,
              chunks TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS nodes (
              id TEXT PRIMARY KEY,
              type_id TEXT NOT NULL,
              label TEXT NOT NULL,
              embedding BLOB,
              properties TEXT NOT NULL DEFAULT '{}',
              content_ref TEXT,
              confidence REAL NOT NULL DEFAULT 0.9,
              version INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              valid_until TEXT,
              deprecated INTEGER NOT NULL DEFAULT 0,
              provenance_id TEXT NOT NULL,
              FOREIGN KEY(provenance_id) REFERENCES provenance(id)
            );
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label);
            CREATE INDEX IF NOT EXISTS idx_nodes_dep ON nodes(deprecated);

            CREATE TABLE IF NOT EXISTS edges (
              id TEXT PRIMARY KEY,
              source TEXT NOT NULL,
              target TEXT NOT NULL,
              type_id TEXT NOT NULL,
              weight REAL NOT NULL DEFAULT 1.0,
              confidence REAL NOT NULL DEFAULT 0.9,
              directional INTEGER NOT NULL DEFAULT 1,
              version INTEGER NOT NULL DEFAULT 1,
              valid_until TEXT,
              deprecated INTEGER NOT NULL DEFAULT 0,
              provenance_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(source) REFERENCES nodes(id),
              FOREIGN KEY(target) REFERENCES nodes(id),
              FOREIGN KEY(provenance_id) REFERENCES provenance(id)
            );
            CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(source, type_id, deprecated);
            CREATE INDEX IF NOT EXISTS idx_edges_tgt ON edges(target, type_id, deprecated);

            CREATE TABLE IF NOT EXISTS uncertainty (
              node_id TEXT PRIMARY KEY,
              confidence REAL NOT NULL,
              coverage REAL NOT NULL,
              freshness_score REAL NOT NULL,
              contradiction_set TEXT NOT NULL DEFAULT '[]',
              last_verified TEXT NOT NULL,
              FOREIGN KEY(node_id) REFERENCES nodes(id)
            );

            CREATE TABLE IF NOT EXISTS assertions (
              id TEXT PRIMARY KEY,
              claim TEXT NOT NULL,
              source_node_ids TEXT NOT NULL,
              confidence REAL NOT NULL,
              created_at TEXT NOT NULL,
              plan_step_id TEXT
            );
            """
        )

    # -------- nodes --------
    def insert_node(self, node: Node) -> None:
        self.conn.execute(
            "INSERT INTO nodes(id,type_id,label,embedding,properties,content_ref,confidence,version,created_at,updated_at,valid_until,deprecated,provenance_id)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(node.id), node.type_id, node.label, _emb_to_blob(node.embedding),
                json.dumps(node.properties), str(node.content_ref) if node.content_ref else None,
                node.confidence, node.version,
                node.created_at.isoformat(), node.updated_at.isoformat(),
                node.valid_until.isoformat() if node.valid_until else None,
                int(node.deprecated), str(node.provenance_id),
            ),
        )

    def _row_to_node(self, r: sqlite3.Row) -> Node:
        return Node(
            id=uuid.UUID(r["id"]),
            type_id=r["type_id"], label=r["label"],
            embedding=_blob_to_emb(r["embedding"]),
            properties=json.loads(r["properties"]),
            content_ref=uuid.UUID(r["content_ref"]) if r["content_ref"] else None,
            confidence=r["confidence"], version=r["version"],
            created_at=_dt(r["created_at"]), updated_at=_dt(r["updated_at"]),
            valid_until=_dt(r["valid_until"]),
            deprecated=bool(r["deprecated"]),
            provenance_id=uuid.UUID(r["provenance_id"]),
        )

    def get_node(self, node_id: uuid.UUID) -> Optional[Node]:
        cur = self.conn.execute("SELECT * FROM nodes WHERE id=?", (str(node_id),))
        r = cur.fetchone()
        return self._row_to_node(r) if r else None

    def update_node(self, node: Node) -> None:
        node.version += 1
        node.updated_at = _now()
        self.conn.execute(
            "UPDATE nodes SET label=?,embedding=?,properties=?,content_ref=?,confidence=?,version=?,updated_at=?,valid_until=?,deprecated=? WHERE id=?",
            (
                node.label, _emb_to_blob(node.embedding), json.dumps(node.properties),
                str(node.content_ref) if node.content_ref else None,
                node.confidence, node.version, node.updated_at.isoformat(),
                node.valid_until.isoformat() if node.valid_until else None,
                int(node.deprecated), str(node.id),
            ),
        )

    def deprecate_node(self, node_id: uuid.UUID) -> None:
        self.conn.execute("UPDATE nodes SET deprecated=1, updated_at=? WHERE id=?",
                          (_now().isoformat(), str(node_id)))

    def find_by_property(self, type_id: str, prop: str, value: Any) -> list[Node]:
        # JSON1 extension is available in stdlib sqlite3 since 3.38
        cur = self.conn.execute(
            "SELECT * FROM nodes WHERE type_id=? AND deprecated=0 AND json_extract(properties, ?)=?",
            (type_id, f"$.{prop}", value),
        )
        return [self._row_to_node(r) for r in cur.fetchall()]

    def find_by_type(self, type_id: str, include_deprecated: bool = False) -> list[Node]:
        q = "SELECT * FROM nodes WHERE type_id=?"
        if not include_deprecated:
            q += " AND deprecated=0"
        cur = self.conn.execute(q, (type_id,))
        return [self._row_to_node(r) for r in cur.fetchall()]

    def all_nodes(self, include_deprecated: bool = False) -> list[Node]:
        q = "SELECT * FROM nodes"
        if not include_deprecated:
            q += " WHERE deprecated=0"
        cur = self.conn.execute(q)
        return [self._row_to_node(r) for r in cur.fetchall()]

    def count_by_type(self, type_id: str) -> int:
        cur = self.conn.execute("SELECT COUNT(*) AS c FROM nodes WHERE type_id=? AND deprecated=0", (type_id,))
        return int(cur.fetchone()["c"])

    # -------- edges --------
    def insert_edge(self, edge: Edge) -> None:
        self.conn.execute(
            "INSERT INTO edges(id,source,target,type_id,weight,confidence,directional,version,valid_until,deprecated,provenance_id,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(edge.id), str(edge.source), str(edge.target), edge.type_id,
                edge.weight, edge.confidence, int(edge.directional), edge.version,
                edge.valid_until.isoformat() if edge.valid_until else None,
                int(edge.deprecated), str(edge.provenance_id),
                edge.created_at.isoformat(),
            ),
        )

    def _row_to_edge(self, r: sqlite3.Row) -> Edge:
        return Edge(
            id=uuid.UUID(r["id"]),
            source=uuid.UUID(r["source"]), target=uuid.UUID(r["target"]),
            type_id=r["type_id"], weight=r["weight"], confidence=r["confidence"],
            directional=bool(r["directional"]), version=r["version"],
            valid_until=_dt(r["valid_until"]),
            deprecated=bool(r["deprecated"]),
            provenance_id=uuid.UUID(r["provenance_id"]),
            created_at=_dt(r["created_at"]),
        )

    def get_edges_out(self, node_id: uuid.UUID, rel_type: Optional[str] = None) -> list[Edge]:
        if rel_type:
            cur = self.conn.execute(
                "SELECT * FROM edges WHERE source=? AND type_id=? AND deprecated=0",
                (str(node_id), rel_type),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM edges WHERE source=? AND deprecated=0", (str(node_id),)
            )
        return [self._row_to_edge(r) for r in cur.fetchall()]

    def get_edges_in(self, node_id: uuid.UUID, rel_type: Optional[str] = None) -> list[Edge]:
        if rel_type:
            cur = self.conn.execute(
                "SELECT * FROM edges WHERE target=? AND type_id=? AND deprecated=0",
                (str(node_id), rel_type),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM edges WHERE target=? AND deprecated=0", (str(node_id),)
            )
        return [self._row_to_edge(r) for r in cur.fetchall()]

    # -------- content --------
    def insert_content(self, content: Content) -> None:
        self.conn.execute(
            "INSERT INTO contents(id,format,data,hash,encoding,source_uri,extracted_at,chunks) VALUES(?,?,?,?,?,?,?,?)",
            (
                str(content.id), content.format, content.data, content.hash,
                content.encoding, content.source_uri,
                content.extracted_at.isoformat(),
                json.dumps([str(c) for c in content.chunks]),
            ),
        )

    def get_content(self, content_id: uuid.UUID) -> Optional[Content]:
        cur = self.conn.execute("SELECT * FROM contents WHERE id=?", (str(content_id),))
        r = cur.fetchone()
        if not r:
            return None
        return Content(
            id=uuid.UUID(r["id"]),
            format=r["format"], data=r["data"], hash=r["hash"],
            encoding=r["encoding"], source_uri=r["source_uri"],
            extracted_at=_dt(r["extracted_at"]),
            chunks=[uuid.UUID(x) for x in json.loads(r["chunks"])],
        )

    # -------- provenance --------
    def insert_provenance(self, prov: ProvenanceRecord) -> None:
        self.conn.execute(
            "INSERT INTO provenance(id,source_type,source_uri,extracted_by,extracted_at,raw_content_id,pipeline_run_id,trust_level)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (
                str(prov.id), prov.source_type.value, prov.source_uri, prov.extracted_by,
                prov.extracted_at.isoformat(),
                str(prov.raw_content_id) if prov.raw_content_id else None,
                str(prov.pipeline_run_id) if prov.pipeline_run_id else None,
                prov.trust_level.value,
            ),
        )

    def get_provenance(self, prov_id: uuid.UUID) -> Optional[ProvenanceRecord]:
        cur = self.conn.execute("SELECT * FROM provenance WHERE id=?", (str(prov_id),))
        r = cur.fetchone()
        if not r:
            return None
        return ProvenanceRecord(
            id=uuid.UUID(r["id"]),
            source_type=SourceType(r["source_type"]),
            source_uri=r["source_uri"], extracted_by=r["extracted_by"],
            extracted_at=_dt(r["extracted_at"]),
            raw_content_id=uuid.UUID(r["raw_content_id"]) if r["raw_content_id"] else None,
            pipeline_run_id=uuid.UUID(r["pipeline_run_id"]) if r["pipeline_run_id"] else None,
            trust_level=TrustLevel(r["trust_level"]),
        )

    # -------- uncertainty --------
    def upsert_uncertainty(self, u: UncertaintyRecord) -> None:
        self.conn.execute(
            "INSERT INTO uncertainty(node_id,confidence,coverage,freshness_score,contradiction_set,last_verified)"
            " VALUES(?,?,?,?,?,?) ON CONFLICT(node_id) DO UPDATE SET"
            " confidence=excluded.confidence, coverage=excluded.coverage,"
            " freshness_score=excluded.freshness_score,"
            " contradiction_set=excluded.contradiction_set,"
            " last_verified=excluded.last_verified",
            (
                str(u.node_id), u.confidence, u.coverage, u.freshness_score,
                json.dumps([str(x) for x in u.contradiction_set]),
                u.last_verified.isoformat(),
            ),
        )

    def get_uncertainty(self, node_id: uuid.UUID) -> Optional[UncertaintyRecord]:
        cur = self.conn.execute("SELECT * FROM uncertainty WHERE node_id=?", (str(node_id),))
        r = cur.fetchone()
        if not r:
            return None
        return UncertaintyRecord(
            node_id=uuid.UUID(r["node_id"]),
            confidence=r["confidence"], coverage=r["coverage"],
            freshness_score=r["freshness_score"],
            contradiction_set=[uuid.UUID(x) for x in json.loads(r["contradiction_set"])],
            last_verified=_dt(r["last_verified"]),
        )

    # -------- assertions --------
    def insert_assertion(self, a: Assertion) -> None:
        self.conn.execute(
            "INSERT INTO assertions(id,claim,source_node_ids,confidence,created_at,plan_step_id) VALUES(?,?,?,?,?,?)",
            (
                str(a.id), a.claim, json.dumps([str(x) for x in a.source_node_ids]),
                a.confidence, a.created_at.isoformat(), a.plan_step_id,
            ),
        )

    def close(self) -> None:
        self.conn.close()
