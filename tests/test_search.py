"""Tests for storing chunks (copilot/db.py) and searching them (copilot/search.py).

These need a running Postgres with pgvector (docker compose up -d db) and DATABASE_URL set.
They use tiny hand-made vectors instead of a real model, so the expected order is obvious:
the query vector points the same way as "anmeldung-1", so that chunk must come first.
"""

import os

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
    upsert_chunks,
)
from copilot.search import search  # noqa: E402


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
    with connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("DROP TABLE IF EXISTS chunks")
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
        yield connection
        connection.execute("DROP TABLE IF EXISTS chunks")
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


def test_results_carry_what_we_need_to_cite(conn):
    best = search(conn, one_hot(0), limit=1)[0]
    assert best.url == "https://example.berlin/anmeldung-1"
    assert best.section == "Section anmeldung-1"
    assert best.text == "Register within 14 days."
    assert best.topic == "anmeldung"
