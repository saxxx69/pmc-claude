from __future__ import annotations
import json
from pathlib import Path
from typing import Union

from pmc.schema.types import Schema


def load_schema(path: Union[str, Path]) -> Schema:
    """Load a schema JSON file. Supports the magic name 'default' to load
    the bundled default schema."""
    p = Path(path)
    if str(path) == "default":
        # bundled default schema relative to repo
        p = Path(__file__).resolve().parents[2] / "schema" / "default.json"
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Schema.model_validate(data)
