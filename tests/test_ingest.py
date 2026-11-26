"""Tests for the ingestion pipeline. They never touch the real internet:
downloads go through httpx.MockTransport, which plays the role of a website."""

from pathlib import Path

import httpx

from copilot.ingest.chunk import chunk_markdown, split_long_text, split_sections
from copilot.ingest.clean import clean_html, normalize_markdown
from copilot.ingest.fetch import (
    RobotsChecker,
    fetch_source,
    get_with_retry,
    is_bot_challenge,
    raw_paths,
)
from copilot.ingest.sources import Source, load_sources

FIXTURE = Path(__file__).parent / "fixtures" / "anmeldung.html"
SOURCE = Source(url="https://example.berlin/anmeldung", topic="anmeldung", language="de")


# --- sources -----------------------------------------------------------------


def test_load_sources_reads_real_file():
    sources = load_sources()
    assert len(sources) > 0
    assert all(s.url.startswith("https://") for s in sources)


# --- cleaning ----------------------------------------------------------------


def test_clean_keeps_content_and_drops_boilerplate():
    page = clean_html(FIXTURE.read_bytes())
    assert page is not None
    assert "14 Tagen" in page.markdown
    assert "## Erforderliche Unterlagen" in page.markdown
    assert "Impressum" not in page.markdown  # footer removed
    assert "Startseite" not in page.markdown  # navigation removed
    assert page.title.startswith("Wohnsitz anmelden")


def test_normalize_repairs_broken_sentences():
    # Real example from willkommenszentrum.berlin.de
    broken = "You must register your \n  place of residence\n  \n within **14 days of moving in**."
    assert normalize_markdown(broken) == (
        "You must register your place of residence within 14 days of moving in."
    )


def test_normalize_keeps_structure():
    markdown = "## Documents\n\n- Passport\n- Landlord's\n  confirmation\n\nThat is all.\n\nNext."
    assert normalize_markdown(markdown) == (
        "## Documents\n\n- Passport\n- Landlord's confirmation\n\nThat is all.\n\nNext."
    )


def test_clean_keeps_every_section_of_the_berlin_rental_guide():
    # Regression: trafilatura's default mode kept only the last of five sections here,
    # so the deposit rules ("Mietsicherheiten") never reached the database.
    html = (Path(__file__).parent / "fixtures" / "berlin_mietvertraege.html").read_bytes()
    text = clean_html(html).markdown
    assert "Vertragsfreiheit" in text  # section 1
    assert "Mietsicherheiten" in text  # section 3
    assert "Abstandszahlung" in text  # section 4


def test_clean_returns_none_for_empty_page():
    assert clean_html("<html><body><nav>Menu</nav></body></html>") is None


# --- chunking ----------------------------------------------------------------


def test_sections_keep_heading_hierarchy():
    markdown = clean_html(FIXTURE.read_bytes()).markdown
    paths = [" > ".join(s.heading_path) for s in split_sections(markdown)]
    assert "Wohnsitz anmelden > Voraussetzungen" in paths
    # h3 nests under the h2 above it
    assert "Wohnsitz anmelden > Erforderliche Unterlagen > Für Familien" in paths
    # a new h2 replaces the previous h2 and its h3
    assert "Wohnsitz anmelden > Gebühren" in paths


def test_chunks_are_numbered_in_page_order():
    chunks = chunk_markdown(clean_html(FIXTURE.read_bytes()).markdown)
    assert [c.position for c in chunks] == list(range(len(chunks)))
    assert any("Reisepass" in c.text for c in chunks)


def test_long_sections_are_split_at_paragraphs():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(10))
    pieces = split_long_text(text, max_chars=800)
    assert len(pieces) > 1
    assert all(len(p) <= 800 for p in pieces)
    assert "".join(pieces).count("Paragraph") == 10  # nothing lost


def test_tiny_fragments_are_dropped():
    chunks = chunk_markdown("# Title\n\nok\n\n## Real section\n\n" + "Useful content. " * 10)
    assert len(chunks) == 1
    assert chunks[0].section == "Title > Real section"


# --- downloading -------------------------------------------------------------


def make_client(robots_txt: str, page_status: int = 200) -> tuple[httpx.Client, list[str]]:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots_txt)
        return httpx.Response(
            page_status, content=FIXTURE.read_bytes(), headers={"content-type": "text/html"}
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), requested


def test_fetch_saves_page_and_metadata(tmp_path):
    client, _ = make_client(robots_txt="User-agent: *\nAllow: /")
    result = fetch_source(SOURCE, client, RobotsChecker(client), raw_dir=tmp_path)
    body_path, meta_path = raw_paths(SOURCE.url, tmp_path)
    assert result.status == "ok"
    assert body_path.read_bytes() == FIXTURE.read_bytes()
    assert meta_path.exists()
    assert result.fetched_at is not None


def test_second_fetch_uses_cache(tmp_path):
    client, requested = make_client(robots_txt="")
    robots = RobotsChecker(client)
    fetch_source(SOURCE, client, robots, raw_dir=tmp_path)
    requests_after_first = len(requested)
    result = fetch_source(SOURCE, client, robots, raw_dir=tmp_path)
    assert result.status == "cached"
    assert len(requested) == requests_after_first  # no new download


def test_robots_txt_is_respected(tmp_path):
    client, requested = make_client(robots_txt="User-agent: *\nDisallow: /")
    result = fetch_source(SOURCE, client, RobotsChecker(client), raw_dir=tmp_path)
    assert result.status == "blocked_by_robots"
    assert "/anmeldung" not in requested  # the page itself was never requested


def test_bot_challenge_page_is_not_saved(tmp_path):
    # Real case: make-it-in-germany.com answered "200 OK" with a Radware challenge page.
    challenge = (
        "<html><head><title>Radware Page</title></head><body>"
        "Verifying your browser before proceeding... Incident ID: 123</body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=challenge, headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_source(SOURCE, client, RobotsChecker(client), raw_dir=tmp_path)
    assert result.status == "bot_protection"
    assert not raw_paths(SOURCE.url, tmp_path)[0].exists()


def test_normal_page_is_not_mistaken_for_challenge():
    assert not is_bot_challenge(FIXTURE.read_text(encoding="utf-8"))


def test_retries_after_too_many_requests():
    calls = {"n": 0}
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "5"})
        return httpx.Response(200, text="finally")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    response = get_with_retry(client, "https://example.eu/page", sleep=waits.append)
    assert response.status_code == 200
    assert waits == [5.0, 5.0]  # honoured the server's Retry-After header


def test_gives_up_after_max_retries():
    waits: list[float] = []
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    response = get_with_retry(client, "https://example.eu/page", sleep=waits.append)
    assert response.status_code == 429
    assert len(waits) == 3  # MAX_RETRIES
    assert waits == sorted(waits)  # each wait at least as long as the one before


def test_http_errors_are_reported_not_raised(tmp_path):
    client, _ = make_client(robots_txt="", page_status=404)
    result = fetch_source(SOURCE, client, RobotsChecker(client), raw_dir=tmp_path)
    assert result.status == "error"
    assert "404" in result.error
    assert not raw_paths(SOURCE.url, tmp_path)[0].exists()
