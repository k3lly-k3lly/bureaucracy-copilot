"""Very small English/German detector, good enough for short questions.

It counts common function words ("the", "is" vs "der", "ist"). No model or library needed,
and it is predictable, which matters because the answer language depends on it.
"""

import re

GERMAN_WORDS = {
    "der", "die", "das", "dem", "den", "und", "ist", "sie", "ich", "mich", "mir", "mein", "meine",
    "nicht", "mit", "ein", "eine", "einen", "für", "muss", "kann", "darf", "wie", "was", "wo",
    "wann", "welche", "welcher", "welches", "nach", "bei", "von", "zu", "im", "auf", "oder", "wenn",
    "du", "dich", "dir", "musst", "sein", "sind", "um", "ja", "nein", "auch", "nur", "es", "sich",
    "wird", "werden", "haben", "hat", "ihre", "ihnen", "einer", "zum", "zur", "vom", "beim", "als",
}  # fmt: skip
ENGLISH_WORDS = {
    "the", "and", "is", "are", "you", "your", "to", "of", "a", "an", "for", "must", "can", "i",
    "do", "does", "what", "how", "where", "when", "which", "my", "need", "have", "in", "at", "if",
}  # fmt: skip


def detect_language(text: str) -> str:
    """Return 'de' or 'en'. Ties go to German only if the text has umlauts or ß."""
    words = re.findall(r"[a-zäöüß]+", text.lower())
    german = sum(w in GERMAN_WORDS for w in words)
    english = sum(w in ENGLISH_WORDS for w in words)
    if german != english:
        return "de" if german > english else "en"
    return "de" if re.search(r"[äöüß]", text.lower()) else "en"


LANGUAGE_NAMES = {"en": "English", "de": "German"}
