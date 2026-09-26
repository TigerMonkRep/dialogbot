/** Temporary preview gate. Server-only: read from process.env, never NEXT_PUBLIC_.
 *
 * PREVIEW_GATE               → ON BY DEFAULT: "/" and "/signup" require the preview cookie (or a session),
 *                              so P00 is the first page while the platform is being built. "off" opens them.
 * PREVIEW_ACCESS_CODES       → comma-separated invitation codes (case-insensitive).
 * PREVIEW_COOKIE_SECRET      → ≥ 32 chars; signs the cookie. Rotating it locks everyone out again.
 *
 * Fails closed: gate on without a valid secret or codes means no code unlocks anything.
 * Uses Web Crypto so it runs in the proxy as well as in route handlers. */
export const PREVIEW_COOKIE = "db_preview";
export const PREVIEW_MAX_AGE = 60 * 60 * 24 * 30;
const PAYLOAD = "dialogbot-preview-v1";

export const gateEnabled = () => process.env.PREVIEW_GATE !== "off";
const secret = () => {
  const s = process.env.PREVIEW_COOKIE_SECRET ?? "";
  return s.length >= 32 ? s : null;
};
export const normaliseCode = (c: string) => c.trim().toUpperCase().replace(/\s+/g, "");
export const accessCodes = () => (process.env.PREVIEW_ACCESS_CODES ?? "").split(",").map(normaliseCode).filter((c) => c.length >= 8);

const b64url = (buf: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function hmac(key: string, data: string): Promise<string> {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(data)));
}

/** Constant-time string comparison (both inputs are short). */
export function safeEqual(a: string, b: string): boolean {
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0;
}

export async function cookieValue(): Promise<string | null> {
  const s = secret();
  return s ? `v1.${await hmac(s, PAYLOAD)}` : null;
}

export async function cookieValid(value: string | undefined): Promise<boolean> {
  const expected = await cookieValue();
  return Boolean(value && expected && safeEqual(value, expected));
}

export function codeValid(code: string): boolean {
  if (!secret()) return false;
  const c = normaliseCode(code);
  // Check every code so timing does not reveal how many exist or which one matched.
  return accessCodes().reduce((ok, known) => safeEqual(c, known) || ok, false);
}
