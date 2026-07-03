# --- Base stage (common for dev & prod) ---
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/venv \
    PATH="/venv/bin:$PATH"

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install runtime system dep
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# --- Development Stage ---
# Includes dev deps, tests, and source code
FROM base AS development

# Install all deps including dev
COPY pyproject.toml uv.lock ./
RUN uv sync --extra dev

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- Production Stage ---
# Optimized, lightweight, no dev deps, no tests
FROM base AS production

# Install only prod deps
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

# Copy app files
COPY app ./app/
COPY alembic ./alembic/
COPY alembic.ini ./
COPY scripts ./scripts/

# Final sync for production (no-dev)
RUN uv sync --no-dev

RUN groupadd -r devplanet && useradd -r -g devplanet devplanet
RUN chown -R devplanet:devplanet /app /venv
USER devplanet

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
