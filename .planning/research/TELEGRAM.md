# Telegram Bot Development Research: SaaS AI Receptionist

**Researched:** 2026-03-30
**Domain:** Python Telegram bot development for multi-tenant SaaS
**Confidence:** HIGH (verified against official docs and PyPI registry)

---

## Summary

This research covers production Telegram bot development in Python for a multi-tenant SaaS product — specifically an AI receptionist for clinics in Kazakhstan. The product needs to handle multi-turn booking conversations powered by OpenAI, support multiple clinic tenants with isolated data, and run reliably on a budget appropriate for a solo founder.

**Primary recommendation:** Use aiogram 3 (latest: 3.26.0) with FastAPI for webhooks, Redis for FSM state storage, one bot token per clinic for clean tenant isolation, and Railway as the first deployment target (~$5-20/month).

---

## Q1: Python Telegram Bot Library Comparison (2025)

### Current Versions (verified against PyPI, 2026-03-30)

| Library | Latest Version | Architecture | Production Readiness |
|---------|---------------|--------------|----------------------|
| aiogram | 3.26.0 | Async from day one (asyncio + aiohttp) | HIGH |
| python-telegram-bot | 22.7 | Async since v20 (rebuild), was sync before | HIGH |
| pyTelegramBotAPI (telebot) | 4.32.0 | Primarily synchronous | LOW for this use case |

### Recommendation: aiogram 3

**Why aiogram 3 wins for this use case:**

1. **Built async from the ground up.** aiogram was designed around asyncio from its first version. python-telegram-bot was synchronous for years and rebuilt around asyncio in v20 (released 2022). For a production webhook bot handling concurrent users, native async matters.

2. **First-class FSM.** aiogram 3 ships a built-in Finite State Machine (`aiogram.fsm`) with `StatesGroup`, pluggable storage backends (MemoryStorage, RedisStorage), and clean context injection. Multi-turn booking conversations are a first-class citizen.

3. **Middleware and dependency injection.** aiogram 3 has a proper middleware pipeline and `@router.message()` handler system. You can inject clinic context (tenant data) per request via middleware — critical for multi-tenant routing.

4. **Webhook-native.** aiogram 3 integrates cleanly with FastAPI via ASGI. The official docs show a webhook setup with `SimpleRequestHandler` and `setup_application` helpers.

5. **Active development.** 3.26.0 released in 2025; active release cadence. Large Telegram community in Russia/CIS means extensive tutorials and community support, which matters given your Kazakhstan context.

**Why not python-telegram-bot:**
Equally capable post-v20, but its FSM story is weaker (you build it yourself). Its `ConversationHandler` is functional but not as ergonomic as aiogram's `StatesGroup`. The middleware system is less composable.

**Why not telebot (pyTelegramBotAPI):**
Synchronous by default. You would fight the event loop for OpenAI API calls. Avoid for any bot that makes external async HTTP calls.

### Installation

```bash
pip install aiogram==3.26.0 fastapi uvicorn aiohttp redis
```

---

## Q2: Multi-Tenant Architecture — One Shared Bot vs. One Token Per Clinic

### Two Models

#### Model A: Single Shared Bot, Internal Routing

One bot token. All clinics' patients message the same Telegram bot handle. The bot reads a `clinic_id` stored in the database per patient user, then routes to the correct clinic's data.

**Pros:**
- Single deployment, easier infra
- Zero-config for tenants (no @BotFather steps)
- Cheaper at the start

**Cons:**
- Single bot username for all clinics (e.g., `@MedCenterBot`). Clinics cannot brand their own bot name.
- A single flood control ban affects all tenants simultaneously.
- Tenant isolation relies entirely on application-level logic — higher risk of data leakage bugs.
- Harder to offboard one clinic without affecting others.
- First message from a new patient has no clinic context until they identify themselves or click a deep link.

#### Model B: One Bot Token Per Clinic (Recommended)

