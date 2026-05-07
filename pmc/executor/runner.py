from __future__ import annotations
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Optional

from pmc.planner.plan import Plan, Step
from pmc.executor.context import ExecutionContext
from pmc.executor.tracer import Tracer
from pmc.storage.backend import StorageBackend
from pmc.storage.hnsw_index import HNSWIndex
from pmc.embeddings.embedder import Embedder
from pmc.schema.types import Schema
from pmc.models import Node, Unknown
from pmc import operations as ops


@dataclass
class ExecutionResult:
    plan_id: uuid.UUID
    status: str  # COMPLETE | PARTIAL | FAILED | TIMEOUT
    bindings: dict[str, Any] = field(default_factory=dict)
    assertions: list[uuid.UUID] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    trace: dict = field(default_factory=dict)


class Executor:
    def __init__(self, backend: StorageBackend, hnsw: HNSWIndex, embedder: Embedder, schema: Schema):
        self.backend = backend
        self.hnsw = hnsw
        self.embedder = embedder
        self.schema = schema

    def execute(self, plan: Plan) -> ExecutionResult:
        ctx = ExecutionContext()
        tr = Tracer()
        errors: list[str] = []
        steps = self._topo_sort(plan.steps)
        timeout_ms = int(plan.execution.get("timeout_ms", 10000))

        for step in steps:
            t0 = time.time()
            try:
                value = self._dispatch(step, ctx)
            except Exception as e:
                tr.record(step.step_id, step.op, step.output_binding, None,
                          int((time.time() - t0) * 1000), error=str(e))
                errors.append(f"{step.step_id}:{e}")
                if step.on_type_error == "HALT":
                    return ExecutionResult(plan_id=plan.plan_id, status="FAILED",
                                            bindings=ctx.bindings, errors=errors,
                                            trace=tr.to_dict())
                continue

            ctx.bind(step.output_binding, value)
            wall = int((time.time() - t0) * 1000)
            tr.record(step.step_id, step.op, step.output_binding, value, wall)

            if _is_empty(value) and step.on_empty.get("policy") == "HALT":
                return ExecutionResult(plan_id=plan.plan_id, status="PARTIAL",
                                        bindings=ctx.bindings,
                                        assertions=ctx.assertions, errors=errors,
                                        trace=tr.to_dict())
            if ctx.elapsed_ms() > timeout_ms:
                return ExecutionResult(plan_id=plan.plan_id, status="TIMEOUT",
                                        bindings=ctx.bindings,
                                        assertions=ctx.assertions, errors=errors,
                                        trace=tr.to_dict())

        return ExecutionResult(plan_id=plan.plan_id, status="COMPLETE",
                                bindings=ctx.bindings,
                                assertions=ctx.assertions, errors=errors,
                                trace=tr.to_dict())

    # -------- dispatch --------
    def _dispatch(self, step: Step, ctx: ExecutionContext) -> Any:
        a = ctx.resolve(step.args)
        op = step.op
        if op == "SELECT_EXACT":
            return ops.select_exact(self.backend, a["type"], a["property"], a["value"])
        if op == "SELECT_APPROX":
            hits = ops.select_approx(self.backend, self.hnsw, self.embedder,
                                     a["query"], a.get("type_filter"),
                                     int(a.get("k", 10)), float(a.get("threshold", 0.5)))
            return [n for n, _ in hits]
        if op == "SELECT_BY_ID":
            return ops.select_by_id(self.backend, uuid.UUID(str(a["id"])))
        if op == "SELECT_FRESH":
            return ops.select_fresh(self.backend, a["type"], a["property"], a["value"],
                                    timedelta(seconds=int(a.get("max_age_sec", 3600))))
        if op == "TRAVERSE":
            nodes = _as_node_list(a.get("node"))
            out: list[Node] = []
            for n in nodes:
                out.extend(ops.traverse(self.backend, n.id, a["rel"], a.get("direction", "out")))
            return out
        if op == "EXPAND":
            nodes = _as_node_list(a.get("nodes"))
            return ops.expand(self.backend, [n.id for n in nodes],
                              a.get("rel_types"), int(a.get("max_hops", 2)),
                              a.get("direction", "out"))
        if op == "PATH_FIND":
            src = _first_id(a.get("source"))
            tgt = _first_id(a.get("target"))
            return ops.path_find(self.backend, src, tgt, a.get("rel_types"))
        if op == "SUBGRAPH":
            root = _first_id(a.get("root"))
            return ops.subgraph(self.backend, root, int(a.get("depth", 2)), a.get("rel_types"))
        if op == "INTERSECT":
            return ops.intersect_nodes(_as_node_list(a["a"]), _as_node_list(a["b"]))
        if op == "UNION":
            return ops.union_nodes(_as_node_list(a["a"]), _as_node_list(a["b"]))
        if op == "DIFFERENCE":
            return ops.difference_nodes(_as_node_list(a["a"]), _as_node_list(a["b"]))
        if op == "FILTER":
            cond = a.get("condition", "")
            nodes = _as_node_list(a.get("input"))
            return ops.filter_pred(nodes, _make_predicate(cond))
        if op == "TOP_K":
            return ops.top_k(_as_node_list(a.get("input")), int(a.get("k", 10)))
        if op == "COUNT":
            return ops.count(_as_node_list(a.get("input")))
        if op == "AGGREGATE":
            return ops.aggregate(_as_node_list(a.get("input")), a["fn"], a.get("prop"))
        if op == "REDUCE":
            return ops.reduce_best(_as_node_list(a.get("input")))
        if op == "ASSERT":
            sources = _as_node_list(a.get("sources"))
            res = ops.assert_claim(self.backend, a.get("claim", ""),
                                    [n.id for n in sources],
                                    float(a.get("confidence_threshold", 0.7)),
                                    plan_step_id=step.step_id)
            if isinstance(res, Unknown):
                return res
            ctx.assertions.append(res)
            return res
        if op == "CHECK_COVERAGE":
            return ops.check_coverage(self.backend, self.hnsw, self.embedder,
                                       a.get("topic", ""))
        if op == "INFER":
            return ops.infer(self.backend, self.schema, a["rule_id"])
        if op == "GET_TYPE":
            n = _as_node_list(a.get("node"))
            return n[0].type_id if n else None
        if op == "GET_PROVENANCE":
            n = _as_node_list(a.get("node"))
            return ops.get_provenance(self.backend, n[0].id) if n else None
        raise NotImplementedError(f"op_not_implemented:{op}")

    # -------- topo sort --------
    def _topo_sort(self, steps: list[Step]) -> list[Step]:
        idx = {s.step_id: s for s in steps}
        order: list[Step] = []
        visited: set[str] = set()
        temp: set[str] = set()

        def visit(sid: str) -> None:
            if sid in visited:
                return
            if sid in temp:
                raise RuntimeError(f"circular_dependency:{sid}")
            temp.add(sid)
            for d in idx[sid].depends_on:
                if d in idx:
                    visit(d)
            temp.remove(sid)
            visited.add(sid)
            order.append(idx[sid])

        for s in steps:
            visit(s.step_id)
        return order


