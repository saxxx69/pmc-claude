from __future__ import annotations
import os
import uuid
from typing import Optional

from pmc.synthesis.prompt import SYNTHESIS_PROMPT
from pmc.storage.backend import StorageBackend
from pmc.operations.reasoning import CoverageReport
from pmc.llm import call_llm, detect_backend, LLMError


def _format_assertions(backend: StorageBackend, assertion_ids: list[uuid.UUID]) -> str:
    if not assertion_ids:
        return "(no assertions — answer must be UNKNOWN)"
    lines: list[str] = []
    for i, aid in enumerate(assertion_ids, 1):
        # We store assertions in SQLite; re-fetch via raw SQL on the backend.
        # We fall back to a placeholder if the row cannot be loaded.
        row = backend.conn.execute(  # type: ignore[attr-defined]
            "SELECT claim, source_node_ids, confidence FROM assertions WHERE id=?",
            (str(aid),),
        ).fetchone()
        if row is None:
            lines.append(f"[A{i}] (assertion {aid} missing)")
            continue
        import json as _json
        sources = _json.loads(row["source_node_ids"])
        src_labels: list[str] = []
        for sid in sources[:5]:
            n = backend.get_node(uuid.UUID(sid))
            if n:
                tag = n.properties.get("path") or n.label
                src_labels.append(f"{n.type_id}:{tag}")
        lines.append(
            f"[A{i}] Claim: {row['claim']}\n"
            f"      Sources: {', '.join(src_labels) or '(none)'}\n"
            f"      Confidence: {row['confidence']:.2f}"
        )
    return "\n".join(lines)


def synthesize(
    backend: StorageBackend,
    query: str,
    assertion_ids: list[uuid.UUID],
    coverage: Optional[CoverageReport] = None,
    model: Optional[str] = None,
) -> str:
    coverage_txt = coverage.to_text() if coverage else "verdict=UNKNOWN score=0.0"
    prompt = SYNTHESIS_PROMPT.format(
        assertions=_format_assertions(backend, assertion_ids),
        coverage=coverage_txt,
        query=query,
    )
    if detect_backend() == "fallback":
        # Offline fallback: emit a deterministic textual summary directly
        # from the assertion list. No free generation.
        if not assertion_ids:
            return f"[UNKNOWN: no_assertions_for_query: {query}]"
        return _format_assertions(backend, assertion_ids)
    try:
        return call_llm(
            prompt,
            model=model or os.environ.get("PMC_SYNTH_MODEL"),
            max_tokens=1024,
        )
    except LLMError as e:
        if not assertion_ids:
            return f"[UNKNOWN: no_assertions_for_query: {query}]"
        # If the LLM call fails, return the raw assertion list rather than
        # invented text — the no-hallucination invariant is preserved.
        return _format_assertions(backend, assertion_ids) + f"\n\n[note: synthesis_unavailable: {e}]"
