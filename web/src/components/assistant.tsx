"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { Icon } from "./ui";

/** «Ændr noget»: the person says what to change, the assistant shows it as before → after, and nothing applies before
 *  «Godkend». One component: a sticky column from 1280 px, a full-screen sheet behind a button below that, and the same
 *  panel in the setup (there it is called «Jeg hjælper med trin N»). */

type Proposal = { id: string; kind: string; label: string; summary: string; before: string; after: string };
type Msg =
  | { id: number; from: "bot" | "user"; text: string; link?: { label: string; href: string } | null }
  | { id: number; from: "card"; proposal: Proposal; state: "open" | "busy" | "applied" | "declined" | "error"; note?: string; href?: string };
type Chip = { label: string } & ({ fill: string } | { href: string } | { say: string } | { test: true });

const SETUP_CHIPS: Record<number, Chip[]> = {
  1: [{ label: "Åbningstider", fill: "Åbningstider man-fre 8-16" }, { label: "Hvad sker der i trin 2?", say: "I trin 2 forbinder du din kalender, så aftaler lander dér. Det er valgfrit – du kan springe det over." }],
  2: [{ label: "Hvad skriver I i kalenderen?", say: "En aftale med kundens navn, nummer og ærinde – og en bekræftelse til jer. Jeres eksisterende aftaler rører jeg aldrig." }, { label: "Hvad sker der i trin 3?", say: "I trin 3 vælger du stemme, forbinder telefonen med en viderestilling og tænder Dialogbot." }],
  3: [{ label: "Hvordan viderestiller jeg?", say: "Tast koden i trin 3 på din telefon og tryk ring. Slå viderestillingen fra igen med koden under den." }, { label: "Kan jeg fortryde?", say: "Ja. Du kan sætte Dialogbot på pause fra I dag, og slå viderestillingen fra på din telefon." }],
};
const PAGE_CHIPS: { match: (p: string) => boolean; chips: Chip[] }[] = [
  { match: (p) => p === "/app", chips: [{ label: "Ret åbningstider", fill: "Åbningstider man-fre 8-16" }, { label: "Tilføj en pris", fill: "Prisen på  er  kr" }, { label: "Vis ugens tal", href: "/app/ugen" }] },
  { match: (p) => p.startsWith("/app/viden"), chips: [{ label: "Læs min prisliste ind", href: "/app/viden?tab=k03" }, { label: "Test mig som kunde", test: true }, { label: "Tilføj et svar", fill: "Spørgsmål:  Svar: " }] },
  { match: (p) => p.startsWith("/app/opkald"), chips: [{ label: "Det, der venter på mig", href: "/app/opkald/henvendelser" }, { label: "Mine opgaver", href: "/app/opkald/opgaver" }] },
  { match: (p) => p.startsWith("/app/ugen"), chips: [{ label: "Ret dagsrapporten", fill: "Send dagsrapporten kl. 7" }, { label: "Se opkaldene", href: "/app/opkald" }] },
  { match: (p) => p.startsWith("/app/aftaler"), chips: [{ label: "Ret bookingregler", fill: "Sæt pausen mellem aftaler til 15 min" }, { label: "Forbind kalenderen", href: "/app/indstillinger/integrationer" }] },
  { match: (p) => p.startsWith("/app/kampagner"), chips: [{ label: "Hør jeres stemme", href: "/app/indstillinger/stemmer" }, { label: "Se afregningen", href: "/app/konto/fakturering" }] },
];
const FALLBACK: Chip[] = [{ label: "Alle indstillinger", href: "/app/indstillinger" }, { label: "Hjælp", href: "/app/hjaelp" }];

const msgOf = (e: unknown, fallback: string) => (e as ApiError)?.message ?? fallback;

