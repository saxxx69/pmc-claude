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
