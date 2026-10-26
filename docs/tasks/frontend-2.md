# Frontend 2: Public Race-Day Pages (10%)

You build what families and spectators watch during the race: the leaderboard, the runner search, and the live GPS maps. On race day thousands of people may open these pages at once on mobile data, so keep them **fast and light**.

## Before you start

- Learn the basics:
  - The [Next.js Learn course](https://nextjs.org/learn), chapters on App Router and data fetching.
  - [React Leaflet](https://react-leaflet.js.org/) basics: a map, a line and markers.
  - MDN: [Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events).
- Run the project locally and read `docs/api-contract.md`, sections *Categories and runners*, *Race day* and *Live GPS tracking*.
- In Phase 1 the race-day endpoints return **fake data**. Build against it and you'll be ready when the real data arrives in Phase 2.

## Where your code lives

```
apps/web/app/results/                # F2.1
apps/web/app/track/                  # F2.2, F2.3
apps/web/app/live/                   # F2.4
apps/web/components/results/
apps/web/components/track/
apps/web/components/live/
```

Don't edit `lib/api.ts`, `lib/tracking.ts` (Lead's helper, you only *call* it), `app/scanner/`, `app/kit/`, or anything in `apps/api/`.

---

## F2.1: Live leaderboard (4 pts)

Page `/results`.

**Acceptance criteria**
- [ ] Table from `GET /results`: position, bib, name, category, last checkpoint, and time (`h:mm:ss`). Show the finish time once the runner has finished.
- [ ] Filters for category (tabs) and gender (All, M, F), stored in the URL query (`?category=HALF&gender=F`) so the link can be shared.
- [ ] Pagination or "Load more" (50 per page).
- [ ] Live updates: subscribe to `/stream/results` with `EventSource`. On each `scan` event, refetch the current page at most once every 5 s (throttle it, don't refetch on every event).
- [ ] A "Live" indicator dot that turns grey when the connection drops, with auto-reconnect.
- [ ] On mobile, the table becomes stacked cards (no horizontal scroll at 375px).
- [ ] Empty state: "Results will appear once the race starts".

## F2.2: Runner search and detail (3 pts)

Page `/track` (search) and page `/track/[bib]` (detail).

**Acceptance criteria**
- [ ] Search box calling `GET /runners/search?q=` with a 300 ms debounce and at least 2 characters. Each result links to `/track/{bib}`.
- [ ] Detail page shows name, bib, category, status badge (Registered, Running, Finished, DNF), finish time and positions once finished.
- [ ] Splits table: checkpoint, distance, time of day, elapsed time, and **pace per km** (calculate it yourself from distance and elapsed time).
- [ ] The detail page updates on SSE events for **this bib only**.
- [ ] "Share" button using `navigator.share` when available, otherwise copy the link.
- [ ] A 404 page for an unknown bib.

## F2.3: Route map (3 pts)

Add the map to `/track/[bib]`, above the splits table.

**Acceptance criteria**
- [ ] Leaflet map with OpenStreetMap tiles. Load it with `dynamic(..., { ssr: false })`, because Leaflet needs the browser.
- [ ] Draw the route line and the checkpoint markers from `GET /route`. Markers for checkpoints the runner has passed are green, the others grey.
- [ ] Runner marker at the GPS position from `live_position`, moved live by `/stream/positions?bib=` (`EventSource`). Animate the move rather than jumping.
- [ ] Use Lead's `displayPosition(live_position, route, checkpoints, splits, status)` from `lib/tracking.ts`, recalculated every 10 s and on every stream event: it returns the live GPS fix while it's fresh, otherwise an estimate. `source: "gps"` is a solid marker; `source: "estimate"` is a pulsing marker labelled "Estimated position".
- [ ] Finished runners show at the finish line. Runners who haven't started show at the start line.
- [ ] Map height 300px on mobile, 450px on desktop.

## F2.4: Live race map (3 pts)

Page `/live`: every runner on one map.

**Acceptance criteria**
- [ ] Route line and checkpoints from `GET /route`, and a small dot per runner from `GET /positions`, refreshed every 5 s (pause while the tab is hidden).
- [ ] Dot colour by category, with a legend. Stale positions are drawn faded.
- [ ] Category filter, stored in the URL (`?category=FULL`).
- [ ] Tapping a dot shows the bib and links to `/track/{bib}`.
- [ ] Stays smooth with 5,000 dots on a cheap Android phone: draw them on a canvas layer (`L.canvas()` / `preferCanvas`), not as 5,000 DOM markers.

---

## Ask Lead when…

- The fake data doesn't cover a case you need (for example a DNF runner).
- The SSE or map behaves differently from the contract.
- You're stuck for more than 2 hours.
