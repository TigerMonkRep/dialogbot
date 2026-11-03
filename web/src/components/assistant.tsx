"use client";
import Link from "@/i18n/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { Icon } from "./ui";
import { useLocale, useRaw, useT } from "@/i18n/client";
import type { T } from "@/i18n/translate";

/** «Ændr noget»: a short conversation. The person asks about Dialogbot or their own setup (answer + a link to the right
 *  page), or says what to change (shown as before → after; nothing applies before «Godkend»). What Dialogbot cannot do is
 *  sent to the Dialogbot team as a wish. One component: a sticky column from 1280 px, a full-screen sheet behind a button
 *  below that, and the same panel in the setup (there it is called «Jeg hjælper med trin N»). */

type Proposal = { id: string; kind: string; label: string; summary: string; before: string; after: string };
type PageLink = { key?: string; label: string; href: string };
type Turn = {
  type: "answer" | "question" | "change" | "request" | "fallback"; reply: string; link?: PageLink | null; proposal: Proposal | null;
  request?: { id: string; summary: string; duplicate: boolean } | null; code?: string | null; vars?: Record<string, string> | null;
};
/** Server codes for its own (Danish) sentences → keys under setup.assistant.codes, used for the other languages. */
const CODES: Record<string, string> = { link_only: "linkOnly", not_understood: "notUnderstood", ai_off: "aiOff", role_needed: "roleNeeded", already: "already", details_missing: "detailsMissing" };
const HISTORY = 10;
type Msg =
  | { id: number; from: "bot" | "user"; text: string; link?: PageLink | null; note?: string; test?: boolean }
  | { id: number; from: "card"; proposal: Proposal; state: "open" | "busy" | "applied" | "declined" | "error"; note?: string; href?: string };
type Chip = { label: string } & ({ fill: string } | { href: string } | { say: string } | { test: true });

/** Setup chips per step: setup.assistant.setupChips in messages. Page chips are built from setup.assistant.chips. */
const pageChips = (t: T): { match: (p: string) => boolean; chips: Chip[] }[] => [
  { match: (p) => p === "/app", chips: [{ label: t("chips.fixHours"), fill: t("chips.fixHoursFill") }, { label: t("chips.addPrice"), fill: t("chips.addPriceFill") }, { label: t("chips.weekNumbers"), href: "/app/ugen" }] },
  { match: (p) => p.startsWith("/app/viden"), chips: [{ label: t("chips.readPriceList"), href: "/app/viden?tab=k03" }, { label: t("chips.testMe"), test: true }, { label: t("chips.addAnswer"), fill: t("chips.addAnswerFill") }] },
  { match: (p) => p.startsWith("/app/opkald"), chips: [{ label: t("chips.waiting"), href: "/app/opkald/henvendelser" }, { label: t("chips.tasks"), href: "/app/opkald/opgaver" }] },
  { match: (p) => p.startsWith("/app/ugen"), chips: [{ label: t("chips.fixReport"), fill: t("chips.fixReportFill") }, { label: t("chips.seeCalls"), href: "/app/opkald" }] },
  { match: (p) => p.startsWith("/app/aftaler"), chips: [{ label: t("chips.fixBooking"), fill: t("chips.fixBookingFill") }, { label: t("chips.connectCalendar"), href: "/app/indstillinger/integrationer" }] },
  { match: (p) => p.startsWith("/app/kampagner"), chips: [{ label: t("chips.hearVoice"), href: "/app/indstillinger/stemmer" }, { label: t("chips.seeBilling"), href: "/app/konto/fakturering" }] },
];
const fallbackChips = (t: T): Chip[] => [{ label: t("chips.allSettings"), href: "/app/indstillinger" }, { label: t("chips.help"), href: "/app/hjaelp" }];
/** Always offered last: ask for something Dialogbot cannot do yet (it goes to the Dialogbot team). */
const wishChip = (t: T): Chip => ({ label: t("chips.wish"), fill: t("chips.wishFill") });

const msgOf = (e: unknown, fallback: string) => (e as ApiError)?.message ?? fallback;

