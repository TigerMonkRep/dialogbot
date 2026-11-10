"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useT } from "@/i18n/client";
import { ADDON, type Task, type TaskStatus } from "@/lib/privat/api";
import { isDanishMobile } from "@/lib/privat/fake";
import { BIG, CHIP, Ex, LINK, SR, TONE } from "./bits";
import { Ico, Tile } from "./icons";
import { useFmt, usePlan, usePrivat } from "./store";
import { Button } from "@/components/ui";
import { currentPushState, enablePush } from "@/lib/privat/push";
import { isStandalone, takeNotifyPending } from "@/lib/install";
import { InstallBanner } from "@/components/install-step";

/** Pill button (Privat: rounded-full everywhere). */
const PILL = "inline-flex items-center justify-center gap-2 rounded-full font-semibold border-2 border-ink min-h-[44px] px-4 text-[15px]";
const PRIMARY = `${PILL} bg-accent text-white hover:bg-accent-deep disabled:opacity-60`;
const OUTLINE = `${PILL} bg-paper text-ink hover:bg-panel`;
export const DAY_CARD = "min-w-0 rounded-[24px] border-2 border-ink bg-paper p-5 flex flex-col gap-3";

/** The three shortcut chips: Mind mig om / Lav en liste / Ring for mig. They fill the composer (never send);
 *  «Ring for mig» only when its add-on is on. */
export function Shortcuts() {
  const t = useT("privat");
  const { setDraft, addonOn } = usePrivat();
  const items: [string, string][] = [["remind", "bell"], ["list", "list"], ...(addonOn(ADDON.call) ? [["call", "phone"] as [string, string]] : [])];
  return (
    <div className="flex gap-2 flex-wrap">
      {items.map(([k, icon]) => (
        <button key={k} type="button" className={CHIP} onClick={() => { setDraft(t(`shortcuts.${k}.text`)); for (const id of ["privat-ask-day", "privat-ask"]) { const el = document.getElementById(id); if (el?.offsetParent) { el.focus(); break; } } }}>
          <Ico name={icon} size={16} />{t(`shortcuts.${k}.label`)}
        </button>
      ))}
    </div>
  );
}

/** Text field + mic (+ send). One draft is shared by Min dag and Samtale; sending from Min dag opens the conversation. */
export function Composer({ withSend = true, id = "privat-ask", quiet = false }: { withSend?: boolean; id?: string; quiet?: boolean }) {
  const t = useT("privat");
  const { draft, setDraft, send, openSheet, focusId, task, busy } = usePrivat();
  return (
    <form onSubmit={(e) => { e.preventDefault(); void send(); }} className="flex gap-2 items-center">
      <label htmlFor={id} className={SR}>{t("day2.inputLabel")}</label>
      <input id={id} value={draft} onChange={(e) => setDraft(e.target.value)} autoComplete="off" enterKeyHint="send"
        placeholder={focusId && task(focusId) ? t("day.placeholderFocus") : t("day.placeholder")}
        className="flex-1 min-w-0 min-h-[52px] rounded-full border-2 border-ink px-5 text-[16px] bg-paper text-ink placeholder:text-muted" />
      <button type="button" onClick={() => openSheet({ kind: "mic" })} aria-label={t("day.micAria")}
        className="inline-flex items-center justify-center w-[52px] h-[52px] rounded-full border-2 border-ink bg-paper hover:bg-panel shrink-0"><Ico name="mic" size={22} /></button>
      {withSend ? (
        <button type="submit" aria-label={t("day.sendAria")} disabled={busy}
          className={`inline-flex items-center justify-center h-[52px] min-w-[52px] px-0 sm:px-5 rounded-full border-2 border-ink shrink-0 disabled:opacity-60 font-semibold text-[15px] ${quiet ? "bg-paper text-ink hover:bg-panel" : "bg-accent text-white hover:bg-accent-deep"}`}>
          <span className="hidden sm:inline">{t("day2.send")}</span><Ico name="send" size={22} stroke={2.4} /></button>
      ) : <button type="submit" className={SR}>{t("day.sendAria")}</button>}
    </form>
  );
}

