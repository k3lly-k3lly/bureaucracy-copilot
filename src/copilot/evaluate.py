"""Measure how well the copilot works, on a fixed set of test questions.

    uv run python -m copilot.evaluate --check            # validate the question file only
    uv run python -m copilot.evaluate --retrieval-only   # search quality, fast, no Groq calls
    uv run python -m copilot.evaluate                    # full run: search + answers
    uv run python -m copilot.evaluate --ids anm-01 rent-01

Each question in data/eval/questions.yaml says:
  - which source(s) should answer it          (expected_urls)
  - which facts a correct answer must contain (must_include)
  - or that the copilot should refuse         (should_refuse: true)

The evaluator scores three things:
  1. Retrieval: is an expected source among the top 5 passages search returns?
  2. Answers:   for answerable questions, does the answer contain the facts, cite an
                expected source, and use the question's language?
  3. Refusals:  does it refuse unanswerable questions, and NOT refuse answerable ones?

Results go to data/eval/report.md (commit this) and data/eval/runs/<time>.json (raw details).
"""

import argparse
import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
import yaml

from copilot.answer import Answer, Llm, answer_question
from copilot.search import SearchResult

QUESTIONS_FILE = Path("data/eval/questions.yaml")
SOURCES_FILE = Path("data/sources.yaml")
REPORT_FILE = Path("data/eval/report.md")
RUNS_DIR = Path("data/eval/runs")
TOP_K = 5
TOPICS = {"anmeldung", "residence_permit", "health_insurance", "renting", "banking", "other"}

# Tiny word lists for a rough "which language is this answer in?" check.
GERMAN_WORDS = {"der", "die", "das", "und", "ist", "sie", "nicht", "mit", "ein", "eine", "für"}
ENGLISH_WORDS = {"the", "and", "is", "you", "your", "to", "of", "a", "for", "must", "can"}


# --- the question file -------------------------------------------------------------------


@dataclass
class Question:
    id: str
    question: str
    language: str
    topic: str
    should_refuse: bool = False
    expected_urls: list[str] = field(default_factory=list)
    must_include: list[str] = field(default_factory=list)  # "14 days|two weeks" = either is fine
    notes: str = ""


def load_questions(path: Path = QUESTIONS_FILE) -> list[Question]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Question(**item) for item in data["questions"]]


def validate_questions(questions: list[Question], source_urls: set[str]) -> list[str]:
    """Return a list of problems (empty = the file is fine)."""
    problems = []
    seen: set[str] = set()
    for q in questions:
        where = f"{q.id}:"
        if q.id in seen:
            problems.append(f"{where} duplicate id")
        seen.add(q.id)
        if q.language not in ("en", "de"):
            problems.append(f"{where} language must be 'en' or 'de'")
        if q.topic not in TOPICS:
            problems.append(f"{where} unknown topic '{q.topic}'")
        if q.should_refuse and (q.expected_urls or q.must_include):
            problems.append(f"{where} a should_refuse question needs no expected_urls/must_include")
        if not q.should_refuse and not q.expected_urls:
            problems.append(f"{where} an answerable question needs at least one expected_url")
        for url in q.expected_urls:
            if url not in source_urls:
                problems.append(f"{where} expected url is not in sources.yaml: {url}")
    return problems


# --- scoring one question ----------------------------------------------------------------


def retrieval_rank(expected_urls: list[str], retrieved_urls: list[str]) -> int | None:
    """1-based position of the first expected source in the results, or None if missing."""
    for position, url in enumerate(retrieved_urls, start=1):
        if url in expected_urls:
            return position
    return None


def missing_facts(text: str, must_include: list[str]) -> list[str]:
    """Facts not found in the answer. Each fact may list alternatives: '14 days|two weeks'."""
    lowered = text.lower()
    return [
        fact
        for fact in must_include
        if not any(option.strip().lower() in lowered for option in fact.split("|"))
    ]


def looks_like_language(text: str, language: str) -> bool:
    words = set(re.findall(r"[a-zäöüß]+", text.lower()))
    german, english = len(words & GERMAN_WORDS), len(words & ENGLISH_WORDS)
    return german >= english if language == "de" else english >= german


@dataclass
class QuestionResult:
    id: str
    question: str
    should_refuse: bool
    retrieved_urls: list[str]
    rank: int | None = None
    answered: bool | None = None  # None = answers were not evaluated (retrieval-only run)
    answer: str = ""
    refusal_reason: str = ""
    cited_urls: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    cited_expected: bool | None = None
    language_ok: bool | None = None
    passed: bool | None = None
    error: str = ""


def score(q: Question, results: list[SearchResult], answer: Answer | None) -> QuestionResult:
    retrieved = [r.url for r in results]
    out = QuestionResult(q.id, q.question, q.should_refuse, retrieved)
    if not q.should_refuse:
        out.rank = retrieval_rank(q.expected_urls, retrieved)
    if answer is None:
        return out

    out.answered = not answer.refused
    out.answer = answer.text
    out.refusal_reason = answer.reason
    out.cited_urls = [c.url for c in answer.citations]
    if q.should_refuse:
        out.passed = answer.refused
        return out
    out.missing = missing_facts(answer.text, q.must_include) if out.answered else q.must_include
    out.cited_expected = any(url in q.expected_urls for url in out.cited_urls)
    out.language_ok = out.answered and looks_like_language(answer.text, q.language)
    out.passed = bool(out.answered and not out.missing and out.cited_expected and out.language_ok)
    return out


# --- summarising a run -------------------------------------------------------------------


def percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}% ({part}/{whole})" if whole else "n/a"


