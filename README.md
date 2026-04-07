# AI Startup

Phase 2 Telegram booking flow for an AI clinic receptionist SaaS focused on clinics in Kazakhstan.

## Phase 2 Scope

- FastAPI application and Telegram webhook endpoint
- aiogram 3 booking bot with local polling support
- PostgreSQL persistence for clinics, patients, bookings, and messages
- Russian-language booking FSM
- OpenAI-assisted extraction for the active booking step
- Duplicate booking protection and booking guardrails

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

Install dependencies and sync the environment:

```bash
uv sync
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

Run the Telegram bot in local polling mode:

```bash
uv run python -m app.bot.polling
```

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

## What Phase 2 Persists

After the user confirms a booking request, the app writes:

- a `patient` row keyed by `clinic_id` and `telegram_user_id`
- a `booking` row with `pending` status
- `message` rows for inbound and outbound turns
