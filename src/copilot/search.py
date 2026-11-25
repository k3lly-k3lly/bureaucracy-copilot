"""Finding the chunks that answer a question.

Two ways of searching, each good at something different:

* Semantic (vector) search finds passages with the same MEANING, even across languages:
  "register my address" finds "Wohnsitz anmelden".
* Keyword (full-text) search finds passages containing the exact WORDS, which matters for
  specific terms like "Kaution", "Sperrkonto" or "§ 551" that meaning-search can blur.

hybrid_search() runs both and merges the two rankings with Reciprocal Rank Fusion (RRF).
"""

from dataclasses import dataclass

RRF_K = 60  # standard constant: dampens the influence of exact rank positions
CANDIDATES = 20  # how many results each method contributes before merging


@dataclass
class SearchResult:
    id: str
    url: str
    topic: str
    section: str
    text: str
    similarity: float  # cosine similarity to the question: 1.0 = same meaning, ~0 = unrelated
    score: float = 0.0  # hybrid ranking score (higher = better); 0 for plain vector search


def search(conn, query_embedding, limit: int = 5, topic: str | None = None) -> list[SearchResult]:
    """Semantic search only: the `limit` chunks closest in meaning, best first.

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


HYBRID_SQL = """
WITH
query AS (
    -- The question could be English or German, so build the keyword query both ways.
    -- plainto_tsquery joins words with AND (&): every word must appear, which is too strict
    -- for a natural question. Swapping & for | means "any of these words" instead;
    -- ts_rank_cd still ranks passages that contain more of them higher.
    SELECT to_tsquery('english', replace(plainto_tsquery('english', %(q)s)::text, '&', '|'))
        || to_tsquery('german', replace(plainto_tsquery('german', %(q)s)::text, '&', '|')) AS tsq
),
semantic AS (
    SELECT id, row_number() OVER (ORDER BY embedding <=> %(emb)s::vector) AS rank
    FROM chunks
    WHERE %(topic)s::text IS NULL OR topic = %(topic)s
    ORDER BY embedding <=> %(emb)s::vector
    LIMIT %(candidates)s
),
keyword AS (
    SELECT id, row_number() OVER (ORDER BY ts_rank_cd(search_tsv, query.tsq) DESC) AS rank
    FROM chunks, query
    WHERE search_tsv @@ query.tsq
      AND (%(topic)s::text IS NULL OR topic = %(topic)s)
    ORDER BY ts_rank_cd(search_tsv, query.tsq) DESC
    LIMIT %(candidates)s
),
fused AS (
    -- Reciprocal Rank Fusion: each list adds 1 / (k + rank). A chunk ranked well by BOTH
    -- methods collects two contributions and rises to the top.
    SELECT id, sum(1.0 / (%(k)s + rank)) AS score
    FROM (SELECT * FROM semantic UNION ALL SELECT * FROM keyword) AS both_lists
    GROUP BY id
)
SELECT c.id, c.url, c.topic, c.section, c.text,
       1 - (c.embedding <=> %(emb)s::vector) AS similarity,
       fused.score::float8 AS score
FROM fused
JOIN chunks AS c USING (id)
ORDER BY fused.score DESC
LIMIT %(limit)s
"""


def hybrid_search(
    conn, question: str, query_embedding, limit: int = 5, topic: str | None = None
) -> list[SearchResult]:
    """Semantic + keyword search merged with Reciprocal Rank Fusion, best first."""
    params = {
        "q": question,
        "emb": query_embedding,
        "topic": topic,
        "candidates": CANDIDATES,
        "k": RRF_K,
        "limit": limit,
    }
    rows = conn.execute(HYBRID_SQL, params).fetchall()
    return [SearchResult(*row) for row in rows]
