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

    def _resize(self, min_capacity: Optional[int] = None) -> None:
        """Grow index capacity. Doubles until STRICTLY GREATER than min_capacity.

        A single doubling is NOT enough when the label is far beyond 2x capacity —
        e.g. after an index reset/reload leaves next_label >> capacity (the 2026-06-03
        freeze: capacity=20000 but next_label=608097, so one 20000->40000 doubling
        still failed and crashed every ingest/checkpoint). Looping until we clear the
        label makes the index genuinely self-healing as the docstring promises."""
        new_capacity = self.capacity * _RESIZE_FACTOR
        if min_capacity is not None:
            while new_capacity <= min_capacity:
                new_capacity *= _RESIZE_FACTOR
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
                self._resize(min_capacity=label)
            try:
                self._index.add_items([vec], [label])
            except RuntimeError:
                # Belt-and-suspenders: hnswlib raises "exceeds max_elements" if the
                # label still overshoots capacity (capacity/label drift after a
                # reload). Grow past the label and retry once so a single bad add can
                # never silently freeze the whole ingest/checkpoint pipeline again.
                self._resize(min_capacity=label)
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
        # Atomic writes (temp file + os.replace): a process killed mid-save can otherwise
        # truncate the live index/meta to 0 bytes — the recurring corruption ROOT CAUSE
        # (hnsw.bin → 0 on 2026-06-09 froze PMC; see .corrupted-*/.frozen-* history).
        # os.replace is atomic within the same filesystem, so the live files are never partial.
        tmp_meta = meta_path + ".tmp"
        with open(tmp_meta, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "dim": self.dim,
                    "capacity": self.capacity,
                    "uuid_to_label": self._uuid_to_label,
                    "next_label": self._next_label,
                },
                f,
            )
        os.replace(tmp_meta, meta_path)
        if self._index is not None:
            tmp_idx = self.persist_path + ".tmp"
            self._index.save_index(tmp_idx)
            os.replace(tmp_idx, self.persist_path)

    def load(self) -> bool:
        """Load index from disk. Returns True if successful, False if files missing."""
        if not self.persist_path:
            return False
        meta_path = self.persist_path + ".meta.json"
        if not os.path.exists(self.persist_path) or not os.path.exists(meta_path):
            return False
        # A 0-byte / truncated index file makes hnswlib.load_index() SEGFAULT (a C++ crash
        # the try/except below CANNOT catch — it kills the process). This recurred for weeks
        # (see hnsw.bin.corrupted-*/.frozen-* backups; froze PMC on 2026-06-09 03:03 when
        # hnsw.bin → 0 bytes). Treat an empty/too-small index as missing so the caller's
        # slow-path rebuilds it from the SQLite embeddings (data is intact in m.db).
        try:
            if os.path.getsize(self.persist_path) == 0:
                return False
        except OSError:
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
            # load_index() above already reassigned self._index to a FRESH but
            # UNINITIALIZED hnswlib.Index (line: self._index = hnswlib.Index(...))
            # and then threw before init completed. The caller's slow-path rebuild
            # (_rehydrate_index) then calls add()->add_items() on that zombie index,
            # which SEGFAULTs in C++ (uninitialized index = null deref →
            # "segfault at 0 ... error 4 in hnswlib...so"). This is the 2026-06-16
            # corruption mode: hnsw.bin is non-zero but "corrupted or unsupported",
            # so the size==0 guard above misses it and EVERY checkpoint/ingest
            # crashed the whole process (PMC checkpoints silently dead for ~39h).
            # Re-initialise a clean EMPTY index at a modest capacity (auto-resizes
            # during rebuild) so the slow-path can repopulate it from the intact
            # m.db embeddings. Strictly safer: turns a fatal crash into self-healing.
            self.capacity = 10000
            self._uuid_to_label = {}
            self._label_to_uuid = {}
            self._next_label = 0
            self._init_index()
            return False


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    s = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(x * x for x in b) ** 0.5 or 1.0
    return s / (na * nb)
