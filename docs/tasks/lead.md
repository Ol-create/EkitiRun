# Lead (Expert): 70%

You own the architecture and everything risky: data, auth, money, the scanner, and timing. You also unblock and review the three newbies.

**First priority:** finish E1, E2 and the stub endpoints. Until they exist, the newbies are blocked.

## Phase 0: Foundation

### E1: Monorepo and tooling (6 pts)

- pnpm workspace containing:
  - `apps/web`: Next.js, Tailwind, shadcn/ui, ESLint, Prettier.
  - `apps/api`: FastAPI with uv, ruff, mypy, pytest.
- `docker-compose.yml` running Postgres 16, Redis 7 and the API with hot reload.
- `pnpm gen:api`: openapi-typescript generates types from `/openapi.json`, wrapped in an openapi-fetch client in `apps/web/lib/api.ts`.
- GitHub Actions: lint, type-check and tests for both apps on every PR. Branch protection on `main`.
- `.env.example` for both apps, and a README with setup steps a newbie can follow on Windows.

### E2: Schema and migrations (6 pts)

- SQLAlchemy 2.0 models and Alembic migrations for: `categories`, `runners`, `otp_codes`, `sponsor_tiers`, `sponsors`, `pledges`, `payments`, `checkpoints`, `scans`, `route`.
- Constraints:
  - Unique `runners.phone`.
  - Unique `runners.bib_number`.
  - Unique `scans.client_id`.
  - Unique `(runner_id, checkpoint_id)` on scans; when a runner is scanned twice, keep the earliest scan.
- Seed script with categories, checkpoints and the route GeoJSON.
- **Stub endpoints:** every route in `docs/api-contract.md` returns realistic fake data, so frontend work can start.
- An example CRUD module (`app/modules/categories/`: router, schemas, service, tests) for Backend to copy.

## Phase 1: Registration and sponsors

### E3: Phone OTP (6 pts)

- Termii integration, with a fake sender in development that logs the code to the console.
- 6-digit code, 10-minute expiry, at most 5 verify attempts.
- Redis rate limits: 1 request per 60 s per phone and 10 per hour per IP.
- Issue a signed `verification_token` (JWT, 30 min) that `/registrations` requires.

### E4: Registration and bibs (6 pts)

- Lock the category row (`SELECT … FOR UPDATE`) so caps can't be exceeded when many people sign up at once.
- Assign bib numbers per category from a sequence, e.g. Full `F0001`, Half `H0001`, 10 km `T0001`, Fun run `R0001`.
- The QR code contains an **HMAC-signed token** (bib + runner id), so a printed QR can't be forged by changing the number.
- QR PNG endpoint generated with segno.

### E5: Paystack (8 pts)

- Initialize the transaction and return `authorization_url`.
- Webhook handler:
  - Verify the `x-paystack-signature` HMAC-SHA512.
  - Re-verify the transaction through the Paystack API.
  - Handle each event only once, keyed on `reference`.
- Pledge state machine: `pending` → `paid` / `failed`.
- The bank transfer channel is enabled for large sponsors.

### E6: PDF pipeline (5 pts)

- ARQ worker container.
- Jobs: render the invoice when a pledge is created and the receipt when it is paid, using Jinja2 + WeasyPrint.
- Upload the PDFs to storage and save their URLs on the pledge.
- Backend writes the templates (B4). You provide the render function and the template context.

## Phase 2: Timing and tracking

### E7: Offline-first scanner PWA (10 pts)

- Route `/scanner` in `apps/web`.
- A volunteer logs in with a checkpoint PIN, which binds the device to a checkpoint.
- Camera scanning with `html5-qrcode`. Each scan gives a beep and a vibration, and shows the runner's name and bib for 2 s.
- Scans queue in IndexedDB (Dexie) with a client UUID. They sync in batches every 10 s when online, and the screen shows a "pending sync" counter.
- Manual bib entry as a fallback for damaged bibs.
- Must work at full speed in airplane mode.

### E8: Scan ingestion (5 pts)

- `POST /scans/batch`:
  - Accepts the device token.
  - Verifies each QR signature.
  - Inserts with `ON CONFLICT DO NOTHING`.
  - Reports results per scan.
- Clock drift: store both device time and server receive time, and flag devices whose clocks are off by more than 2 minutes.

### E9: Timing engine (7 pts)

- Elapsed time per scan, measured from the category's gun start.
- Finish time is the scan at the finish checkpoint.
- Overall, category and gender rankings, cached in Redis and recalculated on each scan batch.
- `GET /results` and `GET /runners/{bib}` read their splits and positions from this engine.

### E10: Position estimate (4 pts)

- Helper `estimatePosition(route, checkpoints, lastSplit, pace, now)` in `apps/web/lib/tracking.ts` (turf.js), returning `{ lat, lng, distance_km, is_estimate }`.
- Stop the estimate at the next checkpoint so a runner never appears ahead of where they could be.
- Unit tests. Frontend 2 calls this helper; they don't change it.

### E11: Live updates (3 pts)

- Redis pub/sub channel `scans`, plus the SSE endpoint `/stream/results` with a heartbeat every 15 s.

## Phase 3: Hardening

### E12: Ship it (4 pts, plus ongoing reviews)

- Deploy: Vercel (web), Render or Railway (API, worker, Redis), Neon (Postgres). Scale up in race week.
- Locust load test: 5,000 spectators on the leaderboard and SSE, plus 20 scanners syncing.
- Race-day runbook: who to call, how to restart, the manual results fallback.
- Full rehearsal on a test route with volunteers.

## Mentoring checklist

- Write every newbie ticket as a GitHub issue with its acceptance criteria.
- Pair for 30 minutes with each newbie on their first ticket.
- Review PRs within 24 hours. Explain the *why* in review comments.
