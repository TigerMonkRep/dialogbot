import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { API_BASE_URL, COOKIE_OPTS, CSRF_HEADER, CSRF_VALUE, OPERATOR_SESSION_COOKIE, SESSION_COOKIE, VIEWAS_COOKIE, WORKSPACE_COOKIE } from "@/lib/config";

/** End "se som kunde": revoke the read-only session at the backend and put the operator's own session back. */
export async function POST(req: NextRequest) {
  if (req.headers.get(CSRF_HEADER) !== CSRF_VALUE) return NextResponse.json({ code: "csrf_required" }, { status: 403 });
  const store = await cookies();
  const viewing = store.get(SESSION_COOKIE)?.value;
  const own = store.get(OPERATOR_SESSION_COOKIE)?.value;
  if (viewing && store.get(VIEWAS_COOKIE)?.value) {
    await fetch(`${API_BASE_URL}/api/v1/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${viewing}` }, cache: "no-store" }).catch(() => undefined);
  }
  store.delete(VIEWAS_COOKIE);
  store.delete(OPERATOR_SESSION_COOKIE);
  store.delete(WORKSPACE_COOKIE);
  if (own) store.set(SESSION_COOKIE, own, COOKIE_OPTS); else store.delete(SESSION_COOKIE);
  return NextResponse.json({ ok: true });
}
