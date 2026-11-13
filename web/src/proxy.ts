import { NextRequest, NextResponse } from "next/server";
import { PROTECTED_PATH_HEADER, SESSION_COOKIE } from "@/lib/config";
import { PREVIEW_COOKIE, cookieValid, gateEnabled } from "@/lib/preview-gate";
import { safeNext } from "@/lib/safe-next";
import { privatKind, privatNext } from "@/lib/privat-next";
import {
  COUNTRY_HEADER, DEFAULT_LOCALE, LOCALE_COOKIE, LOCALE_HEADER, LOCALES, fromAcceptLanguage, fromCountry, isLocale, isPublicPage, type Locale,
} from "@/i18n/config";

// Public pages hidden behind the temporary preview page while PREVIEW_GATE=on.
const GATED = new Set(["/", "/erhverv", "/proev", "/byggevejledning", "/signup"]);

/** The door a visitor chose. Set (1 year, lax, readable by the page) when they open /erhverv or /privat (full loads here, client navigations via <AudienceMemory/>) – also when
 *  they click a Trin-2 panel on the entry page, since the panels link to those two pages. While it is set, "/" sends
 *  them straight to their door. "/?aud=reset" clears it and shows the entry page again (bots and first-time visitors
 *  have no cookie and always see the entry). Not a secret, not personal data: one of two words. */
export const AUDIENCE_COOKIE = "db_aud";
const AUDIENCES = new Set(["erhverv", "privat"]);
const AUDIENCE_RESET = "reset";

// The main domain. Every other host we own (dialogbot.dk, www.*) is sent here with the path kept.
const MAIN_HOST = "dialogbot.app";
const OLD_HOSTS = new Set(["dialogbot.dk", "www.dialogbot.dk", "www.dialogbot.app"]);

function splitLocale(pathname: string): { locale: Locale | null; rest: string } {
  const seg = pathname.split("/")[1] ?? "";
  if (isLocale(seg)) return { locale: seg, rest: pathname.slice(seg.length + 1) || "/" };
  return { locale: null, rest: pathname };
}

function preferred(req: NextRequest): Locale {
  const c = req.cookies.get(LOCALE_COOKIE)?.value;
  if (isLocale(c)) return c;
  return fromCountry(req.headers.get(COUNTRY_HEADER)) ?? fromAcceptLanguage(req.headers.get("accept-language")) ?? DEFAULT_LOCALE;
}

function remember(res: NextResponse, locale: Locale): NextResponse {
  res.cookies.set(LOCALE_COOKIE, locale, { path: "/", maxAge: 60 * 60 * 24 * 365, sameSite: "lax" });
  return res;
}

/** A link prefetch is not a visit: the entry page prefetches both doors, and the last prefetch to land must not become
 *  the remembered audience. Next strips its `rsc`/`next-router-prefetch` headers before the proxy runs, so the only
 *  reliable signal is the browser's own: a full document load has `sec-fetch-dest: document`; prefetches and client
 *  navigations are `empty`. Those are remembered by <AudienceMemory/> on the page itself, which only runs once the page
 *  is actually shown. Requests without the header (bots, curl) count as visits. */
function isDocumentLoad(req: NextRequest): boolean {
  const dest = req.headers.get("sec-fetch-dest");
  return dest === null || dest === "document";
}

function rememberAudience(req: NextRequest, res: NextResponse, audience: "erhverv" | "privat"): NextResponse {
  if (!isDocumentLoad(req)) return res;
  res.cookies.set(AUDIENCE_COOKIE, audience, { path: "/", maxAge: 60 * 60 * 24 * 365, sameSite: "lax" });
  return res;
}

/** "/" (any language): the remembered door, or null to show the entry page. `?aud=reset` clears the memory. */
function audienceDoor(req: NextRequest, locale: Locale): NextResponse | null {
  const aud = req.nextUrl.searchParams.get("aud");
  if (aud === AUDIENCE_RESET) return null;
  const chosen = req.cookies.get(AUDIENCE_COOKIE)?.value;
  if (!chosen || !AUDIENCES.has(chosen)) return null;
  const url = new URL(chosen === "privat" ? "/privat" : `/${locale}/erhverv`, req.url);
  // The ambassador welcome (/a/{slug} → /?anbefalet=…) and campaign parameters travel with the visitor.
  req.nextUrl.searchParams.forEach((v, k) => url.searchParams.set(k, v));
  const res = NextResponse.redirect(url, 307);
  res.headers.set("vary", "cookie, accept-language, x-vercel-ip-country");
  res.headers.set("cache-control", "private, no-store");
  return res;
}

/** The response for "/" when the entry page is shown: never shared-cached (it depends on the cookie) and, after
 *  `?aud=reset`, the memory is cleared. */
function entryResponse(req: NextRequest, res: NextResponse): NextResponse {
  res.headers.set("vary", "cookie, accept-language, x-vercel-ip-country");
  res.headers.set("cache-control", "private, no-store");
  if (req.nextUrl.searchParams.get("aud") === AUDIENCE_RESET) res.cookies.set(AUDIENCE_COOKIE, "", { path: "/", maxAge: 0 });
  return res;
}

