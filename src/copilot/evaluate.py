"""Measure how well the copilot works, on a fixed set of test questions.

    uv run python -m copilot.evaluate --check            # validate the question file only
    uv run python -m copilot.evaluate --retrieval-only   # search quality, fast, no Groq calls
    uv run python -m copilot.evaluate                    # full run: search + answers
    uv run python -m copilot.evaluate --ids anm-01 rent-01
    uv run python -m copilot.evaluate --failed            # re-run only last run's failures
    uv run python -m copilot.evaluate --model openai/gpt-oss-20b
    uv run python -m copilot.evaluate --ci                # the check GitHub runs on every push

Groq's free tier allows a limited number of tokens per model per day. A full run of ~75
questions uses most of that budget, so: re-run failures with --failed, or use --model to
switch to another model (each model has its own daily budget). When the daily limit is hit,
the run stops early and only the questions that actually ran are scored.

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

--ci runs the check from data/eval/ci.yaml: retrieval on all questions, answers on a small
fixed subset, and exits with an error if any score is below its minimum, so a change that
makes the copilot worse turns the GitHub build red.
"""

import argparse
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
import yaml

from copilot.answer import Answer, Llm, answer_question, is_daily_limit
from copilot.language import detect_language
from copilot.search import SearchResult

QUESTIONS_FILE = Path("data/eval/questions.yaml")
SOURCES_FILE = Path("data/sources.yaml")
REPORT_FILE = Path("data/eval/report.md")
RUNS_DIR = Path("data/eval/runs")
CI_FILE = Path("data/eval/ci.yaml")
TOP_K = 5
TOPICS = {"anmeldung", "residence_permit", "health_insurance", "renting", "banking", "other"}

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
    # Models often put a non-breaking space between number and word ("14\u00a0Tagen"),
    # which looks identical but is a different character. Normalise all whitespace first.
    lowered = re.sub(r"\s+", " ", text).lower()
    return [
        fact
        for fact in must_include
        if not any(option.strip().lower() in lowered for option in fact.split("|"))
    ]


