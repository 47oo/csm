# syntax=docker/dockerfile:1
# CSM backend image — Python 3.12 (architecture §2.1).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl is used by the Compose healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install .

# --- Test image: adds pytest/httpx and the test suite (never the runtime default) ---
FROM base AS test
COPY tests ./tests
RUN pip install ".[dev]"
CMD ["pytest", "tests"]

# --- Runtime image (default target): runs as non-root ---
FROM base AS runtime
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]