Each clinic registers their own bot with @BotFather and provides their token through your SaaS dashboard. Your platform stores the token (encrypted), loads it at runtime, and runs each bot as an isolated process or webhook endpoint.

**Pros:**
- Each clinic has its own branded bot name (e.g., `@CitiMedClinicBot`).
- Complete data isolation by design — each bot's state and database scope is separate.
- A rate-limit ban on one clinic's bot does not affect others.
- Clean offboarding: delete the token record, the bot stops.
- Industry-standard SaaS pattern (ClawBotCloud, multi-bot systems on GitHub all use this).

**Cons:**
- More complex infra: multiple bots running simultaneously.
- More webhook URLs to manage (one per clinic or one shared URL with token-based routing).
- Clinic must create a bot via @BotFather (one-time 2-minute setup — acceptable for a B2B sale).

### Recommended Implementation for Model B (Shared Webhook URL, Token Routing)

You do NOT need to run separate processes per clinic. You can run ONE FastAPI service with a single webhook endpoint that handles multiple bot tokens via aiogram's multi-bot support:

```python
# One FastAPI app, one webhook URL, multiple dispatchers
# Pattern: POST /webhook/{bot_token}
# aiogram supports multiple Dispatcher instances in one process
```

The webhook URL pattern is:
```
https://yourapp.railway.app/webhook/{bot_token}
```

Each clinic's bot is registered to this URL. When Telegram sends an update, the token in the URL identifies the clinic. A middleware layer loads clinic data from the database and injects it into handler context.

**Security:** Store bot tokens encrypted in the database (AES-256-GCM). Only decrypt at request time. Never log tokens.

### Scaling Path

| Stage | Approach |
|-------|----------|
| 0-10 clinics | All bots in one process, shared FastAPI + Redis |
| 10-50 clinics | Same, just scale the Railway service vertically |
| 50+ clinics | Extract bot runner to separate workers, use a task queue |

---

## Q3: Webhook Setup and Deployment Options

### Webhook Requirements (Official Telegram Docs)

- HTTPS with a valid TLS certificate (self-signed is supported if you upload it to Telegram)
- Allowed ports: **443, 80, 88, 8443** (no other ports)
- Must respond with HTTP 200 within **60 seconds**
- Supports only one active webhook per token (cannot mix polling + webhook)
- `secret_token` header validation introduced in Bot API 7.0 (2024) — always implement this

### aiogram 3 + FastAPI Webhook Pattern

```python
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from fastapi import FastAPI

app = FastAPI()
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(
        url=f"https://yourdomain.com/webhook/{TELEGRAM_TOKEN}",
        secret_token=WEBHOOK_SECRET,  # verify incoming requests
    )

handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
app.add_route("/webhook/{token}", handler.handle, methods=["POST"])
```

### Deployment Options for Solo Founder

#### Option 1: Railway (Recommended for Starting)

- **Cost:** $5/month Hobby plan; typical bot usage well within that
- **Setup:** Connect GitHub repo, add env vars, auto-deploys on push
- **HTTPS:** Provided automatically, no certificate management
- **Webhook:** Railway assigns a public domain — set it as your webhook URL
- **Database:** PostgreSQL add-on available; Redis add-on available
- **Verdict:** Best DX for a solo founder. Zero infra management. Start here.

#### Option 2: Render

- **Cost:** Paid tier starts at $7/month for always-on (free tier sleeps after 15 min — NOT suitable for a webhook bot that needs to process incoming messages)
- **HTTPS:** Provided automatically
- **Verdict:** Valid alternative to Railway, but Railway has better DX and lower starting cost.

#### Option 3: VPS (Hetzner, DigitalOcean)

- **Cost:** ~$5-6/month for a basic VPS (Hetzner CX11: 2 vCPU, 2GB RAM)
- **Setup:** Docker + Caddy (handles HTTPS/TLS automatically) + systemd
- **Control:** Full. You own the environment.
- **Verdict:** Best price-to-performance at scale. More setup work upfront. Graduate to this when Railway costs become significant (>10 clinics at steady state).

