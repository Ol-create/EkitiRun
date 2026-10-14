# EkitiRun: Team Task Split (Version 1)

**EkitiRun** is the platform. The event keeps its own official name (e.g. "Ekiti Marathon 2027"), so EkitiRun can host future editions and other races.

## Version 1 scope

Free runner registration with phone OTP, bib numbers with QR codes, sponsor payments through Paystack with PDF invoices and receipts, offline checkpoint scanning, split and finish times, a public tracking page, and a live leaderboard.

## Team

| Person | Role | Share | Task file |
|---|---|---|---|
| Lead (expert) | Architecture, backend core, scanner, timing | 70% | [lead.md](lead.md) |
| Frontend 1 | Registration and sponsor screens | 10% | [frontend-1.md](frontend-1.md) |
| Frontend 2 | Public race-day pages (leaderboard, tracking, map) | 10% | [frontend-2.md](frontend-2.md) |
| Backend | Sponsor tiers, pledges, public read endpoints, PDF templates | 10% | [backend.md](backend.md) |

Everyone works against the shared contract in [api-contract.md](../api-contract.md).

## Stack

- **Frontend (`apps/web`):** Next.js (App Router), TypeScript, Tailwind, shadcn/ui, react-hook-form + zod, Leaflet, openapi-fetch.
- **Backend (`apps/api`):** FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, ARQ, Redis, PostgreSQL, WeasyPrint + Jinja2, segno, pytest.
- **Services:** Paystack (payments), Termii (SMS OTP), Cloudinary (logos).
- **Local development:** Docker Compose runs Postgres, Redis and the API. Run `pnpm dev` for the web app.

## Phases

| Phase | Lead | Frontend 1 | Frontend 2 | Backend |
|---|---|---|---|---|
| **0: Foundation** | E1, E2, stub endpoints | Onboarding | Onboarding | Onboarding |
| **1: Registration and sponsors** | E3, E4, E5, E6 | F1.1–F1.4 | F2.1–F2.3 (on mock data) | B1, B2, B4 |
| **2: Timing and tracking** | E7–E11 | Polish and bug fixes | Switch to the real API | B3 |
| **3: Hardening** | E12, race rehearsal | Rehearsal testing | Rehearsal testing | Rehearsal testing |

Onboarding for each newbie:

1. Clone the repo and run it locally.
2. Make a first small PR to learn the Git workflow.
3. Finish the tutorial listed in your task file.

## Team rules

1. **One ticket, one branch, one PR.** Name branches `feat/F1.1-registration-form`, `fix/B3-search-empty`, and so on.
2. **Every PR is reviewed by Lead** before merge. Nobody pushes directly to `main`.
3. **Do not touch** the database schema or migrations, auth or OTP, payments or webhooks, the scanner, or the timing engine. If you need a change there, ask Lead.
4. **When you're stuck for more than 2 hours**, post in the team chat with what you tried and the error.
5. **Definition of done:**
   - CI passes (lint, type-check, tests).
   - It works at 375px mobile width.
   - Loading, empty and error states exist.
   - The ticket's acceptance criteria are checked off in the PR description.
