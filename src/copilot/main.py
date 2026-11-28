"""FastAPI entry point. Run locally with: uv run uvicorn copilot.main:app --reload"""

from collections.abc import Callable, Iterator
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from copilot import __version__
from copilot.answer import Llm, answer_question, groq_llm
from copilot.config import get_settings
from copilot.db import check_database, connect, save_feedback
from copilot.search import hybrid_search

settings = get_settings()

app = FastAPI(title=settings.app_name, version=__version__)

# Browsers block a page from calling an API on a different address unless the API allows it.
# The chat page runs on localhost:3000 (dev) or github.io (live), the API elsewhere, so list
# exactly those sites here: any other website still can't use the API from a visitor's browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

Topic = Literal["anmeldung", "residence_permit", "health_insurance", "renting", "banking"]


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


# --- /ask --------------------------------------------------------------------------------------
# Each dependency below can be swapped in tests (app.dependency_overrides), so the endpoint is
# tested without a real database, model download or Groq account.


def get_db() -> Iterator:
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    with connect(settings.database_url) as conn:
        yield conn


def get_embedder() -> Callable[[list[str]], list[list[float]]]:
    from copilot.embed import embed_texts  # imported lazily: loading the model takes a moment

    return embed_texts


def get_llm() -> Llm:
    if not settings.groq_api_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured")
    return groq_llm(settings.groq_api_key, settings.groq_model)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    topic: Topic | None = None


class CitationOut(BaseModel):
    number: int
    url: str
    section: str
    text: str


class AskResponse(BaseModel):
    answer: str
    refused: bool
    citations: list[CitationOut]
    reason: str = ""


@app.post("/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    conn: Annotated[object, Depends(get_db)],
    embed: Annotated[Callable, Depends(get_embedder)],
    llm: Annotated[Llm, Depends(get_llm)],
) -> AskResponse:
    """Answer a question from the official sources, with citations - or refuse honestly."""
    query_embedding = embed([request.question])[0]
    results = hybrid_search(conn, request.question, query_embedding, limit=5, topic=request.topic)
    try:
        result = answer_question(request.question, results, llm)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            busy = "Answer service is busy, try again"
            raise HTTPException(status_code=503, detail=busy) from exc
        raise HTTPException(status_code=502, detail="Answer service failed") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Answer service unreachable") from exc
    return AskResponse(
        answer=result.text,
        refused=result.refused,
        citations=[CitationOut(**vars(c)) for c in result.citations],
        reason=result.reason,
    )


# --- /feedback ---------------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    """What the chat page sends when someone clicks "Yes" or "No" under an answer."""

    helpful: bool
    question: str = Field(min_length=3, max_length=500)  # same limits as /ask
    answer: str = Field(max_length=4000)
    refused: bool
    cited_urls: list[str] = Field(default_factory=list, max_length=10)


class FeedbackResponse(BaseModel):
    id: int


@app.post("/feedback", response_model=FeedbackResponse, status_code=201)
def feedback(
    request: FeedbackRequest,
    conn: Annotated[object, Depends(get_db)],
) -> FeedbackResponse:
    """Store a "was this helpful?" vote, so bad answers can be found and fixed later."""
    return FeedbackResponse(id=save_feedback(conn, **request.model_dump()))
