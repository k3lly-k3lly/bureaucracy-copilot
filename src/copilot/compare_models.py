"""Compare embedding models on the eval questions, without a database or Groq.

    uv run python -m copilot.compare_models                       # current model only
    uv run python -m copilot.compare_models jinaai/jina-embeddings-v2-base-de

For each model: embed every chunk in data/processed/chunks.jsonl and every answerable
question in data/eval/questions.yaml, then check whether an expected source is among the
5 most similar chunks (semantic search only). Prints hit@5 and MRR, split by question
language, so we can see whether English questions find German pages.

It also prints the best-match similarity for answerable questions and for questions the
copilot should refuse. answer.MIN_SIMILARITY must stay below the lowest answerable score,
and each model has its own similarity scale, so re-check it whenever the model changes.

Each new model is downloaded once (0.2-1.2 GB) and cached by fastembed.
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from copilot.embed import MODEL_NAME, text_for_embedding
from copilot.evaluate import QUESTIONS_FILE, load_questions, retrieval_rank

CHUNKS_FILE = Path("data/processed/chunks.jsonl")
TOP_K = 5


def normalize(vectors) -> np.ndarray:
    matrix = np.array(list(vectors), dtype=np.float32)
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


def evaluate_model(name: str, chunks: list[dict], questions, refusals) -> dict:
    from fastembed import TextEmbedding

    model = TextEmbedding(name)
    # query_embed / passage_embed add the prefixes some models expect ("query: ...").
    passages = normalize(model.passage_embed([text_for_embedding(c) for c in chunks]))
    queries = normalize(model.query_embed([q.question for q in questions]))
    similarity = queries @ passages.T  # cosine similarity, one row per question
    refusal_queries = normalize(model.query_embed([q.question for q in refusals]))
    best_answerable = similarity.max(axis=1)
    best_refusal = (refusal_queries @ passages.T).max(axis=1)

    per_language: dict[str, list[int | None]] = {"en": [], "de": []}
    misses = []
    for i, q in enumerate(questions):
        best = np.argsort(-similarity[i])[:TOP_K]
        rank = retrieval_rank(q.expected_urls, [chunks[j]["url"] for j in best])
        per_language[q.language].append(rank)
        if rank is None:
            misses.append(q.id)
    return {
        "per_language": per_language,
        "misses": misses,
        "best_answerable": best_answerable,
        "best_refusal": best_refusal,
    }


def summary_line(ranks: list[int | None]) -> str:
    if not ranks:
        return "n/a"
    hits = sum(r is not None for r in ranks)
    mrr = sum(1 / r for r in ranks if r) / len(ranks)
    return f"hit@{TOP_K} {100 * hits / len(ranks):3.0f}% ({hits}/{len(ranks)})  MRR {mrr:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(prog="copilot.compare_models")
    parser.add_argument("models", nargs="*", help="fastembed model names to compare")
    args = parser.parse_args()
    models = [MODEL_NAME, *[m for m in args.models if m != MODEL_NAME]]

    chunks = [json.loads(line) for line in CHUNKS_FILE.read_text(encoding="utf-8").splitlines()]
    all_questions = load_questions(QUESTIONS_FILE)
    questions = [q for q in all_questions if not q.should_refuse]
    refusals = [q for q in all_questions if q.should_refuse]
    print(f"{len(chunks)} chunks, {len(questions)} answerable questions\n")

    for name in models:
        started = time.time()
        result = evaluate_model(name, chunks, questions, refusals)
        all_ranks = result["per_language"]["en"] + result["per_language"]["de"]
        print(f"{name}  ({time.time() - started:.0f}s)")
        print(f"  all:     {summary_line(all_ranks)}")
        print(f"  English: {summary_line(result['per_language']['en'])}")
        print(f"  German:  {summary_line(result['per_language']['de'])}")
        print(f"  missed:  {', '.join(result['misses']) or 'none'}")
        good, bad = result["best_answerable"], result["best_refusal"]
        print("  best-match similarity:")
        print(
            f"    answerable:    min {good.min():.2f}  10% {np.percentile(good, 10):.2f}"
            f"  median {np.median(good):.2f}"
        )
        print(
            f"    should-refuse: median {np.median(bad):.2f}  90% {np.percentile(bad, 90):.2f}"
            f"  max {bad.max():.2f}\n"
        )


if __name__ == "__main__":
    main()
