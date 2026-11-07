"use client";
/** Service-worker registration for the two apps – one worker per audience, each limited to its own scope:
 *    Erhverv  /sw-app.js  scope /app/
 *    Privat   /sw.js      scope /privat/
 *  Both shells call `watchSwUpdates`, which registers the worker and reports when a new version is installed and
 *  waiting; the toast (components/sw-update.tsx) then asks the waiting worker to take over, and the page reloads once
 *  the new worker controls it. Push (lib/push.ts, lib/privat/push.ts) reuses `registerSw`. */

export type SwAudience = "erhverv" | "privat";
export const SW: Record<SwAudience, { url: string; scope: string }> = {
  erhverv: { url: "/sw-app.js", scope: "/app/" },
  privat: { url: "/sw.js", scope: "/privat/" },
};

export function swSupported(): boolean {
  return typeof navigator !== "undefined" && "serviceWorker" in navigator && typeof window !== "undefined" && window.isSecureContext;
}

const registrations: Partial<Record<SwAudience, Promise<ServiceWorkerRegistration | null>>> = {};

/** Register (idempotent per audience) – the browser ignores a repeated register of the same script and scope. */
export function registerSw(audience: SwAudience): Promise<ServiceWorkerRegistration | null> {
  if (!swSupported()) return Promise.resolve(null);
  const cached = registrations[audience];
  if (cached) return cached;
  const { url, scope } = SW[audience];
  const p = navigator.serviceWorker.register(url, { scope, updateViaCache: "none" }).catch(() => null);
  registrations[audience] = p;
  return p;
}

export function getSwRegistration(audience: SwAudience): Promise<ServiceWorkerRegistration | undefined> {
  if (!swSupported()) return Promise.resolve(undefined);
  return navigator.serviceWorker.getRegistration(SW[audience].scope).catch(() => undefined);
}

/** Calls `onReady(apply)` once a new worker is installed and waiting. `apply()` asks it to take over; the page reloads
 *  on `controllerchange`. Also re-checks for a new version when the app returns to the foreground. */
export function watchSwUpdates(audience: SwAudience, onReady: (apply: () => void) => void): () => void {
  if (!swSupported()) return () => {};
  let reg: ServiceWorkerRegistration | null = null;
  let announced = false;
  let reloading = false;
  const announce = () => {
    if (announced || !reg?.waiting) return;
    announced = true;
    const waiting = reg.waiting;
    onReady(() => { waiting.postMessage({ type: "skipWaiting" }); });
  };
  const onMessage = (e: MessageEvent) => { if (e.data?.type === "ready") void registerSw(audience).then(() => announce()); };
  const onControllerChange = () => {
    // Only reload when a worker was already in charge – the very first activation must not refresh the page.
    if (reloading || !hadController) return;
    reloading = true;
    window.location.reload();
  };
  const onVisible = () => { if (document.visibilityState === "visible") reg?.update().catch(() => {}); };
  const hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.addEventListener("message", onMessage);
  navigator.serviceWorker.addEventListener("controllerchange", onControllerChange);
  document.addEventListener("visibilitychange", onVisible);
  void registerSw(audience).then((r) => {
    if (!r) return;
    reg = r;
    if (r.waiting && navigator.serviceWorker.controller) announce();
    r.addEventListener("updatefound", () => {
      const w = r.installing;
      if (!w) return;
      w.addEventListener("statechange", () => { if (w.state === "installed" && navigator.serviceWorker.controller) announce(); });
    });
  });
  return () => {
    navigator.serviceWorker.removeEventListener("message", onMessage);
    navigator.serviceWorker.removeEventListener("controllerchange", onControllerChange);
    document.removeEventListener("visibilitychange", onVisible);
  };
}