/** Peter at the bottom of Min dag (thumb zone, sticky over the tabs on a phone). Empty day: Peter's greeting and the
 *  three shortcuts; otherwise only the composer. Its send button is quiet when «Din tur» holds the screen's one primary. */
function AskDock({ empty, quiet }: { empty: boolean; quiet: boolean }) {
  const t = useT("privat");
  const { mode } = usePrivat();
  return (
    <div className="sticky bottom-0 z-10 -mx-4 px-4 pt-3 pb-3 bg-paper border-t-2 border-ink xl:static xl:mx-0 xl:px-0 xl:pb-0 xl:border-t-0 flex flex-col gap-3" data-testid="day-chat-card">
      {(empty || mode === "demo") && (
        <>
          <p className="m-0 self-start max-w-[34rem] bg-panel rounded-[18px_18px_18px_6px] px-4 py-3 text-[16px] leading-[1.45] [overflow-wrap:anywhere]">{mode === "demo" ? t("day2.greetingDemo") : t("day2.greetingShort")}</p>
          <Shortcuts />
        </>
      )}
      <Composer id="privat-ask-day" quiet={quiet} />
    </div>
  );
}

/** «Din tur»: the first task that waits for the user. «Ja, ring» approves a call proposal straight away when nothing
 *  else is needed (number known, phone verified, rights or credits in place); otherwise it opens the full card. */
function YourTurn() {
  const t = useT("privat");
  const { day, tasks, talk, openSheet, balance, addonOn, api, refresh, setError } = usePrivat();
  const plan = usePlan();
  const aw = day?.awaiting ?? tasks.filter((x) => x.status === "awaiting_user" || x.status === "draft");
  const x = aw[0];
  const [busy, setBusy] = useState(false);
  const c = x?.call ?? null;
  const proposal = !!x && x.kind === "call" && x.status === "awaiting_user" && !!c && !c.result && !x.is_example;
  const quick = async () => {
    if (!x || !c) return;
    const mobile = c.is_mobile ?? isDanishMobile(c.phone_e164);
    const rights = plan.entitled && plan.callsLeft > 0;
    const simple = addonOn(ADDON.call) && !!balance?.phone_verified && !!c.phone_e164 && !mobile && c.open_now !== false && (rights || (balance?.credits ?? 0) >= c.max_credits);
    if (!simple) { talk(x.id); return; }
    setBusy(true); setError(null);
    try { await api.approveCall(x.id, { window: c.window, share_phone: c.share_phone }); await refresh(); }
    catch { talk(x.id); }
    finally { setBusy(false); }
  };
  const usage = x ? (plan.entitled && plan.callsQuota > 0 && x.kind === "call" ? t("day2.callQuota", { used: plan.callsUsed + 1, quota: plan.callsQuota, plan: plan.rightsName }) : x.usage_text) : "";
  if (!x) return null;
  return (
    <section className={`${DAY_CARD} shadow-block`} data-testid="your-turn" aria-labelledby="your-turn-h">
      <span className="eyebrow">{aw.length > 1 ? t("day2.yourTurnOf", { n: aw.length }) : t("day2.yourTurn")}</span>
      <h2 id="your-turn-h" className="m-0 font-display font-extrabold text-[21px] leading-tight [overflow-wrap:anywhere]">{x.title}{x.is_example && <> <Ex /></>}</h2>
      <p className="m-0 text-[15px] leading-[1.45] text-ink-soft [overflow-wrap:anywhere]">{proposal && c ? t("call.ask", { name: c.business_name }) : x.next_step}</p>
      {proposal ? <Button className={`${BIG} rounded-full w-full sm:w-auto sm:self-start`} disabled={busy} onClick={quick}>{t("day2.yesCall")}</Button>
        : x.status === "draft" ? <Button className={`${BIG} rounded-full w-full sm:w-auto sm:self-start`} onClick={() => openSheet({ kind: "paywall", taskId: x.id })}>{t("day2.chooseHow")}</Button>
        : <Button className={`${BIG} rounded-full w-full sm:w-auto sm:self-start`} onClick={() => talk(x.id)}>{t("day2.answer")}</Button>}
      <div className="flex items-center gap-4 flex-wrap">
        <button type="button" onClick={() => talk(x.id)} className={LINK}>{t("day2.editPlan")}</button>
        {usage && <span className="text-[13px] text-muted">{usage}</span>}
      </div>
    </section>
  );
}

