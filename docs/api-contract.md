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
| POST | `/registrations` | `{ verification_token, first_name, last_name, gender: "M"\|"F", date_of_birth, email?, category_id, emergency_contact_name, emergency_contact_phone, tracking_consent: true }` | `201 { runner_id, bib_number, category, qr_png_url }`. `401 VERIFICATION_INVALID` (token missing or expired: verify the phone again), `404 CATEGORY_NOT_FOUND`, `409 PHONE_ALREADY_REGISTERED`, `409 CATEGORY_FULL`. `422 TRACKING_CONSENT_REQUIRED` if `tracking_consent` is not `true` (every runner wears a GPS tracker). `422 AGE_REQUIREMENT_NOT_MET` if the runner is younger than the category's minimum age on race day (18 for FULL and HALF, 12 for 10K). The phone number comes from the verification token, not the form |
| GET | `/registrations/{runner_id}/qr.png` | | PNG image of the runner's QR code. This is the `qr_png_url` above. `404 RUNNER_NOT_FOUND`. The QR contains a signed token, `R1.<bib>.<runner id>.<signature>`: scanners send it unchanged as `qr_token`, and an edited code is rejected with `QR_INVALID` |

## Categories and runners (owned by Backend newbie)

| Method | Path | Response |
|---|---|---|
| GET | `/categories` | `[{ id, code, name, distance_km, cap, slots_left, is_full, gun_start_at }]` (`gun_start_at` is null until the race starts), in display order |
| GET | `/categories/{id}` | One category, same shape. `404 CATEGORY_NOT_FOUND` |
| GET | `/runners/search?q=` | `[{ bib_number, full_name, category_code }]`, at most 20. `q` is a name or bib, at least 2 characters |
| GET | `/runners/{bib_number}` | `{ bib_number, full_name, gender, category, status: "registered"\|"started"\|"finished"\|"dnf", splits: [{ checkpoint_id, checkpoint_name, distance_km, scanned_at, elapsed_seconds }], finish_seconds?, position_overall?, position_category?, live_position? }`. `404 RUNNER_NOT_FOUND`. Positions are set once the runner finishes: `position_overall` is the place in their race (all genders), `position_category` the place within their gender in that race. `live_position` has the shape in *Live GPS tracking* below, and is `null` when the runner has no tracker or no GPS fix yet |

## Organiser (admin) sign-in (owned by Lead)

Every endpoint marked "Admin" needs `Authorization: Bearer <token>`. Accounts are made with `python -m scripts.create_admin` (there is no sign-up). In development only, the token `dev-admin` also works; production refuses it.

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/admin/auth/login` | `{ email, password }` | `{ token, expires_at, admin: { id, email, name } }`, token valid 12 h. `401 LOGIN_INVALID` (same for unknown email and wrong password), `429 LOGIN_RATE_LIMITED` (5 failures per email or 10 per IP in 15 min) |
| GET | `/admin/auth/me` | | `{ id, email, name }`. `401 ADMIN_AUTH_REQUIRED` if the token expired or the admin was signed out, deactivated or had their password changed |

## Sponsors (tiers and pledges owned by Backend newbie, payments by Lead)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/sponsor-tiers` | | `[{ id, name, amount_kobo, benefits: string[], sort_order }]` |
| POST | `/admin/sponsor-tiers` | `{ name, amount_kobo, benefits, sort_order }` | `201` tier. Admin only |
| PATCH | `/admin/sponsor-tiers/{id}` | partial | tier. Admin only |
| DELETE | `/admin/sponsor-tiers/{id}` | | `204`. Admin only |
| POST | `/sponsors/pledges` | `{ tier_id? , custom_amount_kobo?, company_name, contact_name, email, phone, website? }`. Send exactly one of `tier_id` or `custom_amount_kobo` | `201 { reference, authorization_url, invoice_pdf_url }` |
| GET | `/sponsors/pledges/{reference}` | | `{ reference, company_name, amount_kobo, status: "pending"\|"paid"\|"failed", receipt_pdf_url? }` |
| GET | `/files/{key}` | | A stored file (sponsor invoice or receipt PDF). The `invoice_pdf_url` and `receipt_pdf_url` links point here; the key contains a random token, so only people with the link can open it. `404 FILE_NOT_FOUND` |
| POST | `/webhooks/paystack` | Paystack payload, signed in `x-paystack-signature` | Lead only. This is the **only** public way a pledge becomes `paid`. Every event is re-verified with Paystack and settled once. `401 INVALID_SIGNATURE`; `502 PAYMENT_PROVIDER_ERROR` when Paystack can't be reached (Paystack retries) |

## Race day (owned by Lead)

