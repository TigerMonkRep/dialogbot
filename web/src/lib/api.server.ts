import "server-only";
import { cookies } from "next/headers";
import { API_BASE_URL, SESSION_COOKIE, WORKSPACE_COOKIE } from "./config";

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
  if (!r.ok) throw Object.assign(new Error(body.message ?? "Fejl"), { ...body, status: r.status }) as ApiError;
  return body as T;
}

export async function currentWorkspaceId(): Promise<string | null> {
  return (await cookies()).get(WORKSPACE_COOKIE)?.value ?? null;
}

export async function isLoggedIn(): Promise<boolean> {
  return Boolean((await cookies()).get(SESSION_COOKIE)?.value);
}
