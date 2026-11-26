"""Tests for the POST /ask endpoint, with the database, model and Groq replaced by fakes."""

import httpx
import pytest
from fastapi.testclient import TestClient

from copilot import main
from copilot.embed import EMBEDDING_DIM
from copilot.search import SearchResult

RESULTS = [
    SearchResult(
        id="chunk-1",
        url="https://example.berlin/anmeldung",
        topic="anmeldung",
        section="Deadlines",
        text="You must register within 14 days of moving in.",
        similarity=0.7,
        score=0.03,
    )
]


@pytest.fixture
def client(monkeypatch):
    searches = []

    def fake_hybrid_search(conn, question, embedding, limit, topic):
        searches.append({"question": question, "topic": topic})
        return RESULTS

    monkeypatch.setattr(main, "hybrid_search", fake_hybrid_search)
    main.app.dependency_overrides[main.get_db] = lambda: None
    main.app.dependency_overrides[main.get_embedder] = lambda: lambda texts: [[0.0] * EMBEDDING_DIM]
    main.app.dependency_overrides[main.get_llm] = lambda: lambda messages: "Within 14 days [1]."
    test_client = TestClient(main.app)
    test_client.searches = searches
    yield test_client
    main.app.dependency_overrides.clear()


def test_ask_returns_answer_with_citation(client):
    response = client.post("/ask", json={"question": "How long do I have to register?"})
    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is False
    assert body["answer"] == "Within 14 days [1]."
    assert body["citations"][0]["url"] == "https://example.berlin/anmeldung"


def test_topic_is_passed_to_search(client):
    client.post("/ask", json={"question": "How long?", "topic": "anmeldung"})
    assert client.searches[-1]["topic"] == "anmeldung"


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "Hi"},  # too short
        {"question": "x" * 501},  # too long
        {"question": "How long?", "topic": "cooking"},  # unknown topic
        {},  # missing question
    ],
)
def test_invalid_requests_are_rejected(client, payload):
    assert client.post("/ask", json=payload).status_code == 422


def test_missing_groq_key_gives_clear_503(client, monkeypatch):
    del main.app.dependency_overrides[main.get_llm]
    monkeypatch.setattr(main.settings, "groq_api_key", None)
    response = client.post("/ask", json={"question": "How long do I have?"})
    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]


def test_rate_limited_llm_gives_503_not_a_crash(client):
    def rate_limited(messages):
        request = httpx.Request("POST", "https://api.groq.com")
        raise httpx.HTTPStatusError("429", request=request, response=httpx.Response(429))

    main.app.dependency_overrides[main.get_llm] = lambda: rate_limited
    response = client.post("/ask", json={"question": "How long do I have?"})
    assert response.status_code == 503
    assert "busy" in response.json()["detail"]
