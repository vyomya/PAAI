"""
Embedding generation.

ChromaDB used to do this for you implicitly via
SentenceTransformerEmbeddingFunction. With pgvector you generate the vector
yourself and hand it to Postgres.

Same model as before (all-MiniLM-L6-v2, 384-dim) so your migrated history
stays comparable with anything embedded from here on. If you ever change the
model you must change settings.embedding_dim, run a migration to alter the
vector column, and re-embed every existing row.
"""
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from config import settings


@lru_cache
def _model() -> SentenceTransformer:
    # Loading takes a few seconds and ~90MB RAM; cached for process lifetime.
    return SentenceTransformer(settings.embedding_model)


def embed(text: str) -> list[float]:
    return _model().encode(text, normalize_embeddings=True).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = _model().encode(texts, normalize_embeddings=True, batch_size=64)
    return [v.tolist() for v in vectors]
