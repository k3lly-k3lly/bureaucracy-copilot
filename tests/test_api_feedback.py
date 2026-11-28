"""Tests for POST /feedback, with the database replaced by a fake."""

import pytest
from fastapi.testclient import TestClient

from copilot import main

VOTE = {
    "helpful": False,
    "question": "How long do I have to register?",
    "answer": "Within 14 days [1].",
    "refused": False,
    "cited_urls": ["https://service.berlin.de/dienstleistung/120686/"],
}


@pytest.fixture
def client(monkeypatch):
    saved = []

    def fake_save_feedback(conn, **vote):
        saved.append(vote)
        return len(saved)

    monkeypatch.setattr(main, "save_feedback", fake_save_feedback)
    main.app.dependency_overrides[main.get_db] = lambda: None
    test_client = TestClient(main.app)
    test_client.saved = saved
    yield test_client
    main.app.dependency_overrides.clear()


def test_feedback_is_saved(client):
    response = client.post("/feedback", json=VOTE)
    assert response.status_code == 201
    assert response.json() == {"id": 1}
    assert client.saved == [VOTE]


def test_cited_urls_are_optional(client):
    vote = {key: value for key, value in VOTE.items() if key != "cited_urls"}
    assert client.post("/feedback", json=vote).status_code == 201
    assert client.saved[0]["cited_urls"] == []


@pytest.mark.parametrize(
    "change",
    [
        {"helpful": None},  # the vote itself is required
        {"question": "Hi"},  # same 3-500 character limit as /ask
        {"answer": "x" * 4001},
        {"cited_urls": ["https://example.org"] * 11},
    ],
)
def test_invalid_feedback_is_rejected(client, change):
    response = client.post("/feedback", json={**VOTE, **change})
    assert response.status_code == 422
    assert client.saved == []


def test_browser_on_the_chat_page_may_send_feedback(client):
    # CORS preflight: the browser asks first whether localhost:3000 may POST here.
    response = client.options(
        "/feedback",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
