"use client";
import { useState } from "react";
import { useT } from "@/i18n/client";
import { ADDON, type Task, type TaskStatus } from "@/lib/privat/api";
import { isDanishMobile } from "@/lib/privat/fake";
import { CHIP, Ex, SR, TONE } from "./bits";
import { Ico, Tile } from "./icons";
import { useFmt, usePlan, usePrivat } from "./store";

/** Pill button (Privat: rounded-full everywhere). */
const PILL = "inline-flex items-center justify-center gap-2 rounded-full font-semibold border-2 border-ink min-h-[44px] px-4 text-[15px]";
const PRIMARY = `${PILL} bg-accent text-white hover:bg-accent-deep disabled:opacity-60`;
const OUTLINE = `${PILL} bg-paper text-ink hover:bg-panel`;
export const DAY_CARD = "rounded-[24px] border-2 border-ink bg-paper p-5 flex flex-col gap-3";

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
export function Composer({ withSend = true, id = "privat-ask" }: { withSend?: boolean; id?: string }) {
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
          className="inline-flex items-center justify-center h-[52px] min-w-[52px] px-0 sm:px-5 rounded-full border-2 border-ink bg-accent text-white hover:bg-accent-deep shrink-0 disabled:opacity-60 font-semibold text-[15px]">
          <span className="hidden sm:inline">{t("day2.send")}</span><Ico name="send" size={22} stroke={2.4} /></button>
      ) : <button type="submit" className={SR}>{t("day.sendAria")}</button>}
    </form>
  );
}

