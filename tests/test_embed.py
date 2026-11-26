"""Tests for copilot/embed.py -

The first two tests check text_for_embedding (no model needed).
The "model" tests download the embedding model once (~640 MB) and check it really
understands meaning, across English and German.
"""

import math

import pytest

from copilot.embed import EMBEDDING_DIM, embed_texts, text_for_embedding


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


# --- text_for_embedding ------------------------------------------------------


def test_text_for_embedding_puts_title_and_section_first():
    chunk = {
        "title": "Wohnsitz anmelden",
        "section": "Wohnsitz anmelden > Gebühren",
        "text": "Die Anmeldung ist gebührenfrei.",
    }
    result = text_for_embedding(chunk)
    assert result.startswith("Wohnsitz anmelden")
    assert "Gebühren" in result
    assert result.endswith("Die Anmeldung ist gebührenfrei.")


def test_text_for_embedding_without_title_or_section():
    chunk = {"title": "", "section": "", "text": "Just the text."}
    assert text_for_embedding(chunk) == "Just the text."


# --- embed_texts (downloads the model the first time) ------------------------


@pytest.mark.model
def test_embed_texts_returns_one_vector_per_text():
    vectors = embed_texts(["first text", "second text", "third text"])
    assert len(vectors) == 3
    assert all(len(v) == EMBEDDING_DIM for v in vectors)
    assert all(isinstance(x, float) for x in vectors[0])


@pytest.mark.model
def test_similar_meaning_scores_higher_even_across_languages():
    question, german_answer, unrelated = embed_texts(
        [
            "How long do I have to register my new address?",
            "Sie müssen sich innerhalb von 14 Tagen nach dem Einzug anmelden.",
            "The rental deposit may not exceed three months' rent.",
        ]
    )
    assert cosine(question, german_answer) > cosine(question, unrelated)
