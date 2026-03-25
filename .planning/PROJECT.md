# AI Receptionist (Kazakhstan)

## What This Is

A SaaS AI voice receptionist for clinics and dental offices in Kazakhstan. When a patient calls, the AI answers, handles the conversation in Kazakh, Russian, or mixed (code-switched) speech, and logs a summary to the clinic's dashboard. Clinic owners see analytics and call history; receptionists see actionable follow-ups like appointment requests.

## Core Value

The only AI receptionist that natively handles Kazakh-Russian code-switching — solving the exact problem no generic tool can solve for Kazakhstan clinics.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] AI answers inbound calls and handles the full conversation (greet, answer questions, collect appointment requests)
- [ ] Supports Kazakh, Russian, and Kazakh-Russian mixed speech (code-switching) from day one
- [ ] Transcribes and summarizes each call, logs to clinic dashboard
- [ ] Multi-tenant dashboard: each clinic has its own account
- [ ] Dashboard shows call log, summaries, and appointment requests for receptionist follow-up
- [ ] Dashboard shows call analytics overview for clinic owner (volume, missed, request types)
- [ ] Monthly subscription billing per clinic
- [ ] Each clinic gets a dedicated phone number (Kazakhstan)

### Out of Scope

- Direct calendar integration — appointment requests log to dashboard only, human confirms (v1) — too many clinic systems to integrate in v1
- Mobile app — web dashboard is sufficient for v1
- Languages beyond Kazakh and Russian — not needed for Kazakhstan market
- English support — not the target market

## Context

- Target market: Clinics and dental offices in Almaty, Kazakhstan
- Builder: Solo developer using Claude Code
- Immediate goal: Land first paying clinic customer with a working demo
- STT approach: Use Whisper large-v3 or Google Cloud STT (Kazakh + Russian support) for v1 MVP. Fine-tune a custom Kazakh-Russian code-switching model in parallel as the core competitive moat.
- Key technical risk: Kazakh is a low-resource language. Off-the-shelf STT accuracy will be imperfect — especially for code-switching. Research phase must evaluate: Whisper large-v3, wav2vec2-XLSR Kazakh fine-tunes, Meta MMS, and Google/Azure STT APIs.
- Voice AI stack needs: STT (speech-to-text), LLM (conversation logic), TTS (text-to-speech response), telephony (inbound calls with a KZ number)

## Constraints

- **Market**: Kazakhstan only — must support local phone numbers and local payment methods
- **Language**: Kazakh + Russian + code-switching is non-negotiable from launch — it's the whole value proposition
- **Timeline**: Build toward a demoable product fast — goal is first customer, not a perfect product
- **Stack**: Builder is a developer using Claude Code — full-stack web app + voice pipeline
- **Budget**: Solo founder — prefer API-first (pay-per-use) over self-hosted infra for v1

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| API-first STT for v1 (Whisper/Google) | Fastest path to demo; fine-tuned model is moat for v2 | — Pending |
| Appointments log to dashboard only (no calendar sync) | Too many clinic systems; receptionist confirms manually in v1 | — Pending |
| Monthly subscription model | Simple SaaS pricing; predictable revenue | — Pending |
| Multi-tenant architecture | Each clinic = isolated account + dedicated number | — Pending |

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
*Last updated: 2026-03-25 after initialization*
