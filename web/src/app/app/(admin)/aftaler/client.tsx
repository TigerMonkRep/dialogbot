"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { ErrorBox, inputCls, useSubmit } from "@/components/ui";
import type { BType, Booking } from "./types";

const BTN = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-[1.5px] border-ink bg-paper text-[14px] font-semibold text-ink hover:bg-panel disabled:opacity-50";
const BTN_PRIMARY = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-50";
const SOURCE: Record<string, string> = { webchat: "Webchat", phone: "Telefon", manual: "Manuelt" };

/** One appointment in the week. Click: details and «Aflys». */
export function BookingCard({ wsId, b, tz, canChange }: { wsId: string; b: Booking; tz: string; canChange: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const time = new Date(b.starts_at).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit", timeZone: tz });
  const cancel = useSubmit(async () => {
    if (!window.confirm("Aflys aftalen? Kunden får ikke automatisk besked – ring eller skriv til dem.")) return;
    await api(`/workspaces/${wsId}/bookings/${b.id}/cancel`, { method: "POST", body: "{}" });
    router.refresh();
  });
  return (
    <li className="rounded-xl border-[1.5px] border-ink bg-paper">
      <button type="button" aria-expanded={open} className="w-full text-left px-3 py-2.5 min-h-[44px] flex flex-col" onClick={() => setOpen(!open)}>
        <span className="font-display font-bold text-[15px] text-ink">{time}</span>
        <span className="text-[14px] font-semibold text-ink">{b.contact_name || b.title}</span>
        <span className="text-[13px] text-ink-soft">{b.title}</span>
      </button>
      {open && (
        <div className="border-t-[1.5px] border-line px-3 py-3 flex flex-col gap-2 text-[14px] text-ink">
          <span><b>{b.label}</b> · {SOURCE[b.source] ?? b.source}</span>
          {(b.contact_phone || b.contact_email) && <span className="text-ink-soft">{[b.contact_phone, b.contact_email].filter(Boolean).join(" · ")}</span>}
          {b.note && <span className="text-ink-soft">{b.note}</span>}
          <div className="flex flex-wrap gap-2">
            {b.contact_phone && <a href={`tel:${b.contact_phone}`} className={BTN}>Ring</a>}
            {b.conversation_id && <a href={`/app/opkald/${b.conversation_id}`} className={BTN}>Samtalen</a>}
            {b.lead_id && <a href={`/app/opkald/henvendelser/${b.lead_id}`} className={BTN}>Henvendelse</a>}
            {canChange && <button type="button" className={`${BTN} text-danger`} disabled={cancel.pending} onClick={() => cancel.run()}>Aflys</button>}
          </div>
          <ErrorBox error={cancel.error} />
        </div>
      )}
    </li>
  );
}

type Slot = { start: string; label: string };

/** «Book for en kunde»: name, phone, when – «først ledige» (the default) or a chosen free time. */
export function BookForCustomer({ wsId, types, initialName = "", initialPhone = "" }: { wsId: string; types: BType[]; initialName?: string; initialPhone?: string }) {
  const router = useRouter();
  const [typeId, setTypeId] = useState(types[0].id);
  const [name, setName] = useState(initialName), [phone, setPhone] = useState(initialPhone);
  const [when, setWhen] = useState("first");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [done, setDone] = useState<string | null>(null);
  useEffect(() => {
    api<{ items: Slot[] }>(`/workspaces/${wsId}/bookings/slots?type_id=${typeId}`).then((r) => setSlots(r.items)).catch(() => setSlots([]));
  }, [wsId, typeId, done]);
  const save = useSubmit(async () => {
    const start = when === "first" ? slots[0]?.start : when;
    if (!start) throw { status: 409, code: "no_slots", message: "Der er ingen ledige tider. Tjek åbningstider og kalender." };
    const b = await api<{ label: string }>(`/workspaces/${wsId}/bookings`, { method: "POST", body: JSON.stringify({ type_id: typeId, start, name, phone: phone || null, email: null, note: "" }) });
    setDone(b.label); setName(""); setPhone(""); setWhen("first"); router.refresh();
  });
  return (
    <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      {types.length > 1 && (
        <div><label htmlFor="bk-type" className="block text-[13px] font-semibold mb-1">Hvad skal de have?</label>
          <select id="bk-type" className={inputCls} value={typeId} onChange={(e) => { setDone(null); setTypeId(e.target.value); setWhen("first"); }}>{types.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.duration_minutes} min)</option>)}</select></div>
      )}
      <div><label htmlFor="bk-name" className="block text-[13px] font-semibold mb-1">Navn</label><input id="bk-name" required className={inputCls} value={name} onChange={(e) => { setDone(null); setName(e.target.value); }} /></div>
      <div><label htmlFor="bk-phone" className="block text-[13px] font-semibold mb-1">Telefon</label><input id="bk-phone" type="tel" className={inputCls} value={phone} onChange={(e) => { setDone(null); setPhone(e.target.value); }} /></div>
      <div><label htmlFor="bk-when" className="block text-[13px] font-semibold mb-1">Hvornår</label>
        <select id="bk-when" className={inputCls} value={when} onChange={(e) => setWhen(e.target.value)} disabled={slots.length === 0}>
          <option value="first">{slots[0] ? `Først ledige – ${slots[0].label}` : "Ingen ledige tider"}</option>
          {slots.slice(1, 40).map((s) => <option key={s.start} value={s.start}>{s.label}</option>)}
        </select></div>
      <ErrorBox error={save.error} />
      {done && <p role="status" className="rounded-xl bg-success-soft px-3.5 py-2.5 text-[14px] font-semibold text-success">Booket {done}.</p>}
      <button type="submit" className={BTN_PRIMARY} disabled={save.pending || !name.trim() || slots.length === 0}>{save.pending ? "Booker…" : "Book"}</button>
      <p className="text-[13px] text-muted">Kunden får ingen SMS endnu – send selv en bekræftelse. «Først ledige» tager næste tid, som åbningstider og kalender tillader.</p>
    </form>
  );
}

/** Calendar status: read the busy calendar now, copy the address that shows the bookings in your own calendar. */
export function CalendarTools({ wsId, feedUrl, hasIcs }: { wsId: string; feedUrl: string; hasIcs: boolean }) {
  const router = useRouter();
  const [copied, setCopied] = useState(false);
  const sync = useSubmit(async () => { await api(`/workspaces/${wsId}/bookings/calendar/sync`, { method: "POST", body: "{}" }); router.refresh(); });
  return (
    <div className="flex flex-wrap gap-2">
      {hasIcs && <button type="button" className={BTN} disabled={sync.pending} onClick={() => sync.run()}>{sync.pending ? "Læser…" : "Læs kalenderen nu"}</button>}
      <button type="button" className={BTN} onClick={() => { navigator.clipboard?.writeText(feedUrl); setCopied(true); }}>{copied ? "Adressen er kopieret" : "Kopiér kalenderadresse"}</button>
      <ErrorBox error={sync.error} />
    </div>
  );
}
