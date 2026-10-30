// Service worker: CNV opens even without connection, with the last data downloaded.
// __BUILD__ is replaced at every build, so phones get the new app after an update.
const CACHE = "cnv-__BUILD__";
const SHELL = ["./", "index.html", "app.js", "style.css", "phone.css", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png"];
const POSTERS = "cnv-posters";

self.addEventListener("install", (event) => {
    event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(keys.filter((k) => k !== CACHE && k !== POSTERS).map((k) => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);
    if (event.request.method !== "GET") return;

    if (url.pathname.endsWith("data.json")) {
        // Fresh data when online, the last saved copy when offline
        event.respondWith(
            fetch(event.request)
                .then((resp) => {
                    const copy = resp.clone();
                    caches.open(CACHE).then((cache) => cache.put(event.request, copy));
                    return resp;
                })
                .catch(() => caches.match(event.request))
        );
        return;
    }
    if (url.hostname === "image.tmdb.org") {
        event.respondWith(
            caches.open(POSTERS).then((cache) =>
                cache.match(event.request).then((hit) => hit || fetch(event.request).then((resp) => {
                    cache.put(event.request, resp.clone());
                    return resp;
                }))
            )
        );
        return;
    }
    if (url.origin === self.location.origin) {
        event.respondWith(caches.match(event.request).then((hit) => hit || fetch(event.request)));
    }
});
