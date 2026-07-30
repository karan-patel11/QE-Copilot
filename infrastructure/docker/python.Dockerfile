# Shared image for the Python services (api, worker, scheduler).
# The service to run is selected via the compose `command`, so all three share
# one build and one set of domain packages (no duplication — ADR-0001).
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps kept minimal; psycopg[binary] ships its own libpq.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY packages ./packages
COPY apps ./apps
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

RUN pip install --upgrade pip && pip install -e .

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

ENTRYPOINT ["tini", "--"]

# Default command runs the API; overridden per service in docker-compose.yml.
CMD ["uvicorn", "qe_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
