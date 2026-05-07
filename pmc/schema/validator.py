from __future__ import annotations
from typing import Any, Optional
from pmc.schema.types import Schema, TypeDefinition


def get_type_definition(schema: Schema, type_id: str) -> Optional[TypeDefinition]:
    return schema.types.get(type_id)


def _walk_inheritance(schema: Schema, type_id: str) -> list[TypeDefinition]:
    out: list[TypeDefinition] = []
    cur = schema.types.get(type_id)
    while cur is not None:
        out.append(cur)
        if cur.extends:
            cur = schema.types.get(cur.extends)
        else:
            cur = None
    return out


def is_relation_valid(schema: Schema, source_type: str, rel_type: str, target_type: str) -> bool:
    """Check whether a relation from source_type via rel_type to target_type
    is allowed by the schema (walking inheritance chain on source side)."""
    for td in _walk_inheritance(schema, source_type):
        rel = td.relations_out.get(rel_type)
        if rel is None:
            continue
        if rel.target_type == "*" or rel.target_type == target_type:
            return True
    return False


def validate_node_against_type(schema: Schema, type_id: str, properties: dict[str, Any]) -> list[str]:
    """Returns a list of error strings; empty if valid."""
    errors: list[str] = []
    chain = _walk_inheritance(schema, type_id)
    if not chain:
        return [f"unknown_type: {type_id}"]
    all_props: dict = {}
    for td in reversed(chain):
        all_props.update(td.properties)
    for pname, pdef in all_props.items():
        if pdef.required and pname not in properties:
            errors.append(f"missing_required_property: {pname}")
        if pname in properties and pdef.enum_values:
            if properties[pname] not in pdef.enum_values:
                errors.append(f"invalid_enum_value: {pname}={properties[pname]}")
    return errors
