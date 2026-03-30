# Requirements: AI Clinic Receptionist

**Defined:** 2026-03-30
**Core Value:** Patients can book clinic appointments 24/7 via Telegram without calling — and owners see every booking in one place.

---

## v1 Requirements

### Bot (Patient-facing)

- [ ] **BOT-01**: A patient can start a conversation with the clinic's Telegram bot and receive a Russian-language greeting that explains the bot can help with bookings and service questions.

- [ ] **BOT-02**: The bot guides the patient through collecting four required fields — service type, preferred date and time, full name, and phone number — in a natural conversational flow before creating a booking request.

- [ ] **BOT-03**: The bot uses Telegram's native `request_contact` button to offer patients a one-tap way to share their phone number; manual text input must remain available as a fallback.

- [ ] **BOT-04**: The bot presents a confirmation summary of all collected booking details (name, phone, service, date/time) and asks the patient to confirm ("Всё верно?") before logging the booking.

- [ ] **BOT-05**: After patient confirmation, the bot sends a receipt message in Russian stating the request has been received and that the clinic will call back to confirm — it never claims a slot is definitively available.

- [ ] **BOT-06**: The bot detects and rejects off-topic messages with a polite redirect. After two consecutive off-topic messages, it provides the clinic's phone number as an alternative channel.

- [ ] **BOT-07**: The bot sends a `typing` chat action immediately upon receiving any message, so the patient sees a visual indicator while the OpenAI API call is in progress.

- [ ] **BOT-08**: The bot normalizes all collected phone numbers to `+7XXXXXXXXXX` format and re-prompts with a concrete example if the entered number fails validation.

- [ ] **BOT-09**: The bot handles ambiguous Russian time expressions ("завтра утром", "в пятницу после обеда") by resolving them against the injected current Almaty local time (UTC+5), and asks one targeted clarifying question when the expression is underspecified.

- [ ] **BOT-10**: The bot never provides medical advice; when a patient describes symptoms it redirects them to book a consultation appointment.

- [ ] **BOT-11**: The `/start` command clears any existing conversation state and restarts the flow cleanly, preventing stale FSM state from prior abandoned sessions.

- [ ] **BOT-12**: The bot deduplicates booking requests: if an identical booking (same Telegram user ID + service + preferred datetime) is received within 5 minutes, it informs the patient the request was already received rather than creating a duplicate record.

---

### Dashboard (Owner-facing)

- [ ] **DASH-01**: An authenticated clinic owner can view a paginated table of all booking requests for their clinic, showing: submission time, patient name, phone number (as a clickable `tel:` link), service, preferred datetime, and status.

- [ ] **DASH-02**: The owner can filter the booking table by status (pending / confirmed / cancelled) and by service type without a full page reload.

- [ ] **DASH-03**: The owner can change the status of any booking (pending → confirmed or pending → cancelled) with a single click; the table row updates in place without reloading the full page.

- [ ] **DASH-04**: The owner can view the full Telegram conversation history for any individual booking request.

- [ ] **DASH-05**: The dashboard displays the clinic's Telegram bot configuration status (bot token linked / not linked) so the owner knows whether the bot is active.

---

### Auth and Multi-tenancy

- [ ] **AUTH-01**: A clinic owner can register with an email and password, receiving an email verification link before the account is activated.

- [ ] **AUTH-02**: A registered owner can log in and log out; session is maintained via a secure HTTP-only cookie valid for 24 hours.

- [ ] **AUTH-03**: A logged-in owner can only see and modify booking data that belongs to their own clinic; requests for another clinic's data return 403.

- [ ] **AUTH-04**: A clinic owner can submit their Telegram bot token through the dashboard; the token is stored AES-256-GCM encrypted and never exposed in logs or API responses.

- [ ] **AUTH-05**: When a clinic owner's bot token is saved, the system automatically registers the webhook URL with Telegram and confirms the connection is active.

---

### Infrastructure

