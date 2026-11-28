"""Tests for the rate limiter, with a fake clock so no test has to wait a real minute."""

import httpx
import pytest
from fastapi.testclient import TestClient

from copilot import main
from copilot.ratelimit import MINUTE, RateLimiter, retry_after_header


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_blocks():
    limiter = RateLimiter(limit=3, window=MINUTE, clock=FakeClock())
    assert [limiter.hit("1.2.3.4") for _ in range(3)] == [0, 0, 0]
    assert limiter.hit("1.2.3.4") > 0


def test_says_how_long_to_wait_and_allows_again_after_the_window():
    clock = FakeClock()
    limiter = RateLimiter(limit=2, window=MINUTE, clock=clock)
    limiter.hit("a")  # t = 1000
    clock.now += 20
    limiter.hit("a")  # t = 1020
    clock.now += 10  # t = 1030: full
    assert limiter.hit("a") == pytest.approx(30)  # the first hit leaves the window at 1060
    clock.now += 30  # t = 1060
    assert limiter.hit("a") == 0


def test_blocked_requests_do_not_count():
    # Someone hammering the API while blocked must not extend their own wait forever.
    clock = FakeClock()
    limiter = RateLimiter(limit=1, window=MINUTE, clock=clock)
    limiter.hit("a")
    for _ in range(50):
        limiter.hit("a")
    clock.now += MINUTE
    assert limiter.hit("a") == 0


def test_each_visitor_has_their_own_count():
    limiter = RateLimiter(limit=1, window=MINUTE, clock=FakeClock())
    assert limiter.hit("1.1.1.1") == 0
    assert limiter.hit("1.1.1.1") > 0
    assert limiter.hit("2.2.2.2") == 0


def test_idle_visitors_are_forgotten():
    clock = FakeClock()
    limiter = RateLimiter(limit=5, window=MINUTE, clock=clock)
    for i in range(10_001):
        limiter.hit(f"visitor-{i}")
    clock.now += MINUTE + 1
    limiter.hit("new")  # over 10,000 known visitors: the idle ones are dropped
    assert len(limiter._hits) == 1


def test_retry_after_is_whole_seconds_rounded_up():
    assert retry_after_header(29.2) == {"Retry-After": "30"}
    assert retry_after_header(0.01) == {"Retry-After": "1"}


# --- through the API ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    calls = {"llm": 0}

    def llm(messages):
        calls["llm"] += 1
        return "Within 14 days [1]."

    monkeypatch.setattr(main, "hybrid_search", lambda *args, **kwargs: [_result()])
    monkeypatch.setattr(main, "save_feedback", lambda conn, **vote: 1)
    main.app.dependency_overrides[main.get_db] = lambda: None
    main.app.dependency_overrides[main.get_embedder] = lambda: lambda texts: [[0.0]]
    main.app.dependency_overrides[main.get_llm] = lambda: llm
    test_client = TestClient(main.app)
    test_client.calls = calls
    yield test_client
    main.app.dependency_overrides.clear()


def _result():
    from copilot.search import SearchResult

    return SearchResult(
        id="c1",
        url="https://example.berlin/a",
        topic="anmeldung",
        section="Deadlines",
        text="Register within 14 days.",
        similarity=0.7,
    )


def test_sixth_question_in_a_minute_gets_429_without_using_groq(client):
    limit = main.settings.ask_per_minute
    for _ in range(limit):
        assert client.post("/ask", json={"question": "How long?"}).status_code == 200
    response = client.post("/ask", json={"question": "How long?"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1
    assert client.calls["llm"] == limit  # the blocked question never reached Groq


def test_feedback_has_its_own_limit(client):
    for _ in range(main.settings.ask_per_minute):
        client.post("/ask", json={"question": "How long?"})
    vote = {"helpful": True, "question": "How long?", "answer": "x", "refused": False}
    assert client.post("/feedback", json=vote).status_code == 201  # asking didn't use it up


def test_groq_daily_limit_gets_its_own_error(client):
    def used_up(messages):
        request = httpx.Request("POST", "https://api.groq.com")
        text = "Rate limit reached on tokens per day (TPD)"
        response = httpx.Response(429, request=request, text=text)
        raise httpx.HTTPStatusError(
            f"Groq returned 429: {text}", request=request, response=response
        )

    main.app.dependency_overrides[main.get_llm] = lambda: used_up
    response = client.post("/ask", json={"question": "How long?"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "daily_limit"
