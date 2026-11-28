"""Turn retrieved passages into a short, cited answer - or an honest "I don't know".

The flow for one question:
1. Retrieval found some passages (see search.py).
2. If even the best passage is only weakly related, refuse right away: no LLM call needed.
3. Otherwise send the question + numbered passages to the LLM, with strict rules:
   answer ONLY from the passages, cite every claim like [1], or reply NOT_IN_SOURCES.
4. Check the reply: keep only citations that point to real passages. An answer with no
   valid citation is treated as unsupported and refused, so nothing uncited reaches the user.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from copilot.language import LANGUAGE_NAMES, detect_language
from copilot.search import SearchResult

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Below this similarity the best passage is too unrelated to answer from. Tuned in Week 4
# with `python -m copilot.compare_models` for jina-embeddings-v2-base-de: answerable
# questions scored 0.43 at the lowest (median 0.67), so 0.40 never blocks one of them.
# Off-topic questions overlap heavily (median 0.48, max 0.70), so this check only catches
# clearly unrelated questions; refusing the rest is the model's job (NOT_IN_SOURCES).
MIN_SIMILARITY = 0.40
REFUSAL_MARKER = "NOT_IN_SOURCES"
# Must be at least the chunker's MAX_CHARS (1500), or the end of a chunk never reaches the model.
MAX_PASSAGE_CHARS = 1600

SYSTEM_PROMPT = f"""You answer questions from international students about German bureaucracy \
(address registration, residence permits, health insurance, renting, bank accounts).

Rules:
- Use ONLY the numbered passages provided. Do not use outside knowledge.
- After every sentence that states a fact, cite the passage(s) it comes from, like [1] or [2][3].
- Write citations ONLY as a number in square brackets: [1]. No other symbols, words or ranges.
- If the passages do not contain the answer, reply with exactly: {REFUSAL_MARKER}
- If passages disagree or the answer depends on the person's situation, say so and cite both.
- Answer in the language named at the end of the user message, even if the passages
  are in another language. Be short: 2 to 5 sentences.
