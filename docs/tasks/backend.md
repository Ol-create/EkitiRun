# Backend: Sponsors and Public Read Endpoints (10%)

You build the FastAPI endpoints for sponsor tiers and pledges, the public runner lookups, and the PDF templates. Lead has already set up the database, migrations and an **example module** (`app/modules/categories/`). Copy its structure for every module you build.

## Before you start

- Learn the basics:
  - The [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/), from "First Steps" through "SQL Databases" and "Testing".
  - The [SQLAlchemy 2.0 ORM quickstart](https://docs.sqlalchemy.org/en/20/orm/quickstart.html).
- Run `docker compose up`, then open http://localhost:8000/docs (Swagger) and try the example endpoints.
- Read `docs/api-contract.md`, sections *Categories and runners* and *Sponsors*. Your responses must match it **exactly**.

## Where your code lives

```
apps/api/app/modules/sponsors/     # B1, B2
apps/api/app/modules/runners/      # B3 (read-only endpoints)
apps/api/app/templates/pdf/        # B4
apps/api/app/modules/trackers/     # B5
apps/api/tests/                    # B4 tests
```

Module layout (copied from `categories/`): `router.py` (endpoints), `schemas.py` (Pydantic), `service.py` (database logic), and `tests/`.

**Do not touch:**
- `app/models/` and `alembic/`: ask Lead if you need a column.
- `app/modules/auth/`, `app/modules/payments/`, `app/modules/scans/`, `app/modules/timing/`, `app/modules/gps/` and `app/modules/kit/`.

---

## B1: Sponsor tiers endpoints (3 pts)

**Acceptance criteria**
- [ ] `GET /sponsor-tiers`: public, ordered by `sort_order`, only active tiers.
- [ ] `POST`, `PATCH` and `DELETE /admin/sponsor-tiers`: protected with Lead's `require_admin` dependency.
- [ ] Validation: name 2–60 characters, `amount_kobo` greater than 0, `benefits` a list of 1–15 non-empty strings.
- [ ] DELETE is a **soft delete** (`is_active = false`), because old pledges still point to the tier.
- [ ] Seed script with Platinum (₦5,000,000), Gold (₦2,000,000) and Silver (₦500,000), each with sample benefits.

## B2: Sponsor pledge endpoint (2 pts)

**Acceptance criteria**
- [ ] `POST /sponsors/pledges` validates that **exactly one** of `tier_id` or `custom_amount_kobo` is sent (custom amount at least 1,000,000 kobo, i.e. ₦10,000), plus the email format and a Nigerian phone number.
- [ ] Creates the `sponsor` and `pledge` rows (status `pending`), then calls Lead's `payments.service.start_checkout(pledge)` and returns its `reference` and `authorization_url`.
- [ ] Enqueues the invoice job with `await enqueue("render_invoice", pledge_id)`.
- [ ] `GET /sponsors/pledges/{reference}` returns the status and receipt URL, and `404` for an unknown reference.
- [ ] You never set the status to `paid`. Only Lead's webhook does that.

## B3: Public runner endpoints (3 pts)

**Acceptance criteria**
- [ ] `GET /categories` adds `slots_left = cap - registered_count` and `is_full`, using one query (no query per category).
- [ ] `GET /runners/search?q=`:
  - If `q` looks like a bib (e.g. `H0123`), match the bib exactly.
  - Otherwise, match the name case-insensitively (`ILIKE`).
  - At most 20 results, and `422` if `q` is shorter than 2 characters.
- [ ] `GET /runners/{bib_number}` returns the shape in the contract, with splits ordered by checkpoint distance. Get splits and positions from `timing.service.get_runner_result(runner_id)`; don't calculate them yourself.
- [ ] **Never** return phone, email, date of birth or emergency contact on these public endpoints. Add a test that checks this.

## B4: PDF templates and tests (2 pts)

**Acceptance criteria**
- [ ] `templates/pdf/invoice.html` and `receipt.html` (Jinja2 + CSS for WeasyPrint). Include:
  - The race logo.
  - Invoice or receipt number.
  - Date.
  - Sponsor company and contact.
  - Tier name or "Custom".
  - Amount in ₦.
  - Organiser bank details (invoice only).
  - "PAID" stamp and the Paystack reference (receipt only).
- [ ] Preview them with Lead's `scripts/render_pdf_preview.py` and attach both PDFs to your PR.
- [ ] pytest coverage for B1–B3:
  - Success cases.
  - Validation errors.
  - Admin protection.
  - Soft delete.
  - Search by name and by bib.
  - The private-fields test.

## B5: Tracker inventory endpoints (2 pts)

Code lives in `apps/api/app/modules/trackers/`. Lead owns the GPS ingestion and kit endpoints; you build the admin inventory.

**Acceptance criteria**
- [ ] `GET /admin/trackers?status=` lists trackers with the assigned bib, battery and last-seen time, filterable by status.
- [ ] `POST /admin/trackers` adds a tracker (`409 TRACKER_EXISTS` for a duplicate `device_id` or `label`), and `PATCH /admin/trackers/{id}` changes the label or marks it `lost`.
- [ ] All three are protected with `require_admin`.
- [ ] A CSV import script (`scripts/import_trackers.py`) so the organisers can load hundreds of trackers from the supplier's list.
- [ ] pytest coverage: success, duplicates, admin protection, status filter.

---

## Ask Lead when…

- You need a database column or a new table.
- A Lead service you call (`start_checkout`, `get_runner_result`, `enqueue`) doesn't behave as described.
- You're stuck for more than 2 hours.