- [ ] **INFRA-01**: Incoming Telegram webhook requests are validated against the `X-Telegram-Bot-Api-Secret-Token` header; requests without a valid secret are rejected with 403 before any processing occurs.

- [ ] **INFRA-02**: Each incoming Telegram update is checked for duplicate processing using its `update_id`; duplicate updates (Telegram retries) are acknowledged with 200 but not reprocessed.

- [ ] **INFRA-03**: OpenAI API errors (429, 5xx) are caught and the patient receives a user-friendly Russian-language error message with the clinic's phone number, rather than a crash or silence.

---

## v2 Requirements

*(Deferred — do not build until v1 is validated with paying customers)*

- **Voice channel**: Inbound phone call handling via a voice AI agent (e.g., Twilio + ElevenLabs or Whisper).
- **WhatsApp channel**: WhatsApp Business API integration as a second patient-facing channel.
- **Kazakh language**: Full Kazakh-language support; Kazakh/Russian code-switching is the competitive moat.
- **Calendar sync**: Two-way sync with Google Calendar or clinic scheduling systems to check real availability before confirming a slot.
- **Automated reminders**: SMS or Telegram reminder messages sent 24 hours before a confirmed appointment.
- **Self-service clinic signup**: Web-based onboarding flow so clinics can register and configure without founder involvement.
- **Subscription billing**: Stripe or Kaspi Pay integration for automated monthly billing per clinic.
- **Analytics dashboard**: Booking volume trends, peak hours, service breakdown charts for clinic owners.
- **Doctor preference**: Let patients specify a preferred doctor when booking, routing to the correct specialist.

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Voice calls | Deferred to v2; text MVP must be validated first |
| WhatsApp | Deferred; Telegram API is simpler and Telegram is widely used in Kazakhstan |
| Direct calendar sync | Too many clinic system variants; manual confirmation by receptionist in v1 |
| Mobile app (iOS/Android) | Web dashboard is sufficient for clinic owners in v1 |
| Kazakh language | Russian-first for speed; Kazakh is the v2 differentiation moat |
| Email collection from patients | No use case until automated reminders exist (v2) |
| Medical record integration | Out of scope; clinic handles post-booking internally |
| Doctor-level scheduling | Service-type routing is sufficient; doctor preference is v2 |
| Automated slot conflict detection | No live calendar in v1; clinic receptionist handles scheduling manually |
| Insurance / date-of-birth collection | Adds friction with no v1 benefit |

---

## Traceability

| Requirement | Description (short) | Phase | Status |
|-------------|----------------------|-------|--------|
| BOT-01 | Russian greeting on /start | Phase 2 | Pending |
| BOT-02 | Conversational booking flow (4 fields) | Phase 2 | Pending |
| BOT-03 | request_contact button + text fallback | Phase 2 | Pending |
| BOT-04 | Confirmation summary before logging | Phase 2 | Pending |
| BOT-05 | Receipt message after confirmation | Phase 2 | Pending |
| BOT-06 | Off-topic detection with phone fallback | Phase 2 | Pending |
| BOT-07 | typing chat action while API call runs | Phase 2 | Pending |
| BOT-08 | Phone normalization to +7XXXXXXXXXX | Phase 2 | Pending |
| BOT-09 | Resolve Russian relative time expressions | Phase 2 | Pending |
| BOT-10 | No medical advice; redirect to booking | Phase 2 | Pending |
| BOT-11 | /start clears stale FSM state | Phase 2 | Pending |
| BOT-12 | 5-minute booking deduplication | Phase 2 | Pending |
| DASH-01 | Paginated booking table for owner | Phase 3 | Pending |
| DASH-02 | Filter by status/service without reload | Phase 3 | Pending |
| DASH-03 | Single-click status update in-place | Phase 3 | Pending |
| DASH-04 | Conversation history view per booking | Phase 3 | Pending |
| DASH-05 | Bot configuration status in dashboard | Phase 4 | Pending |
| AUTH-01 | Owner registration with email verification | Phase 3 | Pending |
| AUTH-02 | Login/logout with HTTP-only cookie | Phase 3 | Pending |
| AUTH-03 | Data isolation — 403 on cross-clinic access | Phase 3 | Pending |
| AUTH-04 | Bot token stored AES-256-GCM encrypted | Phase 4 | Pending |
| AUTH-05 | Auto-register webhook on token save | Phase 4 | Pending |
| INFRA-01 | Webhook secret token header validation | Phase 5 | Pending |
| INFRA-02 | update_id idempotency via Redis | Phase 5 | Pending |
| INFRA-03 | OpenAI error → Russian fallback message | Phase 2 | Pending |

