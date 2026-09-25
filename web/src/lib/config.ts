/** Server-only configuration. Never expose API_BASE_URL credentials to the browser. */
export const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
export const SESSION_COOKIE = "db_session";
export const WORKSPACE_COOKIE = "db_ws";
export const CSRF_HEADER = "x-requested-with";
export const CSRF_VALUE = "dialogbot";
export const COOKIE_OPTS = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
  maxAge: 60 * 60 * 24 * 14,
};
