# Deploying EkitiRun

| Part | Where | Why |
|---|---|---|
| Web app (`apps/web`) | **Vercel** | Next.js host, global CDN for the public pages |
| API, worker, GPS writer | **Render** (Frankfurt), from `render.yaml` | Docker services described in the repo |
| Redis | **Render Key Value** (Frankfurt), from `render.yaml` | Same network as the API; `noeviction` |
| Postgres | **Neon** (AWS eu-central-1, Frankfurt) | Managed Postgres with branching for staging |
| Traccar (GPS gateway) | A small cloud VM (any VPS in Frankfurt) with public TCP ports | Trackers connect over raw TCP, which Render and Vercel don't accept |

Frankfurt is the closest region of these providers to Nigeria. Keep the API, Redis and the database in the same region.

There are two environments: **staging** (rehearsals, load tests, demo data) and **production** (race). Use a separate Render project, Neon branch and Vercel project (or preview environment) for each.

## Accounts and decisions needed first

- [ ] Domain, e.g. `ekitirun.ng` (web) and `api.ekitirun.ng` (API).
- [ ] Render, Neon and Vercel accounts (team/organisation, billing).
- [ ] Paystack live secret key (business verification can take days), webhook URL set to `https://api.<domain>/api/v1/webhooks/paystack`.
- [ ] Termii live key, **registered sender ID "EkitiRun"** and DND route enabled (can take days).
- [ ] Organiser name, address, email and bank details for invoices.
- [ ] Race date, kit-desk PIN.

## 1. Database (Neon)

1. Create a project in **AWS eu-central-1**, database `ekitirun`.
2. Copy two connection strings and change `postgresql://` to `postgresql+asyncpg://`:
   - **pooled** (host contains `-pooler`): becomes `DATABASE_URL`. The API turns off asyncpg's statement cache automatically for it.
   - **direct** (no `-pooler`): becomes `MIGRATION_DATABASE_URL`, used only by migrations.
3. asyncpg doesn't understand `sslmode=require`: replace it with `ssl=require` in both URLs (and drop `channel_binding=...` if present).

## 2. Backend (Render)

1. Render dashboard: **New > Blueprint**, pick this repository. It reads `render.yaml` and proposes the API, worker, GPS writer and Redis.
2. Fill in the values marked `sync: false` (database URLs, keys, URLs, organiser details, `KIT_PIN`, `RACE_DATE`). Secrets marked `generateValue` are created by Render; **never change `QR_SIGNING_SECRET` after bibs are printed**, or printed QR codes stop scanning.
3. Deploy. Each API deploy runs `alembic upgrade head` first (`preDeployCommand`).
4. Point `api.<domain>` at the API service (Render: Settings > Custom Domains).
5. In the API's **Shell** tab:
   ```bash
   python -m scripts.seed
   python -m scripts.checkpoint_pins      # print the volunteers' PINs once: save them
   python -m scripts.preflight
   ```
   Production refuses to start with development secrets, the fixed OTP code, console SMS or a test Paystack key, so a misconfiguration shows up as a failed deploy, not a quiet problem.

## 3. Web (Vercel)

1. New project from this repository, **Root Directory `apps/web`** (Vercel detects pnpm and Next.js).
2. Environment variable `NEXT_PUBLIC_API_URL=https://api.<domain>`.
3. Point `<domain>` at it. Make sure `CORS_ORIGINS` and `PUBLIC_WEB_URL` on Render list exactly this URL.

## 4. GPS gateway (Traccar)

1. Run `traccar/traccar:6.16.0` on a host with public TCP ports open for your trackers' protocol (and 8082 for its web UI, restricted to the organisers).
2. Configure it from `infra/traccar/traccar.example.xml`, with `forward.url=https://api.<domain>/api/v1/gps/traccar` and the production `GATEWAY_SECRET`.
3. Program the trackers with the gateway's address and port (vendor tool or SMS commands).

## Race week: scaling up

Load-test **staging** at full size first (`docs/runbook.md`, "Load test"). Then, a few days before the race, in production:

| Service | Normal | Race week (starting point; adjust from the load test) |
|---|---|---|
| API | 1 instance, standard | 3+ instances, `WEB_CONCURRENCY=2` |
| GPS writer | 1 | 2 (they share the stream) |
| Redis | standard | a plan with enough memory and connections for the SSE viewers |
| Neon | autoscaling | raise the minimum compute so it doesn't scale down mid-race |

Keep `(DB_POOL_SIZE + DB_MAX_OVERFLOW) x API processes` below Neon's connection limit for the pooled endpoint. Scale back down after the results are final.