type Filter = "all" | "awaiting" | "planned" | "done";
const FILTERS: Record<Filter, TaskStatus[] | null> = {
  all: null, awaiting: ["awaiting_user", "draft"], planned: ["planned", "in_progress", "awaiting_business"], done: ["done", "declined"],
};
const ORDER: Record<TaskStatus, number> = { awaiting_user: 0, draft: 0, in_progress: 1, planned: 2, awaiting_business: 3, done: 4, declined: 5 };

/** Status pill with the short Min dag wording (Afventer dig = yellow, Planlagt = white, Klaret = green). */
export function DayPill({ task }: { task: Task }) {
  const t = useT("privat");
  const k = task.status === "awaiting_user" || task.status === "draft" ? "awaiting" : task.status === "planned" ? "planned" : task.status === "in_progress" ? "inProgress"
    : task.status === "awaiting_business" ? "business" : task.status === "done" ? "done" : "declined";
  return <span className={`inline-flex items-center min-h-6 px-2.5 rounded-full border-[1.5px] text-[12px] font-semibold whitespace-nowrap ${TONE[task.status]}`}>{t(`day2.pill.${k}`)}</span>;
}

function TaskRow({ task }: { task: Task }) {
  const t = useT("privat");
  const f = useFmt();
  const { openTask } = usePrivat();
  const icon = task.kind === "list" ? "list" : task.kind === "reminder" ? "bell" : "phone";
  const others = (task.members ?? []).filter((m) => !m.is_me).map((m) => m.name);
  const sub = task.kind === "list"
    ? [t("day2.listProgress", { done: task.items.filter((i) => i.done).length, n: task.items.length }), others.length ? t("day2.sharedWith", { names: others.join(", ") }) : ""]
    : task.status === "planned" ? [f.when(task.remind_at ?? task.due_at) || task.next_step]
    : [task.next_step, task.status === "awaiting_user" && task.kind === "call" ? task.usage_text : ""];
  return (
    <li>
      <button type="button" onClick={() => openTask(task.id)} aria-label={t("day2.openAria", { title: task.title })}
        className="w-full flex items-center gap-3 text-left rounded-[18px] border-2 border-ink bg-paper px-3.5 py-3 text-ink hover:bg-panel">
        <Tile name={icon} size={38} className={`rounded-[12px] border-2 border-ink ${task.status === "done" ? "bg-success-soft text-ink" : task.status === "awaiting_user" || task.status === "draft" ? "bg-highlight text-ink" : "bg-paper text-ink"}`} />
        <span className="flex-1 min-w-0 flex flex-col gap-0.5">
          <span className="font-semibold text-[15px] line-clamp-1 [overflow-wrap:anywhere]">{task.title}</span>
          <span className="text-[13px] text-ink-soft line-clamp-1 [overflow-wrap:anywhere]" suppressHydrationWarning>{sub.filter(Boolean).join(" · ")}{task.is_example && <> <Ex /></>}</span>
        </span>
      </button>
    </li>
  );
}

/** «Dine opgaver»: at most three open tasks (what waits for the user is in «Din tur»), nearest first, and «Alle opgaver».
 *  Hidden when there is nothing open. */
function TodaySection() {
  const t = useT("privat");
  const { tasks, go } = usePrivat();
  const open = tasks.filter((x) => ["planned", "in_progress", "awaiting_business"].includes(x.status))
    .sort((a, b) => (a.remind_at ?? a.due_at ?? "9").localeCompare(b.remind_at ?? b.due_at ?? "9") || ORDER[a.status] - ORDER[b.status]);
  if (open.length === 0) return null;
  return (
    <section className="flex flex-col gap-2.5" aria-labelledby="day-tasks">
      <div className="flex items-center gap-3">
        <h2 id="day-tasks" className="m-0 font-display font-extrabold text-[20px] tracking-[-0.3px]">{t("day2.tasksTitle")}</h2>
        <span className="flex-1" />
        <button type="button" onClick={() => go("tasks")} className={`${LINK} whitespace-nowrap`}>{t("day2.allTasks")}</button>
      </div>
      <ul className="m-0 p-0 list-none flex flex-col gap-2">
        {open.slice(0, 3).map((x) => <TaskRow key={x.id} task={x} />)}
      </ul>
    </section>
  );
}

