"""Polite downloader.

- Checks each site's robots.txt before downloading.
- Waits between requests so we never hammer a government server.
- Saves the raw page plus a small metadata file in data/raw/, so later steps
  can be re-run without downloading everything again.
"""

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from copilot.ingest.sources import Source

RAW_DIR = Path("data/raw")
USER_AGENT = (
    "BureaucracyCopilotBot/0.1 "
    "(student portfolio project; https://github.com/k3lly-k3lly/bureaucracy-copilot)"
)
DELAY_SECONDS = 2.0
TIMEOUT_SECONDS = 20.0

# Some servers answer "slow down" (429) or "busy" (503). We wait and try again,
# a little longer each time, instead of giving up or hammering the server.
RETRY_STATUS_CODES = {429, 503}
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 10.0
MAX_RETRY_WAIT_SECONDS = 60.0

# Phrases that bot-protection services put on their challenge pages. Such pages often
# come back with "200 OK", so the status code alone does not tell us we were blocked.
BOT_CHALLENGE_MARKERS = (
    "verifying your browser",
    "<title>radware page</title>",
    "<title>just a moment...</title>",  # Cloudflare
    "please enable javascript and cookies to continue",
    "captcha-delivery.com",
)


@dataclass
class FetchResult:
    url: str
    topic: str
    language: str
    status: str  # "ok", "cached", "blocked_by_robots", "bot_protection", "error"
    http_status: int | None = None
    content_type: str | None = None
    fetched_at: str | None = None
    raw_path: str | None = None
    error: str | None = None


def url_id(url: str) -> str:
    """Short, stable file name for a URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def raw_paths(url: str, raw_dir: Path = RAW_DIR) -> tuple[Path, Path]:
    """Where the page body and its metadata are stored."""
    base = raw_dir / url_id(url)
    return base.with_suffix(".body"), base.with_suffix(".json")


class RobotsChecker:
    """Downloads each site's robots.txt once and answers 'may I fetch this URL?'."""

    def __init__(self, client: httpx.Client):
        self.client = client
        self._cache: dict[str, RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parts = urlparse(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self._cache:
            self._cache[root] = self._load(root)
        parser = self._cache[root]
        # No robots.txt (or it could not be read) means no restrictions.
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    def _load(self, root: str) -> RobotFileParser | None:
        try:
            response = self.client.get(f"{root}/robots.txt")
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser


def is_bot_challenge(html: str) -> bool:
    """Detect bot-protection pages (Radware, Cloudflare, captchas) served instead of content."""
    head = html[:20000].lower()
    return any(marker in head for marker in BOT_CHALLENGE_MARKERS)


def retry_wait_seconds(response: httpx.Response, attempt: int) -> float:
    """How long to wait before retrying: the server's Retry-After if given, else back off."""
    retry_after = response.headers.get("retry-after", "")
    if retry_after.isdigit():
        return min(float(retry_after), MAX_RETRY_WAIT_SECONDS)
    return min(RETRY_BASE_SECONDS * 2**attempt, MAX_RETRY_WAIT_SECONDS)


def get_with_retry(client: httpx.Client, url: str, sleep=time.sleep) -> httpx.Response:
    """GET a URL, retrying when the server says it is busy (429) or unavailable (503)."""
    for attempt in range(MAX_RETRIES + 1):
        response = client.get(url)
        if response.status_code not in RETRY_STATUS_CODES or attempt == MAX_RETRIES:
            return response
        wait = retry_wait_seconds(response, attempt)
        print(f"         got {response.status_code}, waiting {wait:.0f}s before retrying...")
        sleep(wait)
    return response


def fetch_source(
    source: Source,
    client: httpx.Client,
    robots: RobotsChecker,
    raw_dir: Path = RAW_DIR,
    refresh: bool = False,
) -> FetchResult:
    """Download one source, or reuse the cached copy if we already have it."""
    body_path, meta_path = raw_paths(source.url, raw_dir)
    base = FetchResult(url=source.url, topic=source.topic, language=source.language, status="")

    if body_path.exists() and meta_path.exists() and not refresh:
        cached = json.loads(meta_path.read_text(encoding="utf-8"))
        return FetchResult(**{**cached, "status": "cached"})

    if not robots.allowed(source.url):
        base.status = "blocked_by_robots"
        return base

    try:
        response = get_with_retry(client, source.url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        base.status = "error"
        base.error = str(exc)
        return base

    if is_bot_challenge(response.text):
        # The site answered "200 OK" but sent a "prove you are a browser" page.
        # We respect that and do not save it as if it were the real content.
        base.status = "bot_protection"
        base.http_status = response.status_code
        return base

    raw_dir.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(response.content)
    result = FetchResult(
        url=source.url,
        topic=source.topic,
        language=source.language,
        status="ok",
        http_status=response.status_code,
        content_type=response.headers.get("content-type", ""),
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        raw_path=str(body_path),
    )
    meta_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def fetch_all(
    sources: list[Source],
    raw_dir: Path = RAW_DIR,
    refresh: bool = False,
    delay: float = DELAY_SECONDS,
) -> list[FetchResult]:
    results = []
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        robots = RobotsChecker(client)
        for i, source in enumerate(sources, start=1):
            result = fetch_source(source, client, robots, raw_dir, refresh)
            results.append(result)
            print(f"[{i:>2}/{len(sources)}] {result.status:<17} {source.url}")
            if result.status == "ok" and i < len(sources):
                time.sleep(delay)  # be polite: only wait after real downloads
    return results
