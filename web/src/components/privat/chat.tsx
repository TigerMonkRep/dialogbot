"use client";
import { useEffect, useRef } from "react";
import { Button, ErrorBox } from "@/components/ui";
import { useT } from "@/i18n/client";
import { LOCATION_OPTION, isDemoPlace, isPlaceOption, type ChatMessage, type Task } from "@/lib/privat/api";
import { useState } from "react";
import { CHIP, ROW, SR, StatusBadge } from "./bits";
import { AddonCard, BrowserApprovalCard, CallCard, DraftCard, ListCard, MoveCard, ReminderCard, ShareProposalCard } from "./cards";
import { Composer, Shortcuts } from "./day";
import { Ico } from "./icons";
import { useFmt, usePrivat } from "./store";

const BOT = "self-start max-w-[90%] bg-panel rounded-[16px_16px_16px_4px] px-3.5 py-2.5 text-[16px] leading-[1.45] [overflow-wrap:anywhere]";
const CARD_KINDS = new Set(["task", "call_proposal", "draft", "share_proposal"]);

function TaskCardFor({ task }: { task: Task }) {
  if (task.kind === "list") return <ListCard task={task} />;
  if (task.kind === "reminder") return <ReminderCard task={task} />;
  return <CallCard task={task} />;
}

/** An earlier card for a task that has a newer card further down: a compact link, so actions exist only once. */
function Earlier({ task }: { task: Task }) {
  const t = useT("privat");
  const { openTask } = usePrivat();
  return (
    <button type="button" className={`${ROW} items-center`} onClick={() => openTask(task.id)} aria-label={t("chat.earlier", { title: task.title })}>
      <span className="flex-1 min-w-0 flex flex-col gap-1"><span className="font-semibold text-[15px] line-clamp-1 [overflow-wrap:anywhere]">{task.title}</span><span><StatusBadge task={task} /></span></span>
      <Ico name="chevron" size={18} />
    </button>
  );
}

