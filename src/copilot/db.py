"""Database helpers: connection, schema, writing chunks with their embeddings, and feedback."""

import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql

from copilot.embed import EMBEDDING_DIM  # the table's vector size must match the model

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,          -- stable: hash of the URL + position on the page
    url         TEXT NOT NULL,
    topic       TEXT NOT NULL,
    language    TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    section     TEXT NOT NULL DEFAULT '',
    text        TEXT NOT NULL,
    position    INTEGER NOT NULL,
    fetched_at  TIMESTAMPTZ,
    embedding   vector({EMBEDDING_DIM}) NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- HNSW index: makes "find the most similar vectors" fast, using cosine distance.
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS chunks_topic_idx ON chunks (topic);

-- Keyword search: a tsvector is the text split into normalised words ("Anmeldungen" -> "anmeld").
-- German pages use German word rules, English pages English ones. Postgres keeps it up to date
-- automatically (GENERATED), and ADD COLUMN IF NOT EXISTS upgrades databases made in Week 2.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS search_tsv tsvector GENERATED ALWAYS AS (
    to_tsvector(
        CASE WHEN language = 'de' THEN 'german'::regconfig ELSE 'english'::regconfig END,
        title || ' ' || section || ' ' || text
    )
) STORED;

CREATE INDEX IF NOT EXISTS chunks_search_tsv_idx ON chunks USING gin (search_tsv);
"""

# "Was this helpful?" clicks from the chat page. Only what the visitor sees on screen is kept:
# no IP address, no browser details, no account. The question can still contain personal
# details someone typed in, so the page tells visitors what is sent before they click.
FEEDBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    helpful     BOOLEAN NOT NULL,
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL,
    refused     BOOLEAN NOT NULL,
    cited_urls  TEXT[] NOT NULL DEFAULT '{}'
);
"""

UPSERT = """
INSERT INTO chunks (id, url, topic, language, title, section, text, position, fetched_at, embedding)
VALUES (%(id)s, %(url)s, %(topic)s, %(language)s, %(title)s, %(section)s, %(text)s,
        %(position)s, %(fetched_at)s, %(embedding)s)
ON CONFLICT (id) DO UPDATE SET
    url = EXCLUDED.url, topic = EXCLUDED.topic, language = EXCLUDED.language,
    title = EXCLUDED.title, section = EXCLUDED.section, text = EXCLUDED.text,
    position = EXCLUDED.position, fetched_at = EXCLUDED.fetched_at,
    embedding = EXCLUDED.embedding, updated_at = now()
"""


def connect(database_url: str) -> psycopg.Connection:
    """Open a connection that understands the pgvector 'vector' type."""
    conn = psycopg.connect(database_url, connect_timeout=5)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def stored_embedding_dim(conn: psycopg.Connection) -> int | None:
    """Vector size of the existing chunks table, or None if there is no table yet.

    For a vector(n) column Postgres stores n as the column's "type modifier".
    Only the current schema is checked, never another schema further down the
    search_path: tests run in their own schema and must not see (or drop!) the real table.
    """
    row = conn.execute(
        "SELECT atttypmod FROM pg_attribute "
        "WHERE attrelid = to_regclass(quote_ident(current_schema()) || '.chunks') "
        "AND attname = 'embedding'"
    ).fetchone()
    return row[0] if row else None


def current_schema(conn: psycopg.Connection) -> str:
    return conn.execute("SELECT current_schema()").fetchone()[0]


def init_schema(conn: psycopg.Connection) -> bool:
    """Create the table and indexes. Returns True if an old table had to be rebuilt.

    When we switch to an embedding model with a different vector size, the old vectors
    can't be compared with new ones, so the table is dropped and rebuilt. Nothing is lost:
    `ingest load` re-creates every row from data/processed/chunks.jsonl.
    """
    existing = stored_embedding_dim(conn)
    rebuilt = existing is not None and existing != EMBEDDING_DIM
    if rebuilt:
        conn.execute(sql.SQL("DROP TABLE {}.chunks").format(sql.Identifier(current_schema(conn))))
    conn.execute(SCHEMA)
    conn.commit()
    return rebuilt


def upsert_chunks(conn: psycopg.Connection, records: list[dict], embeddings) -> None:
    """Insert new chunks or update existing ones (same id). Safe to run again and again."""
    if len(records) != len(embeddings):
        raise ValueError(f"{len(records)} records but {len(embeddings)} embeddings")
    rows = [{**r, "embedding": e} for r, e in zip(records, embeddings, strict=True)]
    with conn.cursor() as cur:
        cur.executemany(UPSERT, rows)
    conn.commit()


def delete_chunks_not_in(conn: psycopg.Connection, keep_ids: list[str]) -> int:
    """Remove chunks that are no longer produced (e.g. a source was removed). Returns count."""
    deleted = conn.execute("DELETE FROM chunks WHERE NOT (id = ANY(%s))", (keep_ids,)).rowcount
    conn.commit()
    return deleted


def count_chunks(conn: psycopg.Connection) -> int:
    return conn.execute("SELECT count(*) FROM chunks").fetchone()[0]


def save_feedback(
    conn: psycopg.Connection,
    *,
    helpful: bool,
    question: str,
    answer: str,
    refused: bool,
    cited_urls: list[str],
) -> int:
    """Store one "was this helpful?" click and return its id.

    Creates the table on first use, so the API works without running `ingest load` first.
    """
    conn.execute(FEEDBACK_SCHEMA)
    row = conn.execute(
        "INSERT INTO feedback (helpful, question, answer, refused, cited_urls) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (helpful, question, answer, refused, cited_urls),
    ).fetchone()
    conn.commit()
    return row[0]


def recent_feedback(conn: psycopg.Connection, limit: int = 20, helpful: bool | None = None):
    """Newest feedback first; pass helpful=False to see only the answers people disliked."""
    conn.execute(FEEDBACK_SCHEMA)
    query = "SELECT id, created_at, helpful, question, answer, refused, cited_urls FROM feedback"
    params: list = []
    if helpful is not None:
        query += " WHERE helpful = %s"
        params.append(helpful)
    query += " ORDER BY id DESC LIMIT %s"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def check_database(database_url: str) -> dict:
    """Connect to Postgres and confirm the pgvector extension is installed."""
    with psycopg.connect(database_url, connect_timeout=5) as conn:
        server_version = conn.execute("SHOW server_version").fetchone()[0]
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
    return {
        "postgres_version": server_version,
        "pgvector_version": row[0] if row else None,
    }
