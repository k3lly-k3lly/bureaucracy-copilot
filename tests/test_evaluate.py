"""Tests for the evaluation harness itself - an evaluator with bugs gives misleading scores."""

import httpx
import pytest
import yaml

from copilot.answer import Answer, Citation
from copilot.evaluate import (
    CI_METRICS,
    SOURCES_FILE,
    Check,
    DailyLimitReached,
    Question,
    call_with_patience,
    check_minimums,
    last_run_failures,
    load_ci_config,
    load_questions,
    looks_like_language,
    missing_facts,
    rates,
    render_report,
    retrieval_rank,
    run,
    run_ci,
    score,
    summarize,
    validate_questions,
)
from copilot.search import SearchResult

URL_A = "https://example.berlin/a"
URL_B = "https://example.berlin/b"


def passage(url: str, similarity: float = 0.7) -> SearchResult:
    return SearchResult(
        id=url, url=url, topic="anmeldung", section="", text="...", similarity=similarity
    )


def answerable(**overrides) -> Question:
    base = dict(
        id="q1",
        question="How long do I have?",
        language="en",
        topic="anmeldung",
        expected_urls=[URL_A],
        must_include=["14 days|two weeks"],
    )
    return Question(**{**base, **overrides})


def answered(text: str, url: str = URL_A) -> Answer:
    return Answer(text=text, refused=False, citations=[Citation(1, url, "", "")])


REFUSED = Answer(text="I couldn't find this.", refused=True, reason="not in sources")


# --- the real question file ----------------------------------------------------------------


def test_real_question_file_is_valid():
    source_urls = {s["url"] for s in yaml.safe_load(SOURCES_FILE.read_text())["sources"]}
    questions = load_questions()
    assert questions, "questions.yaml has no questions"
    assert validate_questions(questions, source_urls) == []


def test_validation_catches_common_mistakes():
    questions = [
        answerable(id="dup"),
        answerable(id="dup"),
        answerable(id="bad-lang", language="fr"),
        answerable(id="no-url", expected_urls=[]),
        answerable(id="unknown-url", expected_urls=["https://not-a-source.example"]),
        Question(
            id="refuse",
            question="?",
            language="en",
            topic="other",
            should_refuse=True,
            must_include=["x"],
        ),
    ]
    problems = "\n".join(validate_questions(questions, {URL_A}))
    for expected in [
        "duplicate id",
        "language must be",
        "needs at least one expected_url",
        "not in sources.yaml",
        "needs no expected_urls",
    ]:
        assert expected in problems


# --- scoring building blocks -------------------------------------------------------------


def test_retrieval_rank():
    assert retrieval_rank([URL_B], [URL_A, URL_B]) == 2
    assert retrieval_rank([URL_B], [URL_A]) is None


def test_missing_facts_accepts_alternatives_and_ignores_case():
    assert missing_facts("Register within Two Weeks.", ["14 days|two weeks"]) == []
    assert missing_facts("Register soon.", ["14 days|two weeks", "free"]) == [
        "14 days|two weeks",
        "free",
    ]


def test_language_check():
    assert looks_like_language("You must register within 14 days [1].", "en")
    assert looks_like_language("Sie müssen sich innerhalb von zwei Wochen anmelden [1].", "de")
    assert not looks_like_language("You must register within 14 days [1].", "de")


# --- scoring whole questions ---------------------------------------------------------------


def test_correct_answer_passes():
    result = score(answerable(), [passage(URL_B), passage(URL_A)], answered("Within 14 days [1]."))
    assert result.rank == 2
    assert result.passed


def test_answer_missing_a_fact_fails():
    result = score(answerable(), [passage(URL_A)], answered("Register soon [1]."))
    assert not result.passed
    assert result.missing == ["14 days|two weeks"]


def test_answer_citing_the_wrong_source_fails():
    result = score(answerable(), [passage(URL_B)], answered("Within 14 days [1].", url=URL_B))
    assert not result.passed
    assert result.cited_expected is False


def test_answer_in_wrong_language_fails():
    q = answerable(language="de", must_include=["14"])
    result = score(q, [passage(URL_A)], answered("You must register within 14 days [1]."))
    assert not result.passed
    assert result.language_ok is False


def test_refusing_an_answerable_question_fails():
    result = score(answerable(), [passage(URL_A)], REFUSED)
    assert result.answered is False
    assert not result.passed


