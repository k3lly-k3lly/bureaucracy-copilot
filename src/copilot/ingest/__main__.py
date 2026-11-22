"""Command line entry point.

uv run python -m copilot.ingest fetch            # download all sources (cached)
uv run python -m copilot.ingest fetch --refresh  # download again, ignoring the cache
uv run python -m copilot.ingest process          # clean + chunk -> data/processed/chunks.jsonl
"""

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from copilot.ingest.chunk import chunk_markdown
from copilot.ingest.clean import clean_html
from copilot.ingest.fetch import RAW_DIR, fetch_all, raw_paths, url_id
from copilot.ingest.sources import DEFAULT_SOURCES_FILE, load_sources

PROCESSED_DIR = Path("data/processed")


def cmd_fetch(args: argparse.Namespace) -> None:
    sources = load_sources(Path(args.sources))
    if args.limit:
        sources = sources[: args.limit]
    results = fetch_all(sources, refresh=args.refresh)
    counts = Counter(r.status for r in results)
    print("\nSummary:", dict(counts))
    for r in results:
        if r.status in ("error", "blocked_by_robots", "bot_protection"):
            print(f"  {r.status}: {r.url}" + (f"\n    {r.error}" if r.error else ""))


def cmd_process(args: argparse.Namespace) -> None:
    sources = load_sources(Path(args.sources))
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "chunks.jsonl"
    report = []
    total = 0

    with out_path.open("w", encoding="utf-8") as out:
        for source in sources:
            body_path, meta_path = raw_paths(source.url, RAW_DIR)
            if not body_path.exists():
                report.append((source.url, "not downloaded", 0))
                continue
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if "html" not in (meta.get("content_type") or "html"):
                report.append((source.url, f"skipped ({meta['content_type']})", 0))
                continue
            page = clean_html(body_path.read_bytes())
            if page is None:
                report.append((source.url, "no content extracted", 0))
                continue
            chunks = chunk_markdown(page.markdown)
            for chunk in chunks:
                record = {
                    "id": f"{url_id(source.url)}-{chunk.position:03d}",
                    "url": source.url,
                    "topic": source.topic,
                    "language": source.language,
                    "title": page.title,
                    "fetched_at": meta.get("fetched_at"),
                    **asdict(chunk),
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
            total += len(chunks)
            report.append((source.url, "ok", len(chunks)))

    print(f"{'chunks':>6}  status                 url")
    for url, status, n in report:
        print(f"{n:>6}  {status:<22} {url}")
    print(f"\nWrote {total} chunks from {len(sources)} sources to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="copilot.ingest")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES_FILE))
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="download all sources")
    fetch.add_argument("--refresh", action="store_true", help="ignore the cache")
    fetch.add_argument("--limit", type=int, default=0, help="only the first N sources")
    fetch.set_defaults(func=cmd_fetch)

    process = sub.add_parser("process", help="clean and chunk downloaded pages")
    process.set_defaults(func=cmd_process)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
