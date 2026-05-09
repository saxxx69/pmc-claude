from __future__ import annotations
import ast
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from pmc.models import (
    Node, Edge, Content, ProvenanceRecord, UncertaintyRecord,
    SourceType, TrustLevel,
)
from pmc.storage.backend import StorageBackend
from pmc.storage.hnsw_index import HNSWIndex
from pmc.embeddings.embedder import Embedder
from pmc.operations.semantic_linking import link_to_neighbors


# extension → (TypeID, ContentFormat)
EXT_MAP: dict[str, tuple[str, str]] = {
    ".py": ("CODE_FILE", "code"),
    ".js": ("CODE_FILE", "code"),
    ".ts": ("CODE_FILE", "code"),
    ".tsx": ("CODE_FILE", "code"),
    ".jsx": ("CODE_FILE", "code"),
    ".rs": ("CODE_FILE", "code"),
    ".go": ("CODE_FILE", "code"),
    ".sh": ("CODE_FILE", "code"),
    ".md": ("DOC", "text"),
    ".txt": ("DOC", "text"),
    ".rst": ("DOC", "text"),
    ".json": ("CONFIG", "json"),
    ".yaml": ("CONFIG", "json"),
    ".yml": ("CONFIG", "json"),
    ".toml": ("CONFIG", "text"),
    ".ini": ("CONFIG", "text"),
    ".cfg": ("CONFIG", "text"),
}

LANG_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript",
    ".rs": "rust", ".go": "go", ".sh": "bash",
}

IGNORE_DIRS = {".git", "__pycache__", "node_modules", "venv", ".venv",
               ".pmc", "dist", "build", ".pytest_cache", ".mypy_cache",
               "backups", "test_reports", ".next", "coverage", "htmlcov"}