function Bar({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div className="h-3 border-2 border-ink rounded-full overflow-hidden bg-paper" role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label}>
      <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
    </div>
  );
}

/** «Dit råderum»: calls left, trial days left (or the plan), «Vælg plan». Without rights: the free quota and credits. */
export function RoomCard() {
  const t = useT("privat");
  const { balance, choosePlan, startTrial } = usePrivat();
  const p = usePlan();
  const eyebrow = p.status === "trial" ? t("day2.room.trialEyebrow", { plan: p.rightsName }) : p.entitled ? t("day2.room.planEyebrow", { plan: p.rightsName, status: t(`plan.status.${p.status}`) }) : t("day2.room.freeEyebrow");
  return (
    <aside className={`${DAY_CARD} shadow-block-sm`} aria-labelledby="room-h" data-testid="room-card">
      <span className="eyebrow">{eyebrow}</span>
      <h2 id="room-h" className="m-0 font-display font-extrabold text-[22px]">{t("day2.room.title")}</h2>
      {p.entitled ? (
        <>
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between text-[14px]"><span>{t("day2.room.callsLeft")}</span><strong>{t("day2.room.callsValue", { left: p.callsLeft, quota: p.callsQuota })}</strong></div>
            <Bar value={p.callsLeft} max={p.callsQuota} label={t("day2.room.callsAria", { left: p.callsLeft, quota: p.callsQuota })} />
          </div>
          {p.status === "trial" && (
            <div className="flex flex-col gap-1.5">
              <div className="flex justify-between text-[14px]"><span>{t("day2.room.trial")}</span><strong>{t("day2.room.trialDays", { n: p.trialDays })}</strong></div>
              <Bar value={p.trialDays} max={p.trialTotal} label={t("day2.room.trialAria", { n: p.trialDays, total: p.trialTotal })} />
            </div>
          )}
          <p className="m-0 text-[13px] text-muted leading-normal">{p.status === "trial" ? t("day2.room.noteTrial", { plan: p.rightsName, price: p.monthlyText(p.rightsKey) }) : t("day2.room.notePlan")}</p>
          <button type="button" className={`${p.plan === "none" ? PRIMARY : OUTLINE} self-start`} onClick={choosePlan}>{p.plan === "none" ? t("day2.room.choosePlan") : t("day2.room.changePlan")}</button>
        </>
      ) : (
        <>
          {p.status !== "none" && <div className="flex justify-between text-[14px]"><span>{t("day2.room.extraCalls")}</span><strong>{balance?.credits ?? 0}</strong></div>}
          <p className="m-0 text-[13px] text-muted leading-normal">{t(p.status === "none" ? "day2.room.noteNone" : "day2.room.noteFree")}</p>
          {p.status === "none"
            ? <button type="button" className={`${PRIMARY} self-start`} onClick={() => void startTrial()}>{t("day2.room.startTrial")}</button>
            : <button type="button" className={`${PRIMARY} self-start`} onClick={choosePlan}>{t("day2.room.choosePlan")}</button>}
        </>
      )}
    </aside>
  );
}

/** Min dag (/privat/dag): the question, «Din tur» (only when something waits – the screen's one primary), «I dag»
 *  (≤ 3 rows) and Peter at the bottom. The plan meter lives on Konto, the apps on the Apps tab (ux-audit #2). The
 *  install step comes after the first own task, never on first paint. */
