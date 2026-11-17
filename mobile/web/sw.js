// The old web version of CNV (before the Flutter app) installed a service worker with this
// name, which kept serving its own pages from the browser's cache. When the browser checks
// for an update it finds this one instead: it empties those caches, removes itself and
// reloads the open pages, which then get the Flutter app. The Flutter app installs no
// service worker of its own (flutter build web --pwa-strategy=none).
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
    event.waitUntil((async () => {
        const keys = await caches.keys();
        await Promise.all(keys.map((key) => caches.delete(key)));
        await self.registration.unregister();
        const pages = await self.clients.matchAll({ type: "window" });
        for (const page of pages) page.navigate(page.url);
    })());
});