function Card({ m, onApply, onDecline }: { m: Extract<Msg, { from: "card" }>; onApply: () => void; onDecline: () => void }) {
  const p = m.proposal;
  const open = m.state === "open" || m.state === "busy" || m.state === "error";
  return (
    <div className={`flex flex-col gap-2.5 p-3.5 rounded-[14px] border-2 bg-panel ${open ? "border-dashed border-ink" : "border-ink"}`} role="group" aria-label={`Ændring: ${p.label}`}>
      <span className="eyebrow">Ændring · før → efter</span>
      <span className="font-display font-bold text-[16px] text-ink">{p.summary}</span>
      <div className="flex flex-wrap items-center gap-2">
        <span className="px-3 py-1 rounded-full border-[1.5px] border-ink bg-paper text-[13px] font-semibold text-ink" aria-label={`Før: ${p.before}`}>{p.before}</span>
        <Icon name="arrow_forward" size={18} />
        <span className="px-3 py-1 rounded-full bg-highlight border-[1.5px] border-ink text-[13px] font-semibold text-ink" aria-label={`Efter: ${p.after}`}>{p.after}</span>
      </div>
      {open && (
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={onApply} disabled={m.state === "busy"} className="min-h-[44px] px-5 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-60">{m.state === "busy" ? "Gemmer …" : "Godkend"}</button>
          <button type="button" onClick={onDecline} disabled={m.state === "busy"} className="min-h-[44px] px-4 rounded-xl bg-paper border-2 border-ink text-ink text-[14px] font-semibold hover:bg-panel-deep disabled:opacity-60">Nej, lad være</button>
        </div>
      )}
      {m.state === "applied" && <p className="m-0 text-[14px] font-semibold text-success">Godkendt og gemt. {m.note}{m.href && <> <Link href={m.href} className="underline text-ink">Se det</Link></>}</p>}
      {m.state === "declined" && <p className="m-0 text-[14px] text-muted">Intet ændret.</p>}
      {m.state === "error" && m.note && <p role="alert" className="m-0 text-[14px] text-danger">{m.note}</p>}
    </div>
  );
}

function Panel({ title, subtitle, chips, msgs, busy, test, canChange, onSend, onChip, onApply, onDecline, onLeaveTest, onClose, className = "" }: {
  title: string; subtitle: string; chips: Chip[]; msgs: Msg[]; busy: boolean; test: boolean; canChange: boolean;
  onSend: (t: string) => void; onChip: (c: Chip, fill: (t: string) => void) => void; onApply: (id: number) => void; onDecline: (id: number) => void;
  onLeaveTest: () => void; onClose?: () => void; className?: string;
}) {
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
          <span className="font-display font-bold text-[16px] text-ink">{test ? "Test mig som kunde" : title}</span>
          <span className="text-[12px] text-muted">{test ? "Spørg, som en kunde ville – kun godkendt viden bruges" : subtitle}</span>
        </div>
        {test && <button type="button" onClick={onLeaveTest} className="min-h-[44px] px-3 text-[13px] font-semibold underline underline-offset-2 text-ink">Tilbage</button>}
        {onClose && <button type="button" onClick={onClose} aria-label="Luk" className="w-11 h-11 -mr-2 rounded-xl flex items-center justify-center text-ink hover:bg-panel"><Icon name="close" size={22} /></button>}
      </div>
      <div className="flex flex-col gap-3 p-4 flex-1 min-h-[200px] overflow-y-auto" role="log" aria-live="polite" aria-label="Samtale">
        {msgs.map((m) => m.from === "card"
          ? <Card key={m.id} m={m} onApply={() => onApply(m.id)} onDecline={() => onDecline(m.id)} />
          : (
            <div key={m.id} className={`flex ${m.from === "bot" ? "justify-start" : "justify-end"}`}>
              <p className={`m-0 px-3.5 py-2.5 text-[14px] leading-relaxed max-w-[320px] whitespace-pre-line border-2 border-ink ${m.from === "bot" ? "bg-paper text-ink rounded-[14px] rounded-bl-[4px]" : "bg-ink text-paper rounded-[14px] rounded-br-[4px]"}`}>
                {m.text}
                {m.from === "bot" && m.link && <> <Link href={m.link.href} className="underline font-semibold">{m.link.label}</Link></>}
              </p>
            </div>
          ))}
        {busy && <p className="m-0 text-[13px] text-muted" role="status">Tænker …</p>}
        <div ref={end} />
      </div>
      <div className="flex flex-col gap-2.5 px-4 pt-3.5 pb-4 border-t-2 border-ink bg-panel">
        {!test && chips.length > 0 && (<>
          <span className="eyebrow">Det, folk oftest beder om</span>
          <div className="flex flex-wrap gap-2">
            {chips.map((c) => "href" in c
              ? <Link key={c.label} href={c.href} onClick={onClose} className="inline-flex items-center min-h-[44px] px-3.5 rounded-full bg-paper border-2 border-ink text-ink text-[14px] font-semibold hover:bg-panel-deep">{c.label}</Link>
              : <button key={c.label} type="button" onClick={() => onChip(c, (t) => { setDraft(t); input.current?.focus(); })} className="min-h-[44px] px-3.5 rounded-full bg-paper border-2 border-ink text-ink text-[14px] font-semibold hover:bg-panel-deep">{c.label}</button>)}
          </div>
        </>)}
        {canChange || test ? (
          <form onSubmit={submit} className="flex gap-2">
            <label htmlFor={askId} className="sr-only">{test ? "Skriv et spørgsmål, som en kunde ville stille" : "Skriv, hvad du vil ændre"}</label>
            <input id={askId} ref={input} type="text" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={1000} autoComplete="off"
              placeholder={test ? "Fx: Hvad koster afslibning?" : "Skriv, hvad du vil ændre …"}
              className="flex-1 min-w-0 min-h-[46px] px-3.5 rounded-xl border-2 border-ink bg-paper text-[15px] text-ink placeholder:text-muted" />
            <button type="submit" disabled={busy || !draft.trim()} aria-label="Send" className="w-[46px] h-[46px] rounded-xl bg-ink text-paper inline-flex items-center justify-center hover:opacity-90 disabled:opacity-50"><Icon name="arrow_forward" size={20} /></button>
          </form>
        ) : <p className="m-0 text-[13px] text-muted">Din rolle kan se, men ikke ændre. Bed en ejer eller administrator om det.</p>}
        <Link href="/app/indstillinger" onClick={onClose} className="self-end text-[12px] text-muted hover:text-ink">Avanceret: alle indstillinger</Link>
      </div>
    </aside>
  );
}

