import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/config";
import { PREVIEW_COOKIE, cookieValid, gateEnabled } from "@/lib/preview-gate";
import { safeNext } from "@/lib/safe-next";

// Public pages hidden behind the temporary preview page (P00) while PREVIEW_GATE=on.
const GATED = new Set(["/", "/signup"]);

/** Optimistic auth gate. Real authorisation happens in the backend on every request. */
export async function proxy(req: NextRequest) {
  const hasSession = Boolean(req.cookies.get(SESSION_COOKIE)?.value);
  const { pathname, search } = req.nextUrl;
  if (gateEnabled() && GATED.has(pathname) && !hasSession) {
    // Invited colleagues must be able to create an account from their invitation link.
    const invited = pathname === "/signup" && (req.nextUrl.searchParams.get("next") ?? "").startsWith("/invite/");
    if (!invited && !(await cookieValid(req.cookies.get(PREVIEW_COOKIE)?.value))) {
      const url = new URL("/preview", req.url);
      if (pathname !== "/") url.searchParams.set("next", pathname + search);
      const res = NextResponse.redirect(url);
      res.headers.set("cache-control", "no-store");
      return res;
    }
  }
  const protectedPath = pathname.startsWith("/app") || pathname.startsWith("/onboarding");
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

export const config = { matcher: ["/", "/app/:path*", "/onboarding/:path*", "/login", "/signup"] };
