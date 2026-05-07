from __future__ import annotations
import uuid
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

ContentFormat = Literal["text", "code", "json", "table", "binary"]


class Chunk(BaseModel):
    id: uuid.UUID
    content_id: uuid.UUID
    sequence: int
    data: bytes
    embedding: list[float] = Field(default_factory=list)
    char_start: int = 0
    char_end: int = 0


class Content(BaseModel):
    id: uuid.UUID
    format: ContentFormat
    data: bytes
    hash: str  # sha256 hex
    encoding: str = "utf-8"
    source_uri: Optional[str] = None
    extracted_at: datetime
    chunks: list[uuid.UUID] = Field(default_factory=list)
