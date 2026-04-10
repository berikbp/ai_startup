# AI Startup

Phase 5 runtime hardening baseline for an AI clinic receptionist SaaS focused on clinics in Kazakhstan.

## Current Scope

- FastAPI application and Telegram webhook endpoint
- aiogram 3 booking bot with local polling support
- PostgreSQL persistence for clinics, owners, patients, bookings, messages, and Telegram bot configuration
- Russian-language booking FSM
- OpenAI-assisted extraction for the active booking step
- Duplicate booking protection and booking guardrails
- Multi-clinic owner signup and login
- Protected owner dashboard with booking list, detail view, status updates, and Telegram bot status
- Clinic settings page for storing encrypted Telegram bot tokens
- Clinic-specific webhook secret validation and bot resolution
- CSRF-protected owner-side form posts with hardened session cookies
- Redis-backed aiogram FSM storage with 24-hour conversation TTL
- Redis-backed Telegram webhook idempotency keyed by clinic and `update_id`
- Structured JSON logging for webhook, Telegram configuration, and OpenAI runtime paths

## Local Development

Start PostgreSQL:

```bash
docker compose up -d db redis
```

Create a local environment file from the example:

```bash
cp .env.example .env
```

Required variables for the current baseline:

- `AUTH_SECRET_KEY`
- `TELEGRAM_TOKEN_ENCRYPTION_KEY`

Optional local-development variables:

- `OPENAI_API_KEY`
- `REDIS_URL`
- `REDIS_KEY_PREFIX`
- `TELEGRAM_WEBHOOK_BASE_URL`
- `TELEGRAM_BOT_TOKEN` for local polling convenience
- `TELEGRAM_FSM_STATE_TTL_SECONDS`
- `TELEGRAM_FSM_DATA_TTL_SECONDS`
- `TELEGRAM_UPDATE_IDEMPOTENCY_TTL_SECONDS`
- `AUTH_CSRF_COOKIE_NAME`
- `AUTH_CSRF_MAX_AGE_SECONDS`
- `LOG_LEVEL`
- `TEST_CLINIC_SLUG`
- `TEST_CLINIC_NAME`
- `TEST_CLINIC_PHONE`
- `TEST_CLINIC_TIMEZONE`

Install dependencies and sync the environment:

```bash
uv sync --group dev
```

Apply the initial migration:

```bash
uv run alembic upgrade head
```

Optionally seed or update a demo clinic row for local polling:

```bash
uv run python -m app.seed
```

Run the application:

```bash
auv run uvicorn main:app --reload
```

Open the owner registration page to create a clinic and its first owner:

```text
http://127.0.0.1:8000/owner/register
```

After the owner exists, use the login page:

```text
http://127.0.0.1:8000/owner/login
```

Run the Telegram bot in local polling mode:

```bash
uv run python -m app.bot.polling
```

Run the automated checks:

```bash
uv run pytest -q
```

The current test suite expects local PostgreSQL to be running and migrations applied.

Verify the health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Telegram Webhook

Webhook route:

```text
POST /webhook/{clinic_slug}
```

Webhook processing now resolves the clinic-specific bot configuration from the database, validates the clinic-specific webhook secret, and short-circuits duplicate Telegram retries by `update_id` before dispatching the update.

## Owner Area

The current owner area provides:

- clinic signup with first-owner creation
- owner login/logout with an HTTP-only cookie
- booking list at `/owner/dashboard`
- booking detail page with patient/message context
- booking status updates to `pending`, `confirmed`, and `cancelled`
- clinic settings at `/owner/settings`
- Telegram connection status on the dashboard
- encrypted Telegram bot token storage per clinic

## Security Baseline

- Owner-side POST routes use signed CSRF tokens rendered into forms and validated against a dedicated cookie.
- The owner session cookie is `HttpOnly`, `SameSite=Lax`, and `Secure` outside local development.
- Owner HTML responses send `Cache-Control: no-store` to avoid caching authenticated pages.
- Telegram webhook requests are validated with a clinic-specific secret token before processing.
- Duplicate Telegram webhook deliveries return HTTP 200 without reprocessing side effects.

## Runtime Notes

- Redis is now required for the bot runtime because both FSM state and webhook idempotency use it.
- The default local Redis URL is `redis://localhost:6379/0`.
- Runtime logs are emitted as JSON-style lines so webhook rejects, duplicate suppressions, and OpenAI/Telegram failures are visible in deployment logs.

## What The App Persists

After the user confirms a booking request, the app writes:

- a `clinic` row for each onboarded clinic
- a `clinic_user` row for each owner
- a `clinic_telegram_config` row when a bot token is connected
- a `patient` row keyed by `clinic_id` and `telegram_user_id`
- a `booking` row with `pending` status
- `message` rows for inbound and outbound turns
