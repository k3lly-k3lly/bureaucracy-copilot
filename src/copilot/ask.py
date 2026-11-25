"""Ask the copilot from the terminal.

uv run python -m copilot.ask "How long do I have to register my address?"
uv run python -m copilot.ask "Wie hoch darf die Kaution sein?" --topic renting
uv run python -m copilot.ask "How long do I have to register?" --passages   # search only, no AI
"""

import argparse
import textwrap

from copilot.answer import answer_question, groq_llm
from copilot.config import get_settings
from copilot.db import connect
from copilot.embed import embed_texts
from copilot.search import hybrid_search


def main() -> None:
    parser = argparse.ArgumentParser(prog="copilot.ask")
    parser.add_argument("question")
    parser.add_argument("--topic", default=None)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--passages", action="store_true", help="show search results only")
    parser.add_argument("--debug", action="store_true", help="also print the raw model reply")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set. Copy .env.example to .env first.")

    query_embedding = embed_texts([args.question])[0]
    with connect(settings.database_url) as conn:
        results = hybrid_search(conn, args.question, query_embedding, args.limit, args.topic)

    if args.passages:
        print(f'\nTop {len(results)} passages for: "{args.question}"\n')
        for i, r in enumerate(results, start=1):
            print(f"{i}. [similarity {r.similarity:.2f}] {r.topic} | {r.section or '(no heading)'}")
            print(textwrap.indent(textwrap.shorten(r.text, width=300), "   "))
            print(f"   {r.url}\n")
        return

    if not settings.groq_api_key:
        raise SystemExit(
            "GROQ_API_KEY is not set in .env (free key: https://console.groq.com/keys)"
        )

    answer = answer_question(
        args.question,
        results,
        groq_llm(settings.groq_api_key, settings.groq_model),
        debug=args.debug,
    )
    print(f"\nQ: {args.question}\n")
    print(textwrap.fill(answer.text, width=100))
    if answer.refused:
        print(f"\n(refused: {answer.reason})")
    for c in answer.citations:
        print(f"\n[{c.number}] {c.section or '(no heading)'}\n    {c.url}")
    print()


if __name__ == "__main__":
    main()