def test_refusal_questions_pass_only_when_refused():
    q = Question(id="r", question="Best bank?", language="en", topic="other", should_refuse=True)
    assert score(q, [passage(URL_A)], REFUSED).passed
    assert not score(q, [passage(URL_A)], answered("Bank X [1].")).passed


def test_retrieval_only_scores_rank_but_not_answers():
    result = score(answerable(), [passage(URL_A)], None)
    assert result.rank == 1
    assert result.passed is None


# --- summary and report --------------------------------------------------------------------


def test_summary_numbers():
    refuse_q = Question(id="r", question="?", language="en", topic="other", should_refuse=True)
    results = [
        score(answerable(id="a1"), [passage(URL_A)], answered("14 days [1].")),  # pass, rank 1
        score(answerable(id="a2"), [passage(URL_B), passage(URL_A)], REFUSED),  # rank 2, refused
        score(refuse_q, [passage(URL_A)], REFUSED),  # correct refusal
    ]
    summary = summarize(results)
    assert summary["Retrieval hit@5"] == "100% (2/2)"
    assert summary["Retrieval MRR"] == "0.75"  # (1/1 + 1/2) / 2
    assert summary["Answer correct (facts + citation + language)"] == "50% (1/2)"
    assert summary["Correct refusals"] == "100% (1/1)"


def test_report_lists_failures_with_reasons():
    results = [score(answerable(), [passage(URL_B)], answered("Soon [1].", url=URL_B))]
    report = render_report(summarize(results), results, "test-model")
    assert "| Retrieval hit@5 | 0% (0/1) |" in report
    assert "expected source not retrieved" in report
    assert "missing facts: 14 days|two weeks" in report


# --- running ----------------------------------------------------------------------------


def test_run_with_fake_search_and_llm():
    questions = [answerable(id="a1"), answerable(id="a2", must_include=["free"])]
    results = run(
        questions,
        search=lambda q: [passage(URL_A)],
        llm=lambda messages: "Within 14 days [1].",
        pause_seconds=0,
        sleep=lambda s: None,
    )
    assert [r.passed for r in results] == [True, False]


def test_rate_limit_is_waited_out_then_retried():
    calls, waits = {"n": 0}, []

    def flaky() -> Answer:
        calls["n"] += 1
        if calls["n"] == 1:
            request = httpx.Request("POST", "https://api.groq.com")
            response = httpx.Response(429, headers={"retry-after": "7"}, request=request)
            raise httpx.HTTPStatusError("429", request=request, response=response)
        return REFUSED

    assert call_with_patience(flaky, sleep=waits.append) is REFUSED
    assert waits == [7.0]


def test_other_errors_are_not_retried():
    def broken() -> Answer:
        request = httpx.Request("POST", "https://api.groq.com")
        raise httpx.HTTPStatusError("500", request=request, response=httpx.Response(500))

    with pytest.raises(httpx.HTTPStatusError):
        call_with_patience(broken, sleep=lambda s: None)


def rate_limited(message: str) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.groq.com")
    response = httpx.Response(429, request=request, text=message)
    error = f"Groq returned 429: {message}"
    return httpx.HTTPStatusError(error, request=request, response=response)


def test_daily_limit_is_not_waited_out():
    # Waiting 60 s can't fix a per-day budget: stop instead of hammering the API.
    def exhausted() -> Answer:
        raise rate_limited("Rate limit reached ... on tokens per day (TPD): Limit 200000")

    waits = []
    with pytest.raises(DailyLimitReached):
        call_with_patience(exhausted, sleep=waits.append)
    assert waits == []


def test_run_stops_at_daily_limit_and_keeps_finished_results():
    calls = {"n": 0}

    def llm(messages):
        calls["n"] += 1
        if calls["n"] > 1:
            raise rate_limited("Rate limit reached on tokens per day (TPD)")
        return "Within 14 days [1]."

    questions = [answerable(id=f"a{i}") for i in range(4)]
    results = run(questions, lambda q: [passage(URL_A)], llm, pause_seconds=0, sleep=lambda s: None)
    assert [r.id for r in results] == ["a0"]
    assert calls["n"] == 2


