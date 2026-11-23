"""Semantic search: find the chunks whose meaning is closest to a question."""

from dataclasses import dataclass


@dataclass
class SearchResult:
    id: str
    url: str
    topic: str
    section: str
    text: str
    similarity: float


def search(conn, query_embedding, limit: int = 5, topic: str | None = None) -> list[SearchResult]:
    """Return the `limit` chunks most similar to query_embedding, best first.

    - `<=>` is pgvector's cosine distance: 0 = same direction (same meaning).
      Ordering by it, smallest first, gives the most similar chunks first.
    - similarity = 1 - distance, so 1.0 means identical meaning.
    - `WHERE %s IS NULL OR topic = %s` makes the topic filter optional.
    - Values are passed as %s parameters, never pasted into the SQL string,
      which protects against SQL injection.
    """
    sql = """
        SELECT id, url, topic, section, text, 1 - (embedding <=> %s::vector) AS similarity
        FROM chunks
        WHERE %s::text IS NULL OR topic = %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    rows = conn.execute(sql, (query_embedding, topic, topic, query_embedding, limit)).fetchall()
    return [SearchResult(*row) for row in rows]
