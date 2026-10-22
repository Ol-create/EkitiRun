// Service worker for /scanner. Owner: Lead (E7).
// Keeps the scanner page and its code available offline, so a volunteer can
// reload it in airplane mode. Scans themselves live in IndexedDB, not here.
// API calls are never cached: they always go to the network.
const CACHE = "ekitirun-scanner-v1";
const PAGE = "/scanner";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add(PAGE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // The page: try the network (to pick up new versions), fall back to the cached copy.
  if (request.mode === "navigate" && url.pathname.startsWith(PAGE)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          void caches.open(CACHE).then((cache) => cache.put(PAGE, copy));
          return response;
        })
        .catch(() => caches.match(PAGE)),
    );
    return;
  }

  // Next.js build files have content hashes in their names, so cached copies never go stale.
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            const copy = response.clone();
            void caches.open(CACHE).then((cache) => cache.put(request, copy));
            return response;
          }),
      ),
    );
  }
});
