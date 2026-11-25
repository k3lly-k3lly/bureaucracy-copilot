"""Tests for answer generation. A fake LLM stands in for Groq, so no API key or internet needed."""

import json

import httpx
import pytest

from copilot.answer import (
    MIN_SIMILARITY,
    REFUSAL_MARKER,
    answer_question,
    build_messages,
    groq_llm,
    normalize_citations,
    parse_citations,
)
from copilot.search import SearchResult


def result(n: int, text: str, similarity: float = 0.7) -> SearchResult:
    return SearchResult(
        id=f"chunk-{n}",
        url=f"https://example.berlin/page-{n}",
        topic="anmeldung",
        section=f"Section {n}",
        text=text,
        similarity=similarity,
    )


RESULTS = [
    result(1, "You must register within 14 days of moving in."),
    result(2, "Registration is free of charge."),
]


def fake_llm(reply: str):
    calls: list[list[dict]] = []

    def llm(messages: list[dict]) -> str:
        calls.append(messages)
        return reply

    return llm, calls


def must_not_be_called(messages):
    raise AssertionError("the LLM should not be called")


# --- building the prompt -----------------------------------------------------------------


def test_prompt_numbers_passages_and_includes_question_and_sources():
    messages = build_messages("How long do I have?", RESULTS)
    assert messages[0]["role"] == "system"
    assert REFUSAL_MARKER in messages[0]["content"]
    user = messages[1]["content"]
    assert "[1] Source: https://example.berlin/page-1 (Section 1)" in user
    assert "[2] Source: https://example.berlin/page-2" in user
    assert "Question: How long do I have?" in user
    assert user.endswith("Answer in English.")


# --- citations ---------------------------------------------------------------------------


def test_parse_citations_keeps_valid_numbers_in_order_of_use():
    assert parse_citations("Free [2]. Within 14 days [1][2].", passage_count=2) == [2, 1]


def test_parse_citations_ignores_numbers_that_point_nowhere():
    assert parse_citations("Claim [1]. Invented [7].", passage_count=2) == [1]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Three months' rent 【1】.", "Three months' rent [1]."),
        ("Three months' rent 【1†L4-L6】.", "Three months' rent [1]."),
        ("Three months' rent [1†source].", "Three months' rent [1]."),
        ("Three months' rent [Passage 2].", "Three months' rent [2]."),
        ("Free [1, 2].", "Free [1][2]."),
        ("Free [1-3].", "Free [1][2][3]."),
        ("Already fine [1][2].", "Already fine [1][2]."),
    ],
)
def test_normalize_citations_accepts_other_styles(raw, expected):
    assert normalize_citations(raw) == expected


def test_answer_with_gpt_oss_style_citations_is_accepted():
    llm, _ = fake_llm("Die Kaution darf höchstens drei Monatsmieten betragen 【1】.")
    answer = answer_question("Wie hoch darf die Kaution sein?", RESULTS, llm)
    assert not answer.refused
    assert answer.text.endswith("betragen [1].")
    assert [c.number for c in answer.citations] == [1]


# --- answering ---------------------------------------------------------------------------


def test_good_answer_returns_text_and_citations():
    llm, calls = fake_llm("You must register within 14 days [1]. It is free [2].")
    answer = answer_question("How long do I have?", RESULTS, llm)
    assert not answer.refused
    assert answer.text == "You must register within 14 days [1]. It is free [2]."
    assert [c.number for c in answer.citations] == [1, 2]
    assert answer.citations[0].url == "https://example.berlin/page-1"
    assert len(calls) == 1


def test_invalid_citation_markers_are_removed_from_the_text():
    llm, _ = fake_llm("Within 14 days [1][5].")
    answer = answer_question("How long?", RESULTS, llm)
    assert answer.text == "Within 14 days [1]."
    assert [c.number for c in answer.citations] == [1]


def test_refuses_without_calling_llm_when_nothing_found():
    answer = answer_question("Anything?", [], must_not_be_called)
    assert answer.refused
    assert answer.citations == []


def test_refuses_without_calling_llm_when_passages_are_unrelated():
    weak = [result(1, "Unrelated text.", similarity=MIN_SIMILARITY - 0.05)]
    answer = answer_question("Which bank is best?", weak, must_not_be_called)
    assert answer.refused
    assert "similarity" in answer.reason


def test_refuses_when_model_says_not_in_sources():
    llm, _ = fake_llm(REFUSAL_MARKER)
    answer = answer_question("Which bank is best?", RESULTS, llm)
    assert answer.refused


def test_refuses_an_answer_without_any_citation():
    llm, _ = fake_llm("You have two weeks, I think.")
    answer = answer_question("How long?", RESULTS, llm)
    assert answer.refused
    assert "cited no passage" in answer.reason


# --- the Groq client (simulated with httpx.MockTransport) ---------------------------------


def test_groq_llm_sends_key_and_model_and_returns_the_reply():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hi [1]."}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = groq_llm("test-key", "test-model", client=client)
    assert llm([{"role": "user", "content": "Hello"}]) == "Hi [1]."
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "test-model"
    assert seen["body"]["temperature"] <= 0.2  # factual answers: low randomness


def test_groq_errors_include_groqs_explanation():
    # Real case: a retired model name made Groq answer 404.
    body = {"error": {"message": "The model `old-model` does not exist", "type": "invalid_request"}}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404, json=body)))
    llm = groq_llm("test-key", "old-model", client=client)
    with pytest.raises(httpx.HTTPStatusError, match="does not exist"):
        llm([{"role": "user", "content": "Hello"}])


def test_reasoning_models_get_low_reasoning_effort():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Ok [1]."}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    groq_llm("k", "openai/gpt-oss-120b", client=client)([{"role": "user", "content": "Hi"}])
    assert seen["body"]["reasoning_effort"] == "low"
    groq_llm("k", "some-llama-model", client=client)([{"role": "user", "content": "Hi"}])
    assert "reasoning_effort" not in seen["body"]


def test_groq_llm_raises_on_rate_limit():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    llm = groq_llm("test-key", "test-model", client=client)
    with pytest.raises(httpx.HTTPStatusError):
        llm([{"role": "user", "content": "Hello"}])
