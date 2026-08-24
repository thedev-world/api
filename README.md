# thedev.world api

FastAPI backend for [thedev.world](https://thedev.world/), handling GitHub contribution ingestion, developer scoring, territory assignment, and asynchronous 3D planet snapshot generation.

> **Live:** [thedev.world](https://thedev.world/)

![Demo](./docs/demo.gif)

## Table of contents

- [Description](#description)
- [Getting started](#getting-started)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Task commands](#task-commands)
- [Code quality & testing](#code-quality--testing)
- [Contributing](#contributing)
- [License](#license)


## Description

[thedev.world](https://thedev.world/) lets developers visualize their GitHub activity on a 3D planet.
This API is the core engine: it ingests public GitHub activity, computes XP scores, assigns developers to hexagonal territories on thematic islands, and generates JSON snapshots served to the front via a CDN.

The API is designed to decouple synchronous traffic (user requests) from heavy background processing (GitHub API calls, 3D layout generation) using Celery workers.

## Getting started

### Prerequisites

- Docker and Docker Compose
- [Task](https://taskfile.dev/) : task runner used to simplify all common commands (not mandatory)

### Installation

1. Copy the environment file:
   ```bash
   cp .env.example .env
   ```
   Then configure your variables, especially the GitHub OAuth credentials (see [Configuration](#configuration)).

2. Build
   ```bash
   task build
   ```

2. Start the full backend stack and apply migrations:
   ```bash
   task dev
   task migrate-up
   ```
   The API starts in hot-reload mode and is available at [http://localhost:8000](http://localhost:8000).
   Interactive Swagger docs are available at `/docs`.

3. *(Optional)* Seed the database with fake developer profiles to test the planet rendering without real GitHub accounts:
   ```bash
   task seed -- --count 150 --clear
   ```

## Tech stack

- **Language**: Python 3.12+
- **Framework**: FastAPI
- **ORM**: SQLAlchemy 2 (async) + asyncpg
- **Database**: PostgreSQL
- **Cache & queue**: Redis
- **Background tasks**: Celery + Celery Beat
- **Object storage**: S3-compatible (MinIO locally, Scaleway in production)
- **Validation**: Pydantic v2
- **Migrations**: Alembic
- **Linting & formatting**: Ruff
- **Testing**: pytest + pytest-asyncio

## Architecture

```mermaid
flowchart TB
    subgraph Frontend
        Client[Next.js Client]
    end

    subgraph API ["FastAPI Application"]
        Router["Routers - auth, me, planet, islands…"]
        Services["Services - scoring, territory, github, snapshot…"]
        Models[SQLAlchemy async models]
        Schemas[Pydantic v2 schemas]

        Router <--> Schemas
        Router --> Services
        Services --> Models
    end

    subgraph Storage
        DB[(PostgreSQL)]
        Cache[(Redis - cache & queue)]
        S3[S3 / Object Storage]
    end

    subgraph Workers
        Worker[Celery Workers]
        Beat[Celery Beat]

        Beat -->|Schedule jobs| Cache
        Worker -->|Consume tasks| Cache
        Worker -->|Run computations| Services
    end

    Client -->|HTTP| Router
    Client -->|Read JSON snapshots| S3
    Models <-->|asyncpg| DB
    Services <-->|Cache & locks| Cache
    Services -->|Upload snapshots| S3
    Services -->|GraphQL / REST| GitHub[GitHub API]
```

### Project structure

```text
devplanet-api/
├── alembic/           # Database migrations and Alembic config
├── app/               # Main application code
│   ├── main.py        # FastAPI entry point
│   ├── database.py    # Async SQLAlchemy session and connection
│   ├── models/        # SQL table definitions (SQLAlchemy ORM)
│   ├── schemas/       # Validation and serialization schemas (Pydantic v2)
│   ├── routers/       # HTTP controllers and API endpoints
│   ├── services/      # Business logic (scoring, GitHub sync, territory placement)
│   └── workers/       # Celery app definition and async task definitions
├── tests/             # Unit and integration tests (pytest)
├── Taskfile.yml       # Task runner configuration
└── docker-compose.yml # Local service stack (API, worker, DB, Redis, MinIO)
```

## Configuration

All configuration is driven by environment variables defined in `.env`. Copy the example file to get started:

```bash
cp .env.example .env
```

The only required manual step is creating a **GitHub OAuth App** to enable authentication locally:

1. Go to GitHub **Settings -> Developer Settings -> OAuth Apps -> New OAuth App**.
2. Set **Homepage URL** to `http://localhost:3000`.
3. Set **Authorization callback URL** to `http://localhost:3000/api/v1/auth/github/callback` *(routed through Next.js so OAuth cookies stay same-origin)*.
4. Save the app and generate a **Client Secret**.
5. Copy the **Client ID** and **Client Secret** into your `.env`.

All other variables in `.env.example` are pre-configured for local development and automatically handle the connection to **PostgreSQL**, **Redis**, and the local **MinIO** S3-compatible storage provided by the Docker stack.

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL async connection string | `postgresql+asyncpg://devplanet:devplanet@postgres:5432/devplanet` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `CELERY_BROKER_URL` | Celery broker (Redis) | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend (Redis) | `redis://redis:6379/0` |
| `GITHUB_TOKEN` | GitHub personal access token (for API calls) | `ghp_...` |
| `GITHUB_OAUTH_CLIENT_ID` | GitHub OAuth App Client ID | `your_oauth_app_client_id` |
| `GITHUB_OAUTH_CLIENT_SECRET` | GitHub OAuth App Client Secret | `your_oauth_app_client_secret` |
| `OAUTH_CALLBACK_URL` | OAuth callback URL (must match GitHub App settings) | `http://localhost:3000/api/v1/auth/github/callback` |
| `ALLOWED_FRONTEND_ORIGINS` | Comma-separated CORS origins | `http://localhost:3000` |
| `JWT_SECRET_KEY` | HS256 secret for session JWTs (min. 32 chars) | `change-me-to-a-long-random-secret` |
| `TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting stored GitHub tokens | *(generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)* |
| `SESSION_COOKIE_SECURE` | Set to `true` in production (HTTPS only) | `false` |
| `S3_ENDPOINT_URL` | S3-compatible storage endpoint | `http://minio:9000` |
| `S3_ACCESS_KEY` | S3 access key | `devplanet` |
| `S3_SECRET_KEY` | S3 secret key | `devplanet` |
| `S3_BUCKET_NAME` | S3 bucket name | `devplanet` |
| `S3_REGION` | S3 region | `us-east-1` |
| `S3_PLANET_JSON_KEY` | Key for the planet snapshot JSON file | `planet-data.json` |

## Task commands

The project uses [Task](https://taskfile.dev/) as a task runner. Run `task` from the repository root to list all available commands.

| Command | Description |
| :--- | :--- |
| `task` / `task default` | List all available commands |
| `task build` | Build local Docker images |
| `task dev` | Start the full stack (Postgres, Redis, API, Celery worker) |
| `task down` | Stop and remove Docker containers |
| `task test` | Run pytest inside the API container (e.g. `task test -- tests/routers/test_health.py -vv`) |
| `task format` | Format code with Ruff (`app`, `alembic`, `tests`) |
| `task lint` | Check code compliance with Ruff |
| `task lint:fix` | Auto-fix Ruff violations |
| `task migrate-create` | Generate a new database migration (e.g. `MSG="add_column" task migrate-create`) |
| `task migrate-up` | Apply pending migrations (`alembic upgrade head`) |
| `task migrate-down` | Roll back the last database migration |
| `task seed` | Seed the database with fake developer profiles (e.g. `task seed -- --count 100 --clear`) |

## Code quality & testing

Before submitting changes, make sure linting and tests pass:

```bash
task lint       # Check
task format     # Format
task test       # Run the test suite
```

## Contributing

Contributions are welcome. Please follow these conventions to keep the history clean and reviews smooth.

### Branch naming

- `feat/feature-name` — new feature (e.g. `feat/github-graphql-sync`)
- `fix/bug-name` — bug fix
- `refactor/refactor-name` — code restructuring with no functional changes
- `chore/topic` — maintenance tasks, config updates, dependency bumps

### Commit conventions

This project follows the [Conventional Commits](https://www.conventionalcommits.org/) specification. All commit messages must be written **in English**:

```
type(scope): description
```

Examples:
- `feat(scoring): add language diversity bonus`
- `fix(celery): solve race condition during cell assignment`
- `chore(deps): bump sqlalchemy version`


### Code coverage

Every new feature, bug fix, or any code update must include the appropriate tests to ensure the changes are properly covered and validated.
All contributions must pass the existing test suite before being approved.

### Process

1. Fork the repository.
2. Create your branch (`git checkout -b feat/my-feature`).
3. Make your changes.
4. Make sure linting and tests pass (`task lint` and `task test`).
5. Commit and push to your fork.
6. Open a detailed Pull Request.

To report a bug or request a feature, open an [Issue](https://github.com/thedev-world/devplanet-api/issues).

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
