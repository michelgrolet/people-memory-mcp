// Minimal service worker — only exists so Chrome/Android considers this
// app installable (manifest + a fetch handler). No caching: person data is
// live from Supabase and must never be served stale.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});
