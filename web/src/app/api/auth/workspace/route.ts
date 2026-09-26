import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { COOKIE_OPTS, CSRF_HEADER, CSRF_VALUE, WORKSPACE_COOKIE } from "@/lib/config";

/** Remembers the selected workspace. Authorisation is still checked by the backend per request. */
export async function POST(req: NextRequest) {
  if (req.headers.get(CSRF_HEADER) !== CSRF_VALUE) return NextResponse.json({ code: "csrf_required" }, { status: 403 });
  const { workspace_id } = await req.json();
  if (typeof workspace_id !== "string" || !/^[0-9a-f-]{36}$/.test(workspace_id)) {
    return NextResponse.json({ code: "validation_failed", message: "Ugyldigt arbejdsrum" }, { status: 422 });
  }
  (await cookies()).set(WORKSPACE_COOKIE, workspace_id, COOKIE_OPTS);
  return NextResponse.json({ ok: true });
}
