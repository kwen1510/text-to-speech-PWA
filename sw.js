const APP_CACHE = "kitten-tts-app-cache-v1";
const MODEL_CACHE = "kitten-tts-model-cache-v1";

const APP_SHELL = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./manifest.webmanifest",
  "./icons/icon.svg",
];

const MODEL_HOSTS = new Set([
  "huggingface.co",
  "cdn-lfs.huggingface.co",
  "cas-bridge.xethub.hf.co",
]);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(APP_CACHE)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  if (MODEL_HOSTS.has(url.hostname)) {
    event.respondWith(cacheModelRequest(event.request));
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match("./index.html")),
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request)),
  );
});

async function cacheModelRequest(request) {
  const cache = await caches.open(MODEL_CACHE);
  const cached = await cache.match(request.url);
  if (cached) return cached;

  const response = await fetch(request);
  if (response.ok) {
    await cache.put(request.url, response.clone());
  }
  return response;
}
