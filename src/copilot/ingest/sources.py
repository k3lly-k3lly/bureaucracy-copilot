"""Load the list of official sources from data/sources.yaml."""

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_SOURCES_FILE = Path("data/sources.yaml")


@dataclass(frozen=True)
class Source:
    url: str
    topic: str
    language: str
    note: str = ""


def load_sources(path: Path = DEFAULT_SOURCES_FILE) -> list[Source]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        Source(
            url=s["url"],
            topic=s["topic"],
            language=s["language"],
            note=s.get("note", ""),
        )
        for s in data["sources"]
    ]