export function DayPage() {
  const t = useT("privat");
  const { mode, tasks, day } = usePrivat();
  // «Own» = made by this user – a list someone shared with a guest does not earn the install step (ux-audit #3).
  const own = tasks.some((x) => !x.is_example && (!x.my_role || x.my_role === "owner"));
  const waiting = (day?.awaiting ?? tasks.filter((x) => x.status === "awaiting_user" || x.status === "draft")).length > 0;
  return (
    <div className="w-full max-w-[760px] mx-auto px-4 pt-5 min-h-full flex flex-col gap-5">
      <h1 id="day-ask" className="m-0 font-display font-extrabold text-[30px] xl:text-[40px] leading-[1.08] tracking-[-0.6px]">{t("day.ask")}</h1>
      {mode === "loading" && <p className="m-0 text-[14px] text-muted" role="status">{t("common.loading")}</p>}
      <PlanNotice />
      <Suspense><WelcomeBanner /></Suspense>
      <InstalledBanner />
      <YourTurn />
      <TodaySection />
      {own && <FirstOpenInstall />}
      <span className="flex-1" />
      <AskDock empty={mode !== "loading" && tasks.length === 0} quiet={waiting} />
    </div>
  );
}

/** One yellow line when the plan needs the user (trial over, payment missing) – the plan meter itself lives on Konto. */
function PlanNotice() {
  const t = useT("privat");
  const { choosePlan } = usePrivat();
  const p = usePlan();
  if (p.status !== "expired" && p.status !== "past_due") return null;
  return (
    <div role="status" className="flex items-center gap-3 flex-wrap rounded-xl border-[1.5px] border-ink bg-highlight px-3.5 py-2" data-testid="plan-notice">
      <span className="flex-1 min-w-[12rem] text-[15px] font-semibold">{p.status === "expired" ? t("plan.status.expired") : t("plan.pastDue")}</span>
      <Button variant="outline" className="rounded-full" onClick={choosePlan}>{t("day2.room.choosePlan")}</Button>
    </div>
  );
}

/** One-time banner after the Privat funnel (/privat/dag?velkommen=1): Peter has set the day up – the first call waits
 *  in «Din tur». Closing it is local; the query is not re-read. */
function WelcomeBanner() {
  const t = useT("privat");
  const params = useSearchParams();
  const [open, setOpen] = useState(params.get("velkommen") === "1");
  if (!open) return null;
  return (
    <div role="status" data-welcome className="flex items-center gap-2 rounded-xl border-[1.5px] border-ink bg-highlight pl-3 pr-1 py-1">
      <span className="flex-1 min-h-[44px] inline-flex items-center text-[15px] font-semibold">{t("day.welcomeFunnel")}</span>
      <button type="button" onClick={() => setOpen(false)} aria-label={t("list.welcomeDismiss")} className="w-11 h-11 inline-flex items-center justify-center shrink-0"><Ico name="close" size={18} /></button>
    </div>
  );
}

/** The installed app's first open after «Download app»: the one tap that turns notifications on (web push needs a tap
 *  inside the home-screen app on iPhone; on Android it may already be on, then nothing shows). */
function InstalledBanner() {
  const t = useT("privat");
  const { api, refresh } = usePrivat();
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!isStandalone() || !takeNotifyPending()) return;
    currentPushState().then((s) => { if (s === "default") setShow(true); });
  }, []);
  if (!show) return null;
  const on = async () => { setBusy(true); try { await enablePush(api); await refresh(); } finally { setBusy(false); setShow(false); } };
  return (
    <div role="status" data-testid="installed-banner" className="flex items-center gap-2 flex-wrap rounded-xl border-[1.5px] border-ink bg-highlight pl-3 pr-2 py-2">
      <span className="flex-1 min-w-[200px] text-[15px] font-semibold">{t("push.installedAsk")}</span>
      <Button className="rounded-full border-2 border-ink" onClick={on} disabled={busy}>{t("push.enable")}</Button>
      <button type="button" onClick={() => setShow(false)} aria-label={t("list.welcomeDismiss")} className="w-11 h-11 inline-flex items-center justify-center shrink-0"><Ico name="close" size={18} /></button>
    </div>
  );
}

/** The first open of Min dag with a login (the funnel ends here – its last step is the app on the home screen):
 *  the install step, once-dismissible, never in the installed app and never for a visitor looking at example data. */
function FirstOpenInstall() {
  const { api, refresh, loggedIn, mode } = usePrivat();
  if (!loggedIn || mode === "loading" || mode === "demo") return null;
  return <InstallBanner audience="privat" enableNotifications={() => enablePush(api).then(() => refresh())} />;
}

/** Old name, kept for imports. */
export const DayPane = DayPage;
