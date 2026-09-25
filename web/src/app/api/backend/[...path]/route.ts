import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { API_BASE_URL, CSRF_HEADER, CSRF_VALUE, SESSION_COOKIE } from "@/lib/config";

/** Same-origin BFF proxy. Attaches the Bearer token from the httpOnly cookie,
 * requires a custom header on mutating requests (CSRF defence on top of SameSite=Lax),
 * and never caches responses. Only /api/v1/* of the backend is reachable. */
async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (req.method !== "GET" && req.headers.get(CSRF_HEADER) !== CSRF_VALUE) {
    return NextResponse.json({ code: "csrf_required", message: "Manglende anti-CSRF-header", field_errors: [] }, { status: 403 });
  }
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const url = new URL(`${API_BASE_URL}/api/v1/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  for (const h of ["content-type", "idempotency-key", "x-request-id"]) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.text();
  const upstream = await fetch(url, { method: req.method, headers, body, cache: "no-store", redirect: "manual" });
  const out = new NextResponse(upstream.status === 204 ? null : upstream.body, { status: upstream.status });
  out.headers.set("content-type", upstream.headers.get("content-type") ?? "application/json");
  out.headers.set("cache-control", "no-store, private");
  const rid = upstream.headers.get("x-request-id");
  if (rid) out.headers.set("x-request-id", rid);
  return out;
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE, proxy as PATCH };
