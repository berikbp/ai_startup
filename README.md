# AI Startup

Phase 1 foundation for an AI clinic receptionist SaaS focused on clinics in Kazakhstan.

## Phase 1 Scope

- FastAPI application scaffold
- PostgreSQL data model with tenant-aware tables
- Alembic migrations
- Local development via Docker Compose
- Railway-ready health check endpoint

## Local Development

Start PostgreSQL:

```bash
docker compose up -d db
```

Create a local environment file from the example:

```bash
cp .env.example .env
```

Install dependencies and sync the environment:

```bash
uv sync
```

Apply the initial migration:

```bash
uv run alembic upgrade head
```

Run the application:

```bash
uv run uvicorn main:app --reload
```

Verify the health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```