#### Option 4: Fly.io

- **Cost:** ~$2-5/month for a small machine
- **Strength:** Good for multi-region; used by production SaaS bots
- **Verdict:** Worth considering if you need geographic proximity to Kazakhstan (Almaty region) — Fly has a Frankfurt region.

### Recommended Migration Path

```
Local polling (dev) → Railway webhook (first 10 clinics) → Hetzner VPS (10+ clinics)
```

---

## Q4: Conversation State Management

### The Problem

A booking conversation has multiple turns:

```
Bot: "Which service are you interested in?"
Patient: "Dentist"
Bot: "What date works for you?"
Patient: "Tomorrow at 3pm"
Bot: "Confirming: Dentist, April 1st, 3:00 PM. Correct?"
Patient: "Yes"
Bot: "Booked! Your appointment ID is #1234."
```

You must persist state between messages. If the process restarts, state must survive.

### aiogram 3 FSM

aiogram 3's FSM is built around `StatesGroup`. Each state is a step in a conversation.

```python
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

class BookingFlow(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()
    confirming = State()

@router.message(BookingFlow.choosing_service)
async def handle_service_choice(message: Message, state: FSMContext):
    await state.update_data(service=message.text)
    await state.set_state(BookingFlow.choosing_date)
    await message.answer("What date works for you?")

@router.message(BookingFlow.choosing_date)
async def handle_date(message: Message, state: FSMContext):
    data = await state.get_data()  # {'service': 'Dentist'}
    await state.update_data(date=message.text)
    await state.set_state(BookingFlow.choosing_time)
    await message.answer("What time?")
```

State is stored per (user_id, chat_id) key automatically.

### Storage Backend Comparison

| Backend | Class | Persistence | Use When |
|---------|-------|-------------|----------|
| MemoryStorage | `aiogram.fsm.storage.memory.MemoryStorage` | Lost on restart | Local dev only |
| RedisStorage | `aiogram.fsm.storage.redis.RedisStorage` | Survives restarts | Production |

**Use RedisStorage in production. Always.**

```python
from aiogram.fsm.storage.redis import RedisStorage

storage = RedisStorage.from_url("redis://localhost:6379/0")
dp = Dispatcher(storage=storage)
```

RedisStorage supports `state_ttl` and `data_ttl` to auto-expire stale conversations (e.g., 24 hours).

### OpenAI Conversation History Storage

FSM stores the booking flow *state* (which step the user is on). OpenAI needs the full *message history* (a list of `{"role": ..., "content": ...}` dicts) for contextual responses.

Store OpenAI conversation history separately:

**Option A: Redis (same Redis, different key namespace)**
```python
# Key: openai_history:{tenant_id}:{user_id}
# Value: JSON-serialized list of message dicts
# TTL: 24 hours (avoids unbounded token growth)
```

**Option B: PostgreSQL (durable, queryable)**
```python
# Table: conversation_messages (tenant_id, user_id, role, content, created_at)
# Fetch last N messages for each OpenAI call
```

**Recommendation:** Redis for conversation history (fast, TTL-native, same infra you already have for FSM). PostgreSQL for completed appointments (durable business data).

**Token Management:** Cap OpenAI history at last 10-15 messages per user to control costs. The booking context is short-lived — patients don't need 3-month conversation memory.

### Multi-Tenant State Key Isolation

With Model B (one token per clinic), FSM state keys are scoped to the bot token automatically because each bot has its own Dispatcher instance. No additional namespacing needed.

With Model A (shared bot), prefix all state and Redis keys with `{clinic_id}:` to prevent cross-tenant data access.

---

## Q5: Production Gotchas and Common Mistakes

### Gotcha 1: Webhook 60-Second Timeout

**What happens:** Telegram waits 60 seconds for HTTP 200. If your handler awaits an OpenAI API call that takes 30+ seconds (rare but possible), you approach the limit. If you time out, Telegram retries the update — you process it twice.

