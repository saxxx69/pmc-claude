from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class SourceType(str, Enum):
    FILE = "file"
    DB_QUERY = "db_query"
    API_CALL = "api_call"
    INFERENCE = "inference"
    HUMAN = "human"


class TrustLevel(str, Enum):
    VERIFIED = "verified"
    TRUSTED = "trusted"
    UNVERIFIED = "unverified"
    CONTESTED = "contested"


class ProvenanceRecord(BaseModel):
    id: uuid.UUID
    source_type: SourceType
    source_uri: str
    extracted_by: str  # tool/agent/method name
    extracted_at: datetime
    raw_content_id: Optional[uuid.UUID] = None
    pipeline_run_id: Optional[uuid.UUID] = None
    trust_level: TrustLevel = TrustLevel.UNVERIFIED
