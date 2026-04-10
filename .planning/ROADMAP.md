# Roadmap: AI Clinic Receptionist

**Product:** AI receptionist SaaS for clinics in Kazakhstan (Telegram + web dashboard)
**Core Value:** Patients can book clinic appointments 24/7 via Telegram without calling — and owners see every booking in one place.
**Milestone:** v1 — demoable product to land first paying clinic customer
**Created:** 2026-03-30
**Granularity:** Standard

---

## Phases

- [x] **Phase 1: Foundation** — Project scaffold, database schema, multi-tenant data model, deployment pipeline
- [x] **Phase 2: Telegram Bot Core** — aiogram 3 bot with FSM booking flow and OpenAI function-calling integration
- [x] **Phase 3: Owner Dashboard** — FastAPI + HTMX dashboard with auth, booking table, and conversation history
- [x] **Phase 4: Integration and Polish** — Connect bot to dashboard, bot token management, end-to-end demo flow
- [x] **Phase 5: Hardening** — Redis FSM state, webhook security, idempotency, error handling for production

---

## Phase Details

### Phase 1: Foundation

**Goal**: The project is deployable to Railway with a working database, multi-tenant schema, and CI/CD pipeline, so all subsequent phases build on a stable base.

**Depends on**: Nothing

**Requirements**: (none — enabling infrastructure for all phases)

**Plans**:
1. Initialize Python project with `uv`, `pyproject.toml`, FastAPI, SQLModel, Alembic, aiogram 3, and all dependencies locked
2. Design and implement the PostgreSQL multi-tenant schema: `Clinic`, `ClinicUser`, `Patient`, `Booking`, `Message` tables with `clinic_id` FK on every tenant-scoped table
3. Configure Alembic migrations with `SQLModel.metadata` in `env.py`; run initial migration against Railway PostgreSQL
4. Set up Railway deployment with environment variables, auto-deploy on push, and health-check endpoint (`GET /health`)

**Success Criteria** (what must be TRUE when this phase completes):
1. `uv run alembic upgrade head` runs cleanly against a fresh Railway PostgreSQL database with no errors
2. `GET /health` on the Railway deployment returns `{"status": "ok"}` with HTTP 200
3. Pushing a commit to `main` triggers an automatic Railway redeploy that succeeds
4. All five tables exist in the database with correct foreign keys and `clinic_id` isolation columns visible via `psql \d`

---

### Phase 2: Telegram Bot Core

**Goal**: A patient can start a conversation with the clinic's Telegram bot, get guided through the booking flow in Russian, and have their booking request saved to the database.

**Depends on**: Phase 1

**Requirements**: BOT-01, BOT-02, BOT-03, BOT-04, BOT-05, BOT-06, BOT-07, BOT-08, BOT-09, BOT-10, BOT-11, BOT-12, INFRA-03

**Plans**:
1. Set up aiogram 3 dispatcher with `StatesGroup` FSM (`Greeting → Service → DateTime → Name → Phone → Confirm`), register webhook route `POST /webhook/{clinic_slug}`, and inject clinic context via middleware
2. Integrate OpenAI GPT-4o-mini with function calling (`strict: true`, `parallel_tool_calls=False`) for natural language field extraction; inject Almaty current datetime (UTC+5) into every system prompt; implement hybrid FSM+LLM flow where FSM controls state transitions and LLM handles natural language within each state
3. Implement patient UX requirements: `typing` chat action on every message (BOT-07), `request_contact` button for phone with text fallback (BOT-03), phone normalization to `+7XXXXXXXXXX` with re-prompt on failure (BOT-08), booking confirmation summary with "Всё верно?" prompt (BOT-04), receipt message after confirmation (BOT-05)
4. Implement guard requirements: off-topic detection with phone fallback after two consecutive off-topic messages (BOT-06), medical advice rejection redirecting to consultation booking (BOT-10), `/start` command clearing stale FSM state (BOT-11), 5-minute deduplication check on identical booking requests (BOT-12), OpenAI API error handling with Russian-language user message and clinic phone fallback (INFRA-03)
5. Write booking record to PostgreSQL on patient confirmation; test full booking flow end-to-end against a real Telegram bot token using a test clinic row

**Success Criteria** (what must be TRUE when this phase completes):
1. A real person can send `/start` to the test bot, complete the booking flow in Russian, and see a confirmation message — the booking appears in the `bookings` table in PostgreSQL
2. Sending `/start` mid-conversation resets all state cleanly; a new booking can be completed immediately after
3. Sending "расскажи мне анекдот" twice results in the bot providing the clinic phone number instead of continuing the off-topic exchange
4. Entering "завтра утром" as a time results in the bot asking a single clarifying question (e.g. "В какое время утром вам удобно?") rather than crashing or accepting the ambiguous value
5. Submitting an identical booking (same user, service, datetime) within 5 minutes results in "запрос уже получен" instead of a duplicate record in the database
6. Simulating an OpenAI 429 error results in a Russian-language fallback message with the clinic phone number delivered to the patient — no crash, no silence

---

### Phase 3: Owner Dashboard

**Goal**: A clinic owner can register, log in, and view all bookings and conversation history for their clinic through a web dashboard.

**Depends on**: Phase 1

**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, AUTH-01, AUTH-02, AUTH-03

