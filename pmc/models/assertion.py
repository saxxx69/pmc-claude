from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, Union
from pydantic import BaseModel, Field


class Assertion(BaseModel):
    """A grounded claim with explicit source nodes. Output of ASSERT op."""
    id: uuid.UUID
    claim: str
    source_node_ids: list[uuid.UUID]
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime
    plan_step_id: Optional[str] = None


class Unknown(BaseModel):
    """Returned by ASSERT when the claim cannot be grounded."""
    kind: str = "UNKNOWN"
    reason: str

    def __init__(self, reason: str = "", **kwargs):
        super().__init__(reason=reason, **kwargs)


# Discriminated result of ASSERT op
AssertResult = Union[Assertion, Unknown]
