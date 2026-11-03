import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/config";
import { PREVIEW_COOKIE, cookieValid, gateEnabled } from "@/lib/preview-gate";
import { safeNext } from "@/lib/safe-next";
import {
  DEFAULT_LOCALE, LOCALE_COOKIE, LOCALE_HEADER, LOCALES, fromAcceptLanguage, isLocale, isPublicPage, type Locale,
} from "@/i18n/config";

// Public pages hidden behind the temporary preview page while PREVIEW_GATE=on.
const GATED = new Set(["/", "/proev", "/byggevejledning", "/signup"]);

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
  return fromAcceptLanguage(req.headers.get("accept-language")) ?? DEFAULT_LOCALE;
}

function remember(res: NextResponse, locale: Locale): NextResponse {
  res.cookies.set(LOCALE_COOKIE, locale, { path: "/", maxAge: 60 * 60 * 24 * 365, sameSite: "lax" });
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
    const h = new Headers(req.headers);
    h.set(LOCALE_HEADER, urlLocale);
    const res = NextResponse.rewrite(new URL(rest + search, req.url), { request: { headers: h } });
    if (gateEnabled() && GATED.has(rest)) res.headers.set("cache-control", "private, no-store");
    return remember(res, urlLocale);
  }

  // 3. A marketing page without a language: send the visitor to their language's version.
  if (isPublicPage(pathname)) {
    const l = preferred(req);
    const res = NextResponse.redirect(new URL(`/${l}${pathname === "/" ? "" : pathname}${search}`, req.url), 307);
    res.headers.set("vary", "cookie, accept-language");
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
  const res = NextResponse.next();
  if (protectedPath) res.headers.set("cache-control", "no-store, private");
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
  const invited = path === "/signup" && (next.startsWith("/invite/") || next.startsWith("/ambassador") || next.startsWith("/tilbud/"));
  if (invited || (await cookieValid(req.cookies.get(PREVIEW_COOKIE)?.value))) return null;
  const url = new URL("/preview", req.url);
  if (path !== "/") url.searchParams.set("next", path + search);
  const res = NextResponse.redirect(url);
  res.headers.set("cache-control", "no-store");
  return res;
}

// Everything except Next's own files, API routes and files with an extension (images, robots.txt, sitemap.xml …).
export const config = { matcher: ["/((?!_next/|api/|a/|.*\\.[a-zA-Z0-9]+$).*)"] };

export const _test = { isPublicPage, splitLocale, LOCALES };
