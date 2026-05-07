from __future__ import annotations
import os
import shutil
import subprocess
from typing import Optional


class LLMError(Exception):
    pass


def detect_backend() -> str:
    """Pick the best available LLM backend.

    Priority:
      1. PMC_LLM_BACKEND env var if set (claude-cli | anthropic | fallback)
      2. anthropic SDK if ANTHROPIC_API_KEY is set
      3. claude CLI if available on PATH (uses your Claude Code subscription)
      4. fallback (deterministic offline stub)
    """
    explicit = os.environ.get("PMC_LLM_BACKEND")
    if explicit:
        return explicit
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if shutil.which("claude"):
        return "claude-cli"
    return "fallback"


def call_llm(prompt: str, *, model: Optional[str] = None,
             max_tokens: int = 2048, system: Optional[str] = None) -> str:
    """Unified LLM gateway. Returns the assistant's text response.

    On any backend failure, raises LLMError. Callers may catch and fall back
    to a deterministic stub (e.g. the planner does this).
    """
    backend = detect_backend()
    if backend == "anthropic":
        return _call_anthropic(prompt, model=model, max_tokens=max_tokens, system=system)
    if backend == "claude-cli":
        return _call_claude_cli(prompt, model=model, system=system)
    if backend == "fallback":
        raise LLMError("backend=fallback")
    raise LLMError(f"unknown_backend:{backend}")


def _call_anthropic(prompt: str, *, model: Optional[str],
                    max_tokens: int, system: Optional[str]) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise LLMError(f"anthropic_sdk_missing:{e}") from e
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    kwargs: dict = {
        "model": model or os.environ.get("PMC_PLANNER_MODEL", "claude-sonnet-4-6"),
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    try:
        msg = client.messages.create(**kwargs)
        return msg.content[0].text  # type: ignore[union-attr]
    except Exception as e:
        raise LLMError(f"anthropic_api_failed:{e}") from e


def _call_claude_cli(prompt: str, *, model: Optional[str],
                     system: Optional[str]) -> str:
    """Invoke the local `claude` CLI in print mode. Uses the user's
    Claude Code subscription — no API key required."""
    cli = shutil.which("claude")
    if not cli:
        raise LLMError("claude_cli_not_found")
    cmd: list[str] = [cli, "-p"]
    chosen_model = model or os.environ.get("PMC_PLANNER_MODEL")
    if chosen_model:
        cmd += ["--model", chosen_model]
    full_prompt = prompt if system is None else f"{system}\n\n{prompt}"
    cmd.append(full_prompt)
    timeout = int(os.environ.get("PMC_LLM_TIMEOUT_SEC", "120"))
    try:
        out = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise LLMError(f"claude_cli_timeout:{timeout}s") from e
    except Exception as e:
        raise LLMError(f"claude_cli_invocation_failed:{e}") from e
    if out.returncode != 0:
        raise LLMError(
            f"claude_cli_exit:{out.returncode}:{(out.stderr or '').strip()[:200]}"
        )
    text = (out.stdout or "").strip()
    if not text:
        raise LLMError("claude_cli_empty_output")
    return text
