from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer

from pmc.memory import PMCMemory
from pmc.dataset.generator import generate_pairs
from pmc.dataset.splitter import split_pairs


app = typer.Typer(help="PMC — Palace of Computational Memory CLI", no_args_is_help=True)


def _open_memory(db: str, schema: str) -> PMCMemory:
    if not Path(db).parent.exists():
        Path(db).parent.mkdir(parents=True, exist_ok=True)
    return PMCMemory.create(db, schema=schema)


@app.command()
def ingest(
    path: str = typer.Argument(..., help="Path to the project to ingest"),
    db: str = typer.Option(None, "--db", help="SQLite db path"),
    schema: str = typer.Option("default", "--schema", help="Schema path or 'default'"),
):
    """Ingest a filesystem tree into m."""
    db = db or os.environ.get("PMC_DB", "./.pmc/m.db")
    m = _open_memory(db, schema)
    rep = m.ingest(path, kind="filesystem")
    typer.echo(json.dumps({
        "files_seen": rep.files_seen,
        "nodes_created": rep.nodes_created,
        "edges_created": rep.edges_created,
        "skipped": rep.skipped,
        "errors": rep.errors[:5],
        "pipeline_run_id": str(rep.pipeline_run_id),
    }, indent=2))
    m.close()


@app.command()
def query(
    question: str = typer.Argument(..., help="The query in natural language"),
    db: str = typer.Option(None, "--db"),
    schema: str = typer.Option("default", "--schema"),
    show_plan: bool = typer.Option(False, "--show-plan"),
    show_trace: bool = typer.Option(False, "--show-trace"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Run the full PMC query pipeline."""
    db = db or os.environ.get("PMC_DB", "./.pmc/m.db")
    m = _open_memory(db, schema)
    res = m.query(question)
    if json_out:
        out = {
            "status": res.status,
            "text": res.text,
            "assertions": [str(a) for a in res.assertions],
            "verification": res.verification.__dict__ if res.verification else None,
            "coverage": res.coverage.__dict__ if res.coverage else None,
            "errors": res.errors,
        }
        if show_trace:
            out["trace"] = res.trace
        typer.echo(json.dumps(out, indent=2, default=str))
    else:
        typer.echo(res.text)
        if getattr(res, 'vector_fallback_text', None):
            typer.echo("\n" + res.vector_fallback_text)
        if getattr(res, 'self_healing_promoted', None):
            typer.echo(f"\n[self-healing: {res.self_healing_promoted} node(s) promoted to graph]")
        if show_plan and res.plan_id:
            typer.echo(f"\n--- plan_id: {res.plan_id}")
        if show_trace:
            typer.echo("\n--- trace:\n" + json.dumps(res.trace, indent=2, default=str))
    m.close()
    sys.exit(0 if res.status in ("COMPLETE", "PARTIAL") else 1)


@app.command()
def plan(
    question: str = typer.Argument(...),
    db: str = typer.Option(None, "--db"),
    schema: str = typer.Option("default", "--schema"),
):
    """Generate and display the plan WITHOUT executing it."""
    db = db or os.environ.get("PMC_DB", "./.pmc/m.db")
    m = _open_memory(db, schema)
    p, vrep = m.plan(question)
    typer.echo(p.model_dump_json(indent=2))
    typer.echo(f"\n--- validation: ok={vrep.ok} errors={vrep.errors}")
    m.close()


@app.command()
def stats(
    db: str = typer.Option(None, "--db"),
    schema: str = typer.Option("default", "--schema"),
    schema_only: bool = typer.Option(False, "--schema-only"),
):
    """Print stats about m."""
    db = db or os.environ.get("PMC_DB", "./.pmc/m.db")
    if not Path(db).exists() and schema_only:
        typer.echo(json.dumps({"db": db, "exists": False}, indent=2))
        return
    m = _open_memory(db, schema)
    s = m.stats()
    if schema_only:
        s = {"schema_id": s["schema_id"], "schema_version": s["schema_version"],
             "node_types": list(s["node_counts_by_type"].keys())}
    typer.echo(json.dumps(s, indent=2, default=str))
    m.close()


@app.command()
def bootstrap(
    project: str = typer.Argument(...),
    db: str = typer.Option(None, "--db"),
    schema: str = typer.Option("default", "--schema"),
    gen_dataset: int = typer.Option(0, "--gen-dataset",
                                    help="N synthetic (c, plan) pairs to generate"),
    out_dir: Optional[str] = typer.Option(None, "--out-dir"),
):
    """Ingest a project and optionally generate the bootstrap dataset."""
    db = db or os.environ.get("PMC_DB", "./.pmc/m.db")
    out_dir = out_dir or os.path.join(os.path.dirname(db) or ".", "dataset")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    m = _open_memory(db, schema)
    rep = m.ingest(project)
    typer.echo(json.dumps({
        "ingested_nodes": rep.nodes_created,
        "ingested_edges": rep.edges_created,
    }, indent=2))
    if gen_dataset > 0:
        pairs = generate_pairs(m.backend, n=gen_dataset, seed=42)
        train, val, test = split_pairs(pairs, seed=42)
        for name, items in [("train", train), ("val", val), ("test", test)]:
            p = Path(out_dir) / f"{name}.jsonl"
            with open(p, "w", encoding="utf-8") as f:
                for c, plan_obj in items:
                    f.write(json.dumps(
                        {"query": c, "plan": plan_obj.model_dump(mode="json")},
                        default=str,
                    ) + "\n")
        typer.echo(json.dumps({
            "dataset_dir": out_dir,
            "train": len(train), "val": len(val), "test": len(test),
        }, indent=2))
    m.close()


if __name__ == "__main__":
    app()


# ── conversation commands (added by pmc-conversation patch) ─────────────────

from pmc.ingestion.conversation import ingest_turn, ConversationTurn  # noqa: E402
from pmc.operations.conversation import get_context_for_prompt         # noqa: E402


@app.command("converse-ingest")
def converse_ingest(
    session_id: str = typer.Option(...,  "--session-id",   help="Stable session identifier"),
    user_text:  str = typer.Option("",   "--user-text",    help="User message text"),
    assistant_text: str = typer.Option("", "--assistant-text", help="Assistant reply text"),
    db:      str = typer.Option(None,    "--db"),
    schema:  str = typer.Option("default", "--schema"),
    project: str = typer.Option("",      "--project",      help="Project name tag"),
):
    """
    Ingest a user+assistant exchange as CONVERSATION_TURN nodes.

    Called automatically by the pmc-conversation-ingest.sh PostToolUse hook
    after every Claude response. Safe to call multiple times (idempotent).
    """
    db = db or os.environ.get("PMC_DB", "./.pmc/m.db")
    m = _open_memory(db, schema)

    # Determine current turn count for this session to assign turn_index
    row = m.backend.conn.execute(
        "SELECT COALESCE(MAX(json_extract(properties, '$.turn_index')), -1) as mx "
        "FROM nodes WHERE type_id='CONVERSATION_TURN' "
        "AND json_extract(properties,'$.session_id')=?",
        (session_id,),
    ).fetchone()
    next_index = (row["mx"] + 1) if row else 0

    results = []
    for role, text in [("user", user_text), ("assistant", assistant_text)]:
        if not text.strip():
            continue
        rep = ingest_turn(
            m.backend, m.hnsw, m.embedder,
            ConversationTurn(
                session_id=session_id,
                turn_index=next_index,
                role=role,
                text=text,
                project=project,
            ),
        )
        results.append({
            "role": role,
            "turn_index": next_index,
            "turn_node_id": str(rep.turn_node_id),
            "session_node_id": str(rep.session_node_id),
            "session_created": rep.session_created,
            "references_created": rep.references_created,
            "follows_created": rep.follows_created,
        })
        next_index += 1

    typer.echo(json.dumps(results, indent=2))
    m.close()


@app.command("conversation-context")
def conversation_context(
    query:      str = typer.Argument(...,              help="The current user prompt"),
    session_id: str = typer.Option(...,  "--session-id"),
    db:         str = typer.Option(None, "--db"),
    schema:     str = typer.Option("default", "--schema"),
    recent:     int = typer.Option(6,    "--recent",   help="# recent turns to inject"),
    semantic:   int = typer.Option(4,    "--semantic", help="# past-session turns to inject"),
    json_out:   bool = typer.Option(False, "--json"),
):
    """
    Retrieve conversation context for the current prompt.

    Called automatically by pmc-user-prompt.sh before every Claude response.
    Prints a plain-text block ready for injection as <system-reminder>,
    or JSON when --json is set.
    """
    db = db or os.environ.get("PMC_DB", "./.pmc/m.db")
    m = _open_memory(db, schema)

    ctx = get_context_for_prompt(
        m.backend, m.hnsw, m.embedder,
        query=query,
        session_id=session_id,
        recent_n=recent,
        semantic_k=semantic,
    )

    if json_out:
        typer.echo(json.dumps({
            "total_turns_in_db": ctx.total_turns,
            "recent_count": len(ctx.recent),
            "semantic_count": len(ctx.semantic),
            "recent": [n.properties for n in ctx.recent],
            "semantic": [n.properties for n in ctx.semantic],
        }, indent=2, default=str))
    else:
        text = ctx.to_text()
        if text:
            typer.echo(text)

    m.close()
