from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class UncertaintyRecord(BaseModel):
    node_id: uuid.UUID
    confidence: float = Field(ge=0.0, le=1.0)
    coverage: float = Field(ge=0.0, le=1.0, default=1.0)
    freshness_score: float = Field(ge=0.0, le=1.0, default=1.0)
    contradiction_set: list[uuid.UUID] = Field(default_factory=list)
    last_verified: datetime