@dataclass
class IngestReport:
    nodes_created: int = 0
    edges_created: int = 0
    files_seen: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    pipeline_run_id: uuid.UUID = field(default_factory=uuid.uuid4)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _walk(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            yield Path(dirpath) / fn


def _make_provenance(uri: str, run_id: uuid.UUID) -> ProvenanceRecord:
    return ProvenanceRecord(
        id=uuid.uuid4(),
        source_type=SourceType.FILE,
        source_uri=uri,
        extracted_by="pmc.ingestion.filesystem.v0.1",
        extracted_at=_now(),
        pipeline_run_id=run_id,
        trust_level=TrustLevel.TRUSTED,
    )


def _extract_python_imports(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.append(node.module)
    return out


def _extract_python_functions(source: str) -> list[tuple[str, str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = f"{node.name}(...)"
            out.append((node.name, sig))
    return out


def ingest_filesystem(
    backend: StorageBackend,
    hnsw: HNSWIndex,
    embedder: Embedder,
    root: str,
    include_content: bool = True,
) -> IngestReport:
    report = IngestReport()
    rootp = Path(root).resolve()
    file_node_by_path: dict[str, uuid.UUID] = {}
    py_imports: list[tuple[uuid.UUID, list[str]]] = []

    # Support single-file ingest (hook passes individual file paths)
    def _files():
        if rootp.is_file():
            yield rootp
        else:
            yield from _walk(rootp)

    # Pass 1: create file/doc/config nodes
    for fp in _files():
        ext = fp.suffix.lower()
        if ext not in EXT_MAP:
            continue
        type_id, fmt = EXT_MAP[ext]
        report.files_seen += 1
        try:
            data = fp.read_bytes()
        except Exception as e:
            report.errors.append(f"read_failed:{fp}:{e}")
            report.skipped += 1
            continue

        prov = _make_provenance(str(fp), report.pipeline_run_id)
        backend.insert_provenance(prov)

        content_id: Optional[uuid.UUID] = None
        if include_content:
            sha = hashlib.sha256(data).hexdigest()
            content = Content(
                id=uuid.uuid4(), format=fmt, data=data, hash=sha,
                source_uri=str(fp), extracted_at=_now(),
            )
            backend.insert_content(content)
            content_id = content.id

        rel_path = str(fp.relative_to(rootp))
        text_for_embed = (data[:2000].decode("utf-8", errors="replace")
                          if fmt in ("text", "code", "json") else fp.name)
        emb = embedder.encode(f"{type_id} {rel_path} {text_for_embed[:500]}")

        props: dict = {"path": rel_path}
        if type_id == "CODE_FILE":
            props["language"] = LANG_MAP.get(ext, "other")
            props["line_count"] = data.count(b"\n") + 1
            props["module"] = fp.stem
        elif type_id == "DOC":
            props["title"] = fp.stem
            props["topic"] = fp.stem
        elif type_id == "CONFIG":
            props["key"] = fp.stem

        node = Node(
            id=uuid.uuid4(),
            type_id=type_id,
            label=fp.name,
            embedding=emb,
            properties=props,
            content_ref=content_id,
            confidence=0.9,
            created_at=_now(), updated_at=_now(),
            provenance_id=prov.id,
        )
        backend.insert_node(node)
        backend.upsert_uncertainty(UncertaintyRecord(
            node_id=node.id, confidence=0.9, coverage=1.0, freshness_score=1.0,
            last_verified=_now(),
        ))
        hnsw.add(node.id, emb)
        report.edges_created += link_to_neighbors(node.id, emb, backend, hnsw, run_id=report.pipeline_run_id)
        file_node_by_path[rel_path] = node.id
        report.nodes_created += 1

        # Extract Python imports + functions for later linking
        if ext == ".py":
            try:
                src = data.decode("utf-8", errors="replace")
            except Exception:
                src = ""
            py_imports.append((node.id, _extract_python_imports(src)))
            for fname, sig in _extract_python_functions(src):
                f_prov = _make_provenance(f"{fp}::{fname}", report.pipeline_run_id)
                backend.insert_provenance(f_prov)
                f_emb = embedder.encode(f"FUNCTION {fname} in {rel_path}")
                f_node = Node(
                    id=uuid.uuid4(), type_id="FUNCTION", label=fname,
                    embedding=f_emb,
                    properties={"name": fname, "signature": sig},
                    confidence=0.85,
                    created_at=_now(), updated_at=_now(),
                    provenance_id=f_prov.id,
                )
                backend.insert_node(f_node)
                hnsw.add(f_node.id, f_emb)
                report.edges_created += link_to_neighbors(f_node.id, f_emb, backend, hnsw, run_id=report.pipeline_run_id)
                edge_prov = _make_provenance(f"{fp}#defines#{fname}", report.pipeline_run_id)
                backend.insert_provenance(edge_prov)
                backend.insert_edge(Edge(
                    id=uuid.uuid4(),
                    source=node.id, target=f_node.id,
                    type_id="DEFINES", weight=1.0, confidence=0.95,
                    provenance_id=edge_prov.id, created_at=_now(),
                ))
                report.nodes_created += 1
                report.edges_created += 1

    # Pass 2: link Python imports
    for src_nid, imports in py_imports:
        for imp in imports:
            target_path = imp.replace(".", "/") + ".py"
            tgt_nid = file_node_by_path.get(target_path)
            if tgt_nid is None:
                # try basename match
                base = imp.split(".")[-1] + ".py"
                for p, nid in file_node_by_path.items():
                    if p.endswith(base):
                        tgt_nid = nid
                        break
            if tgt_nid is None:
                continue
            prov = _make_provenance(f"import:{imp}", report.pipeline_run_id)
            backend.insert_provenance(prov)
            backend.insert_edge(Edge(
                id=uuid.uuid4(),
                source=src_nid, target=tgt_nid,
                type_id="IMPORTS", weight=1.0, confidence=0.9,
                provenance_id=prov.id, created_at=_now(),
            ))
            report.edges_created += 1

    return report
