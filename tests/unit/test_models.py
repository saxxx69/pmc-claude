import uuid
from datetime import datetime, timezone
from pmc.models import Node, Edge, ProvenanceRecord, SourceType, TrustLevel


def test_node_minimum():
    pid = uuid.uuid4()
    n = Node(
        id=uuid.uuid4(), type_id="CODE_FILE", label="x.py",
        embedding=[0.1, 0.2, 0.3],
        properties={"path": "/x.py", "language": "python"},
        confidence=0.9, version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        provenance_id=pid,
    )
    assert n.deprecated is False


def test_provenance_enums():
    p = ProvenanceRecord(
        id=uuid.uuid4(), source_type=SourceType.FILE, source_uri="/x",
        extracted_by="t", extracted_at=datetime.now(timezone.utc),
        trust_level=TrustLevel.TRUSTED,
    )
    assert p.trust_level == TrustLevel.TRUSTED
    assert p.source_type == SourceType.FILE