def looks_like_language(text: str, language: str) -> bool:
    return detect_language(text) == language


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
    errors = [r for r in results if r.error]
    scored = [r for r in results if not r.error]  # an API error says nothing about quality
    answerable = [r for r in scored if not r.should_refuse]
    refusable = [r for r in scored if r.should_refuse]
    ranks = [r.rank for r in answerable]
    summary = {
        "Questions": f"{len(scored)} scored ({len(answerable)} answerable, "
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
    if errors:
        summary["Errors (not scored)"] = str(len(errors))
    return summary


def rates(results: list[QuestionResult]) -> dict[str, float | None]:
    """The headline scores as fractions (0.0-1.0), for comparing against minimums.

    None means "nothing to measure" (e.g. no refusal questions in the run).
    """
    scored = [r for r in results if not r.error]
    answerable = [r for r in scored if not r.should_refuse]
    refusable = [r for r in scored if r.should_refuse]

    def ratio(part: int, whole: int) -> float | None:
        return part / whole if whole else None

    out = {"retrieval_hit": ratio(sum(r.rank is not None for r in answerable), len(answerable))}
    if any(r.answered is not None for r in scored):
        out |= {
            "answered": ratio(sum(bool(r.answered) for r in answerable), len(answerable)),
            "answer_correct": ratio(sum(bool(r.passed) for r in answerable), len(answerable)),
            "correct_refusals": ratio(sum(bool(r.passed) for r in refusable), len(refusable)),
        }
    return out


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


class DailyLimitReached(Exception):
    """Groq's per-day token/request budget is used up: waiting a minute will not help."""


def call_with_patience(fn: Callable[[], Answer], retries: int = 3, sleep=time.sleep) -> Answer:
    """Free-tier rate limits: on 429, wait (as long as the server asks, max 60 s) and retry."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429 or attempt == retries:
                raise
            if is_daily_limit(exc):
                raise DailyLimitReached(str(exc)) from exc
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
            except DailyLimitReached as exc:
                print(f"\nStopped after {i - 1} of {len(questions)} questions: {exc}")
                break
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


# --- the CI check ------------------------------------------------------------------------

CI_METRICS = ("retrieval_hit", "answered", "answer_correct", "correct_refusals")


@dataclass
class Check:
    metric: str
    value: float | None
    minimum: float

    @property
    def ok(self) -> bool:
        # The tiny tolerance stops 12/15 from "failing" a 0.80 minimum through float rounding.
        return self.value is not None and self.value >= self.minimum - 1e-9


def load_ci_config(questions: list[Question], path: Path = CI_FILE) -> dict:
    """Read ci.yaml and make sure it only names questions and metrics that exist."""
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    known = {q.id for q in questions}
    unknown_ids = [i for i in config["answer_questions"] if i not in known]
    unknown_metrics = [m for m in config["minimums"] if m not in CI_METRICS]
    if unknown_ids or unknown_metrics:
        raise SystemExit(
            f"Problems in {path}: unknown question ids {unknown_ids}, "
            f"unknown metrics {unknown_metrics} (allowed: {', '.join(CI_METRICS)})"
        )
    return config


def check_minimums(measured: dict[str, float | None], minimums: dict[str, float]) -> list[Check]:
    """One Check per minimum whose metric was measured in this run."""
    return [Check(m, measured[m], minimum) for m, minimum in minimums.items() if m in measured]


def render_checks(checks: list[Check]) -> str:
    def fmt(value: float | None) -> str:
        return "n/a" if value is None else f"{100 * value:.0f}%"

    lines = ["| Check | Score | Minimum | Result |", "| --- | --- | --- | --- |"]
    for c in checks:
        result = "pass" if c.ok else "**FAIL**"
        lines.append(f"| {c.metric} | {fmt(c.value)} | {fmt(c.minimum)} | {result} |")
    return "\n".join(lines) + "\n"


def run_ci(
    questions: list[Question],
    search: Search,
    llm: Llm | None,
    config: dict,
    model: str,
    sleep=time.sleep,
) -> bool:
    """Run the CI check. Returns True if every measured score meets its minimum."""
    print(f"Step 1/2: retrieval on all {len(questions)} questions (no Groq calls)")
    measured = {"retrieval_hit": rates(run(questions, search, None))["retrieval_hit"]}
    report = ""

    wanted = set(config["answer_questions"])
    subset = [q for q in questions if q.id in wanted]
    if llm is None:
        print("\n::warning::GROQ_API_KEY is not set, so answers were not checked.")
    else:
        print(f"\nStep 2/2: answers on {len(subset)} questions from {CI_FILE} ({model})")
        answers = run(subset, search, llm, sleep=sleep)
        if len(answers) < len(subset):
            # Hitting the free daily limit says nothing about quality: warn, don't fail.
            print("\n::warning::Groq's daily limit was reached, so answers were not checked.")
        else:
            if any(r.error for r in answers):
                print("\n::warning::Some questions hit API errors and were not scored.")
            r = rates(answers)
            measured |= {m: r[m] for m in ("answered", "answer_correct", "correct_refusals")}
            report = render_report(summarize(answers), answers, model).split("## Failures", 1)[1]

    checks = check_minimums(measured, config["minimums"])
    table = render_checks(checks)
    print("\n" + table)
    if report:
        print("Answer failures:" + report)

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")  # shown on the GitHub run page
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("## Eval check\n\n" + table)
            if report:
                f.write("\n### Answer failures\n" + report)

    ok = all(c.ok for c in checks)
    print("All scores meet their minimums." if ok else "Some scores are below their minimum.")
    return ok


def last_run_failures(runs_dir: Path = RUNS_DIR) -> set[str]:
    """Ids that did not pass in the most recent run (errors count as not passed)."""
    runs = sorted(runs_dir.glob("*.json"))
    if not runs:
        raise SystemExit(f"No previous runs in {runs_dir}")
    return {r["id"] for r in json.loads(runs[-1].read_text()) if r["passed"] is not True}


def main() -> None:
    parser = argparse.ArgumentParser(prog="copilot.evaluate")
    parser.add_argument("--check", action="store_true", help="only validate the question file")
    parser.add_argument("--retrieval-only", action="store_true", help="skip answers (no Groq)")
    parser.add_argument("--ids", nargs="*", help="only these question ids")
    parser.add_argument("--failed", action="store_true", help="only last run's failures")
    parser.add_argument("--model", help="Groq model to use instead of GROQ_MODEL")
    parser.add_argument("--ci", action="store_true", help=f"run the check in {CI_FILE}")
    args = parser.parse_args()

    questions = load_questions()
    source_urls = {s["url"] for s in yaml.safe_load(SOURCES_FILE.read_text())["sources"]}
    problems = validate_questions(questions, source_urls)
    if problems:
        raise SystemExit("Problems in questions.yaml:\n  " + "\n  ".join(problems))
    print(f"questions.yaml is valid: {len(questions)} questions.")
    ci_config = load_ci_config(questions)  # also checked by --check, so typos show up early
    if args.check:
        print(f"{CI_FILE} is valid: {len(ci_config['answer_questions'])} answer questions.")
        return
    if args.ids:
        questions = [q for q in questions if q.id in set(args.ids)]
    if args.failed:
        failed = last_run_failures()
        questions = [q for q in questions if q.id in failed]
        print(f"Re-running {len(questions)} questions that failed last time.")

    from copilot.answer import groq_llm
    from copilot.config import get_settings
    from copilot.db import connect
    from copilot.embed import embed_texts
    from copilot.search import hybrid_search

    settings = get_settings()
    model_name = args.model or settings.groq_model
    llm = None
    if args.ci:
        if settings.groq_api_key:
            llm = groq_llm(settings.groq_api_key, model_name)
    elif not args.retrieval_only:
        if not settings.groq_api_key:
            raise SystemExit("GROQ_API_KEY is not set (or use --retrieval-only)")
        llm = groq_llm(settings.groq_api_key, model_name)

    with connect(settings.database_url) as conn:

        def search(question: str) -> list[SearchResult]:
            return hybrid_search(conn, question, embed_texts([question])[0], limit=TOP_K)

        if args.ci:
            raise SystemExit(0 if run_ci(questions, search, llm, ci_config, model_name) else 1)
        results = run(questions, search, llm)

    summary = summarize(results)
    model = "retrieval only" if llm is None else model_name
    REPORT_FILE.write_text(render_report(summary, results, model), encoding="utf-8")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_file = RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    run_file.write_text(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))

    print()
    for name, value in summary.items():
        print(f"  {name:<46} {value}")
    if len(results) < len(questions):
        print(f"\n  Only {len(results)} of {len(questions)} questions ran (daily limit).")
        print("  Try again later, or use --model with another model.")
    print(f"\nReport: {REPORT_FILE}   Details: {run_file}")


if __name__ == "__main__":
    main()
