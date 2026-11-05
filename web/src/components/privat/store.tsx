"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";
import type { ApiError } from "@/lib/client";
import { CONFLICT, isUnavailable, realPrivat, type Addon, type Balance, type ChatMessage, type Day, type Group, type LedgerEntry, type PrivatApi, type Referrals, type Subscription, type Task,
  type BillingInterval, type Plan, type PlanKey, type SubscriptionPlan, type SubscriptionStatus } from "@/lib/privat/api";
import { createFakePrivat, type FakePrivat } from "@/lib/privat/fake";
import { useLocale, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";
import { PLANS, TRIAL_DAYS } from "@/lib/privat/plans";

/** fake = full simulation (NEXT_PUBLIC_PRIVAT_FAKE=1, or the real API is missing); demo = visitor without login looking at
 *  example data (creating something asks for login); real = the Privat API. */
export type Mode = "loading" | "fake" | "demo" | "real";
/** needsPlan: «Med i Plus – start 14 dage gratis / Vælg plan» (an app or a call needs trial/Plus/Familie). */
export type SheetKind = "login" | "mic" | "paywall" | "buy" | "sponsor" | "share" | "addon" | "addonOff" | "needsPlan";
export type Sheet = { kind: SheetKind; taskId?: string | null; addonKey?: string; groupId?: string } | null;
/** "store" = Butikken (/privat/butik); "addons" is kept as an alias for the old name. */
export type Screen = "day" | "chat" | "tasks" | "task" | "account" | "store" | "addons" | "people";
export type Session = { loggedIn: boolean; name: string | null; email: string | null; businessWsId: string | null };

export const FORCE_FAKE = process.env.NEXT_PUBLIC_PRIVAT_FAKE === "1";
const FAKE_LOGIN_KEY = "dialogbot-privat-fake-login";
const PENDING_KEY = "dialogbot-privat-pending";
export const FAKE_KEY = "dialogbot-privat-fake";

export function screenOf(path: string): { screen: Screen; taskId: string | null } {
  const m = path.match(/^\/privat\/opgaver\/([^/]+)/);
  if (m) return { screen: "task", taskId: decodeURIComponent(m[1]) };
  if (path.startsWith("/privat/opgaver")) return { screen: "tasks", taskId: null };
  if (path.startsWith("/privat/konto")) return { screen: "account", taskId: null };
  if (path.startsWith("/privat/butik") || path.startsWith("/privat/tilfoejelser") || path.startsWith("/privat/kalender")) return { screen: "store", taskId: null };
  if (path.startsWith("/privat/folk")) return { screen: "people", taskId: null };
  if (path.startsWith("/privat/samtale")) return { screen: "chat", taskId: null };
  return { screen: "day", taskId: null };
}

const DESK = "(min-width: 1280px)";
export function useIsDesk(): boolean {
  return useSyncExternalStore(
    (cb) => { const mq = window.matchMedia(DESK); mq.addEventListener("change", cb); return () => mq.removeEventListener("change", cb); },
    () => window.matchMedia(DESK).matches, () => false);
}

const ss = {
  get: (k: string) => { try { return sessionStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { sessionStorage.setItem(k, v); } catch { /* ignore */ } },
  del: (k: string) => { try { sessionStorage.removeItem(k); } catch { /* ignore */ } },
};

type Ctx = {
  mode: Mode; simulated: boolean; session: Session; loggedIn: boolean;
  api: PrivatApi; fake: FakePrivat | null;
  balance: Balance | null; tasks: Task[]; day: Day | null; messages: ChatMessage[]; pending: ChatMessage | null; ledger: LedgerEntry[]; addons: Addon[] | null; referrals: Referrals | null; groups: Group[];
  /** GET /privat/subscription (null until loaded or when the backend lacks it – then `balance` may still carry the plan fields). */
  subscription: Subscription | null; setSubscription(s: Subscription | null): void;
  /** Plan rights apply (trial, active or past_due). */
  entitled: boolean;
  task(id: string | null | undefined): Task | undefined;
  addonOn(key: string): boolean;
  draft: string; setDraft(v: string): void;
  focusId: string | null; setFocus(id: string | null): void;
  sheet: Sheet; openSheet(s: Sheet): void; closeSheet(): void;
  note: string; setNote(v: string): void;
  busy: boolean; error: ApiError | null; setError(e: ApiError | null): void;
  refresh(retried?: boolean): Promise<void>;
  /** Run a mutation, then reload everything. Errors land in `error`; the result is then undefined. */
  run<T>(fn: (api: PrivatApi) => Promise<T>): Promise<T | undefined>;
  send(text?: string): Promise<void>;
  /** Send a message about a specific task (e.g. the business's number for a call proposal). */
  sendAbout(text: string, taskId: string): Promise<void>;
  /** The user answered «Hvor skal jeg lede?»: save the location, then resend the request that needed it. */
  saveLocation(body: { city?: string; postcode?: string; lat?: number; lng?: number }): Promise<void>;
  pick(messageId: string, optionId: string): Promise<void>;
  simulatedLogin(): Promise<void>;
  screen: Screen; routeTaskId: string | null; isDesk: boolean;
  openTask(id: string): void; talk(id: string): void; go(s: Screen): void;
  /** Konto with the plan picker open («Vælg plan» everywhere). */
  choosePlan(): void;
  /** «Start 14 dage gratis»: straight to the checkout (Plus, monthly) – the card first, then the trial. */
  startTrial(): Promise<void>;
};
const C = createContext<Ctx | null>(null);
export function usePrivat(): Ctx { const c = useContext(C); if (!c) throw new Error("PrivatProvider mangler"); return c; }

export function PrivatProvider({ session, children }: { session: Session; children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const isDesk = useIsDesk();
  const { screen, taskId: routeTaskId } = screenOf(path);
  const [mode, setMode] = useState<Mode>("loading");
  const apiRef = useRef<PrivatApi>(realPrivat);
  const fakeRef = useRef<FakePrivat | null>(null);
  const [fakeLogin, setFakeLogin] = useState(false);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [day, setDay] = useState<Day | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [addons, setAddons] = useState<Addon[] | null>(null);
  const [referrals, setReferrals] = useState<Referrals | null>(null);
  const [groups, setGroups] = useState<Group[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [draft, setDraft] = useState("");
  const [focusId, setFocus] = useState<string | null>(null);
  const [sheet, setSheet] = useState<Sheet>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const pendingRef = useRef<string | null>(null);

  const loggedIn = session.loggedIn || fakeLogin;

  const refresh = useCallback(async (retried = false): Promise<void> => {
    const a = apiRef.current;
    try { await a.me(); } catch (e) {
      // GETs answer 404 privat_account_missing until the private account exists: create it once and go on.
      if (!retried && (e as ApiError).code === CONFLICT.accountMissing) { await a.account(); return refresh(true); }
      throw e;
    }
    const x = await a.bootstrap();  // one round trip instead of ten
    setBalance(x.me); setDay(x.day); setTasks(x.tasks); setMessages(x.messages); setLedger(x.ledger); setAddons(x.addons);
    setReferrals(x.referrals); setGroups(x.groups); setSubscription(x.subscription);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      const useFake = (key: string, m: Mode) => { const f = createFakePrivat(key); fakeRef.current = f; apiRef.current = f; return m; };
      let m: Mode;
      if (FORCE_FAKE) {
        m = useFake(FAKE_KEY, "fake");
        if (ss.get(FAKE_LOGIN_KEY) === "1") setFakeLogin(true);
      } else if (!session.loggedIn) {
        m = useFake("dialogbot-privat-demo", "demo");
      } else {
        try { await realPrivat.account(); m = "real"; }
        catch (e) {
          if (isUnavailable(e)) { m = useFake(FAKE_KEY, "fake"); }
          else { m = "real"; setError(e as ApiError); }
        }
        const pending = ss.get(PENDING_KEY);
        if (pending) { setDraft(pending); ss.del(PENDING_KEY); }
      }
      if (!alive) return;
      setMode(m);
      try { await refresh(); } catch (e) { setError(e as ApiError); }
    })();
    return () => { alive = false; };
  }, [session.loggedIn, refresh]);

  // Polling: shared lists (others change them) and calls in progress. Only while the page is visible.
  const needsPoll = tasks.some((t) => t.shared || t.status === "in_progress");
  useEffect(() => {
    if (mode === "loading" || !needsPoll) return;
    const id = setInterval(() => { if (document.visibilityState === "visible") refresh().catch(() => {}); }, 5000);
    return () => clearInterval(id);
  }, [mode, needsPoll, refresh]);

  const run = useCallback(async <T,>(fn: (api: PrivatApi) => Promise<T>): Promise<T | undefined> => {
    setBusy(true); setError(null);
    try { const r = await fn(apiRef.current); await refresh(); return r; }
    catch (e) { setError(e as ApiError); try { await refresh(); } catch { /* ignore */ } return undefined; }
    finally { setBusy(false); }
  }, [refresh]);

  const go = useCallback((s: Screen) => {
    const href = { day: "/privat/dag", chat: "/privat/samtale", tasks: "/privat/opgaver", task: "/privat/opgaver", account: "/privat/konto", store: "/privat/butik", addons: "/privat/butik", people: "/privat/folk" }[s];
    router.push(href);
  }, [router]);
  const openTask = useCallback((id: string) => router.push(`/privat/opgaver/${encodeURIComponent(id)}`), [router]);
  const choosePlan = useCallback(() => router.push("/privat/konto?planer=1"), [router]);
  const startTrial = useCallback(async () => {
    if (!loggedIn) { setSheet({ kind: "login" }); return; }
    const r = await run((a) => a.subscriptionCheckout({ plan: "plus", interval: "month" }));
    if (r?.url) window.location.href = r.url;
  }, [loggedIn, run]);
  const talk = useCallback((id: string) => { setFocus(id); if (!isDesk) router.push("/privat/samtale"); }, [isDesk, router]);

  const afterMessages = useCallback((msgs: ChatMessage[]) => {
    setMessages((cur) => [...cur, ...msgs.filter((m) => !cur.some((c) => c.id === m.id))]);
    const d = msgs.find((m) => m.kind === "draft" && m.task_id);
    if (d) setSheet({ kind: "paywall", taskId: d.task_id });
    const withTask = msgs.find((m) => m.task_id && m.kind !== "move");
    if (withTask?.task_id) setFocus(withTask.task_id);
  }, []);

  // The user's line shows at once (a «pending» bubble) and Peter's typing dots run until the API answers; the real
  // messages replace the bubble. On an error the bubble goes and the text returns to the field.
  const [pending, setPending] = useState<ChatMessage | null>(null);
  const doSend = useCallback(async (t: string) => {
    setBusy(true); setError(null);
    setPending({ id: `pending-${Date.now()}`, role: "user", kind: "text", text: t, task_id: null, about_task_id: focusId, before: null, after: null, options: null, links: null, created_at: new Date().toISOString() });
    try {
      const r = await apiRef.current.send(t, focusId);
      setBalance(r.balance);
      afterMessages(r.messages);
      setPending(null);  // the real messages are in place – before the refresh, so the line never shows twice
      await refresh();
    } catch (e) { setError(e as ApiError); setDraft(t); }
    finally { setPending(null); setBusy(false); }
  }, [focusId, afterMessages, refresh]);

  const send = useCallback(async (text?: string) => {
    const t = (text ?? draft).trim();
    if (!t) return;
    if (!loggedIn && !/hvad venter/i.test(t)) {
      pendingRef.current = t;
      ss.set(PENDING_KEY, t);
      setDraft(""); setSheet({ kind: "login" });
      return;
    }
    setDraft("");
    if (screen === "day" || (!isDesk && screen !== "chat")) router.push("/privat/samtale");
    await doSend(t);
  }, [draft, loggedIn, isDesk, screen, router, doSend]);

  const sendAbout = useCallback(async (text: string, taskId: string) => {
    setBusy(true); setError(null);
    try { const r = await apiRef.current.send(text, taskId); setBalance(r.balance); afterMessages(r.messages); await refresh(); }
    catch (e) { setError(e as ApiError); }
    finally { setBusy(false); }
  }, [afterMessages, refresh]);

  const saveLocation = useCallback(async (body: { city?: string; postcode?: string; lat?: number; lng?: number }) => {
    setBusy(true); setError(null);
    try {
      await apiRef.current.setLocation(body);
      const lastUser = [...messages].reverse().find((m) => m.role === "user");
      setBusy(false);
      if (lastUser) await doSend(lastUser.text); else await refresh();
    } catch (e) { setError(e as ApiError); setBusy(false); }
  }, [messages, doSend, refresh]);

  const simulatedLogin = useCallback(async () => {
    ss.set(FAKE_LOGIN_KEY, "1"); ss.del(PENDING_KEY);
    setFakeLogin(true); setSheet(null);
    const p = pendingRef.current; pendingRef.current = null;
    if (p) { if (screen === "day" || (!isDesk && screen !== "chat")) router.push("/privat/samtale"); await doSend(p); }
  }, [doSend, isDesk, screen, router]);

  const pick = useCallback(async (messageId: string, optionId: string) => {
    setBusy(true); setError(null);
    try { const r = await apiRef.current.pickOption(messageId, optionId); setBalance(r.balance); afterMessages(r.messages); await refresh(); }
    catch (e) { setError(e as ApiError); }
    finally { setBusy(false); }
  }, [afterMessages, refresh]);

  const closeSheet = useCallback(() => {
    setSheet((s) => { if (s?.kind === "login" && pendingRef.current) { setDraft(pendingRef.current); pendingRef.current = null; ss.del(PENDING_KEY); } return null; });
  }, []);

  const value = useMemo<Ctx>(() => ({
    mode, simulated: mode === "fake", session, loggedIn, api: apiRef.current, fake: fakeRef.current,
    balance, tasks, day, messages, pending, ledger, addons, referrals, groups, subscription, setSubscription,
    entitled: subscription ? subscription.entitled : !!balance?.entitled,
    task: (id) => (id ? tasks.find((t) => t.id === id) : undefined),
    // Without a catalog (API not there yet) nothing is hidden.
    addonOn: (key) => !addons || addons.length === 0 || !!addons.find((a) => a.key === key)?.enabled || !addons.some((a) => a.key === key),
    draft, setDraft, focusId, setFocus, sheet, openSheet: setSheet, closeSheet, note, setNote, busy, error, setError,
    refresh, run, send, sendAbout, saveLocation, pick, simulatedLogin, screen, routeTaskId, isDesk, openTask, talk, go, choosePlan, startTrial,
  }), [sendAbout, saveLocation, mode, session, loggedIn, balance, tasks, day, messages, ledger, addons, referrals, groups, subscription, draft, focusId, sheet, closeSheet, note, busy, error,
    refresh, run, send, pick, simulatedLogin, screen, routeTaskId, isDesk, openTask, talk, go, choosePlan, startTrial]);

  return <C.Provider value={value}>{children}</C.Provider>;
}

// ---------- subscription view ----------
export type PlanView = {
  plan: SubscriptionPlan; status: SubscriptionStatus; entitled: boolean; trialDays: number; trialTotal: number;
  callsQuota: number; callsUsed: number; callsLeft: number;
  /** The plan whose rights apply («Plus» during the trial) and its name. */
  rightsKey: PlanKey; rightsName: string;
  plans: Plan[]; interval: BillingInterval | null; periodEnd: string | null; cancelAtPeriodEnd: boolean;
  /** kr. per month for a plan key (monthly billing). */
  monthlyKr(key: PlanKey): number;
};
/** One view of the subscription for the UI: GET /subscription when loaded, else the plan fields on /me, else nothing. */
export function usePlan(): PlanView {
  const { subscription: sb, balance: b } = usePrivat();
  return useMemo(() => {
    const plans: Plan[] = sb?.plans?.length ? sb.plans : PLANS.map((p) => ({ key: p.key, name: p.name, monthly_minor: p.monthly * 100, yearly_monthly_minor: p.yearlyMonthly * 100,
      yearly_total_minor: p.yearlyTotal * 100, calls: p.calls, people: p.people, apps_included: p.appsIncluded, recommended: p.recommended, features: p.features }));
    const plan: SubscriptionPlan = sb?.plan ?? b?.plan ?? "none";
    const status: SubscriptionStatus = sb?.status ?? b?.plan_status ?? "none";
    const entitled = sb ? sb.entitled : !!b?.entitled;
    const rightsKey: PlanKey = plan === "none" ? "plus" : plan;
    const rightsName = plans.find((p) => p.key === rightsKey)?.name ?? "Plus";
    return {
      plan, status, entitled, trialDays: sb?.trial_days_left ?? b?.trial_days_left ?? 0, trialTotal: TRIAL_DAYS,
      callsQuota: sb?.calls_quota ?? b?.calls_quota ?? 0, callsUsed: sb?.calls_used ?? b?.calls_used ?? 0, callsLeft: sb?.calls_left ?? b?.calls_left ?? 0,
      rightsKey, rightsName, plans, interval: sb?.interval ?? null, periodEnd: sb?.current_period_end ?? null, cancelAtPeriodEnd: !!sb?.cancel_at_period_end,
      monthlyKr: (key) => Math.round((plans.find((p) => p.key === key)?.monthly_minor ?? 0) / 100),
    };
  }, [sb, b]);
}

// ---------- formatting (Europe/Copenhagen wall clock of the browser) ----------
export function useFmt() {
  const t = useT("privat");
  const locale = useLocale();
  return useMemo(() => {
    const tag = HTML_LANG[locale];
    const time = (iso: string) => new Intl.DateTimeFormat(tag, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
    const offset = (iso: string) => {
      const a = new Date(); a.setHours(0, 0, 0, 0); const b = new Date(iso); b.setHours(0, 0, 0, 0);
      return Math.round((b.getTime() - a.getTime()) / 86_400_000);
    };
    const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
    const weekday = (iso: string) => cap(new Intl.DateTimeFormat(tag, { weekday: "long" }).format(new Date(iso)));
    const when = (iso: string | null | undefined): string => {
      if (!iso) return "";
      const off = offset(iso); const tm = time(iso);
      if (off === 0) return t("when.today", { time: tm });
      if (off === 1) return t("when.tomorrow", { time: tm });
      if (off === -1) return t("when.yesterday", { time: tm });
      if (off > 1 && off < 7) return t("when.weekday", { weekday: weekday(iso), time: tm });
      return t("when.date", { date: new Intl.DateTimeFormat(tag, { day: "numeric", month: "long" }).format(new Date(iso)), time: tm });
    };
    /** Short history stamp: «Nu», «14.12», «I går 14.12», «Mandag 10.03». */
    const stamp = (iso: string): string => {
      if (Date.now() - new Date(iso).getTime() < 90_000) return t("when.now");
      const off = offset(iso); const tm = time(iso);
      if (off === 0) return tm;
      if (off === -1) return t("when.yesterdayShort", { time: tm });
      return `${weekday(iso)} ${tm}`;
    };
    const dateLabel = () => {
      const parts = new Intl.DateTimeFormat(tag, { weekday: "long", day: "numeric", month: "long" }).formatToParts(new Date());
      const get = (k: string) => parts.find((p) => p.type === k)?.value ?? "";
      return t("date.label", { weekday: cap(get("weekday")), day: get("day"), month: get("month") });
    };
    const month = () => new Intl.DateTimeFormat(tag, { month: "long" }).format(new Date());
    const duration = (sec: number | null | undefined) => {
      const s = Math.max(0, sec ?? 0); return t("call.duration", { m: Math.floor(s / 60), s: s % 60 });
    };
    const date = (iso: string) => new Intl.DateTimeFormat(tag, { day: "numeric", month: "long", year: "numeric" }).format(new Date(iso));
    return { time, when, stamp, dateLabel, month, duration, date, offset };
  }, [t, locale]);
}

/** Initials for member avatars. */
export const initials = (name: string) => {
  const n = name.trim();
  if (/^\+?[\d\s-]{6,}$/.test(n)) return n.replace(/\D/g, "").slice(-2); // a phone number: its last two digits
  return n.split(/\s+/).map((p) => p.charAt(0)).join("").slice(0, 2).toUpperCase() || "?";
};