function Message({ m, latestCard, open, prevUser }: { m: ChatMessage; latestCard: boolean; open: boolean; prevUser: string | null }) {
  const t = useT("privat");
  const { task, pick, openTask, tasks, busy } = usePrivat();
  const tk = task(m.task_id);
  if (m.role === "user") {
    const about = task(m.about_task_id);
    return (
      <div className="self-end max-w-[86%] flex flex-col items-end gap-1">
        {about && <span className="text-[12px] font-semibold text-muted [overflow-wrap:anywhere]">{t("chat.aboutTask", { title: about.title })}</span>}
        <div className="bg-ink text-paper rounded-[16px_16px_4px_16px] px-3.5 py-2.5 text-[16px] leading-[1.4] [overflow-wrap:anywhere]">{m.text}</div>
      </div>
    );
  }
  // A booking on a business's own website, filled in and waiting for the user's yes (its own kind: never a quota draft).
  if (m.kind === "booking_proposal") return <BrowserApprovalCard m={m} task={tk} open={!m.answered_option_id} />;
  if (CARD_KINDS.has(m.kind) && tk) {
    if (!latestCard) return <Earlier task={tk} />;
    if (m.kind === "draft") return <DraftCard task={tk} />;
    if (m.kind === "share_proposal") return <ShareProposalCard task={tk} text={m.text} groupId={m.options?.[0]?.id} />;
    return <TaskCardFor task={tk} />;
  }
  switch (m.kind) {
    case "move": return <MoveCard task={tk} before={m.before ?? ""} after={m.after ?? ""} />;
    case "addon": return <AddonCard addonKey={m.addon_key ?? ""} retryText={prevUser} />;
    case "waiting": {
      const biz = tasks.filter((x) => x.status === "awaiting_business").length;
      return (
        <div className="self-stretch flex flex-col gap-2">
          <div className={BOT}>{m.text}</div>
          {(m.links ?? []).map((id) => {
            const x = task(id);
            if (!x) return null;
            return (
              <button key={id} type="button" className={`${ROW} border-2`} onClick={() => openTask(id)}>
                <span className="w-2.5 h-2.5 rounded-full bg-highlight border-[1.5px] border-ink shrink-0 mt-1.5" aria-hidden />
                <span className="flex-1 min-w-0 flex flex-col gap-0.5"><span className="font-semibold line-clamp-2 [overflow-wrap:anywhere]">{x.title}</span><span className="text-[14px] text-ink-soft">{x.next_step}</span></span>
                <span className="text-[14px] font-semibold text-accent shrink-0">{t("chat.answer")}</span>
              </button>
            );
          })}
          {biz > 0 && <p className="m-0 text-[14px] text-ink-soft">{t("chat.businessWaiting", { n: biz })}</p>}
        </div>
      );
    }
    case "clarify": {
      const opts = m.options ?? [];
      if (opts.some((o) => o.id === LOCATION_OPTION.geo || o.id === LOCATION_OPTION.city)) return <LocationAsk m={m} open={open} />;
      const places = opts.some((o) => isPlaceOption(o.id));
      const demo = opts.some((o) => isDemoPlace(o.id));
      return (
        <div className="self-stretch flex flex-col gap-2">
          <div className={BOT}>{m.text}</div>
          {open && places && (
            <div role="group" aria-label={t("chat.chooseAnswer")} className="flex flex-col gap-2" data-testid="business-results">
              {opts.map((o) => {
                const parts = (o.sub ?? "").split(" · ");
                const last = parts[parts.length - 1] ?? "";
                const phone = isPlaceOption(o.id) && (/^\+?[\d\s]{8,}$/.test(last) || /nummer|number/i.test(last)) ? parts.pop() : undefined;
                return (
                  <button key={o.id} type="button" disabled={busy} className={`${ROW} border-2`} onClick={() => pick(m.id, o.id)}>
                    {isPlaceOption(o.id) && <span className="mt-0.5 text-accent"><Ico name="phone" size={20} /></span>}
                    <span className="flex-1 min-w-0 flex flex-col gap-0.5">
                      <span className="font-semibold">{o.label}</span>
                      {parts.length > 0 && <span className="text-[13px] text-ink-soft [overflow-wrap:anywhere]">{parts.slice(0, 2).join(" · ")}</span>}
                      {parts.length > 2 && <span className={`text-[13px] font-semibold ${/^Lukket|^Closed/.test(parts[2]) ? "text-ink" : "text-success"}`}>{parts.slice(2).join(" · ")}</span>}
                      {phone && <span className="text-[13px] text-muted">{phone}</span>}
                    </span>
                  </button>
                );
              })}
              <p className="m-0 text-[12px] text-muted">{demo ? t("chat.demoData") : t("chat.googleData")}</p>
            </div>
          )}
          {open && !places && (
            <div role="group" aria-label={t("chat.chooseAnswer")} className="flex flex-col gap-2">
              {(m.options ?? []).map((o) => (
                <button key={o.id} type="button" disabled={busy} className={`${ROW} border-2`} onClick={() => pick(m.id, o.id)}>
                  <span className="flex-1 min-w-0 flex flex-col gap-0.5"><span className="font-semibold">{o.label}</span>{o.sub && <span className="text-[13px] text-muted">{o.sub}</span>}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      );
    }
    default:
      return m.text ? <div className={BOT}>{m.text}</div> : null;
  }
}

export function ChatPane() {
  const t = useT("privat");
  const f = useFmt();
  const { messages, pending, focusId, setFocus, task, error, note, setNote, mode } = usePrivat();
  const end = useRef<HTMLDivElement>(null);
  const focus = task(focusId);
  // Follow the conversation: new messages, and the last card changing state (proposal → in progress → answered).
  const last = messages[messages.length - 1];
  const lastState = last?.task_id ? `${task(last.task_id)?.status}:${task(last.task_id)?.call?.result ?? ""}` : "";
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [messages.length, lastState, pending]);
  // The last message per task carries the live card; older ones become compact links.
  const lastFor = new Map<string, string>();
  for (const m of messages) if (m.task_id && CARD_KINDS.has(m.kind)) lastFor.set(m.task_id, m.id);
  return (
    <>
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 flex flex-col gap-3">
        <div className="hidden xl:flex flex-col gap-3 pt-2 pb-3 border-b-[1.5px] border-line">
          <p className="eyebrow m-0" suppressHydrationWarning>{f.dateLabel()}</p>
          <h1 className="m-0 font-display font-extrabold text-[34px] leading-[1.1] tracking-[-0.6px]">{t("day.ask")}</h1>
          <Shortcuts />
        </div>
        <div aria-live="polite" aria-relevant="additions" className="flex flex-col gap-3">
          <div className={BOT}>{mode === "demo" ? t("chat.welcomeDemo") : t("chat.welcome")}</div>
          {messages.map((m, i) => {
            const later = messages.slice(i + 1);
            const prevUser = [...messages.slice(0, i)].reverse().find((x) => x.role === "user")?.text ?? null;
            return (
              <div key={m.id} className="flex flex-col gap-2">
                <Message m={m} latestCard={!m.task_id || lastFor.get(m.task_id) === m.id} open={!m.answered_option_id && !later.some((x) => x.role === "user")} prevUser={prevUser} />
              </div>
            );
          })}
          {pending && (
            <>
              {/* The 5 s background refresh can bring the saved line in from the server before Peter has answered
                  (a link search takes 10-20 s): then only the real line is shown, the dots stay. */}
              {!messages.some((m) => m.role === "user" && m.text === pending.text && Date.parse(m.created_at) > Date.parse(pending.created_at) - 120_000) && (
                <div className="flex flex-col gap-2"><Message m={pending} latestCard open={false} prevUser={null} /></div>)}
              <div className={`${BOT} flex items-center gap-1.5`} role="status" aria-label={t("chat.typing")} data-testid="typing">
                <span className="sr-only">{t("chat.typing")}</span>
                {[0, 1, 2].map((i) => <span key={i} aria-hidden className="w-2 h-2 rounded-full bg-ink/60 animate-bounce" style={{ animationDelay: `${i * 150}ms` }} />)}
              </div>
            </>
          )}
          {note && (
            <div role="status" className="self-stretch flex items-start gap-2 rounded-xl border-[1.5px] border-ink bg-panel p-3 text-[14px]">
              <span className="flex-1">{note}</span>
              <button type="button" onClick={() => setNote("")} aria-label={t("sheet.close")} className="w-8 h-8 -m-1 inline-flex items-center justify-center"><Ico name="close" size={16} /></button>
            </div>
          )}
          <ErrorBox error={error} />
        </div>
        <div ref={end} />
      </div>
      <div className="flex-none border-t-2 border-ink px-3 pt-2.5 pb-3 bg-paper flex flex-col gap-2">
        {focus && (
          <div className="flex items-center gap-2 bg-highlight border-[1.5px] border-ink rounded-xl py-1 pr-1 pl-3">
            <span className="flex-1 min-w-0 text-[14px] line-clamp-2 [overflow-wrap:anywhere]"><b>{t("chat.talkingAbout")}</b> {focus.title}</span>
            <button type="button" onClick={() => setFocus(null)} aria-label={t("chat.stopFocus")} className="w-11 h-11 inline-flex items-center justify-center rounded-lg hover:bg-highlight-deep"><Ico name="close" size={18} stroke={2.4} /></button>
          </div>
        )}
        <Composer id="privat-ask" />
      </div>
    </>
  );
}

/** «Hvor skal jeg lede?»: position only after a tap, or a typed city/postcode. Then the request is sent again. */
function LocationAsk({ m, open }: { m: ChatMessage; open: boolean }) {
  const t = useT("privat");
  const { saveLocation, busy } = usePrivat();
  const [typing, setTyping] = useState(false);
  const [city, setCity] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const geo = () => {
    setErr(null);
    if (!navigator.geolocation) { setErr(t("location.unavailable")); setTyping(true); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => { void saveLocation({ lat: +p.coords.latitude.toFixed(3), lng: +p.coords.longitude.toFixed(3) }); },
      () => { setErr(t("location.denied")); setTyping(true); },
      { maximumAge: 600_000, timeout: 10_000 });
  };
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const v = city.trim();
    if (!v) return;
    void saveLocation(/^\d{4}$/.test(v) ? { postcode: v } : { city: v });
  };
  return (
    <div className="self-stretch flex flex-col gap-2">
      <div className={BOT}>{m.text}</div>
      {open && (
        <div className="flex flex-col gap-2" data-testid="location-ask">
          <div className="flex gap-2 flex-wrap">
            <button type="button" className={CHIP} onClick={geo} disabled={busy}><Ico name="arrow" size={16} />{t("location.useMine")}</button>
            <button type="button" className={CHIP} onClick={() => setTyping(true)} aria-expanded={typing}>{t("location.type")}</button>
          </div>
          {typing && (
            <form onSubmit={submit} className="flex gap-2">
              <label htmlFor={`loc-${m.id}`} className={SR}>{t("location.label")}</label>
              <input id={`loc-${m.id}`} autoFocus value={city} onChange={(e) => setCity(e.target.value)} autoComplete="postal-code" placeholder={t("location.placeholder")}
                className="flex-1 min-w-0 min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px]" />
              <Button type="submit" className="border-2 border-ink" disabled={busy}>{t("location.save")}</Button>
            </form>
          )}
          <p className="m-0 text-[12px] text-muted">{t("location.privacy")}</p>
          {err && <p role="alert" className="m-0 text-[13px] text-danger">{err}</p>}
        </div>
      )}
    </div>
  );
}
