# Devplanet API

Backend HTTP API for **Devplanet**, built with **FastAPI**.

**Stack:** Python 3.12+, FastAPI, SQLAlchemy 2 (async) with asyncpg, Alembic for migrations, PostgreSQL, Redis, and Celery for background work. The app is containerised with docker compose, linting and tests use Ruff and pytest inside the API image. Configuration is driven by environment variables (see `.env.example`).

## Task commands

Run these from this directory with [Task](https://taskfile.dev/) installed.

| Command | Description |
|--------|-------------|
| `task` / `task default` | List available tasks |
| `task build` | Build Docker images |
| `task dev` | Start Postgres, Redis, API, and Celery worker |
| `task down` | Stop and remove containers |
| `task test` | Run pytest in the API container (pass extra args after `--`, e.g. `task test -- tests/routers/test_health.py -vv`) |
| `task format` | Run Ruff format on `app`, `alembic`, and `tests` in the API container |
| `task lint` | Run Ruff check in the API container |
| `task lint:fix` | Run Ruff check with `--fix` in the API container |
| `task migrate-create` | Create an Alembic autogenerate revision (optional: `MSG=...`) |
| `task migrate-up` | Apply migrations (`upgrade head`) |
| `task migrate-down` | Downgrade one revision |

Copy `.env.example` to `.env` and adjust as needed before running the stack.
