"""Turn a raw HTML page into clean Markdown: main content only, headings kept.

trafilatura removes navigation, headers, footers and cookie banners. We ask it
for Markdown so the section headings survive; the chunker splits on them.
"""

import re
from dataclasses import dataclass

import trafilatura

MIN_CONTENT_CHARS = 100

# Lines that start a new Markdown element: heading, list item, numbered item, table row.
STRUCTURAL = re.compile(r"^(#{1,6}\s|[-*+]\s|\d+[.)]\s|\|)")


def _is_text(line: str) -> bool:
    return not STRUCTURAL.match(line)


def normalize_markdown(markdown: str) -> str:
    """Repair text that trafilatura broke across lines.

    Pages often wrap words in links or glossary pop-ups, which leaves sentences like
    "You must register your\\n  place of residence\\n  \\n within **14 days**".
    We join broken lines back into sentences, drop bold/italic markers, and collapse
    extra spaces, while keeping headings, list items and table rows on their own lines.
    """
    markdown = markdown.replace("**", "").replace("__", "")
    blocks: list[list[str]] = []
    for raw_block in re.split(r"\n[ \t]*\n", markdown):
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_block.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            continue
        merged: list[str] = []
        for line in lines:
            # A plain text line continues the previous line (a wrapped sentence or list item),
            # unless the previous line is a heading.
            if merged and _is_text(line) and not merged[-1].startswith("#"):
                merged[-1] = f"{merged[-1]} {line}"
            else:
                merged.append(line)
        # A sentence split across two "paragraphs": previous block ends mid-sentence.
        if (
            blocks
            and _is_text(merged[0])
            and _is_text(blocks[-1][-1])
            and not blocks[-1][-1].rstrip().endswith((".", "!", "?", ":"))
        ):
            blocks[-1][-1] = f"{blocks[-1][-1]} {merged[0]}"
            merged = merged[1:]
        if merged:
            blocks.append(merged)
    return "\n\n".join("\n".join(block) for block in blocks)


@dataclass
class CleanPage:
    title: str
    markdown: str


def _extract(html: bytes | str, favor_recall: bool) -> str:
    return (
        trafilatura.extract(
            html,
            output_format="markdown",
            include_tables=True,
            include_links=False,
            include_comments=False,
            include_images=False,
            favor_recall=favor_recall,
        )
        or ""
    )


def clean_html(html: bytes | str) -> CleanPage | None:
    """Return the page's main content as Markdown, or None if nothing useful is left."""
    # trafilatura's default mode sometimes throws away most of a page: on the Berlin
    # rental guide it kept 1 of 5 sections. Its "recall" mode keeps more, but on other
    # pages it keeps *less*. Neither wins everywhere, so run both and keep the longer one.
    markdown = max(_extract(html, favor_recall=False), _extract(html, favor_recall=True), key=len)
    # trafilatura falls back to any leftover text (e.g. a lone menu) when a page
    # has no real content, so treat very short results as "nothing useful".
    if not markdown or len(markdown.strip()) < MIN_CONTENT_CHARS:
        return None
    metadata = trafilatura.extract_metadata(html)
    title = (metadata.title if metadata and metadata.title else "").strip()
    return CleanPage(title=title, markdown=normalize_markdown(markdown))
