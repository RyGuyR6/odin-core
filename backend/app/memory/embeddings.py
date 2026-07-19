from __future__ import annotations
import hashlib, math, re
from dataclasses import dataclass

@dataclass(slots=True)
class EmbeddingResult:
    vector: list[float]
    model: str
    dimensions: int

class LocalHashEmbedder:
    """Deterministic, dependency-free semantic-ish embeddings for local operation and tests."""
    def __init__(self, dimensions: int = 256, model: str = "odin-hash-v1"):
        self.dimensions = dimensions; self.model = model
    def embed(self, text: str) -> EmbeddingResult:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9_]+", text.lower())
        for token in tokens:
            for feature in {token, *[token[i:i+3] for i in range(max(0, len(token)-2))]}:
                digest = hashlib.blake2b(feature.encode(), digest_size=16).digest()
                idx = int.from_bytes(digest[:8], "big") % self.dimensions
                sign = 1.0 if digest[8] & 1 else -1.0
                vector[idx] += sign
        norm = math.sqrt(sum(v*v for v in vector))
        if norm: vector = [v/norm for v in vector]
        return EmbeddingResult(vector, self.model, self.dimensions)

def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a: return 0.0
    return max(-1.0, min(1.0, sum(x*y for x,y in zip(a,b))))

def get_embedder(provider: str, model: str, dimensions: int):
    # local-hash is intentionally always available. External provider adapters can
    # be introduced later without changing persistence or retrieval interfaces.
    if provider not in {"local-hash", "hash", "local"}:
        raise ValueError(f"Unsupported memory embedding provider: {provider}")
    return LocalHashEmbedder(dimensions=dimensions, model=model)
