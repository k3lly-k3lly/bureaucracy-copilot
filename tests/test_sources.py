"""Checks that data/sources.yaml stays well-formed as you add sources."""

from pathlib import Path
from urllib.parse import urlparse

import yaml

SOURCES_FILE = Path(__file__).parent.parent / "data" / "sources.yaml"
ALLOWED_LANGUAGES = {"de", "en"}


def load_sources():
    data = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))
    return data["topics"], data["sources"]


def test_every_source_is_valid():
    topics, sources = load_sources()
    for source in sources:
        assert urlparse(source["url"]).scheme == "https", source["url"]
        assert source["topic"] in topics, f"Unknown topic: {source['topic']}"
        assert source["language"] in ALLOWED_LANGUAGES, source["url"]


def test_no_duplicate_urls():
    _, sources = load_sources()
    urls = [s["url"] for s in sources]
    assert len(urls) == len(set(urls)), "Duplicate URLs in sources.yaml"
