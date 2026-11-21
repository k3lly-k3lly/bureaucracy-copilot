"""FastAPI entry point. Run locally with: uv run uvicorn copilot.main:app --reload"""

from fastapi import FastAPI, HTTPException

from copilot import __version__
from copilot.config import get_settings
from copilot.db import check_database

settings = get_settings()

app = FastAPI(title=settings.app_name, version=__version__)


@app.get("/health")
def health() -> dict:
    """Liveness check: the API process is up. Does not touch the database."""
    return {"status": "ok", "version": __version__}


@app.get("/health/db")
def health_db() -> dict:
    """Readiness check: the database is reachable and pgvector is installed."""
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    try:
        info = check_database(settings.database_url)
    except Exception as exc:  # report any connection problem as "not ready"
        raise HTTPException(status_code=503, detail=f"Database unreachable: {exc}") from exc
    if info["pgvector_version"] is None:
        raise HTTPException(status_code=503, detail="pgvector extension is not installed")
    return {"status": "ok", **info}
