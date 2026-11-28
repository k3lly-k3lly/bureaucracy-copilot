"""Tests for storing and reading feedback in Postgres (copilot/db.py).

Like test_search.py, these run in a temporary schema, so real feedback is never touched.
"""

import os
import uuid

import pytest

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set"),
]

from copilot.db import connect, recent_feedback, save_feedback  # noqa: E402


@pytest.fixture
def conn():
    schema = f"test_{uuid.uuid4().hex[:8]}"
    with connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(f"CREATE SCHEMA {schema}")
        connection.execute(f"SET search_path TO {schema}, public")
        connection.commit()
        try:
            yield connection
        finally:
            connection.rollback()
            connection.execute(f"DROP SCHEMA {schema} CASCADE")
            connection.commit()


def vote(helpful: bool, question: str = "How long do I have to register?") -> dict:
    return {
        "helpful": helpful,
        "question": question,
        "answer": "Within 14 days [1].",
        "refused": False,
        "cited_urls": ["https://service.berlin.de/dienstleistung/120686/"],
    }


def test_first_vote_creates_the_table(conn):
    # No table exists yet in the fresh schema: saving must still work.
    feedback_id = save_feedback(conn, **vote(True))
    assert isinstance(feedback_id, int)
    rows = recent_feedback(conn)
    assert len(rows) == 1
    _, _, helpful, question, _, refused, cited_urls = rows[0]
    assert (helpful, question, refused) == (True, "How long do I have to register?", False)
    assert cited_urls == ["https://service.berlin.de/dienstleistung/120686/"]


def test_newest_first_and_filter_unhelpful(conn):
    save_feedback(conn, **vote(True, "first?"))
    save_feedback(conn, **vote(False, "second?"))
    save_feedback(conn, **vote(False, "third?"))
    assert [row[3] for row in recent_feedback(conn)] == ["third?", "second?", "first?"]
    assert [row[3] for row in recent_feedback(conn, helpful=False)] == ["third?", "second?"]
    assert [row[3] for row in recent_feedback(conn, limit=1)] == ["third?"]
