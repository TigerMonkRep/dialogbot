import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { API_BASE_URL, COOKIE_OPTS, CSRF_HEADER, CSRF_VALUE, SESSION_COOKIE } from "@/lib/config";

/** Exchanges credentials for a backend session and stores it in an httpOnly cookie. */
export async function POST(req: NextRequest) {
  if (req.headers.get(CSRF_HEADER) !== CSRF_VALUE) {
    return NextResponse.json({ code: "csrf_required", message: "Manglende anti-CSRF-header" }, { status: 403 });
  }
  const r = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: "POST", headers: { "content-type": "application/json", "user-agent": req.headers.get("user-agent") ?? "" },
    body: await req.text(), cache: "no-store",
  });
  const body = await r.json();
  if (!r.ok) return NextResponse.json(body, { status: r.status });
  (await cookies()).set(SESSION_COOKIE, body.access_token, COOKIE_OPTS);
  return NextResponse.json({ user: body.user }, { headers: { "cache-control": "no-store" } });
}