| Method | Path | Response |
|---|---|---|
| GET | `/route?category=FULL` | `{ category_code, length_km, route: GeoJSON LineString, checkpoints: [{ id, name, distance_km, lat, lng }] }`. Each category has its own course; `category` defaults to `FULL`. `404 CATEGORY_NOT_FOUND` |
| GET | `/results?category=&gender=&limit=50&offset=0` | `{ items: [{ position, bib_number, full_name, gender, category_code, status: "started"\|"finished"\|"dnf", last_checkpoint, elapsed_seconds, finish_seconds? }], total }`. Finishers first by time, then runners still going (furthest first), then DNF. `limit` is at most 200. Elapsed times count from the category's gun start (`null` until it is recorded); `position` is the place in the race, or among the runner's gender with `gender=`. Without `category`, every race is listed in order. Served from a cache that refreshes after every scan upload |
| POST | `/admin/categories/{id}/gun-start` | Admin. `{ at? }` (empty = now). Returns `{ category_id, category_code, gun_start_at }`. All elapsed times count from it |
| POST / DELETE | `/admin/runners/{bib_number}/dnf` | Admin. Mark (or unmark) a runner as did-not-finish. Returns `{ bib_number, status }`. `404 RUNNER_NOT_FOUND` |
| GET | `/stream/results?category=` | Server-Sent Events (`EventSource`). `event: scan` each time a runner is scanned, with data `{ bib_number, category_code, checkpoint_id, checkpoint_name, distance_km, scanned_at, elapsed_seconds }` (`elapsed_seconds` is `null` until the gun start is recorded). `category` (e.g. `HALF`) limits it to one race. A `: ping` comment every 15 s keeps the connection open. Treat an event as "something changed": re-fetch what the page shows (throttled), don't patch it from the event |
| POST | `/scanner/login` | `{ pin, device_id }` (6-digit checkpoint PIN). Returns `{ token, expires_at, checkpoint: { id, code, name, distance_km, is_start, is_finish, category_codes } }`; the token lasts 24 h. `401 PIN_INVALID`, `429 PIN_RATE_LIMITED` after 10 wrong PINs per IP in 15 min |
| GET | `/scanner/roster` | Scanner only. `{ checkpoint_id, generated_at, runners: [{ runner_id, bib_number, full_name, category_code }] }`: everyone on this checkpoint's course, so the phone can show names offline. `401 SCANNER_AUTH_REQUIRED` |
| GET | `/scanner/devices` | Admin only. `[{ device_id, checkpoint_id, checkpoint_name, category_codes, first_seen_at, last_seen_at, scans_uploaded, clock_offset_s, clock_flagged }]`: every scanner phone, phones whose clock is off by more than 2 minutes first |
| POST | `/scans/batch` | Scanner only (`Authorization: Bearer <token>`), for its own checkpoint (`403 WRONG_CHECKPOINT` otherwise). `{ device_id, checkpoint_id, sent_at, scans: [{ client_id, qr_token, scanned_at, entry: "qr"\|"manual" }] }` (at most 500 scans; for `manual`, `qr_token` is the typed bib; `sent_at` is the phone's clock at upload, used to measure clock drift). Returns `{ results: [{ client_id, status: "accepted"\|"duplicate"\|"invalid", bib_number?, reason? }] }`. `accepted`: saved, or it replaced a later scan of that runner here (the earliest clock-corrected time wins). `duplicate`: already saved (a retry or a later re-scan): treat as done. `invalid` with `reason`: `bad_qr` (edited or damaged code), `unknown_bib`, `wrong_course` (the runner's race doesn't pass this checkpoint) |

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
| POST | `/gps/positions` | Gateway only, authenticated with the `X-Gateway-Secret` header. `{ positions: [{ device_id, lat, lng, accuracy_m?, battery_pct?, recorded_at }] }` | `202`. Unknown or unassigned devices are ignored. Points more than 200 m from the route are stored but not shown. Points are queued and saved by the GPS writer within a second or two; the response only counts what was queued. The secret can also be sent as `?secret=` |
| POST | `/gps/traccar` | Gateway only (same secret). Traccar's own JSON forwarding (`forward.type=json`), one position per request: `{ position: { latitude, longitude, accuracy?, fixTime, attributes: { batteryLevel? } }, device: { uniqueId } }`. Returns `202 { accepted: 0 or 1 }` |
| GET | `/positions?category=` | | `{ updated_at, runners: [{ bib_number, category_code, gender, lat, lng, distance_km, is_stale }] }`. Latest point for every runner on course, refreshed every 5 s and served from cache. Runners who finished or are DNF are left out. Each dot is drawn on the course line at the runner's smoothed distance |
| GET | `/stream/positions?bib=` | | Server-Sent Events for one runner. `event: position` with data `{ bib_number, ...live_position }`, sent straight away with the current position (if any), then on every new fix. `404 RUNNER_NOT_FOUND`. Heartbeat every 15 s |
| GET | `/admin/trackers?status=` | | `[{ id, device_id, label, status: "available"\|"assigned"\|"returned"\|"lost", bib_number?, battery_pct?, last_seen_at? }]`. Admin only |
| POST | `/admin/trackers` | `{ device_id, label }` | `201` tracker. Admin only. `409 TRACKER_EXISTS` |
| PATCH | `/admin/trackers/{id}` | `{ label?, status? }` | tracker. Admin only |
| POST | `/kit/login` | `{ pin, device_id }` (the 6-digit `KIT_PIN`) | `{ token, expires_at }`, valid 24 h; send as `Authorization: Bearer <token>` to the kit endpoints. `401 PIN_INVALID`, `429 PIN_RATE_LIMITED` (shared with the scanner PIN limit) |
| POST | `/kit/assign` | `{ qr_token \| bib_number, tracker_label }`: exactly one of the scanned QR or a typed bib (damaged QR; check ID). `tracker_label` may be `TRK-0031`, `31` or the tracker's device number | Kit desk only. `{ bib_number, full_name, category_code, tracker_label, already_assigned }` (scanning the same pair again returns `already_assigned: true`). Also records the runner's kit collection. `400 QR_INVALID`, `404 RUNNER_NOT_FOUND` / `TRACKER_NOT_FOUND`, `409 TRACKER_IN_USE` (says who has it), `409 RUNNER_HAS_TRACKER`, `409 TRACKER_LOST` |
| POST | `/kit/return` | `{ tracker_label }` | Kit desk only. `{ bib_number, full_name, tracker_label }`. Sets the tracker to `returned` and takes the runner off the live map. `409 TRACKER_NOT_ASSIGNED` if it isn't out |
| GET | `/kit/outstanding` | | Kit desk only. `{ out, trackers: [{ tracker_label, bib_number, full_name, category_code, race_status, assigned_at }] }`: trackers not returned yet; `race_status: "finished"` ones should be handed back |

Location history is deleted 30 days after the race.

## Phase 0 stub behaviour

While an endpoint is still a stub (Phase 0 to 2), it returns fake data and these inputs trigger each case. Nothing a stub receives is saved.

| Endpoint | How to trigger it |
|---|---|
| `POST /auth/otp/request`, `/auth/otp/verify` | **Real since E3.** In development no SMS is sent and every code is `123456` (`OTP_DEV_CODE`); the message is printed in the API log (`docker compose logs -f api`). To see `OTP_RATE_LIMITED`, request twice within a minute. To see `OTP_TOO_MANY_ATTEMPTS`, enter a wrong code 5 times |
| `POST /registrations`, `GET .../qr.png` | **Real since E4**: runners are saved. To see `PHONE_ALREADY_REGISTERED`, register the same phone twice. Get `category_id` from `GET /categories`. Registered runners don't appear in search or results until B3 and E9 |
| `GET /categories` | Already real: reads the database (run the seed first). `slots_left` ignores registrations until B3 |
| `GET /results` | **Real since E9**: registered runners, ranked from their scans. Record a gun start (`POST /admin/categories/{id}/gun-start`) to see elapsed times |
| `GET /stream/results` | **Real since E11**: an event for every scan that upload accepts |
| Runner search and detail (until B3) | A simulated race of 240 runners (bibs `F0001`–`F0050`, `H0001`–`H0070`, `T0001`–`T0060`, `R0001`–`R0060`). It starts about 100 minutes in when the API starts and loops every 6.5 hours, so there are always finishers, runners on course, DNFs, runners who never started, stale trackers and runners without one |
| `POST /sponsors/pledges` | Still a stub until B2 (the Paystack side is real since E5). Skips Paystack: `authorization_url` goes straight to `/sponsors/thank-you`. A company name containing "fail" ends `failed`, one containing "pending" stays `pending`, anything else is `paid`. PDF links open a placeholder PDF |
| Admin endpoints | Sign in with `POST /admin/auth/login` (accounts from `scripts/create_admin.py`), or in development send `Authorization: Bearer dev-admin` |
| `POST /gps/positions`, `POST /gps/traccar` | **Real since E13.** Send `X-Gateway-Secret` with the value of `GATEWAY_SECRET` in `apps/api/.env`. Only points from trackers assigned to a runner are saved. `GET /positions` and `/stream/positions` are real since E14: they show registered runners wearing an assigned tracker |
| `/kit/*` | **Real since E15.** Log in with `KIT_PIN` (development: `246810`). Trackers must exist in the `trackers` table (B5 adds the admin and CSV import) |
| `POST /scans/batch` | **Real since E8**: scans are saved for registered runners only (fake-race bibs are `invalid`) |