/** «Hvad skal jeg klare for dig?» – Peter's card with greeting, chips and the composer. */
function ChatCard() {
  const t = useT("privat");
  const { mode } = usePrivat();
  return (
    <div className={`${DAY_CARD} shadow-block`} data-testid="day-chat-card">
      <div className="flex items-center gap-3">
        <span className="w-11 h-11 rounded-full bg-accent text-white border-2 border-ink font-display font-extrabold text-[18px] inline-flex items-center justify-center shrink-0" aria-hidden>P</span>
        <span className="flex flex-col min-w-0"><span className="font-display font-bold text-[17px]">{t("day2.peter")}</span><span className="text-[13px] text-muted">{t("day2.peterRole")}</span></span>
        <span className="flex-1" />
        <span className="inline-flex items-center gap-1.5 min-h-6 px-2.5 rounded-full border-[1.5px] border-success bg-success-soft text-success text-[11px] font-semibold uppercase tracking-[0.06em]"><span className="w-2 h-2 rounded-full bg-success" aria-hidden />{t("day2.ready")}</span>
      </div>
      <div className="flex items-start gap-2.5">
        <span className="w-7 h-7 rounded-full bg-panel-deep border-[1.5px] border-ink font-display font-extrabold text-[12px] inline-flex items-center justify-center shrink-0 mt-0.5" aria-hidden>P</span>
        <p className="m-0 bg-panel rounded-[18px_18px_18px_6px] px-4 py-3 text-[16px] leading-[1.45] [overflow-wrap:anywhere]">{mode === "demo" ? t("day2.greetingDemo") : t("day2.greeting")}</p>
      </div>
      <Shortcuts />
      <Composer id="privat-ask-day" />
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
  return (
    <div className={`${DAY_CARD} bg-panel`} data-testid="your-turn">
      <div className="flex items-center gap-2">
        <span className="w-8 h-8 rounded-full bg-highlight border-2 border-ink inline-flex items-center justify-center" aria-hidden><Ico name="bell" size={16} /></span>
        <span className="eyebrow">{t("day2.yourTurn")}</span>
        <span className="flex-1" />
        <span className="text-[13px] font-semibold text-muted">{t("day2.yourTurnCount", { n: aw.length })}</span>
      </div>
      {x ? (
        <>
          <h2 className="m-0 font-display font-extrabold text-[22px] leading-tight">{t("day2.awaiting")}</h2>
          <p className="m-0 text-[16px] leading-[1.45] [overflow-wrap:anywhere]"><b>{x.title}.</b> {proposal && c ? t("call.ask", { name: c.business_name }) : x.next_step}{x.is_example && <> <Ex /></>}</p>
          <div className="flex gap-2 flex-wrap">
            {proposal ? <button type="button" className={PRIMARY} disabled={busy} onClick={quick}>{t("day2.yesCall")}</button>
              : x.status === "draft" ? <button type="button" className={PRIMARY} onClick={() => openSheet({ kind: "paywall", taskId: x.id })}>{t("day2.chooseHow")}</button>
              : <button type="button" className={PRIMARY} onClick={() => talk(x.id)}>{t("day2.answer")}</button>}
            <button type="button" className={OUTLINE} onClick={() => talk(x.id)}>{t("day2.editPlan")}</button>
          </div>
          {usage && <span className="text-[13px] text-muted">{usage}</span>}
        </>
      ) : (
        <>
          <h2 className="m-0 font-display font-extrabold text-[22px] leading-tight">{t("day2.nothingWaiting")}</h2>
          <p className="m-0 text-[15px] text-ink-soft">{t("day2.nothingWaitingText")}</p>
        </>
      )}
    </div>
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
        <DayPill task={task} />
      </button>
    </li>
  );
}

/** «Dine opgaver» with the filter chips. Shows the first eight; «Se alle →» opens Mine opgaver. */
function TasksSection() {
  const t = useT("privat");
  const f = useFmt();
  const { tasks, go, mode } = usePrivat();
  const [filter, setFilter] = useState<Filter>("all");
  const st = FILTERS[filter];
  const list = tasks.filter((x) => !st || st.includes(x.status)).sort((a, b) => ORDER[a.status] - ORDER[b.status] || (a.due_at ?? "9").localeCompare(b.due_at ?? "9"));
  return (
    <section className="flex flex-col gap-3" aria-labelledby="day-tasks">
      <div className="flex items-end gap-3">
        <div className="flex flex-col gap-0.5 min-w-0">
          <span className="eyebrow" suppressHydrationWarning>{f.dateLabel()}</span>
          <h2 id="day-tasks" className="m-0 font-display font-extrabold text-[24px] tracking-[-0.4px]">{t("day2.tasksTitle")}</h2>
        </div>
        <span className="flex-1" />
        <button type="button" onClick={() => go("tasks")} className="min-h-[44px] text-[15px] font-semibold text-accent underline underline-offset-[3px] hover:text-accent-deep whitespace-nowrap">{t("day2.seeAll")}</button>
      </div>
      <div className="flex gap-2 flex-wrap" role="group" aria-label={t("day2.tasksTitle")}>
        {(Object.keys(FILTERS) as Filter[]).map((k) => (
          <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}
            className={`${CHIP} min-h-[40px] ${filter === k ? "!bg-ink !text-paper" : ""}`}>{t(`day2.filter.${k}`)}</button>
        ))}
      </div>
      {mode !== "loading" && list.length === 0 && <p className="m-0 text-[15px] text-muted">{filter === "all" ? t("day2.emptyAll") : t("day2.empty")}</p>}
      <ul className="m-0 p-0 list-none flex flex-col gap-2">
        {list.slice(0, 8).map((x) => <TaskRow key={x.id} task={x} />)}
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
  const { balance, addons, openSheet, choosePlan } = usePrivat();
  const p = usePlan();
  const limit = balance?.free_limit ?? 10;
  const freeLeft = Math.max(0, limit - (balance?.free_used ?? 0));
  const eyebrow = p.status === "trial" ? t("day2.room.trialEyebrow", { plan: p.rightsName }) : p.entitled ? t("day2.room.planEyebrow", { plan: p.rightsName, status: t(`plan.status.${p.status}`) }) : t("day2.room.freeEyebrow");
  const fresh = addons?.find((a) => !a.enabled && a.status !== "coming_soon" && a.requires_plan);
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
          <p className="m-0 text-[13px] text-muted leading-normal">{p.status === "trial" ? t("day2.room.noteTrial", { plan: p.rightsName, price: p.monthlyKr(p.rightsKey) }) : t("day2.room.notePlan")}</p>
          <button type="button" className={`${p.plan === "none" ? PRIMARY : OUTLINE} self-start`} onClick={choosePlan}>{p.plan === "none" ? t("day2.room.choosePlan") : t("day2.room.changePlan")}</button>
        </>
      ) : (
        <>
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between text-[14px]"><span>{t("day2.room.freeLeft")}</span><strong>{freeLeft} / {limit}</strong></div>
            <Bar value={freeLeft} max={limit} label={t("account.freeBarAria", { used: balance?.free_used ?? 0, limit })} />
          </div>
          <div className="flex justify-between text-[14px]"><span>{t("day2.room.extraCalls")}</span><strong>{balance?.credits ?? 0}</strong></div>
          <p className="m-0 text-[13px] text-muted leading-normal">{t("day2.room.noteFree", { limit })}</p>
          <button type="button" className={`${PRIMARY} self-start`} onClick={choosePlan}>{p.status === "none" ? t("day2.room.startTrial") : t("day2.room.choosePlan")}</button>
        </>
      )}
      {fresh && (
        <button type="button" onClick={() => openSheet({ kind: "addon", addonKey: fresh.key })} className="mt-1 flex items-center gap-3 text-left rounded-[18px] border-[1.5px] border-ink bg-panel px-3 py-2.5 hover:bg-panel-deep">
          <span className="flex-1 min-w-0 flex flex-col"><span className="eyebrow text-[11px]">{t("day2.room.newInStore")}</span><span className="font-semibold text-[15px]">{fresh.name}</span><span className="text-[13px] text-ink-soft line-clamp-1">{fresh.tagline}</span></span>
          <span className="text-[14px] font-semibold text-accent whitespace-nowrap">{t("day2.room.see")}</span>
        </button>
      )}
    </aside>
  );
}

/** Min dag (/privat/dag): the question with Peter's card, «Din tur», «Dine opgaver» and «Dit råderum». */
export function DayPage() {
  const t = useT("privat");
  const { mode } = usePrivat();
  return (
    <div className="w-full max-w-[1160px] mx-auto px-4 pt-5 pb-8 flex flex-col gap-7">
      <section className="flex flex-col gap-4" aria-labelledby="day-ask">
        <div className="flex flex-col gap-1.5">
          <p className="eyebrow m-0 hidden xl:block">{t("day2.eyebrow")}</p>
          <h1 id="day-ask" className="m-0 font-display font-extrabold text-[30px] xl:text-[40px] leading-[1.08] tracking-[-0.6px]">{t("day.ask")}</h1>
          <p className="m-0 text-[16px] text-ink-soft hidden xl:block">{t("day2.lead")}</p>
        </div>
        {mode === "loading" && <p className="m-0 text-[14px] text-muted" role="status">{t("common.loading")}</p>}
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px] xl:gap-6 items-start">
          <ChatCard />
          <YourTurn />
        </div>
      </section>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px] xl:gap-6 items-start">
        <TasksSection />
        <RoomCard />
      </div>
    </div>
  );
}

/** Old name, kept for imports. */
export const DayPane = DayPage;
