"""
pmc.operations.conversation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Retrieval operations for conversation history stored in the PMC graph.

These functions are used by the UserPromptSubmit hook to inject relevant
conversation context into Claude's prompt — replacing the need to keep the
full transcript in the context window.

Two retrieval strategies
------------------------

1. ``recent_turns(session_id, n)``
   The last *n* turns from the current session, in chronological order.
   Always included — gives Claude immediate short-term continuity.

2. ``semantic_turns(query, session_id, k, threshold)``
   Top-k turns from *any* session whose embedding is similar to *query*.
   Gives Claude long-term memory across sessions.

Both are combined by ``get_context_for_prompt()``, which is the single
function called by the hook.

Output format
-------------
Plain text block ready to be injected as ``<system-reminder>`` content::

    [PMC conversation context]
    --- recent (this session) ---
    [turn 3 | user | 2026-05-08T10:12:00]
    Come posso ridurre il drawdown massimo?

    [turn 4 | assistant | 2026-05-08T10:12:05]
    Il parametro chiave è risk_per_trade in system_configs.py...

    --- semantically related (past sessions) ---
    [turn 7 | user | session:abc12345 | 2026-05-07T09:00:00]
    Qual è il valore attuale di risk_per_trade?
    ...
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from pmc.storage.backend import StorageBackend
from pmc.storage.hnsw_index import HNSWIndex
from pmc.embeddings.embedder import Embedder
from pmc.models import Node


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fmt_turn(node: Node, show_session: bool = False) -> str:
    """Render a CONVERSATION_TURN node as a compact text block."""
    props = node.properties
    header_parts = [
        f"turn {props.get('turn_index', '?')}",
        props.get("role", "?"),
        props.get("timestamp", "")[:19].replace("T", " "),
    ]
    if show_session:
        sid = props.get("session_id", "")[:8]
        header_parts.insert(2, f"session:{sid}")
    header = " | ".join(p for p in header_parts if p)
    text = props.get("text", "").strip()
    # Cap long turns to avoid blowing the injected context budget
    if len(text) > 600:
        text = text[:600] + "…"
    return f"[{header}]\n{text}"


def _fetch_turns_by_ids(
    backend: StorageBackend,
    node_ids: list[uuid.UUID],
) -> list[Node]:
    """Fetch and return Node objects, silently dropping missing ids."""
    out: list[Node] = []
    for nid in node_ids:
        n = backend.get_node(nid)
        if n and n.type_id == "CONVERSATION_TURN" and not n.deprecated:
            out.append(n)
    return out


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def recent_turns(
    backend: StorageBackend,
    session_id: str,
    n: int = 6,
) -> list[Node]:
    """
    Return the last *n* CONVERSATION_TURN nodes from *session_id*,
    ordered from oldest to newest (chronological).
    """
    rows = backend.conn.execute(  # type: ignore[attr-defined]
        "SELECT id FROM nodes "
        "WHERE type_id='CONVERSATION_TURN' "
        "AND json_extract(properties, '$.session_id')=? "
        "AND (deprecated IS NULL OR deprecated=0) "
        "ORDER BY json_extract(properties, '$.turn_index') DESC "
        "LIMIT ?",
        (session_id, n),
    ).fetchall()
    if not rows:
        return []
    ids = [uuid.UUID(r["id"]) for r in rows]
    nodes = _fetch_turns_by_ids(backend, ids)
    # Reverse so output is oldest→newest
    nodes.sort(key=lambda nd: nd.properties.get("turn_index", 0))
    return nodes


def semantic_turns(
    backend: StorageBackend,
    hnsw: HNSWIndex,
    embedder: Embedder,
    query: str,
    current_session_id: str,
    k: int = 4,
    threshold: float = 0.55,
) -> list[Node]:
    """
    Return top-k CONVERSATION_TURN nodes from *any* session that are
    semantically similar to *query*, excluding the current session
    (those are already covered by ``recent_turns``).
    """
    vec = embedder.encode(f"CONVERSATION_TURN {query[:800]}")
    hits = hnsw.query(vec, k=k * 6)  # over-fetch to filter type + session

    out: list[Node] = []
    seen: set[uuid.UUID] = set()
    for nid, score in hits:
        if score < threshold:
            continue
        if nid in seen:
            continue
        seen.add(nid)
        node = backend.get_node(nid)
        if node is None or node.deprecated:
            continue
        if node.type_id != "CONVERSATION_TURN":
            continue
        if node.properties.get("session_id") == current_session_id:
            continue
        out.append(node)
        if len(out) >= k:
            break
    return out


@dataclass
class ConversationContext:
    """Structured context block ready for injection into Claude's prompt."""
    recent: list[Node] = field(default_factory=list)
    semantic: list[Node] = field(default_factory=list)
    total_turns: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.recent and not self.semantic

    def to_text(self) -> str:
        """Render as a <system-reminder> block for the UserPromptSubmit hook."""
        if self.is_empty:
            return ""

        lines = ["[PMC conversation context]"]

        if self.recent:
            lines.append(f"\n--- recente (sessione corrente, ultimi {len(self.recent)} turni) ---")
            for node in self.recent:
                lines.append(_fmt_turn(node, show_session=False))

        if self.semantic:
            lines.append(f"\n--- semanticamente rilevante (sessioni precedenti) ---")
            for node in self.semantic:
                lines.append(_fmt_turn(node, show_session=True))

        lines.append(
            "\nUsa questo contesto per mantenere continuità. "
            "Non citare questi turni esplicitamente a meno che l'utente non lo chieda."
        )
        return "\n".join(lines)


def get_context_for_prompt(
    backend: StorageBackend,
    hnsw: HNSWIndex,
    embedder: Embedder,
    query: str,
    session_id: str,
    recent_n: int = 6,
    semantic_k: int = 4,
    semantic_threshold: float = 0.55,
) -> ConversationContext:
    """
    Main entry point for the UserPromptSubmit hook.

    Combines recent turns (short-term memory) and semantically similar
    turns from past sessions (long-term memory) into a single
    ``ConversationContext`` ready for injection.

    Parameters
    ----------
    query:
        The current user prompt — used for semantic search.
    session_id:
        Current session id — used to separate recent vs past turns.
    recent_n:
        How many recent turns from the current session to include.
    semantic_k:
        How many semantically similar turns from past sessions to include.
    semantic_threshold:
        Minimum cosine similarity for past-session turns.
    """
    rec = recent_turns(backend, session_id, n=recent_n)
    sem = semantic_turns(
        backend, hnsw, embedder, query,
        current_session_id=session_id,
        k=semantic_k,
        threshold=semantic_threshold,
    )
    total = backend.conn.execute(  # type: ignore[attr-defined]
        "SELECT COUNT(*) as c FROM nodes WHERE type_id='CONVERSATION_TURN'",
    ).fetchone()
    return ConversationContext(
        recent=rec,
        semantic=sem,
        total_turns=total["c"] if total else 0,
    )
