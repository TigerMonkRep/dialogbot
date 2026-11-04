"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import type { ApiError } from "@/lib/client";
import { track } from "@/components/site-analytics";
import { FORCE_FAKE, INDUSTRIES, isUnavailable, readDraftCookie, realFunnel, writeDraftCookie,
  type Answers, type Draft, type FunnelApi, type FunnelKind, type GateBody, type Industry, type Utm } from "@/lib/funnel/api";
import { fakeFunnel } from "@/lib/funnel/fake";

/** What the gate sent, kept for the code step (resend) and the reveal page (the number we ring). Per draft. */
export type GateInfo = { draftId: string; phone_display: string; body: GateBody };
const GATE_KEY = "dialogbot-funnel-gate";
const FALLBACK_KEY = "dialogbot-funnel-fake-fallback";
const ss = {
  get: (k: string) => { try { return sessionStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { sessionStorage.setItem(k, v); } catch { /* ignore */ } },
  del: (k: string) => { try { sessionStorage.removeItem(k); } catch { /* ignore */ } },
};
export function readGateInfo(draftId: string | null): GateInfo | null {
  try { const g = JSON.parse(ss.get(GATE_KEY) ?? "null") as GateInfo | null; return g && g.draftId === draftId ? g : null; } catch { return null; }
}

type Ctx = {
  kind: FunnelKind; base: string; total: number; hook: string | null;
  /** The step in the URL (1-based); 0 outside the numbered steps (e.g. /start/klar). */
  step: number;
  draft: Draft | null; status: "loading" | "ready" | "error"; error: ApiError | null;
  api: FunnelApi; simulated: boolean;
  /** PATCH one step's answers; the draft in the context is replaced by the response. */
  answer(step: number, answers: Answers): Promise<Draft | null>;
  refresh(): Promise<Draft | null>;
  go(step: number): void; next(): void; back(): void;
  gate: GateInfo | null; setGate(g: GateInfo | null): void;
  /** Start over with a fresh draft (keeps the hook). */
  restart(): Promise<void>;
  audience: React.ReactNode;
};
const FunnelCtx = createContext<Ctx | null>(null);

export function useFunnel(): Ctx {
  const c = useContext(FunnelCtx);
  if (!c) throw new Error("FunnelProvider mangler");
  return c;
}

/** Wraps a funnel's pages (layout): loads or creates the draft once, keeps it while the person moves between the steps
 *  (client navigation), and chooses the real API or the in-browser mock. `audience` is the server-rendered
 *  «Til virksomheder | Til dig derhjemme» bar the shell shows at the very top. */
export function FunnelProvider({ kind, base, total, audience, children }: { kind: FunnelKind; base: string; total: number; audience?: React.ReactNode; children: React.ReactNode }) {
  const router = useRouter();
  const params = useParams<{ step?: string }>();
  const search = useSearchParams();
  const hookParam = search.get("h");
  const hook = hookParam && /^[\w-]{1,40}$/.test(hookParam) ? hookParam : null;
  const step = /^\d+$/.test(params.step ?? "") ? Number(params.step) : 0;
  const [simulated, setSimulated] = useState<boolean>(() => FORCE_FAKE || (typeof window !== "undefined" && ss.get(FALLBACK_KEY) === "1"));
  const api: FunnelApi = simulated ? fakeFunnel : realFunnel;
  const apiRef = useRef(api); apiRef.current = api;
  const [draft, setDraft] = useState<Draft | null>(null);
  const [status, setStatus] = useState<Ctx["status"]>("loading");
  const [error, setError] = useState<ApiError | null>(null);
  const [gate, setGateState] = useState<GateInfo | null>(null);
  const tracked = useRef<string>("");

  const useFake = useCallback(() => { ss.set(FALLBACK_KEY, "1"); setSimulated(true); apiRef.current = fakeFunnel; return fakeFunnel; }, []);

  const create = useCallback(async (a: FunnelApi): Promise<Draft> => {
    const b = search.get("b");
    const industry = kind === "erhverv" && b && (INDUSTRIES as string[]).includes(b) ? (b as Industry) : null;
    const utm: Utm = {};
    for (const k of ["source", "medium", "campaign", "content"] as const) { const v = search.get(`utm_${k}`); if (v) utm[k] = v.slice(0, 120); }
    const d = await a.create({ kind, hook, industry, utm: Object.keys(utm).length ? utm : undefined });
    writeDraftCookie(d.id);
    ss.del(GATE_KEY);
    return d;
  }, [kind, hook, search]);

  // Load the draft from the cookie, or start a new one. A draft of the other kind, or one already verified, is not
  // continued: the person starts afresh (their account exists; the old draft expires by itself). The pages outside
  // the numbered steps (the reveal page, step 0) only read: they need the verified draft and never create one.
  useEffect(() => {
    let alive = true;
    const reveal = step === 0;
    (async () => {
      let a = apiRef.current;
      const id = readDraftCookie();
      let d: Draft | null = null;
      try {
        if (id) {
          try { d = await a.get(id); }
          catch (e) {
            if (!simulated && isUnavailable(e)) { a = useFake(); try { d = await a.get(id); } catch { d = null; } }
            else d = null; // expired / unknown: start over
          }
        }
        if (d && (d.kind !== kind || (d.gated && !reveal))) d = null;
        if (reveal) { if (alive) { setDraft(d); setGateState(readGateInfo(d?.id ?? null)); setStatus("ready"); } return; }
        if (!d) {
          try { d = await create(a); }
          catch (e) {
            if (!simulated && isUnavailable(e)) d = await create(useFake()); else throw e;
          }
        }
        if (!alive) return;
        setDraft(d); setGateState(readGateInfo(d.id)); setStatus("ready");
      } catch (e) {
        if (!alive) return;
        setError(e as ApiError); setStatus("error");
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind]);

  // One funnel_step per step view (not again on re-renders).
  useEffect(() => {
    if (!draft || step === 0) return;
    const key = `${draft.id}:${step}`;
    if (tracked.current === key) return;
    tracked.current = key;
    track("funnel_step", { kind, step, hook, industry: draft.answers.industry ?? null });
  }, [draft, step, kind, hook]);

  const answer = useCallback(async (s: number, answers: Answers) => {
    if (!draft) return null;
    setError(null);
    try {
      const d = await apiRef.current.patch(draft.id, s, answers);
      setDraft(d);
      return d;
    } catch (e) {
      // Optimistic: the answers stay in the local draft so the person can go on; the next PATCH carries them again.
      setDraft((cur) => cur ? { ...cur, answers: { ...cur.answers, ...answers } } : cur);
      setError(e as ApiError);
      return null;
    }
  }, [draft]);

  const refresh = useCallback(async () => {
    if (!draft) return null;
    try { const d = await apiRef.current.get(draft.id); setDraft(d); return d; } catch (e) { setError(e as ApiError); return null; }
  }, [draft]);

  const go = useCallback((s: number) => { router.push(`${base}/${s}`); }, [router, base]);
  const next = useCallback(() => { if (step > 0 && step < total) router.push(`${base}/${step + 1}`); }, [router, base, step, total]);
  const back = useCallback(() => { if (step > 1) router.push(`${base}/${step - 1}`); else router.push(kind === "privat" ? "/privat" : "/"); }, [router, base, step, kind]);
  const setGate = useCallback((g: GateInfo | null) => { setGateState(g); if (g) ss.set(GATE_KEY, JSON.stringify(g)); else ss.del(GATE_KEY); }, []);
  const restart = useCallback(async () => {
    setStatus("loading"); setDraft(null); setGate(null);
    try { const d = await create(apiRef.current); setDraft(d); setStatus("ready"); router.push(`${base}/1`); }
    catch (e) { setError(e as ApiError); setStatus("error"); }
  }, [create, router, base, setGate]);

  const value = useMemo<Ctx>(() => ({
    kind, base, total, hook, step, draft, status, error, api, simulated, answer, refresh, go, next, back, gate, setGate, restart, audience,
  }), [kind, base, total, hook, step, draft, status, error, api, simulated, answer, refresh, go, next, back, gate, setGate, restart, audience]);
  return <FunnelCtx.Provider value={value}>{children}</FunnelCtx.Provider>;
}

/** The highest step the person may open: one past the last answered step, the code step once the gate has sent a code.
 *  Pages call it to send a deep link back to where the draft actually is. */
export function reachableStep(draft: Draft | null, gate: GateInfo | null, gateStep: number): number {
  if (!draft) return 1;
  if (gate && gate.draftId === draft.id) return gateStep + 1;
  return Math.max(1, Math.min(gateStep, draft.step + 1));
}
