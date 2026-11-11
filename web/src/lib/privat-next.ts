/** Dialogbot Privat context and its return address (`next`) – one rule for /signup, /login, /verify-email,
 *  /password/forgot and /password/reset (QA F-JP-01..05, F-JP-10). The API has the same rule
 *  (app/modules/identity/privat_context.py) and puts `for=privat&next=…` in the mailed links, so the person returns to
 *  the plan, list or group they came from – also when the mail opens another browser.
 *
 *  `next` counts only as a relative path under /privat, /g/ or /i/: no "//host", no "/\host", no "..", no spaces. */
const PRIVAT_NEXT = /^\/(?:privat(?=$|[/?#])|g\/|i\/)[A-Za-z0-9\-._~/?#[\]@!$&'()*+,;=%:]*$/;

export const PRIVAT_HOME = "/privat/dag";

/** `next` when it is a safe Privat return address, else null. */
export function privatNext(next: string | null | undefined): string | null {
  if (!next || next.length > 512 || next.includes("//") || next.includes("..") || /%2e|%2f|%5c/i.test(next)) return null;
  return PRIVAT_NEXT.test(next) ? next : null;
}

/** A page opened with ?next=<Privat route> (or ?for=privat) is a Privat page: orange frame, Privat words. */
export function isPrivatContext(params: { get(name: string): string | null }): boolean {
  return params.get("for") === "privat" || privatNext(params.get("next")) !== null;
}

/** What the person is on their way to: the trial (landing page, plans), a shared list/group (a free account, no trial
 *  promised – F-JP-05), or somewhere else in Privat. */
export function privatKind(next: string | null): "trial" | "list" | "other" {
  if (!next || next === "/privat" || next.startsWith("/privat?") || next.startsWith("/privat/konto")) return "trial";
  if (next.startsWith("/privat/invitation/") || next.startsWith("/g/") || next.startsWith("/i/")) return "list";
  return "other";
}

/** "&next=…" for a link (empty without a safe `next`). */
export function nextQuery(next: string | null, sep: "?" | "&" = "&"): string {
  const n = privatNext(next);
  return n ? `${sep}next=${encodeURIComponent(n)}` : "";
}
