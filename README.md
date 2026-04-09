# AI Startup

Phase 3 owner dashboard for an AI clinic receptionist SaaS focused on clinics in Kazakhstan.

## Current Scope

- FastAPI application and Telegram webhook endpoint
- aiogram 3 booking bot with local polling support
- PostgreSQL persistence for clinics, patients, bookings, and messages
- Russian-language booking FSM
- OpenAI-assisted extraction for the active booking step
- Duplicate booking protection and booking guardrails
- Owner registration and login
- Protected owner dashboard with booking list, detail view, and status updates

## Local Development

Start PostgreSQL:

```bash
docker compose up -d db
```

Create a local environment file from the example:

```bash
cp .env.example .env
```

Required variables for Phase 2:

- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`
- `TEST_CLINIC_SLUG`
- `TEST_CLINIC_NAME`
- `TEST_CLINIC_PHONE`
- `TEST_CLINIC_TIMEZONE`
- `AUTH_SECRET_KEY`

Install dependencies and sync the environment:

```bash
uv sync --group dev
```

Apply the initial migration:

```bash
uv run alembic upgrade head
```

Seed or update the test clinic row:

```bash
uv run python -m app.seed
```

Run the application:

```bash
uv run uvicorn main:app --reload
```

Open the owner registration page once to create the first clinic owner:

```text
http://127.0.0.1:8000/owner/register
```

After the first owner exists, use the login page:

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

If `TELEGRAM_WEBHOOK_BASE_URL` is set, application startup registers the webhook automatically using `TELEGRAM_WEBHOOK_SECRET`.

## Owner Dashboard

The Phase 3 owner area provides:

- first-owner registration for the configured clinic
- owner login/logout with an HTTP-only cookie
- booking list at `/owner/dashboard`
- booking detail page with patient/message context
- booking status updates to `pending`, `confirmed`, and `cancelled`

The current owner flow is still single-clinic in practice and uses the env-seeded clinic row.

## What The App Persists

After the user confirms a booking request, the app writes:

- a `patient` row keyed by `clinic_id` and `telegram_user_id`
- a `booking` row with `pending` status
- `message` rows for inbound and outbound turns

Owner access is stored in `clinic_user`.
