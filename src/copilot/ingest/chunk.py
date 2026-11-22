"""Split a cleaned page into chunks: small passages that search can return and cite.

Strategy:
1. Split on Markdown headings, so each chunk belongs to one section of the page.
2. Keep the heading path (e.g. "Wohnsitz anmelden > Voraussetzungen") with the chunk,
   because a passage like "Bring your passport" means little without its heading.
3. If a section is too long, split it further at paragraph boundaries.
"""

import re
from dataclasses import dataclass

HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
MAX_CHARS = 1500  # roughly 300-400 words: long enough for context, short enough to be precise
MIN_CHARS = 40  # drop fragments like a lone "Back to top"


@dataclass
class Section:
    heading_path: list[str]
    text: str


@dataclass
class Chunk:
    section: str  # heading path joined with " > "
    text: str
    position: int  # order within the page


def split_sections(markdown: str) -> list[Section]:
    """Group lines under the most recent heading, tracking the heading hierarchy."""
    sections: list[Section] = []
    path: list[tuple[int, str]] = []  # (level, heading text)
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            sections.append(Section([h for _, h in path], text))
        buffer.clear()

    for line in markdown.splitlines():
        match = HEADING.match(line)
        if match:
            flush()
            level, heading = len(match.group(1)), match.group(2)
            path = [(lvl, h) for lvl, h in path if lvl < level]  # drop deeper/equal headings
            path.append((level, heading))
        else:
            buffer.append(line)
    flush()
    return sections


def split_long_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split text at paragraph breaks into pieces of at most max_chars (when possible)."""
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pieces.append(current)
        # A single paragraph longer than the limit is split at sentence ends.
        while len(paragraph) > max_chars:
            cut = paragraph.rfind(". ", 0, max_chars)
            cut = cut + 1 if cut > 0 else max_chars
            pieces.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        current = paragraph
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(markdown: str, max_chars: int = MAX_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in split_sections(markdown):
        for piece in split_long_text(section.text, max_chars):
            if len(piece) >= MIN_CHARS:
                chunks.append(Chunk(" > ".join(section.heading_path), piece, len(chunks)))
    return chunks
