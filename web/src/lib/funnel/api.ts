"use client";
/** The quiz-funnels (/start and /privat/start) – typed client for the public /api/v1/funnel/* endpoints, reached
 *  through the BFF proxy (/api/backend/funnel/…). The contract is docs/funnel-brief: one draft without an account,
 *  answered step by step (PATCH), gated by name + mobile + e-mail → SMS code (verify) which also logs the person in.
 *  The same interface is implemented in-browser by ./fake.ts (NEXT_PUBLIC_FUNNEL_FAKE=1, or when the API is missing)
 *  so the pages work end to end before the backend lands. */
import type { ApiError } from "@/lib/client";

export type FunnelKind = "erhverv" | "privat";
export type Industry = "haandvaerker" | "klinik" | "salon" | "vaerksted" | "raadgiver" | "restaurant";
export const INDUSTRIES: Industry[] = ["haandvaerker", "klinik", "salon", "vaerksted", "raadgiver", "restaurant"];
export const MISSED = ["lunch", "after16", "driving", "weekend", "never_free"] as const;
export const WANTS = ["book", "message", "prices"] as const;
export const POSTPONED = ["dentist", "bike", "car_inspection", "gift", "doctor", "hairdresser", "insurance", "landlord"] as const;
export const HOUSEHOLD = ["alone", "couple", "kids", "parents"] as const;
export const HATE_CALLS = ["health", "workshop", "municipality", "restaurant"] as const;
export const REMIND_AT = ["morning", "lunch", "evening"] as const;
/** Ad hooks that change the step-1 headline (site.funnel.hooks.<hook>); anything else gets the default. */
export const HOOKS = ["stige", "1605", "telefonsvarer"] as const;

export type Company = { name: string; address: string | null; phone_display: string | null; website: string | null; opening_hours_text: string | null; place_id: string | null };
export type Estimate = { missed_per_week: number; source: string };
export type BuildErhverv = { knowledge: "pending" | "done" | "skipped"; voice: "done" | "pending"; hours: "done" | "default" | "pending"; number: "done" | "pending" };
export type BuildPrivat = { tasks: number; lists: number; first_call: { title: string } | null };
export type Answers = Record<string, unknown> & {
  industry?: Industry; company_name?: string; place_id?: string | null; missed?: string[]; missed_per_week?: number; wants?: string[];
  postponed?: string[]; household?: string; hate_calls?: string; remind_at?: string; assistant_name?: string;
};
export type Draft = {
  id: string; kind: FunnelKind; hook: string | null; step: number; answers: Answers;
  company: Company | null; estimate: Estimate | null;
  build: BuildErhverv | BuildPrivat | null;
  gated: boolean; expires_at: string;
};
export type Place = { place_id: string; name: string; address: string; phone_display: string | null; website: string | null; open_now: boolean | null };
export type Utm = { source?: string; medium?: string; campaign?: string; content?: string };
export type GateBody = { name: string; email: string; phone: string; consent: true; website?: string };
export type GateResult = { status: "code_sent"; phone_display: string };
export type VerifyResult = { status: "ok"; next: string };
export type Call = { status: string; summary: string | null; duration_seconds: number | null; audio_url?: string | null };
/** `call_problem`: why no call was placed (call is null) – the page must say so, never «hun ringer nu» (F-E2A-03-X03). */
export type Reveal = { call: Call | null; call_problem?: string | null; workspace_id: string | null };

export type FunnelApi = {
  create(body: { kind: FunnelKind; hook?: string | null; industry?: string | null; utm?: Utm }): Promise<Draft>;
  get(id: string): Promise<Draft>;
  patch(id: string, step: number, answers: Answers): Promise<Draft>;
  places(q: string, industry?: string | null): Promise<Place[]>;
  gate(id: string, body: GateBody): Promise<GateResult>;
  /** Also logs the person in (the BFF route stores the session cookie); the page then follows `next`. */
  verify(id: string, code: string): Promise<VerifyResult>;
  reveal(id: string): Promise<Reveal>;
};

