"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Icon, inputCls, useSubmit } from "@/components/ui";
import { useLocale, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";

type BType = { id: string; name: string; duration_minutes: number; description: string; active: boolean };
export type Settings = {
  version: number; enabled: boolean; lead_time_hours: number; horizon_days: number; buffer_minutes: number;
  busy_ics_url: string | null; busy_synced_at: string | null; busy_error: string | null; busy_blocks: number;
  feed_url: string; has_opening_hours: boolean; types: BType[];
};
type Slot = { start: string; label: string };

const Lbl = ({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) => <label htmlFor={htmlFor} className="block text-label-md font-semibold mb-1">{children}</label>;

export function CancelBooking({ wsId, id }: { wsId: string; id: string }) {
  const router = useRouter();
  const t = useT("settings");
  const c = useSubmit(async () => {
    if (!window.confirm(t("booking.cancelConfirm"))) return;
    await api(`/workspaces/${wsId}/bookings/${id}/cancel`, { method: "POST", body: "{}" });
    router.refresh();
  });
  return <button type="button" onClick={() => c.run()} disabled={c.pending} className="text-label-md text-danger hover:underline disabled:opacity-50">{t("booking.cancel")}</button>;
}

/** Book on behalf of a customer (e.g. from a phone call the team took itself). */
export function ManualBooking({ wsId, types }: { wsId: string; types: BType[] }) {
  const router = useRouter();
  const tr = useT("settings");
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
    <form className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <h2 className="font-display text-headline-sm text-ink">{tr("booking.manual.title")}</h2>
      {done && <Alert kind="ok">{tr("booking.manual.done", { label: done })}</Alert>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div><Lbl htmlFor="mb-type">{tr("booking.manual.type")}</Lbl><select id="mb-type" className={inputCls} value={f.type_id} onChange={set("type_id")}>{types.map((t) => <option key={t.id} value={t.id}>{tr("booking.manual.typeOption", { name: t.name, n: t.duration_minutes })}</option>)}</select></div>
        <div><Lbl htmlFor="mb-start">{tr("booking.manual.time")}</Lbl><select id="mb-start" className={inputCls} value={f.start} onChange={set("start")}>{slots.length === 0 ? <option value="">{tr("booking.manual.noSlots")}</option> : slots.map((x) => <option key={x.start} value={x.start}>{x.label}</option>)}</select></div>
        <div><Lbl htmlFor="mb-name">{tr("booking.manual.name")}</Lbl><input id="mb-name" className={inputCls} value={f.name} onChange={set("name")} /></div>
        <div><Lbl htmlFor="mb-phone">{tr("booking.manual.phone")}</Lbl><input id="mb-phone" type="tel" className={inputCls} value={f.phone} onChange={set("phone")} /></div>
        <div><Lbl htmlFor="mb-email">{tr("booking.manual.email")}</Lbl><input id="mb-email" type="email" className={inputCls} value={f.email} onChange={set("email")} /></div>
        <div><Lbl htmlFor="mb-note">{tr("booking.manual.note")}</Lbl><input id="mb-note" className={inputCls} value={f.note} onChange={set("note")} /></div>
      </div>
      <ErrorBox error={save.error} />
      <div><Button type="submit" icon="event_available" disabled={save.pending || !f.start || !f.name.trim()}>{tr("booking.manual.submit")}</Button></div>
    </form>
  );
}

export function TypesEditor({ wsId, types }: { wsId: string; types: BType[] }) {
  const router = useRouter();
  const tr = useT("settings");
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
    <div className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
      <h2 className="font-display text-headline-sm text-ink">{tr("booking.types.title")}</h2>
      <p className="text-body-sm text-ink-soft">{tr("booking.types.intro")}</p>
      {types.length > 0 && <ul className="flex flex-col gap-1">{types.map((t) => (
        <li key={t.id} className="flex flex-wrap items-center gap-2 p-2 rounded-lg bg-panel">
          <span className="text-label-lg text-ink">{t.name}</span>
          <span className="text-body-sm text-ink-soft">{tr("booking.types.minutes", { n: t.duration_minutes })}</span>
          <span className={`ml-auto px-2 py-0.5 rounded-full text-label-sm ${t.active ?"bg-success-soft text-success":"bg-line text-ink-soft"}`}>{t.active ? tr("booking.types.active") : tr("booking.types.off")}</span>
          <Button type="button" variant="ghost" onClick={() => toggle.run(t)} disabled={toggle.pending}>{t.active ? tr("booking.types.turnOff") : tr("booking.types.turnOn")}</Button>
        </li>
      ))}</ul>}
      <form className="grid grid-cols-1 md:grid-cols-[2fr_1fr_auto] gap-2 items-end" onSubmit={(e) => { e.preventDefault(); add.run(); }}>
        <div><Lbl htmlFor="bt-name">{tr("booking.types.name")}</Lbl><input id="bt-name" className={inputCls} placeholder={tr("booking.types.namePlaceholder")} value={n.name} onChange={(e) => setN({ ...n, name: e.target.value })} /></div>
        <div><Lbl htmlFor="bt-dur">{tr("booking.types.duration")}</Lbl><input id="bt-dur" type="number" min={15} max={480} step={15} className={inputCls} value={n.duration_minutes} onChange={(e) => setN({ ...n, duration_minutes: Number(e.target.value) })} /></div>
        <Button type="submit" icon="add" disabled={add.pending || !n.name.trim()}>{tr("booking.types.add")}</Button>
      </form>
      <ErrorBox error={add.error ?? toggle.error} />
    </div>
  );
}

export function BookingSettingsForm({ wsId, s }: { wsId: string; s: Settings }) {
  const router = useRouter();
  const t = useT("settings");
  const locale = useLocale();
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
    <form className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <h2 className="font-display text-headline-sm text-ink">{t("booking.settings.title")}</h2>
      {saved && <Alert kind="ok">{t("booking.settings.saved")}</Alert>}
      <label className="flex items-center gap-2 text-label-lg text-ink">
        <input type="checkbox" className="w-4 h-4 accent-ink" checked={f.enabled} onChange={(e) => { setSaved(false); setF({ ...f, enabled: e.target.checked }); }} />
        {t("booking.settings.enabled")}
      </label>
      {fieldError(save.error, "enabled") && <p role="alert" className="text-label-md text-danger">{t("booking.settings.needType")}</p>}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <div><Lbl htmlFor="bs-lead">{t("booking.settings.lead")}</Lbl><input id="bs-lead" type="number" min={0} className={inputCls} value={f.lead_time_hours} onChange={num("lead_time_hours")} /></div>
        <div><Lbl htmlFor="bs-hor">{t("booking.settings.horizon")}</Lbl><input id="bs-hor" type="number" min={1} max={90} className={inputCls} value={f.horizon_days} onChange={num("horizon_days")} /></div>
        <div><Lbl htmlFor="bs-buf">{t("booking.settings.buffer")}</Lbl><input id="bs-buf" type="number" min={0} max={240} step={5} className={inputCls} value={f.buffer_minutes} onChange={num("buffer_minutes")} /></div>
      </div>
      <div className="p-3 rounded-lg bg-panel flex flex-col gap-2">
        <h3 className="text-label-lg text-ink font-bold flex items-center gap-1"><Icon name="calendar_month" size={20} />{t("booking.settings.calendarTitle")}</h3>
        <div>
          <Lbl htmlFor="bs-ics">{t("booking.settings.icsLabel")}</Lbl>
          <input id="bs-ics" className={inputCls} placeholder="https://calendar.google.com/calendar/ical/…/private-…/basic.ics" value={f.busy_ics_url} onChange={(e) => { setSaved(false); setF({ ...f, busy_ics_url: e.target.value }); }} />
          <p className="mt-1 text-body-sm text-ink-soft">{t("booking.settings.icsHelp")}</p>
          {s.busy_ics_url && <p className={`mt-1 text-body-sm ${s.busy_error ?"text-danger":"text-ink-soft"}`}>{s.busy_error ? t("booking.settings.icsError", { error: s.busy_error }) : t("booking.settings.icsRead", { when: s.busy_synced_at ? new Date(s.busy_synced_at).toLocaleString(HTML_LANG[locale], { dateStyle: "short", timeStyle: "short" }) : "–", n: s.busy_blocks })} <button type="button" className="underline text-ink" onClick={() => sync.run()} disabled={sync.pending}>{sync.pending ? t("booking.settings.reading") : t("booking.settings.readNow")}</button></p>}
        </div>
        <div>
          <p className="text-label-md font-semibold mb-1">{t("booking.settings.feedLabel")}</p>
          <div className="flex gap-1">
            <input readOnly aria-label={t("booking.settings.feedAria")} className={`${inputCls} font-mono text-[12px]`} value={s.feed_url} />
            <Button type="button" variant="tonal" onClick={() => { navigator.clipboard?.writeText(s.feed_url); setCopied(true); }}>{copied ? t("booking.settings.copied") : t("booking.settings.copy")}</Button>
          </div>
          <p className="mt-1 text-body-sm text-ink-soft">{t("booking.settings.feedHelp")}</p>
        </div>
      </div>
      <ErrorBox error={fieldError(save.error, "enabled") ? null : save.error ?? sync.error} />
      <div><Button type="submit" icon="save" disabled={save.pending}>{save.pending ? t("booking.settings.saving") : t("booking.settings.save")}</Button></div>
    </form>
  );
}
