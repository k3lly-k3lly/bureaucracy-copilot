# Bureaucracy Copilot

> A bilingual (English/German) assistant that answers international students' questions about German bureaucracy — and cites the official source for every claim.

![CI](https://github.com/your-username/bureaucracy-copilot/actions/workflows/ci.yml/badge.svg)

**Status:** 🚧 Week 1 of 8 — project foundations.

## The problem

New arrivals in Germany lose weeks to address registration (Anmeldung), residence permits, health insurance, blocked accounts and rental contracts. The official information is spread across dozens of mostly German-language pages, and forums often give confident but wrong answers.

## What it will do

- Answer questions in English or German, using **only** official sources
- Link every claim to the exact passage it came from
- Say "I don't know" when the sources don't cover a question
- Measure its own accuracy with a test set of 100+ questions that runs in CI

Scope for v1: Berlin, five topics (Anmeldung, student residence permit, health insurance, renting, banking).

> ⚠️ Not legal advice. Always check the linked official source.

## Tech stack

Python · FastAPI · PostgreSQL + pgvector · Docker · GitHub Actions · (coming) Groq-hosted open LLMs · Next.js/TypeScript

Runs entirely on free tiers — see the roadmap for the reasoning.

## Run it locally

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/) and [uv](https://docs.astral.sh/uv/).

```bash
# Start Postgres (with pgvector) and the API
docker compose up --build

# In another terminal
curl http://localhost:8000/health      # {"status":"ok",...}
curl http://localhost:8000/health/db   # shows Postgres + pgvector versions
```

API docs: http://localhost:8000/docs

## Development

```bash
uv sync                       # install dependencies
uv run pre-commit install     # lint automatically on every commit
docker compose up -d db       # start only the database
cp .env.example .env          # point the API at it
uv run pytest -v              # run tests (DB tests run when DATABASE_URL is set)
uv run uvicorn copilot.main:app --reload
```

## Roadmap

- [x] Week 1 — Foundations: API skeleton, Docker, CI
- [ ] Week 2 — Ingestion pipeline
- [ ] Week 3 — Retrieval + cited answers
- [ ] Week 4 — Evaluation harness
- [ ] Weeks 5–6 — Frontend
- [ ] Week 7 — Improve with data
- [ ] Week 8 — Deploy + launch