---

## Key Technical Decisions (from research)

- **aiogram 3.26.0** for Telegram bot — async-native, first-class FSM (`StatesGroup`), middleware pipeline for tenant injection, webhook-native FastAPI integration.
- **One bot token per clinic** — branded bot names, complete data isolation by design, clean offboarding; single FastAPI service with `POST /webhook/{bot_token}` routes updates to the correct clinic dispatcher.
- **Redis (RedisStorage)** for FSM state — survives process restarts; `state_ttl` of 24 hours prevents stale abandoned-session state.
- **OpenAI conversation history in Redis** (separate key namespace, 24-hour TTL, capped at 10–15 messages / 4,000 tokens) — fast, TTL-native, avoids unbounded token growth.
- **GPT-4o-mini with function calling (`strict: true`)** for booking extraction — ~$0.0009 per conversation vs. ~$0.015 for GPT-4o; 100% schema adherence on structured output evals; `parallel_tool_calls=False` required with strict mode.
- **Chat Completions API** (not Assistants API, which is deprecated mid-2026) — client-side history management is low overhead for a short booking flow.
- **Hybrid FSM + LLM architecture** — aiogram FSM controls which field is being collected; LLM handles natural language understanding within each state. More reliable than pure-LLM conversation management.
- **Current Almaty datetime (UTC+5, no DST) injected into every system prompt** — resolves Russian relative time expressions ("завтра в 3") without a separate NLP library; ISO 8601 required in function schema forces the model to resolve relative → absolute before calling the function.
- **`rutimeparser`** as a validation/fallback layer for Russian temporal expressions (not primary parser — library is unmaintained since 2019).
- **FastAPI 0.135.2 + HTMX + Jinja2** for dashboard — single Python codebase shared with bot models, no React build pipeline, HTMX handles interactive table updates (`hx-patch`, `hx-swap`).
- **SQLModel 0.0.37** — one class serves as ORM table definition, Pydantic validation model, and FastAPI response schema; reduces boilerplate significantly; native `fastapi-users` integration.
- **PostgreSQL** from day one — concurrent writes from bot + dashboard processes rule out SQLite; row-level tenant isolation via `clinic_id` FK on every table; optional PostgreSQL RLS as second enforcement layer.
- **fastapi-users 15.0.5** — covers registration, login, JWT, password reset, email verification; cookie transport for dashboard (HTMX requests include cookies automatically); JWT transport for bot API calls.
- **Alembic 1.18.4** for migrations — must import `SQLModel.metadata` in `env.py`; `alembic revision --autogenerate` generates diffs.
- **Railway** for initial deployment — $5/month Hobby plan, auto-HTTPS, PostgreSQL add-on, auto-deploy on push; migrate to Hetzner VPS at 10+ clinics for cost efficiency.
- **Bot token encryption**: AES-256-GCM (`cryptography` library), decrypt only at request time, never logged.
- **Webhook `secret_token` validation** on every incoming Telegram request — prevents fake update injection.
- **Update idempotency via Redis** — `update_id` stored with 1-hour TTL; duplicate updates return 200 without reprocessing.
- **`typing` chat action** sent immediately on message receipt, repeated every 4 seconds during OpenAI call — prevents patients from thinking the bot has crashed.
