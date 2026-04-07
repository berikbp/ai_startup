# Phase 2 Implementation Plan

## Goal

Phase 2 delivers the first real patient-facing booking flow through Telegram.
Starting from the current Phase 1 foundation, the system should let a real user:

1. send `/start` to a test clinic bot
2. complete a Russian-language booking flow
3. confirm the collected details
4. create `patient`, `booking`, and `message` records in PostgreSQL
5. receive a receipt message stating that the clinic will call back to confirm

This phase should produce one working end-to-end path for a single test clinic.
It should not attempt to finish the owner dashboard, auth system, per-clinic bot onboarding, or production hardening.

## Current Baseline

The codebase already includes:

- FastAPI application scaffold
- settings management
- async PostgreSQL session factory
- tenant-aware SQLModel models
- Alembic configuration and initial migration
- `/health` endpoint

Relevant existing models:

- `Clinic`
- `ClinicUser`
- `Patient`
- `Booking`
- `Message`

This is enough to start Phase 2 without a redesign of the database layer.

## Phase 2 Scope

### In Scope

- aiogram 3 Telegram bot integration
- webhook endpoint for Telegram updates
- local polling mode for development
- Russian booking conversation flow
- FSM-based state management for one booking conversation
- OpenAI-powered extraction for bounded conversational understanding
- patient data persistence
- booking persistence
- message logging
- phone normalization
- duplicate booking protection within 5 minutes
- off-topic handling
- medical-advice refusal and redirect to booking
- graceful OpenAI failure fallback

### Explicitly Out of Scope

- owner dashboard UI
- registration / login
- encrypted bot token storage
- multi-bot tenant onboarding UI
- Redis-backed FSM storage
- webhook idempotency via Redis
- production security hardening beyond basic webhook secret validation
- real availability checking or calendar sync

## Product Rules

The Phase 2 bot should follow these product rules:

1. The bot is Russian-first.
2. The bot helps with bookings and clinic service questions only.
3. The bot must not provide medical advice.
4. The bot must never claim a slot is definitively booked or available.
5. The bot collects four required booking fields:
   - service type
   - preferred date and time
   - full name
   - phone number
6. The bot must show a confirmation summary before writing a booking.
7. The bot must send a receipt after confirmation.
8. `/start` must always reset the conversation cleanly.

## Technical Strategy

### Core Architecture

Use a hybrid FSM plus LLM approach:

- aiogram FSM controls the conversation stage
- application code validates and stores structured data
- OpenAI interprets natural-language input for the active step only

This is intentionally not a pure LLM-controlled conversation. The state machine should remain the source of truth for progress through the booking flow.

### Tenant Model for Phase 2

Phase 2 should support one test clinic using:

- one Telegram bot token from env
- one clinic row in the database
- one clinic slug for webhook routing

The design should leave clear seams for Phase 4, where bot tokens move into the database and become clinic-managed.

## Planned File Structure

The current app is too small to hold the full bot flow cleanly in `app/api.py`.
Phase 2 should introduce dedicated bot and service modules.

Suggested structure:

```text
app/
  api.py
  main.py
  config.py
  db.py
  models.py
  bot/
    __init__.py
    dispatcher.py
    router.py
    states.py
    keyboards.py
    copy.py
  services/
    __init__.py
    clinic_service.py
    patient_service.py
    booking_service.py
    message_service.py
    openai_service.py
    normalization.py
```

Optional later additions if needed during implementation:

- `app/schemas/` for structured OpenAI tools
- `app/bot/handlers/` if the single router grows too large

## Configuration Changes

Extend settings in `app/config.py` with Phase 2 runtime config.

Required settings:

- `telegram_bot_token`
- `telegram_webhook_base_url`
- `telegram_webhook_secret`
- `test_clinic_slug`
- `openai_api_key`
- `openai_model` defaulting to `gpt-4o-mini`
- `openai_timeout_seconds`

Optional useful settings:

- `clinic_timezone_default`
- `typing_interval_seconds`
- `booking_duplicate_window_seconds`

`.env.example` should be updated to document the new variables.

## Conversation Design

### State Machine

Recommended states:

- `WAITING_SERVICE`
- `WAITING_DATETIME`
- `WAITING_NAME`
- `WAITING_PHONE`
- `CONFIRMING`

Behavior:

1. `/start` clears any existing state.
2. The bot greets the user in Russian.
3. The bot asks for the service type.
4. The bot asks for preferred date and time.
5. The bot asks for the patient's full name.
6. The bot asks for the phone number.
7. The bot shows a summary and asks `Всё верно?`
8. On confirmation, the app writes the booking and sends the receipt.

### Why This Order

The conversation should ask for service first, then date/time, then name, then phone.

Rationale:

- service establishes booking context early
- date/time is core request data
- name is low-friction
- phone is highest-friction and should be collected after the user is already committed

## Telegram Integration Plan

### Development Modes

Support both:

- local polling mode for development convenience
- FastAPI webhook mode for real Telegram integration

