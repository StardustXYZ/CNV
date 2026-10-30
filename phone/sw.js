// Service worker: CNV opens even without connection, with the last data downloaded.
// __BUILD__ is replaced at every build, so phones get the new app after an update.
const CACHE = "cnv-__BUILD__";
const SHELL = ["./", "index.html", "app.js", "style.css", "phone.css", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png"];
const POSTERS = "cnv-posters";
// The last data.json has its own cache, kept across app updates: the daily build
// replaces CACHE, and with it the copy that lets CNV open without connection.
const DATA = "cnv-data";

self.addEventListener("install", (event) => {
    event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(keys.filter((k) => ![CACHE, POSTERS, DATA].includes(k)).map((k) => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);
    if (event.request.method !== "GET") return;

    if (url.pathname.endsWith("data.json")) {
        // Fresh data when online, the last saved copy when offline (marked for the page)
        event.respondWith(
            fetch(event.request)
                .then((resp) => {
                    if (resp.ok) {
                        const copy = resp.clone();
                        event.waitUntil(caches.open(DATA).then((cache) => cache.put(url.pathname, copy)));
                    }
                    return resp;
                })
                .catch(() => caches.open(DATA)
                    .then((cache) => cache.match(url.pathname))
                    .then((saved) => saved && new Response(saved.body, {
                        headers: { "Content-Type": "application/json", "X-CNV-Offline": "1" },
                    })))
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
