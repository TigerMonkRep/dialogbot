const BASE = "https://next.invalid";

/** Accept only same-origin relative paths for ?next= redirects.
 *  Browsers and the URL parser drop tab/CR/LF and treat "\" like "/", so "/\t/evil.example" becomes "//evil.example"
 *  (QA: open redirect via /login?next=/%09/evil.example). Refuse every control character, whitespace and backslash,
 *  and require that the path resolves to our own origin; "%2e%2e" is refused like ".." would be by the browser. */
export function safeNext(next: string | null | undefined, fallback = "/app"): string {
  if (!next || next.length > 2048 || !next.startsWith("/") || next.startsWith("//")) return fallback;
  // eslint-disable-next-line no-control-regex
  if (/[\u0000- \u007f\\]/.test(next) || /%2e%2e|%2f|%5c/i.test(next)) return fallback;
  try {
    const u = new URL(next, BASE);
    if (u.origin !== BASE) return fallback;
    return u.pathname + u.search + u.hash;
  } catch {
    return fallback;
  }
}
