"use client";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import { ADDON, type Task } from "@/lib/privat/api";
import { CHIP, Ex, ROW, SR, StatusBadge } from "./bits";
import { Ico } from "./icons";
import { useFmt, usePrivat } from "./store";

/** The four shortcut chips. They fill the composer (never send). «Ring for mig» only when its add-on is on. */
export function Shortcuts() {
  const t = useT("privat");
  const { setDraft, addonOn } = usePrivat();
  const items: [string, string][] = [["remind", ""], ["list", ""], ...(addonOn(ADDON.call) ? [["call", ""] as [string, string]] : []), ["waiting", ""]];
  return (
    <div className="flex gap-2 flex-wrap">
      {items.map(([k]) => (
        <button key={k} type="button" className={CHIP} onClick={() => { setDraft(t(`shortcuts.${k}.text`)); for (const id of ["privat-ask-day", "privat-ask"]) { const el = document.getElementById(id); if (el?.offsetParent) { el.focus(); break; } } }}>{t(`shortcuts.${k}.label`)}</button>
      ))}
    </div>
  );
}

/** Text field + mic (+ send). One draft is shared by Min dag and Samtale. */
export function Composer({ withSend = true, id = "privat-ask" }: { withSend?: boolean; id?: string }) {
  const t = useT("privat");
  const { draft, setDraft, send, openSheet, focusId, task, busy } = usePrivat();
  return (
    <form onSubmit={(e) => { e.preventDefault(); void send(); }} className="flex gap-2 items-center">
      <label htmlFor={id} className={SR}>{t("day.inputLabel")}</label>
      <input id={id} value={draft} onChange={(e) => setDraft(e.target.value)} autoComplete="off" enterKeyHint="send"
        placeholder={focusId && task(focusId) ? t("day.placeholderFocus") : t("day.placeholder")}
        className="flex-1 min-w-0 min-h-[52px] rounded-[14px] border-2 border-ink px-3.5 text-[16px] bg-paper text-ink placeholder:text-muted" />
      <button type="button" onClick={() => openSheet({ kind: "mic" })} aria-label={t("day.micAria")}
        className="inline-flex items-center justify-center w-[52px] h-[52px] rounded-xl border-2 border-ink bg-paper hover:bg-panel shrink-0"><Ico name="mic" size={22} /></button>
      {withSend ? (
        <button type="submit" aria-label={t("day.sendAria")} disabled={busy}
          className="inline-flex items-center justify-center w-[52px] h-[52px] rounded-xl border-2 border-ink bg-accent text-white hover:bg-accent-deep shrink-0 disabled:opacity-60"><Ico name="send" size={22} stroke={2.4} /></button>
      ) : <button type="submit" className={SR}>{t("day.sendAria")}</button>}
    </form>
  );
}

function AwaitingRow({ task }: { task: Task }) {
  const t = useT("privat");
  const { openTask } = usePrivat();
  return (
    <button type="button" className={`${ROW} border-2 shadow-block-sm`} onClick={() => openTask(task.id)}>
      <span className="flex-1 min-w-0 flex flex-col gap-1.5">
        <span className="flex gap-1.5 items-center flex-wrap"><StatusBadge task={task} />{task.is_example && <Ex />}</span>
        <span className="font-semibold text-[16px] line-clamp-2 [overflow-wrap:anywhere]">{task.title}</span>
        <span className="text-[14px] text-ink-soft [overflow-wrap:anywhere]">{t("day.next", { next: task.next_step })}</span>
      </span>
      <Ico name="chevron" size={20} className="mt-1" />
    </button>
  );
}

