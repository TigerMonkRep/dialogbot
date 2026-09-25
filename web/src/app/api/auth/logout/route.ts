import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { API_BASE_URL, CSRF_HEADER, CSRF_VALUE, SESSION_COOKIE, WORKSPACE_COOKIE } from "@/lib/config";

export async function POST(req: NextRequest) {
  if (req.headers.get(CSRF_HEADER) !== CSRF_VALUE) return NextResponse.json({ code: "csrf_required" }, { status: 403 });
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  if (token) {
    await fetch(`${API_BASE_URL}/api/v1/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }).catch(() => undefined);
  }
  store.delete(SESSION_COOKIE);
  store.delete(WORKSPACE_COOKIE);
  return NextResponse.json({ ok: true });
}
