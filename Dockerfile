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

# Render sets $PORT; locally it defaults to 8000.
# --proxy-headers: on Render every request arrives through Render's proxy, so the visitor's
# real IP is in the X-Forwarded-For header. The rate limiter needs that IP, not the proxy's.
# Trusting the header from any address (*) is safe only because the container can't be
# reached except through Render's proxy.
CMD ["sh", "-c", "uvicorn copilot.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