export function DayPane() {
  const t = useT("privat");
  const f = useFmt();
  const { day, go, mode } = usePrivat();
  const aw = day?.awaiting ?? [], today = day?.today ?? [], soon = day?.soon ?? [];
  const empty = !!day && !aw.length && !today.length && !soon.length;
  return (
    <div className="px-4 pt-5 pb-7 flex flex-col gap-[22px]">
      <div className="flex flex-col gap-3 xl:hidden">
        <p className="eyebrow m-0" suppressHydrationWarning>{f.dateLabel()}</p>
        <h1 className="m-0 font-display font-extrabold text-[30px] leading-[1.1] tracking-[-0.5px]">{t("day.ask")}</h1>
        <Composer withSend={false} id="privat-ask-day" />
        <Shortcuts />
      </div>
      <div className="hidden xl:block">
        <p className="eyebrow m-0" suppressHydrationWarning>{f.dateLabel()}</p>
        <h2 className="m-0 mt-1 font-display font-extrabold text-[28px] tracking-[-0.5px]">{t("day.title")}</h2>
      </div>
      {mode === "loading" && <p className="m-0 text-[14px] text-muted" role="status">{t("common.loading")}</p>}
      {empty && (
        <div className="rounded-[18px] border-2 border-ink bg-panel p-4 flex flex-col gap-2.5">
          <h3 className="m-0 font-display font-bold text-[20px]">{t("day.emptyTitle")}</h3>
          <p className="m-0 text-[15px] text-ink-soft leading-normal">{t("day.emptyText")}</p>
        </div>
      )}
      {aw.length > 0 && (
        <section className="flex flex-col gap-2.5" aria-labelledby="day-awaiting">
          <div className="flex items-center gap-2">
            <span className="w-7 h-7 rounded-lg bg-highlight inline-flex items-center justify-center font-display font-extrabold text-[14px]">{aw.length}</span>
            <h2 id="day-awaiting" className="m-0 font-display font-bold text-[20px]">{t("day.awaiting")}</h2>
          </div>
          {aw.map((x) => <AwaitingRow key={x.id} task={x} />)}
        </section>
      )}
      {today.length > 0 && (
        <section className="flex flex-col gap-2.5" aria-labelledby="day-today">
          <h2 id="day-today" className="m-0 font-display font-bold text-[20px]">{t("day.today")}</h2>
          {today.map((x) => <TodayRow key={x.id} task={x} />)}
        </section>
      )}
      {soon.length > 0 && (
        <section className="flex flex-col gap-2.5" aria-labelledby="day-soon">
          <h2 id="day-soon" className="m-0 font-display font-bold text-[20px]">{t("day.soon")}</h2>
          {soon.map((x) => <SoonRow key={x.id} task={x} />)}
        </section>
      )}
      <div className="hidden xl:flex gap-2 flex-wrap border-t-[1.5px] border-line pt-4">
        <Button variant="outline" onClick={() => go("tasks")}>{t("day.myTasks")}</Button>
        <Button variant="outline" onClick={() => go("account")}>{t("day.accountBtn")}</Button>
      </div>
    </div>
  );
}

function TodayRow({ task }: { task: Task }) {
  const t = useT("privat");
  const f = useFmt();
  const { openTask } = usePrivat();
  const at = task.remind_at ?? task.due_at;
  return (
    <button type="button" className={ROW} onClick={() => openTask(task.id)}>
      <span className="min-w-[58px] font-display font-bold text-[15px]" suppressHydrationWarning>{at ? f.time(at) : t("when.noTime")}</span>
      <span className="flex-1 min-w-0 flex flex-col gap-1">
        <span className="font-semibold text-[15px] line-clamp-2 [overflow-wrap:anywhere]">{task.title}</span>
        <span className="flex gap-1.5 items-center flex-wrap"><StatusBadge task={task} />{task.is_example && <Ex />}</span>
      </span>
    </button>
  );
}

function SoonRow({ task }: { task: Task }) {
  const f = useFmt();
  const { openTask } = usePrivat();
  return (
    <button type="button" className={ROW} onClick={() => openTask(task.id)}>
      <span className="flex-1 min-w-0 flex flex-col gap-1">
        <span className="font-semibold text-[15px] line-clamp-2 [overflow-wrap:anywhere]">{task.title}</span>
        <span className="text-[14px] text-ink-soft [overflow-wrap:anywhere]" suppressHydrationWarning>{[f.when(task.remind_at ?? task.due_at), task.who].filter(Boolean).join(" · ")}</span>
        <span className="flex gap-1.5 items-center flex-wrap"><StatusBadge task={task} />{task.is_example && <Ex />}</span>
      </span>
    </button>
  );
}
