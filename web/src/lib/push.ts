"use client";
/** Web Push for the business app (Erhverv): new calls, bookings and messages for you. Mirrors lib/privat/push.ts.
 *
 *  Permission is asked only after a tap on the permission card (first visit to Opkald) – never on login. On iPhone,
 *  push only works from the home-screen app (iOS 16.4+), so outside it the install step comes first.
 *
 *  Backend (same push module as Privat, see the backend's push router):
 *    GET    /api/v1/push/public-key            → { public_key }   (falls back to /privat/push/public-key – same VAPID key)
 *    POST   /api/v1/push/subscriptions         { endpoint, keys: { p256dh, auth }, audience: "erhverv", workspace_id }
 *    DELETE /api/v1/push/subscriptions         { endpoint }
 *  All reached through the BFF as /api/backend/… (lib/client.ts). NEXT_PUBLIC_VAPID_PUBLIC_KEY, when set, skips the
 *  key request. */
import { api, type ApiError } from "@/lib/client";
import { getSwRegistration, registerSw } from "@/lib/sw-register";

export const SW_SCOPE = "/app/";
const ASKED_KEY = "dialogbot-erhverv-push-asked";

export function isIos(ua: string): boolean {
  return /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && typeof navigator !== "undefined" && navigator.maxTouchPoints > 1);
}
export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (navigator as Navigator & { standalone?: boolean }).standalone === true || window.matchMedia?.("(display-mode: standalone)").matches === true;
}
/** iPhone/iPad Safari outside the home-screen app: «Del → Føj til hjemmeskærm» has to come first. */
export function needsHomeScreen(): boolean {
  return typeof navigator !== "undefined" && isIos(navigator.userAgent) && !isStandalone();
}
export function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
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
  const reg = await getSwRegistration("erhverv");
  const sub = await reg?.pushManager.getSubscription().catch(() => null);
  return sub && Notification.permission === "granted" ? "on" : "default";
}

async function publicKey(): Promise<string> {
  const env = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  if (env) return env;
  try { return (await api<{ public_key: string }>("/push/public-key")).public_key; }
  catch (e) {
    if ((e as ApiError).status !== 404) throw e;
    return (await api<{ public_key: string }>("/privat/push/public-key")).public_key;
  }
}

/** Ask (after a tap), subscribe with the API's VAPID key and send the subscription to the API. */
export async function enablePush(workspaceId: string): Promise<PushState> {
  if (needsHomeScreen()) return "ios-home";
  if (!pushSupported()) return "unsupported";
  markAsked();
  const perm = await Notification.requestPermission();
  if (perm !== "granted") return perm === "denied" ? "denied" : "default";
  const reg = await registerSw("erhverv");
  if (!reg) return "unsupported";
  const key = await publicKey();
  const sub = (await reg.pushManager.getSubscription()) ?? await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) as BufferSource });
  const j = sub.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } };
  await api("/push/subscriptions", { method: "POST", body: JSON.stringify({ endpoint: j.endpoint ?? sub.endpoint, keys: { p256dh: j.keys?.p256dh ?? "", auth: j.keys?.auth ?? "" }, audience: "erhverv", workspace_id: workspaceId }) });
  return "on";
}

export async function disablePush(): Promise<void> {
  const reg = await getSwRegistration("erhverv");
  const sub = await reg?.pushManager.getSubscription().catch(() => null);
  if (sub) {
    await api("/push/subscriptions", { method: "DELETE", body: JSON.stringify({ endpoint: sub.endpoint }) }).catch(() => {});
    await sub.unsubscribe().catch(() => false);
  }
}

/** The Opkald page asks once; «Ikke nu» counts as asked (Konto can always turn it on). */
export function alreadyAsked(): boolean {
  try { return localStorage.getItem(ASKED_KEY) === "1"; } catch { return false; }
}
export function markAsked(): void {
  try { localStorage.setItem(ASKED_KEY, "1"); } catch { /* optional */ }
}
