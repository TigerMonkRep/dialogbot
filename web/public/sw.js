/* Dialogbot Privat service worker – registered from the /privat pages with scope /privat/ (src/lib/sw-register.ts).
 *
 *  App shell + offline (same module as sw-app.js, kept standalone on purpose):
 *   - /_next/static/*            cache-first (hashed, immutable)
 *   - /icons/*, /fonts/*, /brand/* stale-while-revalidate
 *   - HTML navigations           network only (3 s timeout), then /privat/offline. Pages behind the login are NEVER
 *                                 cached (they carry customer data; the server sends no-store) – F-M2-15-X23
 *   - /api/*                     never touched (and nothing but GET is)
 *  Update flow: a new version does NOT skipWaiting on install; it tells the open pages {type:"ready"} and waits
 *  until one of them answers {type:"skipWaiting"} (the «Ny version klar – Opdater» toast in sw-update.tsx).
 *  Push: payload {title, body, url, tag}; a click focuses the app on `url` (default /privat/dag).
 *
 *  The VERSION line is rewritten by scripts/sw-version.mjs (npm prebuild). */
const VERSION = "ed90daf87d";
const AUDIENCE = "privat";
const SCOPE = "/privat/";
const HOME = "/privat/dag";
const OFFLINE_URL = "/privat/offline";
const CACHE = `dialogbot-${AUDIENCE}-v${VERSION}`;
const NAV_TIMEOUT_MS = 3000;
const ICON = "/icons/privat-icon-192.png";
const BADGE = "/icons/badge-96.png";
const DEFAULT_PUSH_URL = "/privat/dag";

/* ───────────────────────── shared caching module (same in sw-app.js) ───────────────────────── */
const inScope = (path) => path === HOME || path.startsWith(SCOPE);
const isStatic = (path) => path.startsWith("/_next/static/");
const isAsset = (path) => path.startsWith("/icons/") || path.startsWith("/fonts/") || path.startsWith("/brand/") || /\.(woff2?|ttf|otf)$/.test(path);
const cacheable = (res) => !!res && res.ok && !res.redirected && (res.type === "basic" || res.type === "default");

/** The offline page and the scripts/styles it needs, so it renders (and its «Prøv igen» works) without the net.
 *  Behind the login the request may be answered with a redirect – then it is skipped and tried again on the next
 *  successful navigation (see ensureOffline). */
async function precacheOffline(cache) {
  const res = await fetch(OFFLINE_URL, { credentials: "same-origin", cache: "no-store" }).catch(() => null);
  if (!cacheable(res) || !/text\/html/.test(res.headers.get("content-type") || "")) return false;
  const html = await res.clone().text();
  await cache.put(OFFLINE_URL, res);
  const urls = new Set();
  for (const m of html.matchAll(/(?:src|href)="([^"]*\/_next\/static\/[^"]+)"/g)) urls.add(m[1].replace(/&amp;/g, "&"));
  for (const m of html.matchAll(/"(\/_next\/static\/[^"]+\.(?:js|css))"/g)) urls.add(m[1]);
  await Promise.all([...urls].map(async (u) => {
    const url = new URL(u, self.location.origin);
    if (url.origin !== self.location.origin || (await cache.match(url.href))) return;
    const r = await fetch(url.href, { credentials: "same-origin" }).catch(() => null);
    if (cacheable(r)) await cache.put(url.href, r);
  }));
  return true;
}
let offlineReady = false;
async function ensureOffline() {
  if (offlineReady) return;
  const cache = await caches.open(CACHE);
  offlineReady = !!(await cache.match(OFFLINE_URL)) || (await precacheOffline(cache));
}

async function cacheFirst(req) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (cacheable(res)) cache.put(req, res.clone()).catch(() => {});
  return res;
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req);
  const refresh = fetch(req).then((res) => { if (cacheable(res)) cache.put(req, res.clone()).catch(() => {}); return res; }).catch(() => null);
  if (hit) { refresh.catch(() => {}); return hit; }
  const res = await refresh;
  if (res) return res;
  return Response.error();
}

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("timeout")), ms);
    promise.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

/** Removes every cached page in scope except the offline page (logout, 401, and caches left by older versions that
 *  still stored the pages as last seen). */
async function clearPages() {
  for (const name of await caches.keys()) {
    if (!name.startsWith(`dialogbot-${AUDIENCE}-`)) continue;
    const cache = await caches.open(name);
    for (const req of await cache.keys()) { const p = new URL(req.url).pathname; if (inScope(p) && p !== OFFLINE_URL) await cache.delete(req); }
  }
}

/** Navigations: the network wins when it answers within 3 s; otherwise the offline page. The page itself is never
 *  stored: everything in scope sits behind the login (no-store from the server), and a cached copy would show the
 *  previous user's data to the next person on the device. */
async function navigate(req) {
  const cache = await caches.open(CACHE);
  try {
    const res = await withTimeout(fetch(req), NAV_TIMEOUT_MS);
    if (cacheable(res) && /text\/html/.test(res.headers.get("content-type") || "")) ensureOffline().catch(() => {});
    return res;
  } catch {
    const offline = await cache.match(OFFLINE_URL);
    if (offline) return offline;
    return new Response("<!doctype html><meta charset=utf-8><title>Offline</title><p>Ingen forbindelse.</p>", { status: 503, headers: { "content-type": "text/html; charset=utf-8" } });
  }
}

async function notifyClients(msg) {
  const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  for (const c of all) c.postMessage(msg);
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    offlineReady = await precacheOffline(cache).catch(() => false);
    // An older version is still in charge: the pages get the toast and decide when to switch.
    if (self.registration.active) await notifyClients({ type: "ready", version: VERSION, audience: AUDIENCE });
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((n) => n.startsWith(`dialogbot-${AUDIENCE}-`) && n !== CACHE).map((n) => caches.delete(n)));
    await clearPages().catch(() => {});
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  const type = event.data && event.data.type;
  if (type === "skipWaiting") self.skipWaiting();
  if (type === "clearPages") event.waitUntil(clearPages());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const path = url.pathname;
  if (path.startsWith("/api/")) return;
  if (req.mode === "navigate") { if (inScope(path)) event.respondWith(navigate(req)); return; }
  if (isStatic(path)) { event.respondWith(cacheFirst(req)); return; }
  if (isAsset(path)) { event.respondWith(staleWhileRevalidate(req)); return; }
});
/* ───────────────────────── end shared caching module ───────────────────────── */

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data ? event.data.text() : "" }; }
  const title = data.title || "Dialogbot";
  const url = data.url || DEFAULT_PUSH_URL;
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || "",
    icon: ICON,
    badge: BADGE,
    tag: data.tag || undefined,
    renotify: !!data.tag,
    data: { url },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || DEFAULT_PUSH_URL, self.location.origin).href;
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) {
      if (c.url === url && "focus" in c) return c.focus();
    }
    for (const c of all) {
      if (inScope(new URL(c.url).pathname) && "navigate" in c) { await c.navigate(url); return c.focus(); }
    }
    return self.clients.openWindow(url);
  })());
});
