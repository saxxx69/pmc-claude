import os
import pytest
from pmc.llm import detect_backend, call_llm, LLMError


def test_backend_explicit_overrides_all(monkeypatch):
    monkeypatch.setenv("PMC_LLM_BACKEND", "fallback")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert detect_backend() == "fallback"


def test_backend_anthropic_key_takes_precedence(monkeypatch):
    monkeypatch.delenv("PMC_LLM_BACKEND", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert detect_backend() == "anthropic"


def test_backend_fallback_when_nothing(monkeypatch):
    monkeypatch.delenv("PMC_LLM_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Force shutil.which to return None
    monkeypatch.setattr("pmc.llm.shutil.which", lambda _: None)
    assert detect_backend() == "fallback"


def test_call_fallback_raises(monkeypatch):
    monkeypatch.setenv("PMC_LLM_BACKEND", "fallback")
    with pytest.raises(LLMError):
        call_llm("hi")
