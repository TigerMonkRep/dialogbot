"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button, ErrorBox } from "@/components/ui";
import { useT } from "@/i18n/client";
import { icsHref, type Task, type TaskStatus } from "@/lib/privat/api";
import { BIG, Eyebrow, Ex, KindLabel, Kv, LINK, ROW, Sim, StatusBadge } from "./bits";
import { ListBody } from "./cards";
import { WishCover } from "./wish-design";
import { Ico } from "./icons";
import { Composer } from "./day";
import { useFmt, usePrivat } from "./store";

const GROUPS: [string, TaskStatus[]][] = [
  ["awaiting", ["awaiting_user", "draft"]], ["inProgress", ["in_progress"]], ["planned", ["planned"]],
  ["business", ["awaiting_business"]], ["done", ["done", "declined"]],
];
const sharedWithMe = (t: Task) => !!t.my_role && t.my_role !== "owner";

export function TasksPane() {
  const t = useT("privat");
  const f = useFmt();
  const { tasks, openTask, mode } = usePrivat();
  const shared = tasks.filter(sharedWithMe);
  const own = tasks.filter((x) => !sharedWithMe(x));
  const groups = [
    ...GROUPS.map(([k, st]) => ({ key: k, items: own.filter((x) => st.includes(x.status)) })),
    { key: "shared", items: shared },
  ].filter((g) => g.items.length);
  return (
    <div className="px-4 pt-5 pb-7 flex flex-col gap-5" aria-label={t("tasks.title")}>
      <h2 className="m-0 font-display font-extrabold text-[28px] tracking-[-0.5px]">{t("tasks.title")}</h2>
      {/* Below xl the conversation is not on screen, so the list carries its own field: a sent line opens Samtale. */}
      <div className="xl:hidden" data-testid="tasks-composer"><Composer id="privat-ask-tasks" /></div>
      {mode !== "loading" && groups.length === 0 && <p className="m-0 text-[15px] text-muted">{t("tasks.empty")}</p>}
      {groups.map((g) => (
        <section key={g.key} className="flex flex-col gap-2" aria-label={t(`groups.${g.key}`)}>
          <h3 className="m-0 font-body text-[15px] font-semibold flex gap-2">{t(`groups.${g.key}`)} <span className="text-muted font-medium">({g.items.length})</span></h3>
          {g.items.map((x) => (
            <button key={x.id} type="button" className={ROW} onClick={() => openTask(x.id)}>
              <span className="flex-1 min-w-0 flex flex-col gap-[5px]">
                <span className="font-semibold text-[15px] line-clamp-2 [overflow-wrap:anywhere]">{x.title}{x.is_example && <> <Ex /></>}</span>
                <span className="text-[13px] text-ink-soft [overflow-wrap:anywhere]" suppressHydrationWarning><KindLabel task={x} />{" · "}{f.when(x.remind_at ?? x.due_at) || x.next_step}</span>
              </span>
            </button>
          ))}
        </section>
      ))}
    </div>
  );
}

function purpose(task: Task, t: (k: string) => string): string {
  if (task.call) return task.call.may_ask;
  if (task.list_type === "wishlist") return t("tasks.purposeWishlist");
  return task.kind === "list" ? t("tasks.purposeList") : t("tasks.purposeReminder");
}

