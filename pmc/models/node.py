from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class Node(BaseModel):
    """Atomic unit of knowledge in m. Immutable id, never hard-deleted."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: uuid.UUID
    type_id: str
    label: str
    embedding: list[float] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    content_ref: Optional[uuid.UUID] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)
    version: int = 1
    created_at: datetime
    updated_at: datetime
    valid_until: Optional[datetime] = None
    deprecated: bool = False
    provenance_id: uuid.UUID
