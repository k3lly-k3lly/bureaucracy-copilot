"""Search the stored chunks from the terminal.

uv run python -m copilot.ask "How long do I have to register my address?"
uv run python -m copilot.ask "Wie hoch darf die Kaution sein?" --topic renting
"""

import argparse
import textwrap

from copilot.config import get_settings
from copilot.db import connect
from copilot.embed import embed_texts
from copilot.search import search


def main() -> None:
    parser = argparse.ArgumentParser(prog="copilot.ask")
    parser.add_argument("question")
    parser.add_argument("--topic", default=None)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    database_url = get_settings().database_url
    if not database_url:
        raise SystemExit("DATABASE_URL is not set. Copy .env.example to .env first.")

    query_embedding = embed_texts([args.question])[0]
    with connect(database_url) as conn:
        results = search(conn, query_embedding, limit=args.limit, topic=args.topic)

    print(f'\nTop {len(results)} passages for: "{args.question}"\n')
    for i, r in enumerate(results, start=1):
        print(f"{i}. [{r.similarity:.2f}] {r.topic} | {r.section or '(no heading)'}")
        print(textwrap.indent(textwrap.shorten(r.text, width=300), "   "))
        print(f"   {r.url}\n")


if __name__ == "__main__":
    main()
