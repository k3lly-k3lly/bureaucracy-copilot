FROM python:3.12-slim

# uv installs dependencies much faster than pip
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first so Docker can cache this layer
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Then copy the code and install the project itself
COPY src ./src
COPY data ./data
COPY README.md ./
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# Render sets $PORT; locally it defaults to 8000
CMD ["sh", "-c", "uvicorn copilot.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
