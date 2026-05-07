from __future__ import annotations
from typing import Optional, Literal, Any
from pydantic import BaseModel, Field


class PropertyDef(BaseModel):
    type: Literal["string", "int", "float", "bool", "enum", "timestamp", "ref"]
    required: bool = False
    cardinality: Literal["one", "many"] = "one"
    enum_values: Optional[list[str]] = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    unique: bool = False


class RelationDef(BaseModel):
    target_type: str  # may be "*" wildcard
    cardinality: Literal["one", "many"] = "many"
    required: bool = False


class TypeDefinition(BaseModel):
    abstract: bool = False
    extends: Optional[str] = None
    properties: dict[str, PropertyDef] = Field(default_factory=dict)
    relations_out: dict[str, RelationDef] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)


class Schema(BaseModel):
    schema_id: str
    version: str
    types: dict[str, TypeDefinition]
    inference_rules: list[dict[str, Any]] = Field(default_factory=list)
    conflict_resolution_policy: dict[str, Any] = Field(default_factory=dict)
