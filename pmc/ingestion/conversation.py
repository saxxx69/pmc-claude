"""
pmc.ingestion.conversation
~~~~~~~~~~~~~~~~~~~~~~~~~~

Ingests conversation turns (user + assistant messages) into the PMC graph.

Each turn becomes a ``CONVERSATION_TURN`` node. Turns are:
- Linked chronologically via ``FOLLOWS`` edges (linked list).
- Grouped under a ``SESSION`` node via ``PART_OF`` edges.
- Cross-linked to relevant codebase nodes (CODE_FILE, FUNCTION, CONFIG, DOC)
  via ``REFERENCES`` edges, discovered through HNSW vector similarity.

This is what makes the context window effectively infinite: instead of
accumulating raw message text in the LLM context, each turn is stored in
the graph. A ``pmc query`` at the start of every new message retrieves only
the semantically relevant slice of conversation history (~500 tokens) rather
than replaying the full transcript.

Schema nodes produced
---------------------
- ``SESSION``           — one per session_id, upserted (idempotent)
- ``CONVERSATION_TURN`` — one per (session_id, turn_index, role)

Schema edges produced
---------------------
- ``PART_OF``    CONVERSATION_TURN → SESSION
- ``FOLLOWS``    CONVERSATION_TURN → previous CONVERSATION_TURN (if any)
- ``REFERENCES`` CONVERSATION_TURN → codebase node  (top-k vector hits)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from pmc.models import Node, Edge, ProvenanceRecord, SourceType, TrustLevel
from pmc.models.uncertainty import UncertaintyRecord
from pmc.storage.backend import StorageBackend
from pmc.storage.hnsw_index import HNSWIndex
from pmc.embeddings.embedder import Embedder


# ---------------------------------------------------------------------------
# Public input dataclass
# ---------------------------------------------------------------------------

@dataclass
class ConversationTurn:
    """
    A single message to ingest.

    Parameters
    ----------
    session_id:
        Stable identifier for the Claude Code session (e.g. the value of
        ``$CLAUDE_SESSION_ID`` injected by the hook).
    turn_index:
        0-based monotonically increasing index within the session.
    role:
        ``"user"`` or ``"assistant"``.
    text:
        Raw message content.
    timestamp:
        When the message was sent/received. Defaults to now.
    project:
        Optional project name stored on the SESSION node.
    """
    session_id: str
    turn_index: int
    role: str           # "user" | "assistant"
    text: str
    timestamp: Optional[datetime] = None
    project: str = ""


@dataclass
class ConversationIngestReport:
    session_node_id: uuid.UUID
    turn_node_id: uuid.UUID
    references_created: int = 0
    follows_created: int = 0
    session_created: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prov(uri: str, by: str = "pmc.ingestion.conversation.v0.1") -> ProvenanceRecord:
    return ProvenanceRecord(
        id=uuid.uuid4(),
        source_type=SourceType.HUMAN,
        source_uri=uri,
        extracted_by=by,
        extracted_at=_now(),
        trust_level=TrustLevel.TRUSTED,
    )


def _get_or_create_session(
    backend: StorageBackend,
    hnsw: HNSWIndex,
    embedder: Embedder,
    session_id: str,
    project: str,
) -> tuple[uuid.UUID, bool]:
    """
    Return (session_node_id, created).
    Upserts the SESSION node — safe to call on every turn.
    """
    existing = backend.find_by_property("SESSION", "session_id", session_id)
    if existing:
        return existing[0].id, False

    prov = _prov(f"pmc://session/{session_id}")
    backend.insert_provenance(prov)

    emb = embedder.encode(f"SESSION {session_id} {project}")
    node = Node(
        id=uuid.uuid4(),
        type_id="SESSION",
        label=session_id,
        embedding=emb,
        properties={"session_id": session_id, "project": project, "started_at": _now().isoformat()},
        confidence=1.0,
        created_at=_now(), updated_at=_now(),
        provenance_id=prov.id,
    )
    backend.insert_node(node)
    backend.upsert_uncertainty(UncertaintyRecord(
        node_id=node.id, confidence=1.0, coverage=1.0,
        freshness_score=1.0, last_verified=_now(),
    ))
    hnsw.add(node.id, emb)
    return node.id, True


def _find_previous_turn(
    backend: StorageBackend,
    session_id: str,
    current_index: int,
) -> Optional[uuid.UUID]:
    """
    Find the node_id of the turn at (current_index - 1) in this session.
    Returns None if this is the first turn.
    """
    if current_index == 0:
        return None
    rows = backend.conn.execute(  # type: ignore[attr-defined]
        "SELECT id FROM nodes "
        "WHERE type_id='CONVERSATION_TURN' "
        "AND json_extract(properties, '$.session_id')=? "
        "AND json_extract(properties, '$.turn_index')=? "
        "LIMIT 1",
        (session_id, current_index - 1),
    ).fetchone()
    return uuid.UUID(rows["id"]) if rows else None


def _discover_references(
    backend: StorageBackend,
    hnsw: HNSWIndex,
    embedder: Embedder,
    text: str,
    k: int = 5,
    threshold: float = 0.50,
    exclude_types: tuple = ("CONVERSATION_TURN", "SESSION", "INFERRED"),
) -> list[uuid.UUID]:
    """
    Find codebase nodes semantically relevant to *text* via HNSW.
    Excludes conversation nodes themselves to avoid self-referential loops.
    """
    vec = embedder.encode(text[:1000])  # cap to avoid slow encoding on long turns
    hits = hnsw.query(vec, k=k * 4)
    out: list[uuid.UUID] = []
    for nid, score in hits:
        if score < threshold:
            continue
        node = backend.get_node(nid)
        if node is None or node.deprecated:
            continue
        if node.type_id in exclude_types:
            continue
        out.append(nid)
        if len(out) >= k:
            break
    return out


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def ingest_turn(
    backend: StorageBackend,
    hnsw: HNSWIndex,
    embedder: Embedder,
    turn: ConversationTurn,
    references_k: int = 5,
    references_threshold: float = 0.50,
) -> ConversationIngestReport:
    """
    Ingest a single conversation turn into the PMC graph.

    Safe to call multiple times with the same turn (idempotent on
    session_id + turn_index + role via early-exit check).

    Parameters
    ----------
    backend, hnsw, embedder:
        Standard PMC infrastructure objects.
    turn:
        The message to ingest.
    references_k:
        How many codebase nodes to cross-link via REFERENCES.
    references_threshold:
        Minimum cosine similarity for a REFERENCES edge.
    """
    ts = turn.timestamp or _now()
    report = ConversationIngestReport(
        session_node_id=uuid.uuid4(),  # placeholder, set below
        turn_node_id=uuid.uuid4(),
    )

    # ---- 1. Upsert SESSION node ----------------------------------------
    session_nid, created = _get_or_create_session(
        backend, hnsw, embedder, turn.session_id, turn.project
    )
    report.session_node_id = session_nid
    report.session_created = created

    # ---- 2. Idempotency check ------------------------------------------
    # If a turn with this (session_id, turn_index, role) already exists, skip.
    existing_turn = backend.conn.execute(  # type: ignore[attr-defined]
        "SELECT id FROM nodes "
        "WHERE type_id='CONVERSATION_TURN' "
        "AND json_extract(properties, '$.session_id')=? "
        "AND json_extract(properties, '$.turn_index')=? "
        "AND json_extract(properties, '$.role')=? "
        "LIMIT 1",
        (turn.session_id, turn.turn_index, turn.role),
    ).fetchone()
    if existing_turn:
        report.turn_node_id = uuid.UUID(existing_turn["id"])
        return report

    # ---- 3. Create CONVERSATION_TURN node ------------------------------
    prov = _prov(f"pmc://turn/{turn.session_id}/{turn.turn_index}/{turn.role}")
    backend.insert_provenance(prov)

    # Embed: role + first 800 chars of text (enough semantic signal)
    emb_text = f"CONVERSATION_TURN {turn.role}: {turn.text[:800]}"
    emb = embedder.encode(emb_text)

    turn_node = Node(
        id=uuid.uuid4(),
        type_id="CONVERSATION_TURN",
        label=f"{turn.role}[{turn.turn_index}]@{turn.session_id[:8]}",
        embedding=emb,
        properties={
            "session_id":  turn.session_id,
            "turn_index":  turn.turn_index,
            "role":        turn.role,
            "text":        turn.text,
            "timestamp":   ts.isoformat(),
            "token_count": len(turn.text.split()),  # rough estimate
        },
        confidence=1.0,
        created_at=ts, updated_at=ts,
        provenance_id=prov.id,
    )
    backend.insert_node(turn_node)
    backend.upsert_uncertainty(UncertaintyRecord(
        node_id=turn_node.id, confidence=1.0, coverage=1.0,
        freshness_score=1.0, last_verified=_now(),
    ))
    hnsw.add(turn_node.id, emb)
    report.turn_node_id = turn_node.id

    # ---- 4. PART_OF edge → SESSION ------------------------------------
    ep = _prov(f"pmc://edge/part_of/{turn_node.id}")
    backend.insert_provenance(ep)
    backend.insert_edge(Edge(
        id=uuid.uuid4(),
        source=turn_node.id, target=session_nid,
        type_id="PART_OF", weight=1.0, confidence=1.0,
        provenance_id=ep.id, created_at=_now(),
    ))

    # ---- 5. FOLLOWS edge → previous turn ------------------------------
    prev_nid = _find_previous_turn(backend, turn.session_id, turn.turn_index)
    if prev_nid:
        fp = _prov(f"pmc://edge/follows/{turn_node.id}")
        backend.insert_provenance(fp)
        backend.insert_edge(Edge(
            id=uuid.uuid4(),
            source=turn_node.id, target=prev_nid,
            type_id="FOLLOWS", weight=1.0, confidence=1.0,
            provenance_id=fp.id, created_at=_now(),
        ))
        report.follows_created = 1

    # ---- 6. REFERENCES edges → codebase nodes -------------------------
    ref_nids = _discover_references(
        backend, hnsw, embedder, turn.text,
        k=references_k, threshold=references_threshold,
    )
    for ref_nid in ref_nids:
        rp = _prov(f"pmc://edge/references/{turn_node.id}/{ref_nid}")
        backend.insert_provenance(rp)
        backend.insert_edge(Edge(
            id=uuid.uuid4(),
            source=turn_node.id, target=ref_nid,
            type_id="REFERENCES", weight=0.8, confidence=0.8,
            provenance_id=rp.id, created_at=_now(),
        ))
        report.references_created += 1

    return report