- Do not give legal advice beyond what the passages say."""

Llm = Callable[[list[dict]], str]


@dataclass
class Citation:
    number: int
    url: str
    section: str
    text: str


@dataclass
class Answer:
    text: str
    refused: bool
    citations: list[Citation] = field(default_factory=list)
    reason: str = ""


def format_passages(results: list[SearchResult]) -> str:
    blocks = []
    for i, r in enumerate(results, start=1):
        heading = f" ({r.section})" if r.section else ""
        blocks.append(f"[{i}] Source: {r.url}{heading}\n{r.text[:MAX_PASSAGE_CHARS]}")
    return "\n\n".join(blocks)


def build_messages(question: str, results: list[SearchResult]) -> list[dict]:
    # Models drift into the passages' language (German sources -> German answer), so the
    # language is decided in code and stated last, where the model pays most attention.
    language = LANGUAGE_NAMES[detect_language(question)]
    user = (
        f"Passages:\n\n{format_passages(results)}\n\nQuestion: {question}\n\nAnswer in {language}."
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def normalize_citations(text: str) -> str:
    """Rewrite other citation styles models use into plain [n] markers.

    Some models ignore the requested format, e.g. OpenAI's gpt-oss often writes
    【1】 or [1†source]. Others write [Passage 1], [1, 2] or [1-3].
    """
    text = re.sub(r"【\s*(\d+)[^】]*】", r"[\1]", text)  # 【1】, 【1†L3】
    text = re.sub(r"\[(\d+)†[^\]]*\]", r"[\1]", text)  # [1†source]
    text = re.sub(r"\[(?:passage|source)\s*(\d+)\]", r"[\1]", text, flags=re.IGNORECASE)

    def expand(match: re.Match) -> str:  # [1, 2] -> [1][2], [1-3] -> [1][2][3]
        numbers: list[int] = []
        for part in re.split(r"\s*,\s*", match.group(1)):
            if "-" in part:
                start, end = (int(x) for x in part.split("-"))
                numbers.extend(range(start, end + 1) if 0 < end - start < 10 else [start, end])
            else:
                numbers.append(int(part))
        return "".join(f"[{n}]" for n in numbers)

    return re.sub(r"\[(\d+(?:\s*[-,]\s*\d+)+)\]", expand, text)


def parse_citations(text: str, passage_count: int) -> list[int]:
    """Citation numbers used in the answer, in order of first use, ignoring invalid ones."""
    numbers: list[int] = []
    for match in re.finditer(r"\[(\d+)\]", text):
        n = int(match.group(1))
        if 1 <= n <= passage_count and n not in numbers:
            numbers.append(n)
    return numbers


def remove_invalid_citations(text: str, passage_count: int) -> str:
    """Drop markers like [9] that point to a passage the model was never given."""

    def keep_or_drop(match: re.Match) -> str:
        return match.group(0) if 1 <= int(match.group(1)) <= passage_count else ""

    return re.sub(r"\[(\d+)\]", keep_or_drop, text)


REFUSAL_TEXT = {
    "en": "I couldn't find this in the official sources I have. "
    "Please check with the responsible office directly.",
    "de": "Dazu habe ich in meinen offiziellen Quellen nichts gefunden. "
    "Bitte frag direkt bei der zuständigen Stelle nach.",
}


def refusal(reason: str, language: str = "en") -> Answer:
    """An honest "I don't know", in the language of the question."""
    return Answer(text=REFUSAL_TEXT.get(language, REFUSAL_TEXT["en"]), refused=True, reason=reason)


def answer_question(
    question: str, results: list[SearchResult], llm: Llm, debug: bool = False
) -> Answer:
    language = detect_language(question)
    if not results:
        return refusal("no passages found", language)
    best = max(r.similarity for r in results)
    if best < MIN_SIMILARITY:
        return refusal(f"best passage similarity {best:.2f} is below {MIN_SIMILARITY}", language)

    raw_reply = llm(build_messages(question, results)).strip()
    if debug:
        print(f"--- raw model reply ---\n{raw_reply}\n-----------------------")
    reply = normalize_citations(raw_reply)
    if REFUSAL_MARKER in reply:
        return refusal("the model said the passages do not contain the answer", language)

    used = parse_citations(reply, len(results))
    if not used:
        return refusal("the model's answer cited no passage, so it could not be verified", language)

    citations = [
        Citation(n, results[n - 1].url, results[n - 1].section, results[n - 1].text) for n in used
    ]
    text = remove_invalid_citations(reply, len(results))
    return Answer(text=text, refused=False, citations=citations)


def groq_llm(api_key: str, model: str, client: httpx.Client | None = None) -> Llm:
    """An Llm function that calls Groq's OpenAI-compatible chat API."""
    http = client or httpx.Client(timeout=30.0)

    def call(messages: list[dict]) -> str:
        payload = {"model": model, "messages": messages, "temperature": 0.1, "max_tokens": 1024}
        if "gpt-oss" in model:
            # Reasoning models "think" before answering, and thinking uses up tokens.
            # A short factual answer needs little of it.
            payload["reasoning_effort"] = "low"
        response = http.post(GROQ_URL, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
        if response.is_error:
            # Show Groq's own explanation (e.g. "model does not exist"), not just the status code.
            try:
                detail = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                detail = response.text[:300]
            raise httpx.HTTPStatusError(
                f"Groq returned {response.status_code}: {detail}",
                request=response.request,
                response=response,
            )
        return response.json()["choices"][0]["message"]["content"] or ""

    return call


def is_daily_limit(exc: httpx.HTTPStatusError) -> bool:
    """True if Groq refused because today's free budget is used up (not just this minute's)."""
    text = f"{exc} {exc.response.text}".lower()
    return "per day" in text or "(tpd)" in text or "(rpd)" in text
