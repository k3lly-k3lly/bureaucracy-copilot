"""Turn text into embeddings: lists of numbers that capture what the text MEANS.

Two texts with similar meaning get vectors that point in a similar direction,
even if they share no words, and even if one is English and the other German.
"""

from functools import lru_cache

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


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
    """Load the model once and reuse it. The first run downloads it (~220 MB)."""
    from fastembed import TextEmbedding

    return TextEmbedding(MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """One embedding (384 floats) per text, in the same order.

    fastembed returns numpy arrays lazily; .tolist() turns each into a plain list.
    """
    return [vector.tolist() for vector in get_model().embed(texts)]
