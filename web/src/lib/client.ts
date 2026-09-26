"use client";
/** Browser-side API access. All calls go same-origin to /api/backend/* (BFF);
 * the session lives in an httpOnly cookie and is never readable by JS. */
export type ApiError = { status: number; code: string; message: string; field_errors?: { field: string; message?: string }[]; request_id?: string };

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("x-requested-with", "dialogbot");
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  const r = await fetch(`/api/backend${path}`, { ...init, headers, credentials: "same-origin" });
  if (r.status === 204) return undefined as T;
  const body = await r.json().catch(() => ({ code: "http_error", message: r.statusText }));
  if (r.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
    location.href = `/login?expired=1&next=${encodeURIComponent(location.pathname)}`;
  }
  if (!r.ok) throw { ...body, status: r.status } as ApiError;
  return body as T;
}

/** POST that returns binary data (e.g. an audio sample) as a Blob; errors are thrown as ApiError. */
export async function apiBlob(path: string, body: unknown): Promise<Blob> {
  const r = await fetch(`/api/backend${path}`, {
    method: "POST", credentials: "same-origin", body: JSON.stringify(body),
    headers: { "x-requested-with": "dialogbot", "content-type": "application/json" },
  });
  if (!r.ok) throw { ...(await r.json().catch(() => ({ code: "http_error", message: r.statusText }))), status: r.status } as ApiError;
  return r.blob();
}

export function fieldError(err: ApiError | null, field: string): string | undefined {
  return err?.field_errors?.find((f) => f.field === field)?.message;
}
