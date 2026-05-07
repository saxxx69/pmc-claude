from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionContext:
    bindings: dict[str, Any] = field(default_factory=dict)
    nodes_visited: set[uuid.UUID] = field(default_factory=set)
    started_at: float = field(default_factory=time.time)
    assertions: list[uuid.UUID] = field(default_factory=list)

    def bind(self, key: str, value: Any) -> None:
        self.bindings[key] = value

    def resolve(self, ref: Any) -> Any:
        """Resolve $bindings recursively. Strings beginning with $ get
        substituted; lists/dicts are walked."""
        if isinstance(ref, str) and ref.startswith("$"):
            return self.bindings.get(ref)
        if isinstance(ref, list):
            return [self.resolve(x) for x in ref]
        if isinstance(ref, dict):
            return {k: self.resolve(v) for k, v in ref.items()}
        return ref

    def elapsed_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)
