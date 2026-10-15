# API Contract (v1)

This is the shared agreement between frontend and backend.

- **Base URL:** `/api/v1`. All bodies are JSON.
- **Money:** amounts are integers in **kobo** (₦1 = 100 kobo).
- **Times:** ISO 8601 in UTC. Durations are integer seconds.
- **Errors:** every error looks like `{ "detail": "Human-readable message", "code": "MACHINE_CODE" }`.
- **Types:** frontend TypeScript types are generated from FastAPI's `/openapi.json`. Run `pnpm gen:api` and never hand-write them.

In Phase 0, Lead ships **stub versions** of every endpoint below that return fake data, so frontend work can start straight away.

## Auth and registration (owned by Lead)

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/auth/otp/request` | `{ phone }` (format `+234…`) | `204`. `429 OTP_RATE_LIMITED` if requested too often |
| POST | `/auth/otp/verify` | `{ phone, code }` | `{ verification_token }`, valid for 30 min. `400 OTP_INVALID` / `OTP_EXPIRED` |
| POST | `/registrations` | `{ verification_token, first_name, last_name, gender: "M"\|"F", date_of_birth, email?, category_id, emergency_contact_name, emergency_contact_phone, tracking_consent: true }` | `201 { runner_id, bib_number, category, qr_png_url }`. `409 PHONE_ALREADY_REGISTERED`, `409 CATEGORY_FULL`. `422 TRACKING_CONSENT_REQUIRED` if `tracking_consent` is not `true` (every runner wears a GPS tracker) |

## Categories and runners (owned by Backend newbie)

| Method | Path | Response |
|---|---|---|
| GET | `/categories` | `[{ id, code, name, distance_km, cap, slots_left, is_full }]` |
| GET | `/runners/search?q=` | `[{ bib_number, full_name, category_code }]`, at most 20. `q` is a name or bib, at least 2 characters |
| GET | `/runners/{bib_number}` | `{ bib_number, full_name, gender, category, status: "registered"\|"started"\|"finished"\|"dnf", splits: [{ checkpoint_id, checkpoint_name, distance_km, scanned_at, elapsed_seconds }], finish_seconds?, position_overall?, position_category?, live_position? }`. `live_position` has the shape in *Live GPS tracking* below, and is `null` when the runner has no tracker or no GPS fix yet |

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
| GET | `/route` | `{ route: GeoJSON LineString, checkpoints: [{ id, name, distance_km, lat, lng }] }` |
| GET | `/results?category=&gender=&limit=50&offset=0` | `{ items: [{ position, bib_number, full_name, gender, category_code, last_checkpoint, elapsed_seconds, finish_seconds? }], total }` |
| GET | `/stream/results` | Server-Sent Events. `event: scan` with data `{ bib_number, checkpoint_id, elapsed_seconds }` |
| POST | `/scans/batch` | Scanner only. `{ device_id, checkpoint_id, scans: [{ client_id, qr_token, scanned_at }] }` |

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
