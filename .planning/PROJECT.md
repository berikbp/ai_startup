# AI Receptionist (Kazakhstan)

## What This Is

A SaaS AI receptionist for clinics and dental offices in Kazakhstan. Patients chat with the AI via Telegram (or WhatsApp), ask questions about services, and book appointments. Clinic owners log into a web dashboard to see all bookings and conversation history. Voice support comes after the text MVP is validated.

## Core Value

Patients can book clinic appointments 24/7 via Telegram without calling — and owners see every booking in one place.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Bot (Patient-facing)**
- [ ] Telegram bot answers patient questions about clinic services (hours, prices, treatments)
- [ ] Bot collects appointment bookings: patient name, service, preferred date/time
- [ ] Bot confirms booking to patient in chat
- [ ] Supports Russian (primary); Kazakh optional in v1
- [ ] Powered by OpenAI API for natural conversation

**Dashboard (Owner-facing)**
- [ ] Clinic owner can log into a web dashboard
- [ ] Dashboard shows all bookings: patient name, service, time, status
- [ ] Dashboard shows conversation history per patient
- [ ] Owner can mark a booking as confirmed or cancelled
- [ ] Multi-tenant: each clinic has its own account and isolated data

**Infrastructure**
- [ ] Each clinic connects their own Telegram bot (or we manage a shared bot with clinic routing)
- [ ] Monthly subscription billing per clinic

### Out of Scope

- Voice calls — deferred to v2 after text MVP is validated
- WhatsApp — deferred; start with Telegram (easier API, widely used in KZ)
- Direct calendar sync — bookings log to dashboard only; receptionist confirms manually
- Mobile app — web dashboard is sufficient for v1
- Kazakh language — Russian-first for speed; Kazakh-Russian code-switching is v2 moat
- English — not the target market

## Context

- Target market: Clinics and dental offices in Almaty, Kazakhstan
- Builder: Solo developer using Claude Code
- Immediate goal: Land first paying clinic customer with a working demo
- Language stack: Python (pyproject.toml with uv already initialized)
- AI: OpenAI API key already available
- Bot platform: Telegram first (simpler bot API than WhatsApp, popular in KZ)
- Channel evolution: Telegram text → WhatsApp text → Voice agent (phased)
- Key unknown: How to structure per-clinic Telegram bot (one shared bot vs. each clinic registers their own bot token)

## Constraints

- **Market**: Kazakhstan — local phone numbers and payment methods matter for v2
- **Language**: Russian-first for v1; Kazakh+code-switching is the v2 competitive moat
- **Timeline**: Build toward a demoable product fast — first customer is the goal
- **Stack**: Python + OpenAI API; Telegram Bot API for channel
- **Budget**: Solo founder — API-first (pay-per-use), no self-hosted infra for v1

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Text-first (no voice) | De-risk the product; validate core booking flow before adding voice complexity | — Pending |
| Telegram over WhatsApp | Simpler bot API, no business account requirement, popular in KZ | — Pending |
| OpenAI API for AI | Already have key; fastest path to working demo | — Pending |
| Dashboard bookings only (no calendar sync) | Too many clinic systems; receptionist confirms manually in v1 | — Pending |
| Monthly subscription model | Simple SaaS pricing; predictable revenue | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-30 after scope pivot — text-first (Telegram) MVP clarified*
