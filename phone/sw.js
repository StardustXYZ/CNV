// Service worker: CNV opens even without connection, with the last data downloaded.
// __BUILD__ is replaced at every build, so phones get the new app after an update.
const CACHE = "cnv-__BUILD__";
const SHELL = ["./", "index.html", "app.js", "style.css", "phone.css", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png"];
const POSTERS = "cnv-posters";
// The last data.json has its own cache, kept across app updates: the daily build
// replaces CACHE, and with it the copy that lets CNV open without connection.
const DATA = "cnv-data";

self.addEventListener("install", (event) => {
    // Straight from the server: a copy in the browser's HTTP cache could be the previous version
    const fresh = SHELL.map((url) => new Request(url, { cache: "reload" }));
    event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(fresh)).then(() => self.skipWaiting()));
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

// Notification from GitHub (app/push.py): films new in theaters. The user's V films go
// first, read from the copy of the votes the app keeps here (they never leave the phone).
self.addEventListener("push", (event) => {
    let message = {};
    try { message = event.data ? event.data.json() : {}; } catch { /* not JSON: generic notice */ }
    event.waitUntil(showFilms(message));
});

async function showFilms(message) {
    const votes = await caches.open(DATA)
        .then((cache) => cache.match("votes.json"))
        .then((resp) => (resp ? resp.json() : {}))
        .catch(() => ({}));
    const films = message.films || [];
    const mine = films.filter((f) => votes[f.id] === "V");
    const others = films.filter((f) => votes[f.id] !== "V");
    const names = (list) => list.map((f) => f.title).join(", ");
    let title = message.title || "CNV";
    let body = message.body || "Ci sono novità nei cinema.";
    if (films.length) {
        const extra = message.more ? ` e altri ${message.more}` : "";
        if (mine.length) {
            title = `Ora in sala: ${names(mine)}`;
            body = others.length ? `Nuovi anche: ${names(others)}${extra}` : "Tra i film che vuoi vedere";
        } else {
            title = films.length === 1 && !message.more ? "Nuovo in sala" : "Nuovi film in sala";
            body = names(films) + extra;
        }
    }
    const single = mine.length === 1 ? mine[0] : films.length === 1 ? films[0] : null;
    return self.registration.showNotification(title, {
        body,
        icon: "icons/icon-192.png",
        badge: "icons/icon-192.png",
        tag: "cnv-in-sala",
        data: { url: single ? `./#/film/${single.id}` : "./#/" },
    });
}

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const url = new URL(event.notification.data?.url || "./", self.registration.scope).href;
    event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
        const open = windows.find((w) => w.url.startsWith(self.registration.scope));
        return open ? open.navigate(url).then((w) => w && w.focus()) : self.clients.openWindow(url);
    }));
});