export function TaskDetail({ id }: { id: string }) {
  const t = useT("privat");
  const f = useFmt();
  const { task, go, talk, openSheet, run, mode, simulated, error, entitled } = usePrivat();
  const params = useSearchParams();
  const [banner, setBanner] = useState(params.get("velkommen") === "1");
  const x = task(id);
  if (!x) return <div className="px-4 pt-5"><button type="button" className={LINK} onClick={() => go("tasks")}>{t("tasks.back")}</button><p className="text-muted">{mode === "loading" ? t("common.loading") : t("tasks.notFound")}</p></div>;
  const c = x.call;
  const proposal = x.kind === "call" && x.status === "awaiting_user" && c && !c.result && !x.is_example;
  // F-UX-02 / ux-audit #5: someone a list is shared WITH sees the list – not the owner's next step, usage or history.
  const guest = sharedWithMe(x);
  const ownerName = x.members?.find((m) => m.role === "owner")?.name?.split(" ")[0];
  // The «next step» card only where it carries a decision: a call, a draft that needs a plan, a proposal.
  const nextCard = !guest && (x.kind === "call" || x.status === "draft" || !!proposal);
  return (
    <div className="px-4 pt-4 pb-7 flex flex-col gap-4" aria-label={t("tasks.detailAria")}>
      {banner && (
        <div role="status" className="flex items-center gap-2 rounded-xl border-[1.5px] border-ink bg-highlight pl-3 pr-1 py-1">
          <button type="button" onClick={() => go("day")} className="flex-1 min-h-[44px] text-left text-[15px] font-semibold underline underline-offset-2">{t("list.welcomeBanner")}</button>
          <button type="button" onClick={() => setBanner(false)} aria-label={t("list.welcomeDismiss")} className="w-11 h-11 inline-flex items-center justify-center"><Ico name="close" size={18} /></button>
        </div>
      )}
      <button type="button" className={LINK} onClick={() => go("tasks")}>{t("tasks.back")}</button>
      <ErrorBox error={error} />
      {guest ? (ownerName && <Eyebrow>{t("tasks.fromOwner", { name: ownerName })}</Eyebrow>)
        : <div className="flex gap-1.5 items-center flex-wrap"><StatusBadge task={x} /><KindLabel task={x} />{x.is_example && <Ex />}</div>}
      {x.list_type === "wishlist" && x.design ? <WishCover title={x.title} design={x.design} /> : (
        <h2 className="m-0 font-display font-extrabold text-[26px] leading-[1.15] tracking-[-0.4px] [overflow-wrap:anywhere]">{x.title}</h2>
      )}
      {!guest && x.kind === "reminder" && (x.remind_at || x.due_at) && <p className="m-0 text-[16px] font-semibold" suppressHydrationWarning>{f.when(x.remind_at ?? x.due_at)}</p>}
      {nextCard && (
        <div className="rounded-[18px] border-2 border-ink bg-paper p-4 shadow-block flex flex-col gap-2.5">
          <Eyebrow>{t("tasks.next")}</Eyebrow>
          <p className="m-0 text-[17px] font-semibold [overflow-wrap:anywhere]">{x.next_step}</p>
          {/* Empty rows are left out – «Tidspunkt: –» read as if Peter had not heard the time (notes-PB 11). */}
          <Kv rows={([[t("tasks.purpose"), purpose(x, t)], [t("tasks.when"), f.when(x.remind_at ?? x.due_at)], [t("tasks.usage"), x.usage_text]] as [string, string | null | undefined][]).filter((r): r is [string, string] => !!r[1])} />
          {x.status === "draft" && <Button className={`${BIG} rounded-full`} onClick={() => openSheet({ kind: "paywall", taskId: x.id })}>{t("draft.choose")}</Button>}
          {proposal && <Button className={`${BIG} rounded-full`} onClick={() => talk(x.id)}>{t("call.seeProposal")}</Button>}
        </div>
      )}
      {x.kind === "list" && (
        <div className="rounded-[18px] border-2 border-ink bg-paper p-4" style={x.list_type === "wishlist" && x.design?.customized ? { background: x.design.background, color: x.design.text } : undefined}>
          <ListBody task={x} withAdd />
        </div>
      )}
      {c && x.status === "done" && c.result === "answered" && c.confirmed_text && (
        <div className="rounded-[18px] border-2 border-success bg-success-soft p-4 flex flex-col gap-2">
          <Eyebrow className="!text-success">{t("call.outcomeConfirmed")}</Eyebrow>
          {c.business_reply && <p className="m-0 text-[15px] leading-normal">«{c.business_reply}»</p>}
          <Kv rows={[[t("call.agreement"), c.confirmed_text], [t("call.priceAt"), c.business_price_text ?? "–"],
            [t("call.theCall"), <span key="u">{x.usage_text || t("call.callUsage", { duration: f.duration(c.duration_seconds) })} {simulated && <Sim />}</span>]]} />
        </div>
      )}
      {x.appointment && (
        <a href={icsHref(x.appointment)} download data-testid="task-ics"
          className="self-start inline-flex items-center gap-2 min-h-[44px] px-4 rounded-full border-2 border-ink font-semibold text-[15px] hover:bg-panel">
          <Ico name="calendar" size={18} />{t("calendar.addToCalendar")} · {x.appointment.when_text}
        </a>
      )}
      {c && c.result === "no_answer" && x.status === "awaiting_user" && (
        <div className="rounded-[18px] border-2 border-ink bg-panel p-4 flex flex-col gap-2">
          <Eyebrow>{t("call.outcomeLabel")}</Eyebrow>
          <p className="m-0 text-[15px] font-semibold">{entitled && c.paid_via !== "balance" ? t("day2.noAnswerPlan") : t("call.noAnswerTitle")}</p>
          <div className="flex gap-2 flex-wrap">
            <Button className={BIG} onClick={() => run((a) => a.retryCall(x.id)).then(() => talk(x.id))}>{t("call.retry")}</Button>
            <Button variant="outline" onClick={() => run((a) => a.declineCall(x.id))}>{t("call.cancelShort")}</Button>
          </div>
        </div>
      )}
      {(!guest || entitled) && <Button variant="outline" className="self-start border-2 rounded-full" onClick={() => talk(x.id)}>{t("tasks.talk")}</Button>}
      {!guest && x.events.length > 0 && <details className="group" aria-label={t("tasks.history")}>
        <summary className="cursor-pointer list-none min-h-[44px] inline-flex items-center gap-2 font-body text-[15px] font-semibold [&::-webkit-details-marker]:hidden">{t("tasks.history")} <Ico name="chevron" size={16} className="rotate-90 group-open:-rotate-90 transition-transform motion-reduce:transition-none" /></summary>
        <ol className="list-none m-0 pl-3 border-l-2 border-line flex flex-col gap-1.5">
          {[...x.events].reverse().map((e, i) => (
            <li key={i} className="text-[14px] flex gap-2.5"><span className="text-muted min-w-[72px]" suppressHydrationWarning>{f.stamp(e.at)}</span><span className="[overflow-wrap:anywhere] min-w-0">{e.text}</span></li>
          ))}
        </ol>
      </details>}
      {!guest && x.kind === "call" && !x.is_example && x.status !== "in_progress" && x.status !== "planned" && <DeleteCall id={x.id} />}
    </div>
  );
}

/** «Slet opkaldet»: the call and its summary go (kept until then – GDPR, decision 2026-11-11). Asks once. */
function DeleteCall({ id }: { id: string }) {
  const t = useT("privat");
  const { run, go, busy } = usePrivat();
  const [ask, setAsk] = useState(false);
  if (!ask) return <button type="button" className={`${LINK} self-start text-danger`} onClick={() => setAsk(true)} data-testid="delete-call">{t("call.delete")}</button>;
  return (
    <div role="alertdialog" aria-label={t("call.delete")} className="rounded-xl border-2 border-ink bg-paper p-3 flex flex-col gap-2">
      <p className="m-0 text-[15px] font-semibold">{t("call.deleteQ")}</p>
      <div className="flex gap-2 flex-wrap">
        <Button disabled={busy} onClick={async () => { const r = await run(async (a) => { await a.deleteCall(id); return true; }); if (r) go("tasks"); }}>{t("call.deleteYes")}</Button>
        <Button variant="outline" onClick={() => setAsk(false)}>{t("call.deleteNo")}</Button>
      </div>
    </div>
  );
}
