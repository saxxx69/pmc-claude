from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Edge(BaseModel):
    id: uuid.UUID
    source: uuid.UUID
    target: uuid.UUID
    type_id: str  # RelationType
    weight: float = Field(ge=0.0, le=1.0, default=1.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)
    directional: bool = True
    version: int = 1
    valid_until: Optional[datetime] = None
    deprecated: bool = False
    provenance_id: uuid.UUID
    created_at: datetime
