from __future__ import annotations
import hashlib
import os
from typing import Optional


_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_DIM = 384


class Embedder:
    """Wraps sentence-transformers. Falls back to a deterministic hash-based
    pseudo-embedding when the model cannot be loaded (e.g. offline). The
    fallback is stable for tests but not semantically meaningful."""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or os.environ.get("PMC_EMBED_MODEL", _DEFAULT_MODEL)
        self.dim = _DIM
        self._model = None
        self._load()

    def _load(self) -> None:
        if os.environ.get("PMC_EMBED_MODE") == "fallback":
            self._model = None
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self.dim = int(self._model.get_sentence_embedding_dimension())
        except Exception:
            # offline / missing model — use fallback
            self._model = None

    def encode(self, text: str) -> list[float]:
        if self._model is not None:
            v = self._model.encode([text], convert_to_numpy=True, normalize_embeddings=True)[0]
            return v.tolist()
        return self._hash_embed(text)

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        if self._model is not None:
            arr = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            return [v.tolist() for v in arr]
        return [self._hash_embed(t) for t in texts]

    def _hash_embed(self, text: str) -> list[float]:
        # Deterministic pseudo-embedding for offline/test mode.
        # Generates a unit vector seeded by sha256 of text.
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Expand to dim floats by repeating hash bytes, then map to [-1, 1].
        out: list[float] = []
        i = 0
        while len(out) < self.dim:
            out.append((h[i % len(h)] / 255.0) * 2.0 - 1.0)
            i += 1
        # Normalize to unit length
        s = sum(x * x for x in out) ** 0.5 or 1.0
        return [x / s for x in out]


_SINGLETON: Optional[Embedder] = None


def get_embedder() -> Embedder:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = Embedder()
    return _SINGLETON
