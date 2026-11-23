"""Command line entry point.

uv run python -m copilot.ingest fetch            # download all sources (cached)
uv run python -m copilot.ingest fetch --refresh  # download again, ignoring the cache
uv run python -m copilot.ingest process          # clean + chunk -> data/processed/chunks.jsonl
uv run python -m copilot.ingest load             # embed chunks and store them in Postgres
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


BATCH_SIZE = 32


def cmd_load(args: argparse.Namespace) -> None:
    """Embed every chunk and store it in Postgres. Safe to re-run (upsert by id)."""
    from copilot.config import get_settings
    from copilot.db import connect, count_chunks, delete_chunks_not_in, init_schema, upsert_chunks
    from copilot.embed import embed_texts, text_for_embedding

    database_url = get_settings().database_url
    if not database_url:
        raise SystemExit("DATABASE_URL is not set. Copy .env.example to .env first.")

    chunks_path = PROCESSED_DIR / "chunks.jsonl"
    records = [json.loads(line) for line in chunks_path.open(encoding="utf-8")]
    print(f"Embedding {len(records)} chunks (the model downloads once, ~220 MB)...")

    with connect(database_url) as conn:
        init_schema(conn)
        for start in range(0, len(records), BATCH_SIZE):
            batch = records[start : start + BATCH_SIZE]
            embeddings = embed_texts([text_for_embedding(r) for r in batch])
            upsert_chunks(conn, batch, embeddings)
            print(f"  {min(start + BATCH_SIZE, len(records)):>4}/{len(records)}")
        removed = delete_chunks_not_in(conn, [r["id"] for r in records])
        print(f"\nDone. {count_chunks(conn)} chunks in the database ({removed} old ones removed).")


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

    load = sub.add_parser("load", help="embed chunks and store them in Postgres")
    load.set_defaults(func=cmd_load)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
