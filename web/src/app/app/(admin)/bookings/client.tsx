"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Icon, inputCls, useSubmit } from "@/components/ui";

type BType = { id: string; name: string; duration_minutes: number; description: string; active: boolean };
export type Settings = {
  version: number; enabled: boolean; lead_time_hours: number; horizon_days: number; buffer_minutes: number;
  busy_ics_url: string | null; busy_synced_at: string | null; busy_error: string | null; busy_blocks: number;
  feed_url: string; has_opening_hours: boolean; types: BType[];
};
type Slot = { start: string; label: string };

const Lbl = ({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) => <label htmlFor={htmlFor} className="block font-label-md text-label-md font-semibold mb-1">{children}</label>;

export function CancelBooking({ wsId, id }: { wsId: string; id: string }) {
  const router = useRouter();
  const c = useSubmit(async () => {
    if (!window.confirm("Aflys aftalen? Kunden får ikke automatisk besked – ring eller skriv til dem.")) return;
    await api(`/workspaces/${wsId}/bookings/${id}/cancel`, { method: "POST", body: "{}" });
    router.refresh();
  });
  return <button type="button" onClick={() => c.run()} disabled={c.pending} className="font-label-md text-label-md text-error hover:underline disabled:opacity-50">Aflys</button>;
}

/** Book on behalf of a customer (e.g. from a phone call the team took itself). */
export function ManualBooking({ wsId, types }: { wsId: string; types: BType[] }) {
  const router = useRouter();
  const [f, setF] = useState({ type_id: types[0].id, start: "", name: "", phone: "", email: "", note: "" });
  const [slots, setSlots] = useState<Slot[]>([]);
  const [done, setDone] = useState<string | null>(null);
  useEffect(() => {
    api<{ items: Slot[] }>(`/workspaces/${wsId}/bookings/slots?type_id=${f.type_id}`).then((r) => { setSlots(r.items); setF((cur) => ({ ...cur, start: r.items[0]?.start ?? "" })); }).catch(() => setSlots([]));
  }, [wsId, f.type_id, done]);
  const save = useSubmit(async () => {
    const b = await api<{ label: string }>(`/workspaces/${wsId}/bookings`, { method: "POST", body: JSON.stringify({ ...f, phone: f.phone || null, email: f.email || null }) });
    setDone(b.label); setF({ ...f, name: "", phone: "", email: "", note: "" }); router.refresh();
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => { setDone(null); setF({ ...f, [k]: e.target.value }); };
  return (
    <form className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <h2 className="font-headline-sm text-headline-sm text-primary">Book for en kunde</h2>
      {done && <Alert kind="ok">Booket {done}. Henvendelse og opgave er oprettet.</Alert>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-sm">
        <div><Lbl htmlFor="mb-type">Type</Lbl><select id="mb-type" className={inputCls} value={f.type_id} onChange={set("type_id")}>{types.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.duration_minutes} min)</option>)}</select></div>
        <div><Lbl htmlFor="mb-start">Tidspunkt</Lbl><select id="mb-start" className={inputCls} value={f.start} onChange={set("start")}>{slots.length === 0 ? <option value="">Ingen ledige tider</option> : slots.map((x) => <option key={x.start} value={x.start}>{x.label}</option>)}</select></div>
        <div><Lbl htmlFor="mb-name">Kundens navn</Lbl><input id="mb-name" className={inputCls} value={f.name} onChange={set("name")} /></div>
        <div><Lbl htmlFor="mb-phone">Telefon</Lbl><input id="mb-phone" type="tel" className={inputCls} value={f.phone} onChange={set("phone")} /></div>
        <div><Lbl htmlFor="mb-email">E-mail</Lbl><input id="mb-email" type="email" className={inputCls} value={f.email} onChange={set("email")} /></div>
        <div><Lbl htmlFor="mb-note">Note</Lbl><input id="mb-note" className={inputCls} value={f.note} onChange={set("note")} /></div>
      </div>
      <ErrorBox error={save.error} />
      <div><Button type="submit" icon="event_available" disabled={save.pending || !f.start || !f.name.trim()}>Book</Button></div>
    </form>
  );
}

export function TypesEditor({ wsId, types }: { wsId: string; types: BType[] }) {
  const router = useRouter();
  const [n, setN] = useState({ name: "", duration_minutes: 60, description: "" });
  const add = useSubmit(async () => {
    await api(`/workspaces/${wsId}/bookings/types`, { method: "POST", body: JSON.stringify({ ...n, active: true }) });
    setN({ name: "", duration_minutes: 60, description: "" }); router.refresh();
  });
  const toggle = useSubmit(async (t: BType) => {
    await api(`/workspaces/${wsId}/bookings/types/${t.id}`, { method: "PUT", body: JSON.stringify({ ...t, active: !t.active }) });
    router.refresh();
  });
  return (
    <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
      <h2 className="font-headline-sm text-headline-sm text-primary">Bookingtyper</h2>
      <p className="font-body-sm text-body-sm text-on-surface-variant">Fx &quot;Besigtigelse&quot; eller &quot;Rådgivning i butikken&quot;. Varigheden bestemmer, hvor lange tider der tilbydes.</p>
      {types.length > 0 && <ul className="flex flex-col gap-space-xs">{types.map((t) => (
        <li key={t.id} className="flex flex-wrap items-center gap-space-sm p-space-sm rounded-lg bg-surface-container-low">
          <span className="font-label-lg text-label-lg text-primary">{t.name}</span>
          <span className="font-body-sm text-body-sm text-on-surface-variant">{t.duration_minutes} min</span>
          <span className={`ml-auto px-2 py-0.5 rounded-full font-label-sm text-label-sm ${t.active ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-high text-on-surface-variant"}`}>{t.active ? "Aktiv" : "Slået fra"}</span>
          <Button type="button" variant="ghost" onClick={() => toggle.run(t)} disabled={toggle.pending}>{t.active ? "Slå fra" : "Slå til"}</Button>
        </li>
      ))}</ul>}
      <form className="grid grid-cols-1 md:grid-cols-[2fr_1fr_auto] gap-space-sm items-end" onSubmit={(e) => { e.preventDefault(); add.run(); }}>
        <div><Lbl htmlFor="bt-name">Navn</Lbl><input id="bt-name" className={inputCls} placeholder="Besigtigelse" value={n.name} onChange={(e) => setN({ ...n, name: e.target.value })} /></div>
        <div><Lbl htmlFor="bt-dur">Varighed (min)</Lbl><input id="bt-dur" type="number" min={15} max={480} step={15} className={inputCls} value={n.duration_minutes} onChange={(e) => setN({ ...n, duration_minutes: Number(e.target.value) })} /></div>
        <Button type="submit" icon="add" disabled={add.pending || !n.name.trim()}>Tilføj type</Button>
      </form>
      <ErrorBox error={add.error ?? toggle.error} />
    </div>
  );
}

export function BookingSettingsForm({ wsId, s }: { wsId: string; s: Settings }) {
  const router = useRouter();
  const [f, setF] = useState({ enabled: s.enabled, lead_time_hours: s.lead_time_hours, horizon_days: s.horizon_days, buffer_minutes: s.buffer_minutes, busy_ics_url: s.busy_ics_url ?? "" });
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const save = useSubmit(async () => {
    await api(`/workspaces/${wsId}/bookings/settings`, { method: "PUT", body: JSON.stringify({ ...f, busy_ics_url: f.busy_ics_url || null, expected_version: s.version }) });
    setSaved(true); router.refresh();
  });
  const sync = useSubmit(async () => { await api(`/workspaces/${wsId}/bookings/calendar/sync`, { method: "POST", body: "{}" }); router.refresh(); });
  const num = (k: "lead_time_hours" | "horizon_days" | "buffer_minutes") => (e: React.ChangeEvent<HTMLInputElement>) => { setSaved(false); setF({ ...f, [k]: Number(e.target.value) }); };
  return (
    <form className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <h2 className="font-headline-sm text-headline-sm text-primary">Online booking og kalender</h2>
      {saved && <Alert kind="ok">Gemt.</Alert>}
      <label className="flex items-center gap-space-sm font-label-lg text-label-lg text-on-surface">
        <input type="checkbox" className="w-4 h-4 accent-primary" checked={f.enabled} onChange={(e) => { setSaved(false); setF({ ...f, enabled: e.target.checked }); }} />
        Kunder må booke i chatten og i telefonen
      </label>
      {fieldError(save.error, "enabled") && <p role="alert" className="text-label-md text-error">Opret mindst én bookingtype først.</p>}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-space-sm">
        <div><Lbl htmlFor="bs-lead">Tidligst (timer frem)</Lbl><input id="bs-lead" type="number" min={0} className={inputCls} value={f.lead_time_hours} onChange={num("lead_time_hours")} /></div>
        <div><Lbl htmlFor="bs-hor">Højst (dage frem)</Lbl><input id="bs-hor" type="number" min={1} max={90} className={inputCls} value={f.horizon_days} onChange={num("horizon_days")} /></div>
        <div><Lbl htmlFor="bs-buf">Pause mellem aftaler (min)</Lbl><input id="bs-buf" type="number" min={0} max={240} step={5} className={inputCls} value={f.buffer_minutes} onChange={num("buffer_minutes")} /></div>
      </div>
      <div className="p-space-md rounded-lg bg-surface-container-low flex flex-col gap-space-sm">
        <h3 className="font-label-lg text-label-lg text-primary font-bold flex items-center gap-space-xs"><Icon name="calendar_month" size={20} />Jeres kalender (Google eller Outlook)</h3>
        <div>
          <Lbl htmlFor="bs-ics">1. Optaget tid: jeres kalenders hemmelige iCal-adresse</Lbl>
          <input id="bs-ics" className={inputCls} placeholder="https://calendar.google.com/calendar/ical/…/private-…/basic.ics" value={f.busy_ics_url} onChange={(e) => { setSaved(false); setF({ ...f, busy_ics_url: e.target.value }); }} />
          <p className="mt-1 font-body-sm text-body-sm text-on-surface-variant">Google: Indstillinger → din kalender → &quot;Hemmelig adresse i iCal-format&quot;. Outlook: Indstillinger → Kalender → Delte kalendere → Publicer → ICS-link. Vi læser kun start og slut på optagne aftaler – aldrig titler – og opdaterer hvert kvarter.</p>
          {s.busy_ics_url && <p className={`mt-1 font-body-sm text-body-sm ${s.busy_error ? "text-error" : "text-on-surface-variant"}`}>{s.busy_error ? `Fejl: ${s.busy_error}` : `Læst ${s.busy_synced_at ? new Date(s.busy_synced_at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" }) : "–"} · ${s.busy_blocks} optagne perioder`} <button type="button" className="underline text-primary" onClick={() => sync.run()} disabled={sync.pending}>{sync.pending ? "Læser…" : "Læs nu"}</button></p>}
        </div>
        <div>
          <p className="font-label-md text-label-md font-semibold mb-1">2. Se bookingerne i jeres kalender: abonnér på denne adresse</p>
          <div className="flex gap-space-xs">
            <input readOnly aria-label="Kalenderabonnement" className={`${inputCls} font-mono text-[12px]`} value={s.feed_url} />
            <Button type="button" variant="tonal" onClick={() => { navigator.clipboard?.writeText(s.feed_url); setCopied(true); }}>{copied ? "Kopieret" : "Kopiér"}</Button>
          </div>
          <p className="mt-1 font-body-sm text-body-sm text-on-surface-variant">Google: &quot;Andre kalendere&quot; → + → &quot;Fra webadresse&quot;. Outlook: Tilføj kalender → Abonner fra internettet. Hold adressen hemmelig – den viser kundernes navne og numre.</p>
        </div>
      </div>
      <ErrorBox error={fieldError(save.error, "enabled") ? null : save.error ?? sync.error} />
      <div><Button type="submit" icon="save" disabled={save.pending}>{save.pending ? "Gemmer…" : "Gem"}</Button></div>
    </form>
  );
}