**Prevention:**
- Acknowledge the webhook immediately with HTTP 200, then process asynchronously using a background task or task queue.
- Set a hard timeout on OpenAI calls: `openai.timeout = 45` seconds.
- Use streaming responses from OpenAI to send partial text back to the user faster.

```python
@router.message()
async def handle_message(message: Message, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_with_openai, message)
    return Response(status_code=200)  # Acknowledge immediately
```

### Gotcha 2: Duplicate Update Processing

**What happens:** If your server returns a non-200 response or times out, Telegram retries the same update_id. You process the same message twice — potentially creating duplicate bookings.

**Prevention:** Implement idempotency using `update.update_id`. Before processing, check if this update_id was already processed (store in Redis with TTL).

```python
async def is_duplicate(update_id: int, redis: Redis) -> bool:
    key = f"processed_update:{update_id}"
    was_set = await redis.set(key, 1, nx=True, ex=3600)
    return not was_set  # nx=True: only set if NOT exists
```

### Gotcha 3: Rate Limiting (Flood Control)

**Telegram's limits (approximate, not officially documented):**
- ~30 messages/second global
- ~20 messages/minute per group/channel
- 429 errors with a `retry_after` value

**What happens:** If you broadcast to all patients or send rapidly, you hit 429. Telegram bans the bot temporarily.

**Prevention:**
- Always handle `RetryAfter` exceptions and sleep for the specified duration.
- Use aiogram's built-in throttling middleware for user-facing spam protection.
- For broadcasts, add 35ms delay between messages.

```python
from aiogram.exceptions import TelegramRetryAfter
import asyncio

async def safe_send(bot, chat_id, text):
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await bot.send_message(chat_id=chat_id, text=text)
```

### Gotcha 4: Webhook and Polling Cannot Coexist

**What happens:** If you test locally with polling and forget to delete the webhook before deploying, or vice versa, the bot receives no updates or processes them twice.

**Prevention:** Always call `await bot.delete_webhook()` before starting polling locally, and `await bot.set_webhook(url)` on deployment startup. Never run both simultaneously.

### Gotcha 5: Missing `secret_token` Webhook Validation

**What happens:** Anyone who discovers your webhook URL can send fake Telegram updates to your bot.

**Prevention:** Set a `secret_token` when registering the webhook. Validate the `X-Telegram-Bot-Api-Secret-Token` header on every incoming request. aiogram's `SimpleRequestHandler` supports this natively.

### Gotcha 6: Bot Token Exposure

**What happens:** Bot token in code, logs, or environment variable printouts. Anyone with the token controls the bot fully.

**Prevention:**
- Store tokens encrypted in the database (AES-256-GCM), decrypt only at request time.
- Never log bot tokens.
- Use `SECRET_*` env var naming to trigger secret masking in Railway/Render.
- Rotate tokens via @BotFather immediately if exposed.

### Gotcha 7: FSM State Leaks Between Sessions

**What happens:** Patient starts a booking flow, abandons it, comes back days later — bot is still in the middle of the old flow.

**Prevention:**
- Set `state_ttl` and `data_ttl` on RedisStorage (e.g., 24 hours).
- Add a `/start` command handler that always calls `await state.clear()` first.
- Handle unexpected input in any state with a "Sorry, let me restart" fallback.

### Gotcha 8: OpenAI Latency Perception

**What happens:** OpenAI API calls take 2-8 seconds. The chat appears frozen. Patients think the bot is broken.

**Prevention:**
- Send a typing action immediately: `await bot.send_chat_action(chat_id, "typing")`
- Repeat the typing action every 5 seconds if the LLM call is slow.
- Use streaming if near-instant feel is critical.

```python
async def thinking_indicator(bot, chat_id):
    while True:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        await asyncio.sleep(4)
```

---

## Architecture Blueprint

