"""Tests for storing chunks (copilot/db.py) and searching them (copilot/search.py).

These need a running Postgres with pgvector (docker compose up -d db) and DATABASE_URL set.
They use tiny hand-made vectors instead of a real model, so the expected order is obvious:
the query vector points the same way as "anmeldung-1", so that chunk must come first.
"""

import os
import uuid

import pytest

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set"),
]

from copilot.db import (  # noqa: E402
    EMBEDDING_DIM,
    connect,
    count_chunks,
    delete_chunks_not_in,
    init_schema,
    stored_embedding_dim,
    upsert_chunks,
)
from copilot.search import hybrid_search, search  # noqa: E402


def one_hot(index: int, weight: float = 1.0) -> list[float]:
    """A vector pointing along one axis, e.g. one_hot(0) = [1, 0, 0, ...]."""
    vector = [0.0] * EMBEDDING_DIM
    vector[index] = weight
    return vector


def record(id_: str, topic: str, text: str) -> dict:
    return {
        "id": id_,
        "url": f"https://example.berlin/{id_}",
        "topic": topic,
        "language": "en",
        "title": "Test page",
        "section": f"Section {id_}",
        "text": text,
        "position": 0,
        "fetched_at": "2026-11-23T12:00:00+00:00",
    }


@pytest.fixture
def conn():
    """A connection whose `chunks` table lives in a temporary, private schema.

    A schema is a separate namespace inside the database. The tests create their own
    (e.g. test_3f9a1c2b), point the connection at it with search_path, and drop it at the end.
    Your real `chunks` table in the public schema is never touched.
    """
    schema = f"test_{uuid.uuid4().hex[:8]}"
    with connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(f"CREATE SCHEMA {schema}")
        # Look for tables in the test schema first; `public` is still needed for the vector type.
        connection.execute(f"SET search_path TO {schema}, public")
        connection.commit()
        init_schema(connection)
        upsert_chunks(
            connection,
            [
                record("anmeldung-1", "anmeldung", "Register within 14 days."),
                record("anmeldung-2", "anmeldung", "Registration is free of charge."),
                record("renting-1", "renting", "The deposit is at most three months' rent."),
            ],
            [
                one_hot(0),  # same direction as the query below
                [0.7, 0.7] + [0.0] * (EMBEDDING_DIM - 2),  # halfway between axis 0 and 1
                one_hot(1),  # a different direction
            ],
        )
        try:
            yield connection
        finally:
            connection.rollback()
            connection.execute(f"DROP SCHEMA {schema} CASCADE")
            connection.commit()


# --- storing (db.py, already written) ----------------------------------------


def test_upsert_is_idempotent(conn):
    upsert_chunks(conn, [record("anmeldung-1", "anmeldung", "Updated text.")], [one_hot(0)])
    assert count_chunks(conn) == 3  # updated, not duplicated
    text = conn.execute("SELECT text FROM chunks WHERE id = 'anmeldung-1'").fetchone()[0]
    assert text == "Updated text."


def test_removed_chunks_are_deleted(conn):
    removed = delete_chunks_not_in(conn, ["anmeldung-1", "anmeldung-2"])
    assert removed == 1
    assert count_chunks(conn) == 2


# --- searching (search.py) ------------------------------------


def test_most_similar_chunk_comes_first(conn):
    results = search(conn, one_hot(0), limit=3)
    assert [r.id for r in results] == ["anmeldung-1", "anmeldung-2", "renting-1"]


def test_similarity_is_one_for_identical_direction(conn):
    best = search(conn, one_hot(0), limit=1)[0]
    assert best.similarity == pytest.approx(1.0, abs=1e-6)


def test_limit_is_respected(conn):
    assert len(search(conn, one_hot(0), limit=2)) == 2


def test_topic_filter(conn):
    results = search(conn, one_hot(0), limit=5, topic="renting")
    assert [r.id for r in results] == ["renting-1"]