Polling is useful for local iteration.
Webhook mode is the real deployment shape and should be the primary production path.

### Webhook Route

Use a clinic-scoped route:

```text
POST /webhook/{clinic_slug}
```

Phase 2 flow:

1. FastAPI receives the Telegram update.
2. The route resolves the clinic by slug.
3. The route validates the webhook secret header.
4. The update is forwarded into aiogram.
5. Handler logic runs with clinic context attached.

### Clinic Resolution

For this phase, clinic resolution can be implemented as:

- lookup by `clinic_slug`
- require exactly one configured test clinic
- fail fast with 404 or 400 if the clinic is missing

Do not yet implement per-clinic token lookup from the database.

## OpenAI Integration Plan

### Role of the Model

The model should not decide the whole flow.
It should help interpret the current user message and extract structured data for the active step.

### Model Choice

Default model:

- `gpt-4o-mini`

Reasons:

- low cost
- sufficient quality for bounded extraction
- appropriate for strict schema-driven tool calls

### Extraction Strategy

Use strict structured extraction for the active step.

Expected outputs should include some or all of:

- `service_type`
- `preferred_datetime_iso`
- `preferred_datetime_text`
- `datetime_confidence`
- `patient_name`
- `phone_number`
- `off_topic`
- `medical_advice_request`

Set `parallel_tool_calls=False`.

### Prompt Design

Inject into every OpenAI request:

- clinic name
- clinic phone number
- clinic timezone
- current Almaty local datetime
- already collected fields
- missing fields
- explicit restrictions

The prompt must explicitly say:

- stay on booking and clinic-service topics only
- refuse medical advice
- ask a clarifying question for ambiguous time expressions
- never confirm appointment availability

### Time Handling

Use the clinic timezone, defaulting to `Asia/Almaty`.

The model should receive the current local datetime so it can resolve phrases like:

- `завтра утром`
- `в пятницу после обеда`
- `на следующей неделе`

If extracted time is still underspecified, the app should ask one targeted follow-up instead of guessing.

## Validation and Normalization Rules

### Phone Numbers

Normalize all collected phone numbers to:

```text
+7XXXXXXXXXX
```

Accept common user input variants such as:

- `87001234567`
- `+7 700 123 45 67`
- `7(700)1234567`

Validation should happen in application code even if the LLM returns a phone candidate.

If invalid:

- do not advance state
- re-prompt with a concrete format example

### Datetime

Validate that extracted datetimes:

- are valid ISO datetimes
- are timezone-aware or normalized consistently
- are not clearly in the past

If the user provides only a vague range:

- keep `preferred_datetime_text`
- ask one clarifying question
- do not create the booking yet

### Service Type

Phase 2 can start with free-text service capture unless a reliable fixed clinic service list already exists.
If a clinic service catalog is introduced later, validation can tighten to an enum.

## Persistence Plan

### Patient

Persist or update the patient using:

- `clinic_id`
- `telegram_user_id`

Behavior:

- upsert patient record
- update `telegram_username`, `full_name`, and `phone_number` when new verified values are available

### Booking

Create a booking only after the user confirms the summary.

Fields to persist:

- `clinic_id`
- `patient_id`
- `service_type`
- `preferred_datetime_at`
- `preferred_datetime_text`
- `status`
- `source`

Recommended default booking status for this phase:

- `pending`

### Messages

Persist message history for every turn.

At minimum:

- inbound patient messages
- outbound assistant replies

This gives the future dashboard a conversation trail without needing a second migration later.

## Deduplication Plan

Implement duplicate booking protection in the booking service layer, not in Telegram handlers.

Duplicate criteria:

- same `clinic_id`
- same `telegram_user_id`
- same `service_type`
- same `preferred_datetime_at`
- created within the last 5 minutes

If a duplicate is detected:

- do not create a second booking
- respond with a Russian message saying the request was already received

## Guardrails and Failure Handling

### Off-Topic Handling

Track `off_topic_count` in FSM data.

Rules:

1. first off-topic message: polite redirect to booking/service topic
2. second consecutive off-topic message: provide clinic phone number as fallback

Reset the counter after an on-topic user reply.

### Medical Advice

If the user asks for medical advice:

- refuse briefly
- redirect to booking a consultation
- do not answer the medical question itself

### OpenAI Errors

Wrap all OpenAI calls with error handling.

For 429 or 5xx style failures:

- send a short Russian fallback message
- include the clinic phone number
- do not expose raw exception text

### Telegram UX

Immediately show typing status before long work.
If the OpenAI request is slow, keep the typing indicator alive until the reply is sent.

At the phone step:

- show a `request_contact` keyboard button
- continue to accept typed phone numbers as fallback

## Recommended Work Breakdown

### Workstream 1: Runtime and Configuration

- extend settings model
- update `.env.example`
- add OpenAI and Telegram dependencies if missing
- define startup wiring for bot components

### Workstream 2: Bot Infrastructure

