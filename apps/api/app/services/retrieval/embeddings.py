"""Query embedding for vector retrieval."""

from app.services.ingestion import _create_embeddings


def embed_query(query: str) -> list[float]:
    """Embed a single query string. Returns embedding vector."""
    embeddings = _create_embeddings([query])
    return embeddings[0]