def summarize(results: list[QuestionResult]) -> dict[str, str]:
    answerable = [r for r in results if not r.should_refuse]
    refusable = [r for r in results if r.should_refuse]
    ranks = [r.rank for r in answerable]
    summary = {
        "Questions": f"{len(results)} ({len(answerable)} answerable, "
        f"{len(refusable)} should refuse)",
        f"Retrieval hit@{TOP_K}": percent(sum(r is not None for r in ranks), len(answerable)),
        "Retrieval MRR": f"{sum(1 / r for r in ranks if r) / len(ranks):.2f}" if ranks else "n/a",
    }
    if any(r.answered is not None for r in results):
        answered = [r for r in answerable if r.answered]
        summary |= {
            "Answer correct (facts + citation + language)": percent(
                sum(bool(r.passed) for r in answerable), len(answerable)
            ),
            "Answered (not refused)": percent(len(answered), len(answerable)),
            "Cites an expected source": percent(
                sum(bool(r.cited_expected) for r in answered), len(answered)
            ),
            "Contains all key facts": percent(sum(not r.missing for r in answered), len(answered)),
            "Correct refusals": percent(sum(bool(r.passed) for r in refusable), len(refusable)),
        }
    return summary


def render_report(summary: dict[str, str], results: list[QuestionResult], model: str) -> str:
    lines = [
        "# Evaluation report",
        "",
        f"Run: {datetime.now():%Y-%m-%d %H:%M} · model: {model} · top-k: {TOP_K}",
        "",
        "| Metric | Score |",
        "| --- | --- |",
        *[f"| {name} | {value} |" for name, value in summary.items()],
        "",
        "## Failures",
        "",
    ]
    failures = 0
    for r in results:
        problems = []
        if not r.should_refuse and r.rank is None:
            problems.append("expected source not retrieved")
        if r.error:
            problems.append(f"error: {r.error}")
        if r.passed is False:
            if r.should_refuse:
                problems.append("answered but should have refused")
            elif not r.answered:
                problems.append(f"refused ({r.refusal_reason})")
            else:
                if r.missing:
                    problems.append(f"missing facts: {', '.join(r.missing)}")
                if not r.cited_expected:
                    problems.append("did not cite an expected source")
                if not r.language_ok:
                    problems.append("answered in the wrong language")
        if problems:
            failures += 1
            lines.append(f"- **{r.id}** {r.question} - {'; '.join(problems)}")
    if not failures:
        lines.append("None.")
    return "\n".join(lines) + "\n"


# --- running -----------------------------------------------------------------------------

Search = Callable[[str], list[SearchResult]]


def call_with_patience(fn: Callable[[], Answer], retries: int = 3, sleep=time.sleep) -> Answer:
    """Free-tier rate limits: on 429, wait (as long as the server asks, max 60 s) and retry."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429 or attempt == retries:
                raise
            retry_after = exc.response.headers.get("retry-after", "")
            sleep(min(float(retry_after), 60.0) if retry_after.replace(".", "").isdigit() else 20.0)
    raise AssertionError("unreachable")


def run(
    questions: list[Question],
    search: Search,
    llm: Llm | None,
    pause_seconds: float = 2.0,
    sleep=time.sleep,
) -> list[QuestionResult]:
    results = []
    for i, q in enumerate(questions, start=1):
        passages = search(q.question)
        answer, error = None, ""
        if llm is not None:
            try:
                answer = call_with_patience(
                    lambda q=q, passages=passages: answer_question(q.question, passages, llm)
                )
            except httpx.HTTPError as exc:
                error = str(exc)
            if i < len(questions):
                sleep(pause_seconds)  # stay under the free tier's requests-per-minute limit
        result = score(q, passages, answer)
        result.error = error
        if error:
            result.passed = False
        mark = {True: "PASS", False: "FAIL", None: "    "}[result.passed]
        rank = "-" if q.should_refuse else (result.rank or "miss")
        print(f"[{i:>3}/{len(questions)}] {mark} rank={rank!s:<4} {q.id}: {q.question[:60]}")
        results.append(result)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(prog="copilot.evaluate")
    parser.add_argument("--check", action="store_true", help="only validate the question file")
    parser.add_argument("--retrieval-only", action="store_true", help="skip answers (no Groq)")
    parser.add_argument("--ids", nargs="*", help="only these question ids")
    args = parser.parse_args()

    questions = load_questions()
    source_urls = {s["url"] for s in yaml.safe_load(SOURCES_FILE.read_text())["sources"]}
    problems = validate_questions(questions, source_urls)
    if problems:
        raise SystemExit("Problems in questions.yaml:\n  " + "\n  ".join(problems))
    print(f"questions.yaml is valid: {len(questions)} questions.")
    if args.check:
        return
    if args.ids:
        questions = [q for q in questions if q.id in set(args.ids)]

    from copilot.answer import groq_llm
    from copilot.config import get_settings
    from copilot.db import connect
    from copilot.embed import embed_texts
    from copilot.search import hybrid_search

    settings = get_settings()
    llm = None
    if not args.retrieval_only:
        if not settings.groq_api_key:
            raise SystemExit("GROQ_API_KEY is not set (or use --retrieval-only)")
        llm = groq_llm(settings.groq_api_key, settings.groq_model)

    with connect(settings.database_url) as conn:

        def search(question: str) -> list[SearchResult]:
            return hybrid_search(conn, question, embed_texts([question])[0], limit=TOP_K)

        results = run(questions, search, llm)

    summary = summarize(results)
    model = "retrieval only" if llm is None else settings.groq_model
    REPORT_FILE.write_text(render_report(summary, results, model), encoding="utf-8")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_file = RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    run_file.write_text(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))

    print()
    for name, value in summary.items():
        print(f"  {name:<46} {value}")
    print(f"\nReport: {REPORT_FILE}   Details: {run_file}")


if __name__ == "__main__":
    main()