**Plans**:
1. Integrate `fastapi-users 15.0.5` with `SQLModel` backend; implement registration with email verification, login/logout with secure HTTP-only cookie (24-hour session), and all auth routes (`/auth/register`, `/auth/login`, `/auth/logout`)
2. Build Jinja2 HTML templates with HTMX for the booking table: paginated view showing submission time, patient name, phone (clickable `tel:` link), service, preferred datetime, and status; implement `hx-get` filter controls for status and service type without full page reload
3. Implement single-click booking status update: `PATCH /bookings/{id}/status` with `hx-patch` + `hx-swap="outerHTML"` to update only the affected table row; enforce `clinic_id` ownership check returning 403 for cross-clinic attempts
4. Build conversation history view: `GET /bookings/{id}/conversation` renders the full message thread for a selected booking; accessible from the booking table row

**Success Criteria** (what must be TRUE when this phase completes):
1. A new owner can register with email/password, click the verification link, log in, and reach the dashboard — an unverified account cannot log in
2. The booking table shows all bookings for the logged-in clinic; attempting to access another clinic's booking URL returns HTTP 403
3. Selecting "pending" in the status filter updates the table to show only pending bookings without a full page reload (HTMX swap is visible in the network tab)
4. Clicking "Confirm" on a pending booking changes the row status to "confirmed" in place without reloading the page
5. Clicking a patient row opens their conversation history showing all messages exchanged with the bot

---

### Phase 4: Integration and Polish

**Goal**: The bot and dashboard are connected end-to-end through bot token management, so an owner can onboard their bot, see live bookings, and the product is demo-ready.

**Depends on**: Phase 2, Phase 3

**Requirements**: AUTH-04, AUTH-05, DASH-05

**Plans**:
1. Build bot token submission UI in the dashboard settings page: encrypted storage using AES-256-GCM (`cryptography` library), token never exposed in logs or API responses (AUTH-04); display bot configuration status on dashboard (DASH-05)
2. Implement automatic webhook registration on token save: call `setWebhook` Telegram API with the correct `POST /webhook/{clinic_slug}` URL and `secret_token`; display connection status (active / error) in dashboard (AUTH-05)
3. End-to-end integration test: owner submits bot token in dashboard → webhook registers → patient sends message to bot → booking appears in owner's dashboard table in real time; run this flow manually and fix any gaps
4. Demo polish: add Russian-language copy throughout dashboard, sensible empty states ("Нет записей"), loading indicators on HTMX requests, and a one-page demo script for clinic walk-throughs

**Success Criteria** (what must be TRUE when this phase completes):
1. An owner can paste a bot token into the dashboard settings and see "Bot connected" status — the webhook is verified as active with Telegram
2. A patient booking made through the bot appears in the owner's dashboard booking table within seconds of confirmation
3. The dashboard settings page shows "Bot not connected" when no token has been submitted, and "Bot connected" after a valid token is saved and webhook confirmed
4. A complete demo run — owner logs in, views dashboard, patient books via bot, owner confirms the booking — completes without errors and looks presentable to a clinic prospect

---

### Phase 5: Hardening

**Goal**: The system is production-safe with Redis-backed FSM state, webhook request validation, update idempotency, and graceful error recovery.

**Depends on**: Phase 4

**Requirements**: INFRA-01, INFRA-02

**Plans**:
1. Replace in-memory aiogram FSM storage with Redis-backed storage; configure 24-hour state and data TTLs; reuse the same Redis runtime in both FastAPI lifespan and local polling so in-progress conversations survive process restarts
2. Implement Redis-backed `update_id` idempotency keyed by clinic and validated only after the clinic-specific `X-Telegram-Bot-Api-Secret-Token` check passes; duplicate updates return HTTP 200 without reprocessing
3. Add structured JSON-style runtime logging for webhook decisions, Telegram bot configuration failures, and OpenAI extraction failures; document the local stack with PostgreSQL plus Redis and verify the runtime with automated tests

**Success Criteria** (what must be TRUE when this phase completes):
1. Redis-backed FSM state is the default runtime path for both webhook processing and local polling
2. Sending a forged webhook POST without the correct `X-Telegram-Bot-Api-Secret-Token` header returns HTTP 403 before any Telegram update is processed
3. Replaying the same `update_id` twice for the same clinic results in exactly one dispatcher execution — the second request returns HTTP 200 immediately
4. `uv run alembic upgrade head` and `uv run pytest -q` succeed after the hardening changes, and the local development stack documents both PostgreSQL and Redis

---

## Progress Table

| Phase | Plans | Status | Completed |
|-------|-------|--------|-----------|
| 1. Foundation | 4 | Completed | 4/4 |
| 2. Telegram Bot Core | 5 | Completed | 5/5 |
| 3. Owner Dashboard | 4 | Completed | 4/4 |
| 4. Integration and Polish | 4 | Completed | 4/4 |
| 5. Hardening | 3 | Completed | 3/3 |

---

## Requirement Coverage

**Total v1 requirements:** 25
**Mapped:** 25/25

| Requirement | Phase |
|-------------|-------|
| BOT-01 | Phase 2 |
| BOT-02 | Phase 2 |
| BOT-03 | Phase 2 |
| BOT-04 | Phase 2 |
| BOT-05 | Phase 2 |
| BOT-06 | Phase 2 |
| BOT-07 | Phase 2 |
| BOT-08 | Phase 2 |
| BOT-09 | Phase 2 |
| BOT-10 | Phase 2 |
| BOT-11 | Phase 2 |
| BOT-12 | Phase 2 |
| DASH-01 | Phase 3 |
| DASH-02 | Phase 3 |
| DASH-03 | Phase 3 |
| DASH-04 | Phase 3 |
| DASH-05 | Phase 4 |
| AUTH-01 | Phase 3 |
| AUTH-02 | Phase 3 |
| AUTH-03 | Phase 3 |
| AUTH-04 | Phase 4 |
| AUTH-05 | Phase 4 |
| INFRA-01 | Phase 5 |
| INFRA-02 | Phase 5 |
| INFRA-03 | Phase 2 |