- create aiogram dispatcher
- add FSM states
- implement local polling entrypoint
- add FastAPI webhook endpoint
- add clinic-context loading

### Workstream 3: Domain Services

- clinic lookup service
- patient upsert service
- booking create and duplicate-check service
- message logging service
- phone normalization helpers
- datetime validation helpers

### Workstream 4: Conversation Flow

- `/start` reset behavior
- service collection
- datetime collection and clarification
- name collection
- phone collection with contact button
- confirmation summary
- receipt message

### Workstream 5: OpenAI Extraction

- define tool schema
- implement request builder
- inject current clinic/time/state context
- map tool output into internal booking draft structure
- implement error fallback path

### Workstream 6: Verification

- seed one real test clinic
- run end-to-end bot flow manually
- verify rows are created in PostgreSQL
- test duplicate prevention
- test `/start` reset
- test ambiguous datetime clarification
- test OpenAI fallback path

## Detailed Execution Order

This is the recommended implementation sequence.

### Step 1: Stabilize Runtime Inputs

- add config fields
- update `.env.example`
- confirm the current app still boots

### Step 2: Add Bot Module Skeleton

- create bot package
- add dispatcher construction
- add empty states and router
- wire bot initialization into the app

### Step 3: Add Webhook Endpoint

- add `POST /webhook/{clinic_slug}`
- resolve clinic
- validate request secret
- forward updates to aiogram

### Step 4: Add Local Polling Runner

- create a simple dev entrypoint for polling
- ensure polling mode clears webhook before use

### Step 5: Implement Core Services

- patient upsert
- booking create
- duplicate detection
- message logging
- normalization helpers

### Step 6: Implement FSM Flow Without OpenAI

Start with deterministic handlers first.

- `/start`
- ask service
- ask datetime
- ask name
- ask phone
- show summary
- save booking

This gives a working skeleton before model integration.

### Step 7: Add OpenAI Extraction to Each Step

Layer the LLM onto the deterministic flow:

- parse service text
- interpret Russian datetime phrases
- extract names from natural replies
- detect off-topic behavior
- detect medical-advice requests

The FSM remains the source of truth even after model integration.

### Step 8: Add Guardrails

- off-topic counter
- medical-advice refusal
- duplicate booking response
- `/start` reset correctness
- OpenAI fallback messaging

### Step 9: Persist Full Message Trail

- save inbound messages
- save assistant messages
- link to patient and booking where possible

### Step 10: Verify Manually End to End

Manual scenarios:

1. happy path booking
2. `/start` during an active flow
3. ambiguous datetime like `завтра утром`
4. invalid phone number
5. duplicate booking in 5 minutes
6. two off-topic messages
7. medical advice request
8. simulated OpenAI failure

## Testing Plan

The current repository has no tests.
Phase 2 should not rely only on manual Telegram checks.

Minimum automated coverage:

- phone normalization unit tests
- duplicate detection unit tests
- datetime validation unit tests
- `/start` clears FSM state
- confirmation is required before booking creation
- invalid phone input does not advance state
- ambiguous datetime causes clarification

Preferred integration coverage:

- webhook request to booking creation flow using mocked OpenAI output
- persistence checks for `Patient`, `Booking`, and `Message`

## Seed Data Plan

Phase 2 needs one test clinic available in the database.

Add a simple repeatable seed path for:

- clinic name
- clinic slug
- clinic phone number
- clinic timezone

This can be:

- a small script
- a CLI command
- a documented manual SQL snippet

The important part is repeatability, not sophistication.

## Definition of Done

Phase 2 is complete when all of the following are true:

1. A real user can send `/start` to the test bot and complete the booking flow in Russian.
2. The bot collects service, preferred date/time, full name, and phone number.
3. The bot asks for confirmation before saving.
4. On confirmation, the system creates `patient`, `booking`, and `message` rows in PostgreSQL.
5. The receipt message clearly says the clinic will call back to confirm.
6. Sending `/start` mid-conversation resets the flow cleanly.
7. Ambiguous datetime input triggers one specific clarification question.
8. Duplicate booking requests within 5 minutes do not create duplicate records.
9. Two consecutive off-topic messages lead to a phone-number fallback.
10. Medical-advice requests are refused and redirected to consultation booking.
11. OpenAI failures produce a Russian fallback response instead of silence or crashes.

## Things To Avoid

During Phase 2, do not:

- build the dashboard
- build auth
- add Redis prematurely unless truly needed for progress
- switch to a pure LLM conversation manager
- promise appointment availability to the user
- leave message history unpersisted
- bury duplicate detection inside Telegram handler code
- couple Phase 2 to Phase 4 bot-token storage decisions

## Recommended Next Step After Phase 2

Once the Telegram booking flow works end to end, the next major milestone is Phase 3:

- owner registration and login
- booking table
- per-clinic isolation checks
- conversation history view
- status updates from dashboard

At that point, the Phase 2 conversation and persistence layers should already be reusable by the owner-facing dashboard.