function Card({ m, onApply, onDecline }: { m: Extract<Msg, { from: "card" }>; onApply: () => void; onDecline: () => void }) {
  const t = useT("setup.assistant.card");
  const p = m.proposal;
  const open = m.state === "open" || m.state === "busy" || m.state === "error";
  return (
    <div className={`flex flex-col gap-2.5 p-3.5 rounded-[14px] border-2 bg-panel ${open ? "border-dashed border-ink" : "border-ink"}`} role="group" aria-label={t("aria", { label: p.label })}>
      <span className="eyebrow">{t("eyebrow")}</span>
      <span className="font-display font-bold text-[16px] text-ink">{p.summary}</span>
      <div className="flex flex-wrap items-center gap-2">
        <span className="px-3 py-1 rounded-full border-[1.5px] border-ink bg-paper text-[13px] font-semibold text-ink" aria-label={t("before", { value: p.before })}>{p.before}</span>
        <Icon name="arrow_forward" size={18} />
        <span className="px-3 py-1 rounded-full bg-highlight border-[1.5px] border-ink text-[13px] font-semibold text-ink" aria-label={t("after", { value: p.after })}>{p.after}</span>
      </div>
      {open && (
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={onApply} disabled={m.state === "busy"} className="min-h-[44px] px-5 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-60">{m.state === "busy" ? t("saving") : t("approve")}</button>
          <button type="button" onClick={onDecline} disabled={m.state === "busy"} className="min-h-[44px] px-4 rounded-xl bg-paper border-2 border-ink text-ink text-[14px] font-semibold hover:bg-panel-deep disabled:opacity-60">{t("decline")}</button>
        </div>
      )}
      {m.state === "applied" && <p className="m-0 text-[14px] font-semibold text-success">{t("applied")} {m.note}{m.href && <> <Link href={m.href} className="underline text-ink">{t("seeIt")}</Link></>}</p>}
      {m.state === "declined" && <p className="m-0 text-[14px] text-muted">{t("declined")}</p>}
      {m.state === "error" && m.note && <p role="alert" className="m-0 text-[14px] text-danger">{m.note}</p>}
    </div>
  );
}

function Panel({ title, subtitle, chips, msgs, busy, test, canChange, onSend, onChip, onApply, onDecline, onLeaveTest, onClose, className = "" }: {
  title: string; subtitle: string; chips: Chip[]; msgs: Msg[]; busy: boolean; test: boolean; canChange: boolean;
  onSend: (t: string) => void; onChip: (c: Chip, fill: (t: string) => void) => void; onApply: (id: number) => void; onDecline: (id: number) => void;
  onLeaveTest: () => void; onClose?: () => void; className?: string;
}) {
  const tr = useT("setup.assistant");
  const [draft, setDraft] = useState("");
  const askId = useId();
  const input = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView?.({ block: "nearest" }); }, [msgs.length, busy]);
  const submit = (e: React.FormEvent) => { e.preventDefault(); const t = draft.trim(); if (!t || busy) return; setDraft(""); onSend(t); };
  return (
    <aside aria-label={title} className={`bg-paper border-2 border-ink rounded-2xl flex flex-col overflow-hidden ${className}`}>
      <div className="flex items-center gap-3 px-4 py-3.5 border-b-2 border-ink">
        <span className="inline-flex w-9 h-9 rounded-[10px] bg-accent items-center justify-center font-display font-extrabold text-white" aria-hidden>D</span>
        <div className="flex flex-col flex-1 min-w-0">
          <span className="font-display font-bold text-[16px] text-ink">{test ? tr("testTitle") : title}</span>
          <span className="text-[12px] text-muted">{test ? tr("testSubtitle") : subtitle}</span>
        </div>
        {test && <button type="button" onClick={onLeaveTest} className="min-h-[44px] px-3 text-[13px] font-semibold underline underline-offset-2 text-ink">{tr("back")}</button>}
        {onClose && <button type="button" onClick={onClose} aria-label={tr("close")} className="w-11 h-11 -mr-2 rounded-xl flex items-center justify-center text-ink hover:bg-panel"><Icon name="close" size={22} /></button>}
      </div>
      <div className="flex flex-col gap-3 p-4 flex-1 min-h-[200px] overflow-y-auto" role="log" aria-live="polite" aria-label={tr("log")}>
        {msgs.map((m) => m.from === "card"
          ? <Card key={m.id} m={m} onApply={() => onApply(m.id)} onDecline={() => onDecline(m.id)} />
          : (
            <div key={m.id} className={`flex ${m.from === "bot" ? "justify-start" : "justify-end"}`}>
              <p className={`m-0 px-3.5 py-2.5 text-[14px] leading-relaxed max-w-[320px] whitespace-pre-line border-2 border-ink ${m.from === "bot" ? "bg-paper text-ink rounded-[14px] rounded-bl-[4px]" : "bg-ink text-paper rounded-[14px] rounded-br-[4px]"}`}>
                {m.text}
                {m.from === "bot" && m.link && <> <Link href={m.link.href} className="underline font-semibold">{m.link.label}</Link></>}
                {m.from === "bot" && m.note && <span className="flex items-center gap-1 mt-1.5 text-[12px] font-semibold text-success"><Icon name="check_circle" size={16} />{m.note}</span>}
              </p>
            </div>
          ))}
        {busy && <p className="m-0 text-[13px] text-muted" role="status">{tr("thinking")}</p>}
        <div ref={end} />
      </div>
      <div className="flex flex-col gap-2.5 px-4 pt-3.5 pb-4 border-t-2 border-ink bg-panel">
        {!test && chips.length > 0 && (<>
          <span className="eyebrow">{tr("popular")}</span>
          <div className="flex flex-wrap gap-2">
            {chips.map((c) => "href" in c
              ? <Link key={c.label} href={c.href} onClick={onClose} className="inline-flex items-center min-h-[44px] px-3.5 rounded-full bg-paper border-2 border-ink text-ink text-[14px] font-semibold hover:bg-panel-deep">{c.label}</Link>
              : <button key={c.label} type="button" onClick={() => onChip(c, (t) => { setDraft(t); input.current?.focus(); })} className="min-h-[44px] px-3.5 rounded-full bg-paper border-2 border-ink text-ink text-[14px] font-semibold hover:bg-panel-deep">{c.label}</button>)}
          </div>
        </>)}
        {!canChange && !test && <p className="m-0 text-[13px] text-muted">{tr("readOnly")}</p>}
        <form onSubmit={submit} className="flex gap-2">
          <label htmlFor={askId} className="sr-only">{test ? tr("askTestLabel") : tr("askLabel")}</label>
          <input id={askId} ref={input} type="text" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={1000} autoComplete="off"
            placeholder={test ? tr("askTestPlaceholder") : tr("askPlaceholder")}
            className="flex-1 min-w-0 min-h-[46px] px-3.5 rounded-xl border-2 border-ink bg-paper text-[15px] text-ink placeholder:text-muted" />
          <button type="submit" disabled={busy || !draft.trim()} aria-label={tr("send")} className="w-[46px] h-[46px] rounded-xl bg-ink text-paper inline-flex items-center justify-center hover:opacity-90 disabled:opacity-50"><Icon name="arrow_forward" size={20} /></button>
        </form>
        <Link href="/app/indstillinger" onClick={onClose} className="self-end text-[12px] text-muted hover:text-ink">{tr("advanced")}</Link>
      </div>
    </aside>
  );
}

