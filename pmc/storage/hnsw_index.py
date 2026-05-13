from __future__ import annotations
import os
import uuid
import json
from typing import Optional

_RESIZE_FACTOR = 2  # double capacity on overflow


class HNSWIndex:
    """Approximate nearest-neighbor index over node embeddings.

    Falls back to brute-force cosine similarity when hnswlib is missing,
    so the package can run in minimal environments at the cost of speed.

    Auto-resizes when capacity is exceeded — no manual tuning required.
    """

    def __init__(self, dim: int, capacity: int = 10000, persist_path: Optional[str] = None):
        self.dim = dim
        self.capacity = capacity
        self.persist_path = persist_path
        self._uuid_to_label: dict[str, int] = {}
        self._label_to_uuid: dict[int, str] = {}
        self._next_label = 0
        self._index = None
        self._fallback_vecs: dict[int, list[float]] = {}
        self._init_index()

    def _init_index(self) -> None:
        try:
            import hnswlib
            self._index = hnswlib.Index(space="cosine", dim=self.dim)
            self._index.init_index(max_elements=self.capacity, ef_construction=200, M=16)
            self._index.set_ef(50)
        except Exception:
            self._index = None

    def _resize(self) -> None:
        """Double the index capacity in place."""
        new_capacity = self.capacity * _RESIZE_FACTOR
        if self._index is not None:
            self._index.resize_index(new_capacity)
        self.capacity = new_capacity

    def add(self, nid: uuid.UUID, vec: list[float]) -> None:
        key = str(nid)
        if key in self._uuid_to_label:
            return
        label = self._next_label
        self._next_label += 1
        self._uuid_to_label[key] = label
        self._label_to_uuid[label] = key
        if self._index is not None:
            if label >= self.capacity:
                self._resize()
            self._index.add_items([vec], [label])
        else:
            self._fallback_vecs[label] = vec

    def query(self, vec: list[float], k: int = 10) -> list[tuple[uuid.UUID, float]]:
        if not self._uuid_to_label:
            return []
        if self._index is not None:
            k_eff = min(k, len(self._uuid_to_label))
            labels, dists = self._index.knn_query([vec], k=k_eff)
            out: list[tuple[uuid.UUID, float]] = []
            for lab, d in zip(labels[0], dists[0]):
                out.append((uuid.UUID(self._label_to_uuid[int(lab)]), float(1.0 - d)))
            return out
        # fallback: brute-force cosine over normalized vecs
        scores: list[tuple[int, float]] = []
        for lab, v in self._fallback_vecs.items():
            scores.append((lab, _cosine(vec, v)))
        scores.sort(key=lambda x: x[1], reverse=True)
        return [(uuid.UUID(self._label_to_uuid[lab]), s) for lab, s in scores[:k]]

    def save(self) -> None:
        if not self.persist_path:
            return
        os.makedirs(os.path.dirname(self.persist_path) or ".", exist_ok=True)
        meta_path = self.persist_path + ".meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "dim": self.dim,
                    "capacity": self.capacity,
                    "uuid_to_label": self._uuid_to_label,
                    "next_label": self._next_label,
                },
                f,
            )
        if self._index is not None:
            self._index.save_index(self.persist_path)

    def load(self) -> bool:
        """Load index from disk. Returns True if successful, False if files missing."""
        if not self.persist_path:
            return False
        meta_path = self.persist_path + ".meta.json"
        if not os.path.exists(self.persist_path) or not os.path.exists(meta_path):
            return False
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            saved_capacity = meta.get("capacity", self.capacity)
            # Use the larger of saved capacity and current setting
            load_capacity = max(saved_capacity, self.capacity)
            if self._index is not None:
                import hnswlib
                self._index = hnswlib.Index(space="cosine", dim=self.dim)
                self._index.load_index(self.persist_path, max_elements=load_capacity)
                self._index.set_ef(50)
                self.capacity = load_capacity
            self._uuid_to_label = meta["uuid_to_label"]
            self._label_to_uuid = {int(k): v for k, v in meta.get("label_to_uuid", {}).items()}
            # Rebuild reverse map if not persisted
            if not self._label_to_uuid:
                self._label_to_uuid = {v: k for k, v in self._uuid_to_label.items()}
            self._next_label = meta.get("next_label", len(self._uuid_to_label))
            return True
        except Exception:
            return False


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    s = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(x * x for x in b) ** 0.5 or 1.0
    return s / (na * nb)