# -------- helpers --------
def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, str)):
        return len(value) == 0
    if isinstance(value, Unknown):
        return True
    return False


def _as_node_list(value: Any) -> list[Node]:
    if value is None:
        return []
    if isinstance(value, Node):
        return [value]
    if isinstance(value, list):
        out = []
        for v in value:
            if isinstance(v, Node):
                out.append(v)
            elif isinstance(v, tuple) and v and isinstance(v[0], Node):
                out.append(v[0])
        return out
    return []


def _first_id(value: Any) -> uuid.UUID:
    nodes = _as_node_list(value)
    if nodes:
        return nodes[0].id
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        return uuid.UUID(value)
    raise ValueError("cannot_resolve_node_id")


# Safe predicate DSL: supports `<lhs> <op> <rhs>` only.
# lhs: label | type_id | confidence | deprecated | properties.<key>
# op:  == | != | <= | >= | < | >
# rhs: a quoted string OR a number OR true/false
_PRED_RE = re.compile(
    r'^\s*(?P<lhs>label|type_id|confidence|deprecated|properties\.[A-Za-z_][A-Za-z0-9_]*)'
    r'\s*(?P<op>==|!=|<=|>=|<|>)\s*'
    r'(?P<rhs>"[^"]*"|\'[^\']*\'|-?\d+(?:\.\d+)?|true|false)\s*$'
)


def _coerce(rhs: str):
    rhs = rhs.strip()
    if (rhs.startswith('"') and rhs.endswith('"')) or (rhs.startswith("'") and rhs.endswith("'")):
        return rhs[1:-1]
    if rhs == "true":
        return True
    if rhs == "false":
        return False
    if "." in rhs:
        return float(rhs)
    return int(rhs)


def _make_predicate(cond: str):
    m = _PRED_RE.match(cond or "")
    if not m:
        return lambda _n: False
    lhs, op, rhs = m.group("lhs"), m.group("op"), _coerce(m.group("rhs"))

    def get_lhs(n: Node):
        if lhs.startswith("properties."):
            return n.properties.get(lhs.split(".", 1)[1])
        return getattr(n, lhs, None)

    def pred(n: Node) -> bool:
        v = get_lhs(n)
        try:
            if op == "==":
                return v == rhs
            if op == "!=":
                return v != rhs
            if op == "<=":
                return v is not None and v <= rhs
            if op == ">=":
                return v is not None and v >= rhs
            if op == "<":
                return v is not None and v < rhs
            if op == ">":
                return v is not None and v > rhs
        except Exception:
            return False
        return False

    return pred
