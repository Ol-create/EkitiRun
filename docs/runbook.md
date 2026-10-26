# Race-Day Runbook

Print this. Keep one copy at the race office and one with the tech lead.

**Golden rule: checkpoint scans are the official timing.** They live on the scanner phones first and upload when they can. GPS, the live map and the website are for spectators; if they fail, the race result does not.

## People and contacts

Fill in before race week.

| Role | Name | Phone | Responsible for |
|---|---|---|---|
| Tech lead (on call all race day) | | | Everything below; decides on fallbacks |
| Backup tech | | | Takes over if the lead is unreachable |
| Race director | | | Gun starts (tells the tech lead the exact times), DNF decisions |
| Race office | | | Admin endpoints, scanner devices list, results questions |
| Checkpoint captains (one per checkpoint) | | | Their scanner phone, the paper backup sheet |
| Kit desk lead | | | Hand-outs and returns, the "still out" list |
| Hosting support | Render, Neon, Vercel status pages and support | | Outages on their side |

## Race-week timeline

| When | What | How |
|---|---|---|
| T-14 days | Full rehearsal on staging (see below) | |
| T-10 days | Load test staging at full size and fix what fails | `Load test` below |
| T-7 days | Bibs printed: `QR_SIGNING_SECRET` is now frozen | Never rotate it after this |
| T-7 days | Checkpoint PINs made and given to captains | `python -m scripts.checkpoint_pins` |
| T-3 days | Scale production up | `docs/deploy.md`, "Race week" |
| T-3 days | Trackers charged, labelled, imported (B5's CSV import) | |
| T-1 day | Preflight passes; demo data removed | `python -m scripts.preflight` |
| T-1 day | Every scanner phone logs in **with signal** at its checkpoint (downloads the runner list, caches the page) | `/scanner` |
| Race morning | Preflight again; dashboards open; gun starts recorded | Below |
| T+1 day | Results exported and checked; scale down | `python -m scripts.export_results` |
| T+30 days | GPS history deleted automatically (nightly job): check it ran | Worker logs |

## Race morning checklist

- [ ] `python -m scripts.preflight` (Render API shell): no FAIL.
- [ ] Open: Render dashboard (API, worker, GPS writer metrics and logs), Neon dashboard, the public leaderboard and live map, `GET /api/v1/scanner/devices` (admin).
- [ ] Every checkpoint phone: logged in, "Online", battery charged, power bank attached, **paper backup sheet** and pen.
- [ ] Kit desk: `/kit` logged in, trackers counted.
- [ ] **Gun starts:** the moment each race starts, record it (or have the race director call it in and record it straight away):
  ```bash
  curl -X POST https://api.<domain>/api/v1/admin/categories/<id>/gun-start \
       -H "Authorization: Bearer <admin token>" -H "Content-Type: application/json" -d '{}'
  ```
  Missed it? Record it afterwards with `{"at": "2027-03-06T06:30:00+01:00"}`: all times recalculate.

## During the race: what to watch

| Signal | Where | Healthy |
|---|---|---|
| Scans arriving | Leaderboard moves; `scanner/devices` `last_seen_at` recent | Every active checkpoint uploads within a minute |
| Phone clocks | `GET /api/v1/scanner/devices` (flagged first) | No `clock_flagged`; if flagged, ask the volunteer to turn on automatic time (their scans are already corrected) |
| GPS | Live map dots moving; GPS writer logs | Few stale dots; writer not reporting errors |
| API | Render metrics | Response times low, no restarts |

## Incident playbooks

### Scanner phone has no signal
Nothing to do: scans are saved on the phone and upload when signal returns. Tell the volunteer to keep scanning and **not to log out or clear the browser**. Move them to better signal at a quiet moment if "Waiting to upload" keeps growing.

### Scanner phone dies, is lost or breaks
1. Volunteer switches to the **paper backup sheet** (bib + time, with a watch synced to the race clock).
2. A spare phone logs in with the same checkpoint PIN and carries on.
3. Scans still on the dead phone upload if it is revived and logged in to the same checkpoint. Paper-sheet times need entering with their written time: see "Known gaps" (typing a bib into a scanner later would record the time it was typed).

### A runner's time is wrong or missing
Check their splits (`/track/<bib>`). A missing checkpoint scan doesn't stop a finish time (the finish scan is what counts). For a missing **finish** scan, take the time from the paper sheet at the finish and have the tech lead add it before results are published (see "Known gaps").

### Runner drops out
Race office marks them: `POST /api/v1/admin/runners/<bib>/dnf` (admin). Undo with `DELETE` on the same URL.

### API down or very slow
1. Check Render: is the API restarting (crash loop)? Read the last logs.
2. Restart: Render dashboard > API > **Manual Deploy > Restart** (or roll back to the previous deploy).
3. Slow under load: add instances (Render > API > Scaling). Scanners keep queuing meanwhile; nothing is lost.
4. Database overloaded (Neon dashboard): raise the compute size.

### Redis down
- Live map, leaderboard cache and live streams stop; scans still save (they go to Postgres) once the API reaches Redis again (the OTP and PIN rate limits need Redis too).
- GPS points sent while Redis is down are lost (the gateway retries a little); timing is unaffected.
- Restart or wait for Render Key Value; then `python -m scripts.preflight`.

### GPS gateway (Traccar) or trackers down
Spectators see estimated positions instead (the map falls back automatically). Timing is unaffected. Restart Traccar; check the trackers' SIM data.

### Website (Vercel) down
The API still works and scanners keep uploading. Publish standings from the API shell: `python -m scripts.export_results` and share the CSVs.

### SMS (Termii) or payments (Paystack) down
Not race-day critical. Registration and sponsorship can wait; check their status pages.

## Known gaps (decide before race day)

- **No screen for entering or correcting a time by hand** (paper-sheet times, a wrong finish time). Today the tech lead inserts or fixes the `scans` row directly in the database. A small admin "add/correct scan" endpoint would make this safer: worth building before the rehearsal.
- **No admin login yet**: admin calls use the development token, which production refuses. Race-office actions (gun start, DNF) need real admin login before race day.

## Manual results fallback

If the system can't produce results by the time they're needed:
1. **Finish line paper sheets** are the record: two volunteers each write bib + finish time for every finisher.
2. If the database is up: `python -m scripts.export_results --out results` gives one CSV per race from the scans it has. Compare the top places with the paper sheets.
3. Prizes are announced from the checked list, not from the website.

## After the race

- [ ] `python -m scripts.export_results` and archive the CSVs.
- [ ] Prize committee checks the top places against the paper sheets.
- [ ] Trackers: `/kit` "still out" list; chase the rest.
- [ ] Scale down (`docs/deploy.md`).
- [ ] 30 days later: confirm GPS history is gone (nightly job in the worker logs; `gps_positions` older than 30 days count = 0).

## Load test (staging, T-10 days)

```bash
# In the staging API shell (or locally with staging's settings):
python -m scripts.demo_race setup --runners 5000 --started-minutes-ago 60
python -m scripts.loadtest_fixtures > loadtest/fixtures.json     # credentials: delete after

# On a strong machine (or several: locust --master / --worker):
cd apps/api && uv sync --group load
uv run --group load locust -f loadtest/locustfile.py --host https://<staging api> \
    --users 5025 --spawn-rate 50 --run-time 15m --headless --processes -1
```

It ends with **LOAD TEST PASS** or **FAIL** (p95 under 500 ms for the leaderboard and map, under 1 s for scans and GPS, under 1% errors). Scale staging until it passes; production gets the same sizes. Afterwards: `python -m scripts.demo_race reset` and delete `fixtures.json`.

## Rehearsal (staging, T-14 days)

A short course with volunteers, phones and about 20 trackers. It is practice for people as much as for software.

- [ ] Kit desk: 20 volunteers collect bibs and trackers (`/kit`), including one damaged QR (typed bib) and one tracker already out.
- [ ] Gun start recorded by the race director's call.
- [ ] Every checkpoint scans with its PIN; one phone goes into airplane mode for 10 minutes, then reconnects.
- [ ] One phone's clock set 3 minutes wrong: it appears flagged in `scanner/devices`, and its runners' times are still right.
- [ ] Live map and leaderboard watched by "spectators" on mobile data.
- [ ] One runner marked DNF; one tracker returned early; all trackers returned at the finish and "still out" reaches 0.
- [ ] Practise one playbook live (e.g. restart the API mid-race: scanners keep queuing, nothing is lost).
- [ ] Results exported and compared with the paper finish sheets.
