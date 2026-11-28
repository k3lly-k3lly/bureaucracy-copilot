"""Shared test setup: read DATABASE_URL from .env so database tests run locally too."""

import os
from pathlib import Path

import pytest

ENV_FILE = Path(__file__).parent.parent / ".env"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Every test starts with empty rate-limit counts, so tests can't block each other."""
    from copilot import main

    for limiter in (main.ask_per_minute, main.ask_per_day, main.feedback_per_minute):
        limiter.reset()
