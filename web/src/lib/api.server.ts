import "server-only";
import { cookies, headers as requestHeaders } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { API_BASE_URL, PROTECTED_PATH_HEADER, SESSION_COOKIE, WORKSPACE_COOKIE } from "./config";
import { safeNext } from "./safe-next";

export type ApiError = { status: number; code: string; message: string; field_errors?: { field: string; message?: string }[]; request_id?: string };

/** Server-side call to the FastAPI backend with the session from the httpOnly cookie. */
export async function backend<T>(path: string, init: RequestInit = {}): Promise<T> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  const r = await fetch(`${API_BASE_URL}/api/v1${path}`, { ...init, headers, cache: "no-store" });
  if (r.status === 204) return undefined as T;
  const body = await r.json().catch(() => ({ code: "http_error", message: r.statusText }));
  if (r.status === 401) await expiredSession();
  if (!r.ok) throw Object.assign(new Error(body.message ?? "Fejl"), { ...body, status: r.status }) as ApiError;
  return body as T;
}

/** A detail page whose id the backend does not know (404) or cannot parse (422, e.g. a path segment that is not a
 *  UUID) shows «findes ikke» with status 404 – not the error boundary with a 500. */
export async function orNotFound<T>(call: Promise<T>): Promise<T> {
  try {
    return await call;
  } catch (e) {
    const status = (e as Partial<ApiError>).status;
    if (status === 404 || status === 422) notFound();
    throw e;
  }
}

export async function currentWorkspaceId(): Promise<string | null> {
  return (await cookies()).get(WORKSPACE_COOKIE)?.value ?? null;
}

export async function isLoggedIn(): Promise<boolean> {
  return Boolean((await cookies()).get(SESSION_COOKIE)?.value);
}

/** A dead session (logged out elsewhere, password reset, revoked) on a page behind the login: back to the login with
 *  the page (and its query) remembered, instead of a crash. The proxy only lets /login?expired=1 through with the old
 *  cookie, and the login replaces it. Public pages (no header) keep handling the 401 themselves. */
async function expiredSession(): Promise<void> {
  let path: string | null = null;
  try { path = (await requestHeaders()).get(PROTECTED_PATH_HEADER); } catch { return; /* outside a request */ }
  if (!path) return;
  redirect(`/login?expired=1&next=${encodeURIComponent(safeNext(path))}`);
}
