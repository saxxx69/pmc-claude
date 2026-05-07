import os
import uuid
import tempfile
from datetime import datetime, timezone
from pmc.storage.sqlite import SQLiteBackend
from pmc.models import Node, Edge, ProvenanceRecord, SourceType, TrustLevel


def _prov():
    return ProvenanceRecord(
        id=uuid.uuid4(), source_type=SourceType.FILE, source_uri="/p",
        extracted_by="t", extracted_at=datetime.now(timezone.utc),
        trust_level=TrustLevel.TRUSTED,
    )


def _node(prov_id, type_id="CODE_FILE", label="a.py", path="/a.py"):
    return Node(
        id=uuid.uuid4(), type_id=type_id, label=label,
        embedding=[0.1, 0.2, 0.3],
        properties={"path": path, "language": "python"},
        confidence=0.9, version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        provenance_id=prov_id,
    )


def test_roundtrip_node_and_edge():
    with tempfile.TemporaryDirectory() as d:
        be = SQLiteBackend(os.path.join(d, "m.db"))
        be.init_schema()
        p = _prov()
        be.insert_provenance(p)
        n1 = _node(p.id, label="a.py", path="/a.py")
        n2 = _node(p.id, label="b.py", path="/b.py")
        be.insert_node(n1)
        be.insert_node(n2)
        e = Edge(id=uuid.uuid4(), source=n1.id, target=n2.id,
                 type_id="IMPORTS", weight=1.0, confidence=0.9,
                 provenance_id=p.id, created_at=datetime.now(timezone.utc))
        be.insert_edge(e)
        assert be.get_node(n1.id).label == "a.py"
        assert be.get_node(n2.id).label == "b.py"
        outs = be.get_edges_out(n1.id, "IMPORTS")
        assert len(outs) == 1
        assert outs[0].target == n2.id
        ins = be.get_edges_in(n2.id, "IMPORTS")
        assert len(ins) == 1


def test_find_by_property():
    with tempfile.TemporaryDirectory() as d:
        be = SQLiteBackend(os.path.join(d, "m.db"))
        be.init_schema()
        p = _prov()
        be.insert_provenance(p)
        be.insert_node(_node(p.id, path="/a.py"))
        be.insert_node(_node(p.id, path="/b.py"))
        hits = be.find_by_property("CODE_FILE", "path", "/a.py")
        assert len(hits) == 1
        assert hits[0].properties["path"] == "/a.py"


def test_count_and_deprecate():
    with tempfile.TemporaryDirectory() as d:
        be = SQLiteBackend(os.path.join(d, "m.db"))
        be.init_schema()
        p = _prov(); be.insert_provenance(p)
        n = _node(p.id); be.insert_node(n)
        assert be.count_by_type("CODE_FILE") == 1
        be.deprecate_node(n.id)
        assert be.count_by_type("CODE_FILE") == 0
