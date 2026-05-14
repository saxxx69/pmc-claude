"""
pmc_writer.py — API per scrivere nodi PMC nel grafo PMC.
Usato da EDCS, SIS, ECL, ARC per persistere eventi e decisioni cognitive.
"""
from __future__ import annotations
import json
import uuid
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


class PMCWriter:
    """
    Scrive nodi e archi PMC nel database PMC.
    Thread-safe: ogni write apre/chiude la connessione.
    """

    def __init__(self, db_path: str):
        self.db = db_path

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _ensure_pmc_provenance(self, con: sqlite3.Connection) -> str:
        """Ritorna (o crea) il provenance record per nodi PMC."""
        row = con.execute(
            "SELECT id FROM provenance WHERE source_type='pmc_writer' LIMIT 1"
        ).fetchone()
        if row:
            return row[0]
        prov_id = _uid()
        con.execute(
            """INSERT INTO provenance
               (id, source_type, source_uri, extracted_by, extracted_at, trust_level)
               VALUES (?, 'pmc_writer', 'internal://pmc', 'pmc_writer.py', ?, 'high')""",
            (prov_id, _now())
        )
        return prov_id

    def _write_node(self, type_id: str, label: str, properties: dict) -> str:
        node_id = _uid()
        props_json = json.dumps(properties)
        now = _now()
        confidence = properties.get("arc_confidence",
                     properties.get("ecl_confidence", 1.0))
        with self._conn() as con:
            prov_id = self._ensure_pmc_provenance(con)
            con.execute(
                """INSERT INTO nodes
                   (id, type_id, label, properties, confidence, version,
                    created_at, updated_at, deprecated, provenance_id)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?, 0, ?)""",
                (node_id, type_id, label, props_json, confidence, now, now, prov_id)
            )
        return node_id

    def _write_edge(self, source: str, target: str, type_id: str,
                    weight: float = 1.0) -> None:
        with self._conn() as con:
            prov_id = self._ensure_pmc_provenance(con)
            con.execute(
                """INSERT INTO edges
                   (id, source, target, type_id, weight, confidence,
                    directional, version, deprecated, created_at, provenance_id)
                   VALUES (?, ?, ?, ?, ?, 1.0, 1, 1, 0, ?, ?)""",
                (_uid(), source, target, type_id, weight, _now(), prov_id)
            )

    # ── EDCS ─────────────────────────────────────────────────────────────────

    def log_event(self, event_type: str, source: str,
                  payload: Optional[dict] = None,
                  session_id: Optional[str] = None) -> str:
        props = {
            "event_type": event_type,
            "source": source,
            "session_id": session_id or "",
            "payload": json.dumps(payload or {}),
            "timestamp": _now(),
        }
        return self._write_node("EVENT_LOG", f"[EVENT] {event_type} from {source}", props)

    # ── SIS ──────────────────────────────────────────────────────────────────

    def interrupt_l1(self, trigger_metric: str, trigger_value: float,
                     threshold: float, action: str,
                     session_id: Optional[str] = None,
                     cause_event_id: Optional[str] = None) -> str:
        props = {
            "trigger_metric": trigger_metric,
            "trigger_value": trigger_value,
            "threshold": threshold,
            "action": action,
            "session_id": session_id or "",
            "timestamp": _now(),
            "resolved": False,
        }
        node_id = self._write_node(
            "INTERRUPT_L1",
            f"[L1] {trigger_metric}={trigger_value} → {action}",
            props
        )
        if cause_event_id:
            self._write_edge(node_id, cause_event_id, "INTERRUPT_OF")
        return node_id

    def interrupt_l2(self, pattern: str, salience_score: float,
                     action: str, session_id: Optional[str] = None,
                     cause_event_id: Optional[str] = None) -> str:
        props = {
            "pattern": pattern,
            "salience_score": salience_score,
            "action": action,
            "session_id": session_id or "",
            "timestamp": _now(),
        }
        node_id = self._write_node(
            "INTERRUPT_L2",
            f"[L2] {pattern} (salience={salience_score:.2f})",
            props
        )
        if cause_event_id:
            self._write_edge(node_id, cause_event_id, "INTERRUPT_OF")
        return node_id

    def interrupt_l3(self, monitor: str, observation: str, action: str,
                     arc_triggered: bool = False,
                     session_id: Optional[str] = None) -> str:
        props = {
            "monitor": monitor,
            "observation": observation,
            "action": action,
            "arc_triggered": arc_triggered,
            "session_id": session_id or "",
            "timestamp": _now(),
        }
        return self._write_node(
            "INTERRUPT_L3",
            f"[L3] {monitor} → {action}",
            props
        )

    # ── ARC ──────────────────────────────────────────────────────────────────

    def arc_challenge(self, target_node_id: str, challenge_type: str,
                      evidence: str, arc_confidence: float,
                      session_id: Optional[str] = None) -> str:
        props = {
            "target_node_id": target_node_id,
            "challenge_type": challenge_type,
            "evidence": evidence,
            "arc_confidence": arc_confidence,
            "session_id": session_id or "",
            "timestamp": _now(),
            "ecl_status": "pending",
        }
        node_id = self._write_node(
            "ARC_CHALLENGE",
            f"[ARC] {challenge_type} on {target_node_id[:8]}...",
            props
        )
        self._write_edge(node_id, target_node_id, "CHALLENGED_BY")
        return node_id

    def arc_revision(self, original_node_id: str, proposed_content: str,
                     revision_type: str, arc_confidence: float) -> str:
        props = {
            "original_node_id": original_node_id,
            "proposed_content": proposed_content,
            "revision_type": revision_type,
            "arc_confidence": arc_confidence,
            "status": "proposed",
            "timestamp": _now(),
        }
        node_id = self._write_node(
            "ARC_REVISION",
            f"[ARC_REV] {revision_type} {original_node_id[:8]}...",
            props
        )
        self._write_edge(node_id, original_node_id, "SUPERSEDES")
        return node_id

    # ── ECL ──────────────────────────────────────────────────────────────────

    def arbitration_outcome(self, outcome: str, challenger_id: str,
                            challenged_id: str, ecl_confidence: float,
                            reason: str, risk_score: float = 0.0,
                            session_id: Optional[str] = None,
                            reeval_after: Optional[str] = None) -> str:
        props = {
            "outcome": outcome,
            "challenger_id": challenger_id,
            "challenged_id": challenged_id,
            "ecl_confidence": ecl_confidence,
            "risk_score": risk_score,
            "reason": reason,
            "session_id": session_id or "",
            "timestamp": _now(),
            "reeval_after": reeval_after or "",
        }
        node_id = self._write_node(
            "ARBITRATION_OUTCOME",
            f"[ECL] {outcome.upper()} — {reason[:60]}",
            props
        )
        # Collega challenge → outcome
        self._write_edge(challenger_id, node_id, "RESOLVED_TO")
        return node_id

    def update_challenge_status(self, challenge_id: str, status: str) -> None:
        with self._conn() as con:
            row = con.execute(
                "SELECT properties FROM nodes WHERE id=?", (challenge_id,)
            ).fetchone()
            if row:
                props = json.loads(row[0])
                props["ecl_status"] = status
                con.execute(
                    "UPDATE nodes SET properties=?, updated_at=? WHERE id=?",
                    (json.dumps(props), _now(), challenge_id)
                )


def get_writer(db_path: Optional[str] = None) -> PMCWriter:
    """Factory — usa PMC_DB env var se db_path non specificato."""
    import os
    path = db_path or os.environ.get("PMC_DB", "")
    if not path or not Path(path).exists():
        raise RuntimeError(f"PMC_DB non trovato: {path!r}")
    return PMCWriter(path)
