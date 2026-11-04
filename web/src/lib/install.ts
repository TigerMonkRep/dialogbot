"use client";
/** «Download app»: putting Dialogbot on the home screen, as far as each phone allows.
 *
 *  - Android (Chrome, Edge, Samsung Internet): the browser fires `beforeinstallprompt`; we keep that event and
 *    `prompt()` it on the tap – one tap installs the app. Notifications are asked straight after (same origin, same
 *    service worker, so a subscription made here reaches the installed app).
 *  - iPhone/iPad: Apple gives no install API – only Safari's Del → «Føj til hjemmeskærm». The button becomes a short
 *    guide, and web push works once the app is opened from the home screen (iOS 16.4+), where we ask.
 *  - Desktop Chrome/Edge: the same prompt as Android when the browser offers it; otherwise a note to open it on the phone.
 *
 *  The event is captured as early as possible (InstallCapture mounts in the shells); it only fires once per page load. */

type BeforeInstallPromptEvent = Event & { prompt(): Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };

export type Platform = "ios" | "android" | "desktop";
export type InstallState = "installed" | "promptable" | "ios" | "manual";

const PENDING_KEY = "dialogbot-install-notify";
let deferred: BeforeInstallPromptEvent | null = null;
let listening = false;
const listeners = new Set<() => void>();

export function platform(): Platform {
  if (typeof navigator === "undefined") return "desktop";
  const ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1)) return "ios";
  if (/Android/i.test(ua)) return "android";
  return "desktop";
}

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (navigator as Navigator & { standalone?: boolean }).standalone === true || window.matchMedia?.("(display-mode: standalone)").matches === true;
}

/** Start listening for the browser's install prompt (idempotent; call from a client component's effect). */
export function captureInstallPrompt(): void {
  if (listening || typeof window === "undefined") return;
  listening = true;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferred = e as BeforeInstallPromptEvent;
    listeners.forEach((f) => f());
  });
  window.addEventListener("appinstalled", () => { deferred = null; listeners.forEach((f) => f()); });
}

export function onInstallChange(f: () => void): () => void {
  listeners.add(f);
  return () => { listeners.delete(f); };
}

export function installState(): InstallState {
  if (isStandalone()) return "installed";
  if (deferred) return "promptable";
  if (platform() === "ios") return "ios";
  return "manual";
}

/** Show the browser's install sheet. True when the person accepted. */
export async function promptInstall(): Promise<boolean> {
  const ev = deferred;
  if (!ev) return false;
  deferred = null;
  await ev.prompt();
  const { outcome } = await ev.userChoice;
  if (outcome === "accepted") markNotifyPending();
  listeners.forEach((f) => f());
  return outcome === "accepted";
}

/** After an install the installed app asks for notifications on its first open; the flag says it was wanted. */
export function markNotifyPending(): void {
  try { localStorage.setItem(PENDING_KEY, "1"); } catch { /* optional */ }
}
export function takeNotifyPending(): boolean {
  try {
    const v = localStorage.getItem(PENDING_KEY) === "1";
    if (v) localStorage.removeItem(PENDING_KEY);
    return v;
  } catch { return false; }
}