export function AssistantDock({ wsId, canChange, step, column = true, name }: { wsId: string; canChange: boolean; step?: 1 | 2 | 3; column?: boolean; name?: string }) {
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([{ id: 0, from: "bot", text: step ? `Jeg hjælper med trin ${step}. Skriv, hvis noget skal rettes – du ser ændringen, før den gælder.` : `Hej${name ? ` ${name}` : ""}. Hvad vil du ændre? Skriv det med dine egne ord – jeg viser ændringen, før den gælder.` }]);
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

  const send = async (text: string) => {
    add({ from: "user", text });
    setBusy(true);
    try {
      if (test) {
        const r = await api<{ reply: string }>(`/workspaces/${wsId}/assistant/preview`, { method: "POST", body: JSON.stringify({ message: text }) });
        add({ from: "bot", text: r.reply });
      } else {
        const r = await api<{ proposal: Proposal | null; reply: string; link?: { label: string; href: string } | null }>(`/workspaces/${wsId}/assistant/changes`, { method: "POST", body: JSON.stringify({ text, context: path }) });
        add({ from: "bot", text: r.reply, link: r.proposal ? null : r.link });
        if (r.proposal) add({ from: "card", proposal: r.proposal, state: "open" });
      }
    } catch (e) {
      const err = e as ApiError;
      add({ from: "bot", text: err.code === "no_approved_knowledge" ? "Der er endnu ingen godkendt viden at teste mod. Tilføj og godkend noget først." : err.code === "ai_not_configured" ? "Jeg kan ikke svare lige nu. Brug en genvej, eller find det under Alle indstillinger." : msgOf(e, "Det lykkedes ikke. Prøv igen om lidt.") });
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
    } catch (e) { patch(id, { state: "error", note: msgOf(e, "Ændringen kunne ikke gemmes. Prøv igen.") }); }
  };
  const decline = async (id: number) => {
    const card = msgs.find((m) => m.id === id);
    if (!card || card.from !== "card") return;
    patch(id, { state: "declined" });
    await api(`/workspaces/${wsId}/assistant/changes/${card.proposal.id}/decline`, { method: "POST" }).catch(() => undefined);
    add({ from: "bot", text: "Okay, intet ændret." });
  };
  const chip = (c: Chip, fill: (t: string) => void) => {
    if ("fill" in c) fill(c.fill);
    else if ("say" in c) { add({ from: "user", text: c.label }); add({ from: "bot", text: c.say }); }
    else if ("test" in c) { setTest(true); add({ from: "bot", text: "Spørg mig om noget, en kunde kunne spørge om. Jeg svarer kun ud fra jeres godkendte viden." }); }
  };
  const chips = step ? SETUP_CHIPS[step] ?? [] : PAGE_CHIPS.find((c) => c.match(path))?.chips ?? FALLBACK;
  const title = step ? `Jeg hjælper med trin ${step}` : "Ændr noget";
  const subtitle = step ? "Jeg viser altid ændringen, før den gælder" : "Sig det – du ser ændringen, før den gælder";
  const panelProps = { title, subtitle, chips, msgs, busy, test, canChange, onSend: send, onChip: chip, onApply: apply, onDecline: decline, onLeaveTest: () => { setTest(false); add({ from: "bot", text: "Tilbage til ændringer. Hvad vil du ændre?" }); } };
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
        className={`${hide} fixed right-4 ${step ? "bottom-[88px] sm:bottom-6" : "bottom-[76px] sm:bottom-6"} sm:right-6 z-40 inline-flex items-center gap-2 min-h-[52px] pl-4 pr-5 rounded-full bg-ink text-paper border-2 border-ink shadow-block-highlight font-display font-bold text-[15px]`}>
        <Icon name="edit" size={18} />{step ? "Hjælp" : "Ændr noget"}
      </button>
    </>
  );
}
