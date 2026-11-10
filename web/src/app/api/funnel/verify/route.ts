import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { getT } from "@/i18n/server";
import { API_BASE_URL, COOKIE_OPTS, CSRF_HEADER, CSRF_VALUE, KNOWN_ACCOUNT_COOKIE, KNOWN_ACCOUNT_MAX_AGE, SESSION_COOKIE, WORKSPACE_COOKIE } from "@/lib/config";
import { safeNext } from "@/lib/safe-next";
import { visitorIp } from "@/lib/visitor-ip";

/** The funnel's SMS-code check. POST /api/v1/funnel/drafts/{id}/verify creates the user (an existing e-mail gets 409 account_exists, no session) and returns a
 *  session like POST /auth/login does; this route stores it in the httpOnly cookie – exactly as /api/auth/login – and
 *  hands the browser only `next` (the token never reaches JavaScript). Body: {draft_id, code}. */
export async function POST(req: NextRequest) {
  if (req.headers.get(CSRF_HEADER) !== CSRF_VALUE) {
    return NextResponse.json({ code: "csrf_required", message: (await getT("auth"))("errors.csrf") }, { status: 403 });
  }
  const { draft_id, code } = (await req.json().catch(() => ({}))) as { draft_id?: unknown; code?: unknown };
  if (typeof draft_id !== "string" || !/^[\w-]{1,64}$/.test(draft_id) || typeof code !== "string" || !/^\d{4,8}$/.test(code)) {
    return NextResponse.json({ code: "validation_failed", message: "Ugyldig kode", field_errors: [{ field: "code", message: "Ugyldig kode" }] }, { status: 422 });
  }
  const headers: Record<string, string> = { "content-type": "application/json", "user-agent": req.headers.get("user-agent") ?? "" };
  const ip = visitorIp(req.headers);
  if (ip) headers["x-forwarded-for"] = ip;
  const r = await fetch(`${API_BASE_URL}/api/v1/funnel/drafts/${encodeURIComponent(draft_id)}/verify`, {
    method: "POST", headers, body: JSON.stringify({ code }), cache: "no-store",
  });
  const body = await r.json().catch(() => ({ code: "http_error", message: r.statusText }));
  if (!r.ok) return NextResponse.json(body, { status: r.status });
  const token: unknown = body.session_token ?? body.access_token;
  const store = await cookies();
  if (typeof token === "string" && token) {
    store.set(SESSION_COOKIE, token, COOKIE_OPTS);
    store.set(KNOWN_ACCOUNT_COOKIE, "1", { ...COOKIE_OPTS, maxAge: KNOWN_ACCOUNT_MAX_AGE });
  }
  if (typeof body.workspace_id === "string" && /^[0-9a-f-]{36}$/.test(body.workspace_id)) store.set(WORKSPACE_COOKIE, body.workspace_id, COOKIE_OPTS);
  // Only same-origin paths are followed (safeNext), like ?next= on /login.
  return NextResponse.json({ status: body.status ?? "ok", next: safeNext(typeof body.next === "string" ? body.next : null, "/") }, { headers: { "cache-control": "no-store" } });
}
