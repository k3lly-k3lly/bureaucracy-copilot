"""Read the "was this helpful?" votes from the chat page.

    uv run python -m copilot.feedback              # the 20 newest votes
    uv run python -m copilot.feedback --unhelpful  # only answers people marked "No"

A "No" vote is a free test case: if the answer was wrong, add the question to
data/eval/questions.yaml so the evaluation catches it from now on.
"""

import argparse

from copilot.config import get_settings
from copilot.db import connect, recent_feedback


def shorten(text: str, width: int = 100) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def main() -> None:
    parser = argparse.ArgumentParser(prog="copilot.feedback")
    parser.add_argument("--unhelpful", action="store_true", help="only 'No' votes")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set (see .env.example)")
    with connect(settings.database_url) as conn:
        rows = recent_feedback(conn, args.limit, helpful=False if args.unhelpful else None)

    if not rows:
        print("No feedback yet.")
        return
    for id_, created_at, helpful, question, answer, refused, cited_urls in rows:
        vote = "yes" if helpful else "NO "
        status = " (refused)" if refused else ""
        # The database keeps times in UTC; show them in this computer's time zone.
        print(f"#{id_}  {created_at.astimezone():%Y-%m-%d %H:%M}  helpful: {vote}{status}")
        print(f"  Q: {shorten(question)}")
        print(f"  A: {shorten(answer)}")
        for url in cited_urls:
            print(f"     {url}")
        print()


if __name__ == "__main__":
    main()
