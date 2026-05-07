import os
from pmc.schema.loader import load_schema
from pmc.planner.generator import generate_plan
from pmc.planner.validator import validate_plan


def test_planner_offline_stub_produces_valid_plan(monkeypatch):
    # Force offline path: the stub plan generator activates when no API key.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = load_schema("default")
    p = generate_plan("what files exist in the project?", s)
    rep = validate_plan(p, s)
    assert rep.ok, rep.errors
    assert any(st.op == "ASSERT" for st in p.steps)
