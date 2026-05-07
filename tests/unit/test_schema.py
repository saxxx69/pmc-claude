from pmc.schema.loader import load_schema
from pmc.schema.validator import is_relation_valid, validate_node_against_type


def test_default_schema_loads():
    s = load_schema("default")
    assert "CODE_FILE" in s.types
    assert "FUNCTION" in s.types


def test_relation_validation():
    s = load_schema("default")
    assert is_relation_valid(s, "CODE_FILE", "IMPORTS", "CODE_FILE") is True
    assert is_relation_valid(s, "CODE_FILE", "IMPORTS", "FUNCTION") is False
    assert is_relation_valid(s, "CODE_FILE", "DEFINES", "FUNCTION") is True


def test_node_property_validation():
    s = load_schema("default")
    errs = validate_node_against_type(s, "CODE_FILE",
                                      {"path": "/x.py", "language": "python"})
    assert errs == []
    errs = validate_node_against_type(s, "CODE_FILE",
                                      {"path": "/x.py"})  # missing required language
    assert any("language" in e for e in errs)
