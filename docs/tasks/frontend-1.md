# Frontend 1: Registration and Sponsor Screens (10%)

You build what runners and sponsors see when they sign up or pay. Runners will mostly use cheap Android phones on slow data, so design for a **375px screen first** and keep pages light.

## Before you start

- Learn the basics:
  - The [Next.js Learn course](https://nextjs.org/learn), chapters on App Router, pages and forms.
  - react-hook-form + zod: how to validate a form.
- Run the project locally (see the root README) and open http://localhost:3000.
- Read `docs/api-contract.md`, sections *Auth and registration*, *Categories* and *Sponsors*.
- Call the API **only** through `apps/web/lib/api.ts`, which is generated and typed. Never write `fetch` URLs by hand.

## Where your code lives

```
apps/web/app/register/            # F1.1, F1.2, F1.3
apps/web/app/sponsors/            # F1.4
apps/web/components/register/     # your form components
apps/web/components/sponsors/
```

Don't edit `lib/api.ts`, `app/scanner/` or anything in `apps/api/`.

---

## F1.1: Registration form (4 pts)

A multi-step form at `/register`:

1. **Your details:** first name, last name, gender, date of birth, email (optional), phone (Nigerian format; accept `080…` and convert it to `+23480…`).
2. **Category:** cards loaded from `GET /categories`, showing name, distance and "X slots left". Disable full categories and label them "Full".
3. **Emergency contact:** name and phone.
4. **Review:** a summary with Edit buttons, then Continue, which goes to phone verification (F1.2).

**Acceptance criteria**
- [ ] Zod validation on every field, with clear error messages under each field.
- [ ] Runner must be at least 18 for the Full and Half marathon (age on race day). Show the reason if not.
- [ ] Back and Next keep entered data; refreshing the page doesn't lose it (sessionStorage).
- [ ] Loading skeleton while categories load, and a retry button if the request fails.
- [ ] Usable at 375px, with no horizontal scroll.

## F1.2: Phone OTP screen (2 pts)

**Acceptance criteria**
- [ ] On arrival, call `POST /auth/otp/request` and show "Code sent to +234 80* *** **12".
- [ ] 6-digit input with a numeric keyboard on mobile (`inputMode="numeric"`, `autoComplete="one-time-code"`).
- [ ] Resend button disabled with a 60 s countdown. Show a friendly message on `429`.
- [ ] On a valid code, call `POST /auth/otp/verify`, then `POST /registrations` with the form data and `verification_token`.
- [ ] Handle the `OTP_INVALID`, `OTP_EXPIRED`, `PHONE_ALREADY_REGISTERED` and `CATEGORY_FULL` errors (the last one sends the runner back to step 2).

## F1.3: Confirmation page (2 pts)

**Acceptance criteria**
- [ ] Shows the name, category, a large **bib number**, and the QR image from `qr_png_url`.
- [ ] "Download QR" button that saves the PNG, and a print-friendly layout (`@media print`).
- [ ] Short instructions: "Bring this QR code to bib collection".
- [ ] Opening the page directly without registering redirects to `/register`.

## F1.4: Sponsor pages (2 pts)

1. `/sponsors`: tier cards from `GET /sponsor-tiers` showing name, price in ₦ (convert from kobo, e.g. `₦5,000,000`) and benefit list, plus a "Custom amount" card.
2. `/sponsors/pledge?tier=<id>`: form with company name, contact name, email, phone and website (optional). The custom amount field appears only when no tier is chosen (minimum ₦10,000).
3. Submit to `POST /sponsors/pledges`, then redirect the browser to `authorization_url` (Paystack).
4. `/sponsors/thank-you?reference=…`: poll `GET /sponsors/pledges/{reference}` every 3 s, for at most 1 min, until the status is no longer `pending`. Show:
   - **Paid:** a thank-you message and a "Download receipt" link.
   - **Failed:** a "Try again" link.
   - **Still pending:** "We'll email your receipt."

**Acceptance criteria**
- [ ] Money is always shown with `Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' })`.
- [ ] Never mark anything as paid on the frontend. Only show what the API returns.
- [ ] The "Download invoice" link (`invoice_pdf_url`) is visible before payment, for sponsors who pay by bank transfer.

---

## Ask Lead when…

- An API response doesn't match the contract.
- You need a new field or endpoint.
- You're stuck for more than 2 hours.
