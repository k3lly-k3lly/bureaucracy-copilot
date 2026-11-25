"""Database helpers: connection, schema, and writing chunks with their embeddings."""

import psycopg
from pgvector.psycopg import register_vector

EMBEDDING_DIM = 384  # must match the embedding model (see copilot/embed.py)

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


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA)
    conn.commit()


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
