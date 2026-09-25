import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/config";

/** Optimistic auth gate. Real authorisation happens in the backend on every request. */
export function proxy(req: NextRequest) {
  const hasSession = Boolean(req.cookies.get(SESSION_COOKIE)?.value);
  const { pathname, search } = req.nextUrl;
  const protectedPath = pathname.startsWith("/app") || pathname.startsWith("/onboarding");
  if (protectedPath && !hasSession) {
    const url = new URL("/login", req.url);
    url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  if ((pathname === "/login" || pathname === "/signup") && hasSession && !req.nextUrl.searchParams.get("expired")) {
    return NextResponse.redirect(new URL(req.nextUrl.searchParams.get("next") ?? "/app", req.url));
  }
  const res = NextResponse.next();
  if (protectedPath) res.headers.set("cache-control", "no-store, private");
  return res;
}

export const config = { matcher: ["/app/:path*", "/onboarding/:path*", "/login", "/signup"] };