def test_errors_are_left_out_of_the_scores():
    # Regression: 23 rate-limit errors were counted as wrong answers and refusals.
    ok = score(answerable(id="a1"), [passage(URL_A)], answered("14 days [1]."))
    broken = score(answerable(id="a2"), [passage(URL_A)], None)
    broken.error, broken.passed = "Groq returned 429", False
    summary = summarize([ok, broken])
    assert summary["Answer correct (facts + citation + language)"] == "100% (1/1)"
    assert summary["Errors (not scored)"] == "1"


def test_last_run_failures(tmp_path):
    (tmp_path / "20260101-090000.json").write_text('[{"id": "old", "passed": false}]')
    (tmp_path / "20260102-090000.json").write_text(
        '[{"id": "a", "passed": true}, {"id": "b", "passed": false}, {"id": "c", "passed": null}]'
    )
    assert last_run_failures(tmp_path) == {"b", "c"}


# --- the CI check --------------------------------------------------------------------------


def test_real_ci_file_is_valid():
    config = load_ci_config(load_questions())
    assert len(config["answer_questions"]) == 20
    assert set(config["minimums"]) <= set(CI_METRICS)


def test_ci_file_with_unknown_question_id_is_rejected(tmp_path):
    path = tmp_path / "ci.yaml"
    path.write_text("answer_questions: [a1, typo-99]\nminimums: {answered: 0.8}\n")
    with pytest.raises(SystemExit, match="typo-99"):
        load_ci_config([answerable(id="a1")], path)


def test_rates_are_fractions():
    good = score(answerable(id="a1"), [passage(URL_A)], answered("14 days [1]."))
    refused = score(answerable(id="a2"), [passage(URL_A)], REFUSED)
    out = rates([good, refused])
    assert out == {
        "retrieval_hit": 1.0,
        "answered": 0.5,
        "answer_correct": 0.5,
        "correct_refusals": None,  # no refusal questions in this run
    }


def test_minimum_check_handles_rounding_and_missing_values():
    assert Check("answered", 12 / 15, 0.80).ok  # exactly on the line passes
    assert not Check("answered", 11 / 15, 0.80).ok
    assert not Check("correct_refusals", None, 0.80).ok
    # A metric that was not measured (e.g. answers skipped) is not checked at all.
    assert [
        c.metric
        for c in check_minimums({"retrieval_hit": 0.9}, {"retrieval_hit": 0.8, "answered": 0.8})
    ] == ["retrieval_hit"]


CI_QUESTIONS = [
    answerable(id="a1"),
    Question(id="r1", question="Best bank?", language="en", topic="other", should_refuse=True),
]
CI_CONFIG = {
    "answer_questions": ["a1", "r1"],
    "minimums": {m: 1.0 for m in CI_METRICS},
}


def ci_search(question: str):
    # Nothing is found for the off-topic question, so the copilot refuses it.
    return [] if "bank" in question else [passage(URL_A)]


def no_sleep(seconds: float) -> None:
    pass


def test_ci_passes_when_every_score_meets_its_minimum(monkeypatch, tmp_path):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    llm = lambda messages: "Within 14 days [1]."  # noqa: E731
    assert run_ci(CI_QUESTIONS, ci_search, llm, CI_CONFIG, "fake", sleep=no_sleep)
    assert "| answer_correct | 100% | 100% | pass |" in summary.read_text()


def test_ci_fails_when_answers_get_worse(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    llm = lambda messages: "You must register soon [1]."  # noqa: E731  (key fact missing)
    assert not run_ci(CI_QUESTIONS, ci_search, llm, CI_CONFIG, "fake", sleep=no_sleep)
    out = capsys.readouterr().out
    assert "| answer_correct | 0% | 100% | **FAIL** |" in out
    assert "missing facts" in out


def test_ci_skips_answers_but_still_checks_retrieval_at_daily_limit(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    def exhausted(messages):
        raise rate_limited("Rate limit reached on tokens per day (TPD)")

    assert run_ci(CI_QUESTIONS, ci_search, exhausted, CI_CONFIG, "fake", sleep=no_sleep)
    out = capsys.readouterr().out
    assert "daily limit" in out
    assert "answer_correct" not in out


def test_ci_without_key_still_fails_on_bad_retrieval(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    wrong_page = lambda q: [passage(URL_B)]  # noqa: E731
    assert not run_ci(CI_QUESTIONS, wrong_page, None, CI_CONFIG, "fake", sleep=no_sleep)
