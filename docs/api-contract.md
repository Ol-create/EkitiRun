# API Contract (v1)

This is the shared agreement between frontend and backend.

- **Base URL:** `/api/v1`. All bodies are JSON.
- **Money:** amounts are integers in **kobo** (₦1 = 100 kobo).
- **Times:** ISO 8601 in UTC. Durations are integer seconds.
- **Errors:** every error looks like `{ "detail": "Human-readable message", "code": "MACHINE_CODE" }`. Validation errors are `422 VALIDATION_ERROR` and also carry `errors: [{ loc, msg, type }]`, so forms can show a message under each field (`loc` ends with the field name).
- **Types:** frontend TypeScript types are generated from FastAPI's `/openapi.json`. Run `pnpm gen:api` and never hand-write them.

In Phase 0, Lead ships **stub versions** of every endpoint below that return fake data, so frontend work can start straight away. How to trigger each error in the stubs is listed in [Phase 0 stub behaviour](#phase-0-stub-behaviour).

## Auth and registration (owned by Lead)

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/auth/otp/request` | `{ phone }` (format `+234…`) | `204`, and an SMS with a 6-digit code valid for 10 minutes. A new code cancels the previous one. `429 OTP_RATE_LIMITED` at more than 1 request per phone per 60 s (the `detail` says how many seconds to wait) or 10 per IP per hour. `502 SMS_SEND_FAILED` if the SMS couldn't be sent (retry straight away) |
| POST | `/auth/otp/verify` | `{ phone, code }` | `{ verification_token }`, valid for 30 min. `400 OTP_INVALID` (the `detail` says how many attempts are left) / `400 OTP_EXPIRED`. `429 OTP_TOO_MANY_ATTEMPTS` after 5 wrong codes: request a new one |
| POST | `/registrations` | `{ verification_token, first_name, last_name, gender: "M"\|"F", date_of_birth, email?, category_id, emergency_contact_name, emergency_contact_phone, tracking_consent: true }` | `201 { runner_id, bib_number, category, qr_png_url }`. `401 VERIFICATION_INVALID` (token missing or expired: verify the phone again), `404 CATEGORY_NOT_FOUND`, `409 PHONE_ALREADY_REGISTERED`, `409 CATEGORY_FULL`. `422 TRACKING_CONSENT_REQUIRED` if `tracking_consent` is not `true` (every runner wears a GPS tracker) |
| GET | `/registrations/{runner_id}/qr.png` | | PNG image of the runner's QR code. This is the `qr_png_url` above |

## Categories and runners (owned by Backend newbie)

| Method | Path | Response |
|---|---|---|
| GET | `/categories` | `[{ id, code, name, distance_km, cap, slots_left, is_full }]`, in display order |
| GET | `/categories/{id}` | One category, same shape. `404 CATEGORY_NOT_FOUND` |
| GET | `/runners/search?q=` | `[{ bib_number, full_name, category_code }]`, at most 20. `q` is a name or bib, at least 2 characters |
| GET | `/runners/{bib_number}` | `{ bib_number, full_name, gender, category, status: "registered"\|"started"\|"finished"\|"dnf", splits: [{ checkpoint_id, checkpoint_name, distance_km, scanned_at, elapsed_seconds }], finish_seconds?, position_overall?, position_category?, live_position? }`. `404 RUNNER_NOT_FOUND`. Positions are set once the runner finishes: `position_overall` is the place in their race (all genders), `position_category` the place within their gender in that race. `live_position` has the shape in *Live GPS tracking* below, and is `null` when the runner has no tracker or no GPS fix yet |

## Sponsors (tiers and pledges owned by Backend newbie, payments by Lead)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/sponsor-tiers` | | `[{ id, name, amount_kobo, benefits: string[], sort_order }]` |
| POST | `/admin/sponsor-tiers` | `{ name, amount_kobo, benefits, sort_order }` | `201` tier. Admin only |
| PATCH | `/admin/sponsor-tiers/{id}` | partial | tier. Admin only |
| DELETE | `/admin/sponsor-tiers/{id}` | | `204`. Admin only |
| POST | `/sponsors/pledges` | `{ tier_id? , custom_amount_kobo?, company_name, contact_name, email, phone, website? }`. Send exactly one of `tier_id` or `custom_amount_kobo` | `201 { reference, authorization_url, invoice_pdf_url }` |
| GET | `/sponsors/pledges/{reference}` | | `{ reference, company_name, amount_kobo, status: "pending"\|"paid"\|"failed", receipt_pdf_url? }` |
| POST | `/webhooks/paystack` | Paystack payload | Lead only. This is the **only** place a pledge becomes `paid` |

## Race day (owned by Lead)

| Method | Path | Response |
|---|---|---|
| GET | `/route?category=FULL` | `{ category_code, length_km, route: GeoJSON LineString, checkpoints: [{ id, name, distance_km, lat, lng }] }`. Each category has its own course; `category` defaults to `FULL`. `404 CATEGORY_NOT_FOUND` |
| GET | `/results?category=&gender=&limit=50&offset=0` | `{ items: [{ position, bib_number, full_name, gender, category_code, status: "started"\|"finished"\|"dnf", last_checkpoint, elapsed_seconds, finish_seconds? }], total }`. Finishers first by time, then runners still going (furthest first), then DNF. `limit` is at most 200 |
| GET | `/stream/results` | Server-Sent Events. `event: scan` with data `{ bib_number, checkpoint_id, elapsed_seconds }` |
| POST | `/scans/batch` | Scanner only. `{ device_id, checkpoint_id, scans: [{ client_id, qr_token, scanned_at }] }` (at most 500 scans). Returns `{ results: [{ client_id, status: "accepted"\|"duplicate"\|"invalid", bib_number? }] }` |

## Live GPS tracking (owned by Lead, tracker inventory by Backend newbie)

Every runner wears a GPS tracker, handed out at bib collection and returned at the finish. Trackers report to a GPS gateway (Traccar), which forwards each position to the API. **GPS drives the live map only. Official times and results still come from checkpoint scans.**

A `live_position` object, used below and in `GET /runners/{bib_number}`:

```
{ lat, lng, distance_km, recorded_at, is_stale }
```

- `distance_km`: how far along the route the runner is, after snapping the GPS point to the route line.
- `is_stale`: `true` when the last fix is older than 2 minutes (tracker off, flat battery, no signal). The frontend then falls back to `estimatePosition(...)`.

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/gps/positions` | Gateway only, authenticated with the `X-Gateway-Secret` header. `{ positions: [{ device_id, lat, lng, accuracy_m?, battery_pct?, recorded_at }] }` | `202`. Unknown or unassigned devices are ignored. Points more than 200 m from the route are stored but not shown |
| GET | `/positions?category=` | | `{ updated_at, runners: [{ bib_number, category_code, gender, lat, lng, distance_km, is_stale }] }`. Latest point for every runner on course, refreshed every 5 s and served from cache |
| GET | `/stream/positions?bib=` | | Server-Sent Events for one runner. `event: position` with data `{ bib_number, ...live_position }`, sent on every new fix. Heartbeat every 15 s |
| GET | `/admin/trackers?status=` | | `[{ id, device_id, label, status: "available"\|"assigned"\|"returned"\|"lost", bib_number?, battery_pct?, last_seen_at? }]`. Admin only |
| POST | `/admin/trackers` | `{ device_id, label }` | `201` tracker. Admin only. `409 TRACKER_EXISTS` |
| PATCH | `/admin/trackers/{id}` | `{ label?, status? }` | tracker. Admin only |
| POST | `/kit/assign` | `{ qr_token, tracker_label }` | Kit-collection volunteer only. `{ bib_number, full_name, tracker_label }`. `409 TRACKER_IN_USE`, `409 RUNNER_HAS_TRACKER` |
| POST | `/kit/return` | `{ tracker_label }` | Kit or finish volunteer only. `{ bib_number, tracker_label }`. Sets the tracker back to `returned` |

Location history is deleted 30 days after the race.

## Phase 0 stub behaviour

While an endpoint is still a stub (Phase 0 to 2), it returns fake data and these inputs trigger each case. Nothing a stub receives is saved.

| Endpoint | How to trigger it |
|---|---|
| `POST /auth/otp/request`, `/auth/otp/verify` | **Real since E3.** In development no SMS is sent and every code is `123456` (`OTP_DEV_CODE`); the message is printed in the API log (`docker compose logs -f api`). To see `OTP_RATE_LIMITED`, request twice within a minute. To see `OTP_TOO_MANY_ATTEMPTS`, enter a wrong code 5 times |
| `POST /registrations` | The verified phone decides: ending in `0000` gives `PHONE_ALREADY_REGISTERED`, ending in `9999` gives `CATEGORY_FULL`. `category_id` 1 to 4 are FULL, HALF, 10K, FUN |
| `GET /categories` | Already real: reads the database (run the seed first). `slots_left` ignores registrations until B3 |
| Runners, results, positions, streams | A simulated race of 240 runners (bibs `F0001`–`F0050`, `H0001`–`H0070`, `T0001`–`T0060`, `R0001`–`R0060`). It starts about 100 minutes in when the API starts and loops every 6.5 hours, so there are always finishers, runners on course, DNFs, runners who never started, stale trackers and runners without one |
| `POST /sponsors/pledges` | Skips Paystack: `authorization_url` goes straight to `/sponsors/thank-you`. A company name containing "fail" ends `failed`, one containing "pending" stays `pending`, anything else is `paid`. PDF links open a placeholder PDF |
| Admin endpoints | Send `Authorization: Bearer dev-admin` (development only, until admin login exists) |
| `POST /gps/positions` | Send `X-Gateway-Secret` with the value of `GATEWAY_SECRET` in `apps/api/.env` |
| `POST /kit/assign`, `/kit/return` | `qr_token` can be a fake bib such as `R0005`. Trackers `TRK-0001`–`0030` are assigned, `TRK-0031`–`0039` are free, `TRK-0040` is lost |
| `POST /scans/batch` | `qr_token` can be a fake bib; anything else is `invalid` |
