from __future__ import annotations
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional
from pmc.models import Node, Edge, Content, ProvenanceRecord, UncertaintyRecord, Assertion


class StorageBackend(ABC):
    @abstractmethod
    def init_schema(self) -> None: ...

    @abstractmethod
    def insert_node(self, node: Node) -> None: ...

    @abstractmethod
    def get_node(self, node_id: uuid.UUID) -> Optional[Node]: ...

    @abstractmethod
    def update_node(self, node: Node) -> None: ...

    @abstractmethod
    def deprecate_node(self, node_id: uuid.UUID) -> None: ...

    @abstractmethod
    def insert_edge(self, edge: Edge) -> None: ...

    @abstractmethod
    def get_edges_out(self, node_id: uuid.UUID, rel_type: Optional[str] = None) -> list[Edge]: ...

    @abstractmethod
    def get_edges_in(self, node_id: uuid.UUID, rel_type: Optional[str] = None) -> list[Edge]: ...

    @abstractmethod
    def find_by_property(self, type_id: str, prop: str, value: Any) -> list[Node]: ...

    @abstractmethod
    def find_by_type(self, type_id: str, include_deprecated: bool = False) -> list[Node]: ...

    @abstractmethod
    def insert_content(self, content: Content) -> None: ...

    @abstractmethod
    def get_content(self, content_id: uuid.UUID) -> Optional[Content]: ...

    @abstractmethod
    def insert_provenance(self, prov: ProvenanceRecord) -> None: ...

    @abstractmethod
    def get_provenance(self, prov_id: uuid.UUID) -> Optional[ProvenanceRecord]: ...

    @abstractmethod
    def upsert_uncertainty(self, u: UncertaintyRecord) -> None: ...

    @abstractmethod
    def get_uncertainty(self, node_id: uuid.UUID) -> Optional[UncertaintyRecord]: ...

    @abstractmethod
    def insert_assertion(self, a: Assertion) -> None: ...

    @abstractmethod
    def count_by_type(self, type_id: str) -> int: ...

    @abstractmethod
    def all_nodes(self, include_deprecated: bool = False) -> list[Node]: ...
