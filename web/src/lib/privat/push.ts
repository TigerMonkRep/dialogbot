"use client";
/** Web Push for Dialogbot Privat. Permission is asked only at the right moments (first reminder, first call approval,
 *  or Konto → Notifikationer). On iPhone, push only works from the home-screen app (iOS 16.4+), so a short guide comes first. */
import type { PrivatApi } from "./api";

export const SW_URL = "/sw.js";
export const SW_SCOPE = "/privat/";
const ASKED_KEY = "dialogbot-privat-push-asked";

export function isIos(ua: string): boolean {
  return /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && typeof navigator !== "undefined" && navigator.maxTouchPoints > 1);
}
export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (navigator as Navigator & { standalone?: boolean }).standalone === true || window.matchMedia?.("(display-mode: standalone)").matches === true;
}
/** iPhone/iPad Safari outside the home-screen app: show «Del → Føj til hjemmeskærm» before asking. */
export function needsHomeScreen(): boolean {
  return typeof navigator !== "undefined" && isIos(navigator.userAgent) && !isStandalone();
}
export function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export async function registerSw(): Promise<ServiceWorkerRegistration | null> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return null;
  try { return await navigator.serviceWorker.register(SW_URL, { scope: SW_SCOPE }); } catch { return null; }
}

function keyBytes(base64url: string): Uint8Array {
  const pad = "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob((base64url + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export type PushState = "unsupported" | "ios-home" | "default" | "denied" | "on";

export async function currentPushState(): Promise<PushState> {
  if (needsHomeScreen()) return "ios-home";
  if (!pushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  const reg = await navigator.serviceWorker.getRegistration(SW_SCOPE).catch(() => undefined);
  const sub = await reg?.pushManager.getSubscription().catch(() => null);
  return sub && Notification.permission === "granted" ? "on" : "default";
}

/** Ask (after a tap), subscribe with the API's VAPID key and send the subscription to the API. */
export async function enablePush(api: PrivatApi): Promise<PushState> {
  if (needsHomeScreen()) return "ios-home";
  if (!pushSupported()) return "unsupported";
  try { localStorage.setItem(ASKED_KEY, "1"); } catch { /* ignore */ }
  const perm = await Notification.requestPermission();
  if (perm !== "granted") return perm === "denied" ? "denied" : "default";
  const reg = await registerSw();
  if (!reg) return "unsupported";
  const { public_key } = await api.pushPublicKey();
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(public_key) as BufferSource });
  const j = sub.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } };
  await api.pushSubscribe({ endpoint: j.endpoint ?? sub.endpoint, keys: { p256dh: j.keys?.p256dh ?? "", auth: j.keys?.auth ?? "" } });
  return "on";
}

export async function disablePush(api: PrivatApi): Promise<void> {
  const reg = await navigator.serviceWorker?.getRegistration(SW_SCOPE).catch(() => undefined);
  const sub = await reg?.pushManager.getSubscription().catch(() => null);
  if (sub) { await api.pushUnsubscribe(sub.endpoint).catch(() => {}); await sub.unsubscribe().catch(() => false); }
}

/** The first reminder / first call approval asks once; later ones do not (Konto always can). */
export function alreadyAsked(): boolean {
  try { return localStorage.getItem(ASKED_KEY) === "1"; } catch { return false; }
}
