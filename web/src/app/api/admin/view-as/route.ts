import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { API_BASE_URL, COOKIE_OPTS, CSRF_HEADER, CSRF_VALUE, OPERATOR_SESSION_COOKIE, SESSION_COOKIE, VIEWAS_COOKIE, VIEWAS_MAX_AGE, WORKSPACE_COOKIE } from "@/lib/config";

/** Start "se som kunde": the backend (operators only) issues a one-hour READ-ONLY session for the chosen user. The
 *  operator's own session is parked in a separate httpOnly cookie and restored by /api/admin/view-as/end. */
export async function POST(req: NextRequest) {
  if (req.headers.get(CSRF_HEADER) !== CSRF_VALUE) return NextResponse.json({ code: "csrf_required" }, { status: 403 });
  const store = await cookies();
  if (store.get(VIEWAS_COOKIE)?.value) return NextResponse.json({ code: "view_as_nested", message: "Afslut den nuværende visning først" }, { status: 409 });
  const own = store.get(SESSION_COOKIE)?.value;
  if (!own) return NextResponse.json({ code: "session_invalid", message: "Login påkrævet" }, { status: 401 });
  const { user_id, workspace_id } = await req.json().catch(() => ({}));
  const r = await fetch(`${API_BASE_URL}/api/v1/operator/admin/view-as`, {
    method: "POST", cache: "no-store", headers: { Authorization: `Bearer ${own}`, "content-type": "application/json" },
    body: JSON.stringify({ user_id, workspace_id: workspace_id ?? null }),
  });
  const body = await r.json().catch(() => ({ code: "http_error", message: r.statusText }));
  if (!r.ok) return NextResponse.json(body, { status: r.status });
  const opts = { ...COOKIE_OPTS, maxAge: VIEWAS_MAX_AGE };
  store.set(OPERATOR_SESSION_COOKIE, own, opts);
  store.set(SESSION_COOKIE, body.token, opts);
  store.set(VIEWAS_COOKIE, JSON.stringify({ name: body.user.name, email: body.user.email }), opts);
  if (workspace_id) store.set(WORKSPACE_COOKIE, workspace_id, opts); else store.delete(WORKSPACE_COOKIE);
  return NextResponse.json({ ok: true, next: body.ambassador && !workspace_id ? "/ambassador" : "/app/overview" });
}