```
.
├── app/
│   ├── main.py               # FastAPI entry point, webhook registration
│   ├── bot/
│   │   ├── router.py         # aiogram Router, all message handlers
│   │   ├── states.py         # StatesGroup definitions (BookingFlow, etc.)
│   │   ├── keyboards.py      # InlineKeyboard and ReplyKeyboard builders
│   │   └── middleware/
│   │       ├── tenant.py     # Inject clinic data from DB per bot token
│   │       └── throttle.py   # Rate limiting per user
│   ├── services/
│   │   ├── openai_service.py # Conversation history + GPT call logic
│   │   ├── booking_service.py# Appointment CRUD
│   │   └── clinic_service.py # Tenant/clinic data access
│   ├── db/
│   │   ├── models.py         # SQLAlchemy models
│   │   └── session.py        # Async session factory
│   └── core/
│       ├── config.py         # Settings from env vars (pydantic-settings)
│       └── redis.py          # Redis connection pool
├── Dockerfile
├── docker-compose.yml        # Local dev: app + redis + postgres
├── requirements.txt
└── .env.example
```

---

## Standard Stack

```bash
pip install \
  aiogram==3.26.0 \
  fastapi \
  uvicorn[standard] \
  redis[asyncio] \
  sqlalchemy[asyncio] \
  asyncpg \
  pydantic-settings \
  openai \
  cryptography
```

| Package | Purpose |
|---------|---------|
| aiogram 3.26.0 | Telegram bot framework |
| fastapi | ASGI web framework for webhook endpoint |
| uvicorn | ASGI server |
| redis[asyncio] | FSM state + conversation history storage |
| sqlalchemy + asyncpg | Async PostgreSQL ORM |
| pydantic-settings | Config from env vars |
| openai | OpenAI API client |
| cryptography | AES-256-GCM for bot token encryption |

---

## Open Questions

1. **Kazakhstan phone number validation:** Does the booking flow need to collect a Kazakhstani phone number (+7 format)? If so, add a validation step in the FSM using a regex filter.

2. **Language handling:** Russian vs. Kazakh vs. English. aiogram's middleware can detect `message.from_user.language_code`, but clinic patients in Kazakhstan will mostly use Russian. Consider i18n from day one with `fluent.runtime` or `babel`.

3. **Clinic onboarding UX:** How does a clinic provide their bot token to you? A simple web form + your admin API is sufficient early. Do not build a complex portal until you have 3+ paying clinics.

4. **Appointment calendar integration:** Does booking need to check real clinic availability (Google Calendar, custom schedule DB) or is it fire-and-forget (bot collects info, sends to clinic admin via Telegram/email)?

---

## Sources

- [aiogram official docs (3.26.0)](https://docs.aiogram.dev/en/latest/)
- [aiogram FSM documentation](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html)
- [aiogram FSM storages](https://docs.aiogram.dev/en/stable/dispatcher/finite_state_machine/storages.html)
- [aiogram middlewares](https://docs.aiogram.dev/en/latest/dispatcher/middlewares.html)
- [aiogram on PyPI](https://pypi.org/project/aiogram/)
- [python-telegram-bot on PyPI](https://pypi.org/project/python-telegram-bot/)
- [pyTelegramBotAPI on PyPI](https://pypi.org/project/pyTelegramBotAPI/)
- [python-telegram-bot: Avoiding flood limits](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Avoiding-flood-limits)
- [Telegram official webhook guide](https://core.telegram.org/bots/webhooks)
- [Telegram Bot API reference](https://core.telegram.org/bots/api)
- [Railway Telegram bot deployment](https://railway.com/deploy/5kprwG)
- [ClawBotCloud SaaS multi-tenant bot architecture](https://dev.to/clawbotcloud/how-i-built-a-saas-that-deploys-ai-caisaasnextjsdevopshatbots-to-telegram-in-2-minutes-kng)
- [aiogram webhook + FastAPI template](https://github.com/QuvonchbekBobojonov/aiogram-webhook-template)
- [multi-bot-telegram-system on GitHub](https://github.com/kostola/multi-bot-telegram-system)
- [gramio rate limits guide](https://gramio.dev/rate-limits)
