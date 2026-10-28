import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { API_BASE_URL, COOKIE_OPTS, CSRF_HEADER, CSRF_VALUE, OPERATOR_SESSION_COOKIE, SESSION_COOKIE, VIEWAS_COOKIE, WORKSPACE_COOKIE } from "@/lib/config";

export async function POST(req: NextRequest) {
  if (req.headers.get(CSRF_HEADER) !== CSRF_VALUE) return NextResponse.json({ code: "csrf_required" }, { status: 403 });
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  if (token) {
    await fetch(`${API_BASE_URL}/api/v1/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }).catch(() => undefined);
  }
  store.delete(SESSION_COOKIE);
  store.delete(WORKSPACE_COOKIE);
  // Logging out while looking at a customer's account only ends the viewing: the operator stays logged in.
  const own = store.get(OPERATOR_SESSION_COOKIE)?.value;
  if (store.get(VIEWAS_COOKIE)?.value && own) store.set(SESSION_COOKIE, own, COOKIE_OPTS);
  store.delete(VIEWAS_COOKIE);
  store.delete(OPERATOR_SESSION_COOKIE);
  return NextResponse.json({ ok: true });
}