def test_hybrid_search_boosts_exact_keyword_matches(conn):
    # The query vector points at "anmeldung-1", but the words match "renting-1".
    # Hybrid search must rank renting-1 high thanks to the keyword match.
    results = hybrid_search(conn, "deposit three months rent", one_hot(0), limit=3)
    ids = [r.id for r in results]
    assert "renting-1" in ids[:2]
    assert all(isinstance(r.score, float) and r.score > 0 for r in results)


def test_hybrid_search_finds_german_words_from_a_german_question(conn):
    upsert_chunks(
        conn,
        [
            {
                **record("renting-de", "renting", "Mietkaution: höchstens drei Monatsmieten."),
                "language": "de",
            }
        ],
        [one_hot(5)],
    )
    results = hybrid_search(conn, "Wie hoch darf die Mietkaution sein?", one_hot(9), limit=1)
    assert results[0].id == "renting-de"


def test_hybrid_search_respects_topic_filter(conn):
    results = hybrid_search(conn, "deposit", one_hot(0), limit=5, topic="anmeldung")
    assert {r.topic for r in results} == {"anmeldung"}


def test_hybrid_search_is_safe_with_odd_input(conn):
    assert len(hybrid_search(conn, "x'; DROP TABLE chunks; --", one_hot(0), limit=3)) == 3
    assert len(hybrid_search(conn, "", one_hot(0), limit=3)) == 3
    assert count_chunks(conn) == 3  # table untouched


def test_results_carry_what_we_need_to_cite(conn):
    best = search(conn, one_hot(0), limit=1)[0]
    assert best.url == "https://example.berlin/anmeldung-1"
    assert best.section == "Section anmeldung-1"
    assert best.text == "Register within 14 days."
    assert best.topic == "anmeldung"


def test_tests_use_a_private_schema_not_the_real_table(conn):
    """Regression test: an earlier version of these tests dropped the real `chunks` table."""
    schema = conn.execute("SELECT current_schema()").fetchone()[0]
    assert schema.startswith("test_")
    table_schema = conn.execute(
        "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE c.oid = to_regclass('chunks')"
    ).fetchone()[0]
    assert table_schema == schema  # `chunks` resolves to the test schema, not public


def test_table_with_old_vector_size_is_rebuilt(conn):
    # Switching embedding models changes the vector size; old vectors must not survive.
    conn.execute("DROP TABLE chunks")
    conn.execute("CREATE TABLE chunks (id TEXT PRIMARY KEY, embedding vector(3))")
    conn.commit()
    assert stored_embedding_dim(conn) == 3
    assert init_schema(conn) is True
    assert stored_embedding_dim(conn) == EMBEDDING_DIM
    assert init_schema(conn) is False  # second run: nothing to rebuild


def test_rebuild_never_touches_chunks_in_another_schema(conn):
    # Like the real `public.chunks` seen from a test schema: further down the search_path.
    other = f"other_{uuid.uuid4().hex[:8]}"
    fresh = f"fresh_{uuid.uuid4().hex[:8]}"
    conn.execute(f"CREATE SCHEMA {other}")
    conn.execute(f"CREATE TABLE {other}.chunks (id TEXT PRIMARY KEY, embedding vector(3))")
    conn.execute(f"CREATE SCHEMA {fresh}")
    conn.execute(f"SET search_path TO {fresh}, {other}, public")
    conn.commit()
    try:
        assert init_schema(conn) is False  # `fresh` had no table: created, nothing dropped
        dims = conn.execute(
            "SELECT atttypmod FROM pg_attribute "
            f"WHERE attrelid = '{other}.chunks'::regclass AND attname = 'embedding'"
        ).fetchone()
        assert dims == (3,)  # the other schema's table is untouched
    finally:
        conn.execute(f"DROP SCHEMA {fresh} CASCADE")
        conn.execute(f"DROP SCHEMA {other} CASCADE")
        conn.commit()
