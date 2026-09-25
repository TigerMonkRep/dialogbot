import { NextRequest, NextResponse } from "next/server";
import { CSRF_HEADER, CSRF_VALUE } from "@/lib/config";
import { PREVIEW_COOKIE, PREVIEW_MAX_AGE, codeValid, cookieValue, gateEnabled } from "@/lib/preview-gate";
import { safeNext } from "@/lib/safe-next";

/** Checks an invitation code server-side and sets the signed preview cookie. */
export async function POST(req: NextRequest) {
  if (req.headers.get(CSRF_HEADER) !== CSRF_VALUE) {
    return NextResponse.json({ code: "csrf_required", message: "Manglende anti-CSRF-header" }, { status: 403 });
  }
  const body = (await req.json().catch(() => ({}))) as { code?: unknown; next?: unknown };
  const next = safeNext(typeof body.next === "string" ? body.next : "/", "/");
  if (!gateEnabled()) return NextResponse.json({ next });
  const ok = typeof body.code === "string" && body.code.length <= 64 && codeValid(body.code);
  const value = ok ? await cookieValue() : null;
  if (!value) {
    // Slow down guessing; the codes themselves must be long (≥ 8 characters are enforced).
    await new Promise((r) => setTimeout(r, 800));
    return NextResponse.json({ code: "invalid_code", message: "Koden er ikke gyldig. Tjek stavningen, eller skriv dig på ventelisten." }, { status: 400 });
  }
  const res = NextResponse.json({ next });
  res.cookies.set(PREVIEW_COOKIE, value, { httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/", maxAge: PREVIEW_MAX_AGE });
  res.headers.set("cache-control", "no-store");
  return res;
}
