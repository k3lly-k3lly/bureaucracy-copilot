"""Turn text into embeddings: lists of numbers that capture what the text MEANS.

Two texts with similar meaning get vectors that point in a similar direction,
even if they share no words, and even if one is English and the other German.
"""

from functools import lru_cache

# Chosen in Week 4 with `python -m copilot.compare_models`: on our eval questions it put the
# right page in the top 5 for 92% of questions, in English AND German. The previous model
# (paraphrase-multilingual-MiniLM-L12-v2, 384 dims) often failed to match an English
# question to a German page.
MODEL_NAME = "jinaai/jina-embeddings-v2-base-de"
EMBEDDING_DIM = 768


def text_for_embedding(chunk: dict) -> str:
    """Put the page title and section heading in front of the chunk text.

    "It is free of charge." means little alone; with its heading in front
    ("Wohnsitz anmelden > Gebühren") the model knows WHAT is free of charge.
    """
    parts = [chunk.get("title", "").strip(), chunk.get("section", "").strip()]
    header = " > ".join(p for p in parts if p)
    return f"{header}\n{chunk['text']}" if header else chunk["text"]


@lru_cache(maxsize=1)
def get_model():
    """Load the model once and reuse it. The first run downloads it (~640 MB)."""
    from fastembed import TextEmbedding

    return TextEmbedding(MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """One embedding (EMBEDDING_DIM floats) per text, in the same order.

    fastembed returns numpy arrays lazily; .tolist() turns each into a plain list.
    """
    return [vector.tolist() for vector in get_model().embed(texts)]