/** Language routing + optimistic auth gate. Real authorisation happens in the backend on every request. */
export async function proxy(req: NextRequest) {
  const host = (req.headers.get("host") ?? "").toLowerCase().split(":")[0];
  const { pathname, search } = req.nextUrl;

  // 1. Old domains → dialogbot.app, path kept; Danish marketing pages land on /da/… (dialogbot.dk was Danish).
  if (OLD_HOSTS.has(host)) {
    const { locale, rest } = splitLocale(pathname);
    const path = !locale && isPublicPage(rest) && host.endsWith("dialogbot.dk") ? `/da${rest === "/" ? "" : rest}` : pathname;
    return NextResponse.redirect(`https://${MAIN_HOST}${path}${search}`, 308);
  }

  // 2. /<locale>/… : remember the choice and serve the unprefixed page in that language.
  const { locale: urlLocale, rest } = splitLocale(pathname);
  if (urlLocale) {
    if (!isPublicPage(rest)) {
      // /en/app, /de/login …: the app has no language prefix – switch language and go there.
      return remember(NextResponse.redirect(new URL(rest + search, req.url)), urlLocale);
    }
    const gate = await gateFor(req, rest, search);
    if (gate) return gate;
    if (rest === "/") {
      const door = audienceDoor(req, urlLocale);
      if (door) return remember(door, urlLocale);
    }
    const h = new Headers(req.headers);
    h.set(LOCALE_HEADER, urlLocale);
    let res = NextResponse.rewrite(new URL(rest + search, req.url), { request: { headers: h } });
    if (gateEnabled() && GATED.has(rest)) res.headers.set("cache-control", "private, no-store");
    if (rest === "/") res = entryResponse(req, res);
    if (rest === "/erhverv") rememberAudience(req, res, "erhverv");
    return remember(res, urlLocale);
  }

  // 3. A marketing page without a language: send the visitor to their language's version ("/" goes straight to a
  //    remembered door, so the visitor is not bounced twice).
  if (isPublicPage(pathname)) {
    const l = preferred(req);
    if (pathname === "/") {
      const door = audienceDoor(req, l);
      if (door) return door;
    }
    const res = NextResponse.redirect(new URL(`/${l}${pathname === "/" ? "" : pathname}${search}`, req.url), 307);
    res.headers.set("vary", "cookie, accept-language, x-vercel-ip-country");
    return res;
  }

  const gate = await gateFor(req, pathname, search);
  if (gate) return gate;
  const hasSession = Boolean(req.cookies.get(SESSION_COOKIE)?.value);
  // The ambassador portal needs a login; the programme page (/ambassador/bliv) and the parent's page do not.
  const ambassadorPortal = pathname === "/ambassador" || pathname.startsWith("/ambassador/udbetalinger");
  const protectedPath = pathname.startsWith("/app") || pathname.startsWith("/onboarding") || pathname.startsWith("/opsaetning") || ambassadorPortal;
  if (protectedPath && !hasSession) {
    const url = new URL("/login", req.url);
    url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  if ((pathname === "/login" || pathname === "/signup") && hasSession && !req.nextUrl.searchParams.get("expired")) {
    const next = req.nextUrl.searchParams.get("next");
    // Only same-origin paths: "//host" or "/\\host" would leave the site (open redirect).
    return NextResponse.redirect(new URL(safeNext(next), req.url));
  }
  // Pages behind the login learn their own path + query, so a dead session can go to /login?expired=1&next=… (api.server).
  const fwd = new Headers(req.headers);
  fwd.delete(PROTECTED_PATH_HEADER);  // never from the client
  if (protectedPath) fwd.set(PROTECTED_PATH_HEADER, pathname + search);
  const res = NextResponse.next({ request: { headers: fwd } });
  if (protectedPath) res.headers.set("cache-control", "no-store, private");
  // Dialogbot Privat: public without login (the landing /privat, invites /privat/invitation/*, group links /g/*,
  // short links /i/*), and the app pages show example data until the visitor saves a task, so none of them is
  // redirected to /login. They are not localized marketing pages (language = cookie). Pages that depend on the
  // session are never cached by a shared cache.
  if (isPrivatPath(pathname) && pathname !== "/privat") res.headers.set("cache-control", "no-store, private");
  if (pathname === "/privat") rememberAudience(req, res, "privat");
  // Gated pages vary by cookie; never let a shared cache serve them to someone without access.
  if (gateEnabled() && GATED.has(pathname)) res.headers.set("cache-control", "private, no-store");
  return res;
}

/** The temporary preview gate (PREVIEW_GATE=on) for `path` (unprefixed). */
async function gateFor(req: NextRequest, path: string, search: string): Promise<NextResponse | null> {
  const hasSession = Boolean(req.cookies.get(SESSION_COOKIE)?.value);
  if (!gateEnabled() || !GATED.has(path) || hasSession) return null;
  // Invited colleagues, new ambassadors and customers accepting an offer must be able to sign up from their link.
  const next = req.nextUrl.searchParams.get("next") ?? "";
  // A person who was sent a shared Privat list or group has no preview code either (F-JP-16): /signup with a safe
  // Privat next under /privat/invitation/, /g/ or /i/ is let through, like a colleague's invitation.
  const sharedList = privatNext(next) !== null && privatKind(privatNext(next)) === "list";
  const invited = path === "/signup" && (next.startsWith("/invite/") || next.startsWith("/ambassador") || next.startsWith("/tilbud/") || sharedList);
  if (invited || (await cookieValid(req.cookies.get(PREVIEW_COOKIE)?.value))) return null;
  const url = new URL("/preview", req.url);
  if (path !== "/") url.searchParams.set("next", path + search);
  const res = NextResponse.redirect(url);
  res.headers.set("cache-control", "no-store");
  return res;
}

/** Dialogbot Privat routes (public; see above). */
function isPrivatPath(pathname: string): boolean {
  return pathname === "/privat" || pathname.startsWith("/privat/") || pathname.startsWith("/g/") || pathname.startsWith("/i/");
}

// Everything except Next's own files, API routes and files with an extension (images, robots.txt, sitemap.xml …).
export const config = { matcher: ["/((?!_next/|api/|a/|.*\\.[a-zA-Z0-9]+$).*)"] };

export const _test = { isPublicPage, splitLocale, LOCALES, isPrivatPath, AUDIENCE_COOKIE };
