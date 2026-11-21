"""Database helpers. Kept tiny in Week 1: just a connection and a health check."""

import psycopg


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