/** Like lib/client.ts, but a 401 (reveal before login) is returned as an error instead of sending the page to /login. */
async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("x-requested-with", "dialogbot");
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  const r = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (r.status === 204) return undefined as T;
  const body = await r.json().catch(() => ({ code: "http_error", message: r.statusText }));
  if (!r.ok) throw { ...body, status: r.status } as ApiError;
  return body as T;
}
const B = "/api/backend/funnel";

export const realFunnel: FunnelApi = {
  create: (body) => call<Draft>(`${B}/drafts`, { method: "POST", body: JSON.stringify(body) }),
  get: (id) => call<Draft>(`${B}/drafts/${encodeURIComponent(id)}`),
  patch: (id, step, answers) => call<Draft>(`${B}/drafts/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ step, answers }) }),
  places: async (q, industry) => {
    const r = await call<Place[] | { items: Place[] }>(`${B}/places?q=${encodeURIComponent(q)}${industry ? `&industry=${encodeURIComponent(industry)}` : ""}`);
    return Array.isArray(r) ? r : r.items ?? [];
  },
  gate: (id, body) => call<GateResult>(`${B}/drafts/${encodeURIComponent(id)}/gate`, { method: "POST", body: JSON.stringify(body) }),
  // Not through the generic proxy: the Next route stores the session token in the httpOnly cookie (like /api/auth/login).
  verify: (id, code) => call<VerifyResult>("/api/funnel/verify", { method: "POST", body: JSON.stringify({ draft_id: id, code }) }),
  reveal: (id) => call<Reveal>(`${B}/drafts/${encodeURIComponent(id)}/reveal`),
};

export const FORCE_FAKE = process.env.NEXT_PUBLIC_FUNNEL_FAKE === "1";
/** The API is not there (yet): 404 from the proxy, or the feature switched off. Then the in-browser mock takes over. */
export function isUnavailable(e: unknown): boolean {
  const err = e as Partial<ApiError> | undefined;
  return !!err && (err.status === 404 || err.code === "feature_disabled" || err.code === "funnel_disabled");
}

// ---------- the draft cookie (7 days, readable by JS: the page needs the id on every step) ----------
export const DRAFT_COOKIE = "dialogbot_funnel";
const DRAFT_MAX_AGE = 60 * 60 * 24 * 7;
export function readDraftCookie(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp(`(?:^|; )${DRAFT_COOKIE}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}
export function writeDraftCookie(id: string | null) {
  if (typeof document === "undefined") return;
  const secure = location.protocol === "https:" ? "; secure" : "";
  document.cookie = `${DRAFT_COOKIE}=${id ? encodeURIComponent(id) : ""}; path=/; max-age=${id ? DRAFT_MAX_AGE : 0}; samesite=lax${secure}`;
}

/** Fallback estimate while the backend's number is on its way (and in fake mode). Calls missed per week by line of
 *  business and the chosen "when" chips – rough, and the person can change the number. The source is shown. */
const BASE: Record<Industry, number> = { haandvaerker: 14, klinik: 18, salon: 12, vaerksted: 11, raadgiver: 8, restaurant: 16 };
const SHARE: Record<string, number> = { lunch: 0.2, after16: 0.3, driving: 0.3, weekend: 0.25, never_free: 0.6 };
export function localEstimate(industry: Industry | undefined, missed: string[]): Estimate {
  const base = industry ? BASE[industry] : 12;
  const share = Math.min(1, missed.reduce((s, m) => s + (SHARE[m] ?? 0), 0)) || 0.3;
  return { missed_per_week: Math.max(1, Math.round(base * share)), source: "Dialogbot – gennemsnit for branchen (kundeopkald 2025)" };
}

export const isDone = (c: Call | null | undefined) => !!c && ["answered", "completed", "done", "no_answer", "failed", "declined", "busy"].includes(c.status);
