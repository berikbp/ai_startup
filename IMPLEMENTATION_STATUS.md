# Implementation Status

## Completed

Phase 2 Telegram booking flow has been implemented on top of the Phase 1 foundation.

- Added aiogram-based bot infrastructure with:
  - dispatcher wiring
  - FSM states
  - Russian booking prompts and keyboards
  - local polling entrypoint
- Added FastAPI webhook handling at `POST /webhook/{clinic_slug}` with basic secret validation.
- Added domain services for:
  - clinic lookup and test-clinic seeding
  - patient upsert
  - booking creation and duplicate detection
  - message logging
  - phone and datetime normalization
  - OpenAI-backed step extraction
- Added a repeatable seed command for the Phase 2 test clinic.
- Added focused automated tests for normalization and duplicate booking protection.

## Previously Completed

- Replaced the placeholder script with a real FastAPI entrypoint.
- Added an `app/` package with:
  - application factory
  - settings management
  - database session setup
  - tenant-aware SQLModel models
  - `/health` API route
- Added local infrastructure files:
  - `compose.yaml` for PostgreSQL
  - `.env.example` for local configuration
  - `.gitignore`
- Added Alembic configuration and the initial schema migration.
- Updated project dependencies in `pyproject.toml`.
- Generated and updated `uv.lock`.
- Updated `README.md` with local setup and run instructions.

## Database Schema Completed

The initial PostgreSQL schema is in place with these tables:

- `clinic`
- `clinic_user`
- `patient`
- `booking`
- `message`
- `alembic_version`

All tenant-scoped tables include `clinic_id`.

## Verification Completed

The following checks were completed successfully:

- `uv sync`
- `uv run alembic upgrade head`
- database schema creation in local PostgreSQL
- `/health` endpoint response: `{"status":"ok"}`

## Notes

- Local PostgreSQL was moved to port `5434` because port `5433` was already in use in the environment.
- Planning documents in `.planning/` were not modified as part of this implementation step.

## Not Completed Yet

The following items are still pending for later phases:

- dashboard UI
- authentication
- bot token management
- Redis-backed bot state
- production hardening

## Next Recommended Step

Start Phase 3:

- add owner registration and login
- build the booking list/dashboard surface
- expose conversation history and booking status updates