export function AssistantDock({ wsId, canChange, step, column = true, name }: { wsId: string; canChange: boolean; step?: 1 | 2 | 3; column?: boolean; name?: string }) {
  const path = usePathname();
  const router = useRouter();
  const t = useT("setup.assistant");
  const raw = useRaw();
  const locale = useLocale();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([{ id: 0, from: "bot", text: step ? t("greetStep", { step }) : name ? t("greetName", { name }) : t("greet") }]);
  const [busy, setBusy] = useState(false);
  const [test, setTest] = useState(false);
  const next = useRef(1);
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => { document.body.style.overflow = prev; window.removeEventListener("keydown", onKey); };
  }, [open]);

  const add = (m: Omit<Extract<Msg, { from: "bot" | "user" }>, "id"> | Omit<Extract<Msg, { from: "card" }>, "id">) => setMsgs((l) => [...l.slice(-30), { ...m, id: next.current++ } as Msg]);
  // «Ændr» on a tile in Alle indstillinger: open the assistant and ask what the new value should be.
  useEffect(() => {
    const on = (e: Event) => {
      const say = (e as CustomEvent<{ say?: string }>).detail?.say;
      if (!say) return;
      setTest(false); if (window.innerWidth < 1280) setOpen(true);
      setMsgs((l) => [...l.slice(-30), { id: next.current++, from: "bot", text: say } as Msg]);
    };
    window.addEventListener("dialogbot:assistant", on);
    return () => window.removeEventListener("dialogbot:assistant", on);
  }, []);
  const patch = (id: number, p: Partial<Extract<Msg, { from: "card" }>>) => setMsgs((l) => l.map((m) => (m.id === id && m.from === "card" ? { ...m, ...p } : m)));

  /** The conversation so far (text turns of this panel, not «Test mig som kunde»), oldest first. */
  const history = () => msgs.flatMap((m) => (m.from === "card" || m.test ? [] : [{ role: m.from === "user" ? "user" : "assistant", text: m.text }])).slice(-HISTORY);
  /** The server's own sentences are Danish; in another language use our translation of the same sentence. */
  const replyText = (r: Turn) => {
    const key = r.code ? CODES[r.code] : undefined;
    if (locale === "da" || !key) return r.reply;
    return key === "aiOff" ? t("aiOff") : t(`codes.${key}`, { label: r.link ? pageLabel(r.link) : r.vars?.label ?? "" });
  };
  const pageLabel = (l: PageLink) => (l.key && raw<Record<string, string>>("setup.assistant.pages")?.[l.key]) || l.label;
  const send = async (text: string) => {
    const past = history();
    add({ from: "user", text, test });
    setBusy(true);
    try {
      if (test) {
        const r = await api<{ reply: string }>(`/workspaces/${wsId}/assistant/preview`, { method: "POST", body: JSON.stringify({ message: text }) });
        add({ from: "bot", text: r.reply, test: true });
      } else {
        const r = await api<Turn>(`/workspaces/${wsId}/assistant/changes`, { method: "POST", body: JSON.stringify({ text, context: path, history: past }) });
        const note = r.request ? (r.request.duplicate ? t("requestRepeat") : t("requestSent")) : undefined;
        add({ from: "bot", text: replyText(r), link: r.proposal || !r.link ? null : { ...r.link, label: pageLabel(r.link) }, note });
        if (r.proposal) add({ from: "card", proposal: r.proposal, state: "open" });
      }
    } catch (e) {
      const err = e as ApiError;
      add({ from: "bot", text: err.code === "no_approved_knowledge" ? t("noKnowledge") : err.code === "ai_not_configured" ? t("aiOff") : msgOf(e, t("failed")) });
    }
    setBusy(false);
  };
  const apply = async (id: number) => {
    const card = msgs.find((m) => m.id === id);
    if (!card || card.from !== "card") return;
    patch(id, { state: "busy" });
    try {
      const r = await api<{ message: string; href: string }>(`/workspaces/${wsId}/assistant/changes/${card.proposal.id}/apply`, { method: "POST" });
      patch(id, { state: "applied", note: r.message, href: r.href });
      router.refresh();
    } catch (e) { patch(id, { state: "error", note: msgOf(e, t("applyFailed")) }); }
  };
  const decline = async (id: number) => {
    const card = msgs.find((m) => m.id === id);
    if (!card || card.from !== "card") return;
    patch(id, { state: "declined" });
    await api(`/workspaces/${wsId}/assistant/changes/${card.proposal.id}/decline`, { method: "POST" }).catch(() => undefined);
    add({ from: "bot", text: t("declinedReply") });
  };
  const chip = (c: Chip, fill: (t: string) => void) => {
    if ("fill" in c) fill(c.fill);
    else if ("say" in c) { add({ from: "user", text: c.label }); add({ from: "bot", text: c.say }); }
    else if ("test" in c) { setTest(true); add({ from: "bot", text: t("testIntro"), test: true }); }
  };
  const chips = step ? raw<Record<string, Chip[]>>("setup.assistant.setupChips")?.[String(step)] ?? [] : [...(pageChips(t).find((c) => c.match(path))?.chips ?? fallbackChips(t)), wishChip(t)];
  const title = step ? t("titleStep", { step }) : t("title");
  const subtitle = step ? t("subtitleStep") : t("subtitle");
  const panelProps = { title, subtitle, chips, msgs, busy, test, canChange, onSend: send, onChip: chip, onApply: apply, onDecline: decline, onLeaveTest: () => { setTest(false); add({ from: "bot", text: t("backToChanges") }); } };
  const hide = column ? "xl:hidden" : "";
  if (!step && (path.startsWith("/app/konto") || path.startsWith("/app/hjaelp") || path.startsWith("/app/operator"))) return null;
  return (
    <>
      {column && <div className="hidden xl:block w-[360px] shrink-0"><div className="sticky top-24"><Panel {...panelProps} className="shadow-block" /></div></div>}
      {open && (
        <div role="dialog" aria-modal="true" aria-label={title} className={`${hide} fixed inset-0 z-50 bg-paper flex flex-col`} style={{ paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" }}>
          <Panel {...panelProps} onClose={() => setOpen(false)} className="flex-1 rounded-none border-0" />
        </div>
      )}
      <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}
        className={`${hide} fixed right-4 ${step ? "bottom-[calc(var(--action-bar-h,0px)+12px)] sm:bottom-6" : "bottom-[calc(72px+env(safe-area-inset-bottom))] sm:bottom-6"} sm:right-6 z-40 inline-flex items-center gap-2 min-h-[52px] pl-4 pr-5 rounded-full bg-ink text-paper border-2 border-ink shadow-block-highlight font-display font-bold text-[15px]`}>
        <Icon name="edit" size={18} />{step ? t("help") : t("change")}
      </button>
    </>
  );
}
