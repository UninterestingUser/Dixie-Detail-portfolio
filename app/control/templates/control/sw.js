// The control app's service worker: it lets Chrome install the app and shows
// a "can't reach the control app" page when the server is out of reach, such
// as when Tailscale is off. It keeps no customer data: only the offline page
// is cached, and every other page always comes from the server.
const CACHE = "dixie-offline-v1";
const OFFLINE = "{% url 'offline' %}";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add(OFFLINE)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE)));
  }
});
