"use client";
/** App panels for Madplan (household habits), Læge & tandlæge (saved practices), Bil & syn (the car and its dates) and
 *  Pakker (followed parcels). Shown in the app sheet when the app is on. Pakkeliste needs no panel: its lists are
 *  ordinary lists under Opgaver. Peter does all of it in the chat as well. */
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import type { CarInfo, FoodPreferences, HealthContact, Parcel } from "@/lib/privat/api";
import { Eyebrow } from "./bits";
import { usePrivat } from "./store";

const INPUT = "w-full min-h-[44px] rounded-xl border-2 border-ink bg-paper px-3 text-[15px] text-ink";
const CARD = "rounded-[16px] border-[1.5px] border-ink bg-paper p-3 flex flex-col gap-1.5";

function useLoad<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => { try { setData(await fn()); } catch (e) { setErr((e as ApiError).message); } }, [fn]);
  useEffect(() => { void load(); }, [load]);
  const run = async (f: () => Promise<unknown>) => { setErr(null); try { await f(); await load(); } catch (e) { setErr((e as ApiError).message); } };
  return { data, err, run };
}

function Err({ err }: { err: string | null }) {
  return err ? <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p> : null;
}

export function MealsPanel() {
  const t = useT("privat");
  const { api } = usePrivat();
  const fn = useCallback(() => api.foodPreferences(), [api]);
  const { data, err, run } = useLoad<FoodPreferences>(fn);
  const [form, setForm] = useState<FoodPreferences | null>(null);
  useEffect(() => { if (data) setForm(data); }, [data]);
  if (!form) return <Err err={err} />;
  return (
    <form className="rounded-[18px] border-[1.5px] border-ink bg-panel p-3.5 flex flex-col gap-2" data-testid="meals-panel"
      onSubmit={(e) => { e.preventDefault(); void run(() => api.saveFoodPreferences(form)); }}>
      <Eyebrow>{t("moreApps.meals.title")}</Eyebrow>
      <Err err={err} />
      <label className="text-[13px] text-muted flex flex-col gap-1">{t("moreApps.meals.people")}
        <input type="number" min={1} max={20} value={form.people ?? ""} className={INPUT}
          onChange={(e) => setForm({ ...form, people: e.target.value ? Number(e.target.value) : null })} />
      </label>
      <label className="text-[13px] text-muted flex flex-col gap-1">{t("moreApps.meals.avoid")}
        <input value={form.avoid} maxLength={500} className={INPUT} onChange={(e) => setForm({ ...form, avoid: e.target.value })} />
      </label>
      <label className="text-[13px] text-muted flex flex-col gap-1">{t("moreApps.meals.likes")}
        <input value={form.likes} maxLength={500} className={INPUT} onChange={(e) => setForm({ ...form, likes: e.target.value })} />
      </label>
      <Button type="submit" className="rounded-full self-start">{t("moreApps.save")}</Button>
      <p className="m-0 text-[13px] text-muted">{t("moreApps.meals.hint")}</p>
    </form>
  );
}

export function HealthPanel() {
  const t = useT("privat");
  const { api } = usePrivat();
  const fn = useCallback(() => api.healthContacts(), [api]);
  const { data, err, run } = useLoad<{ items: HealthContact[] }>(fn);
  return (
    <section className="flex flex-col gap-2" data-testid="health-panel">
      <Err err={err} />
      <Eyebrow>{t("moreApps.health.title")}</Eyebrow>
      {data && data.items.length === 0 && <p className="m-0 text-[14px] text-muted">{t("moreApps.health.none")}</p>}
      {data?.items.map((c) => (
        <div key={c.kind} className={CARD}>
          <span className="font-semibold text-[15px]">{c.name}</span>
          <span className="text-[14px] text-ink-soft">{c.label} · {c.phone_display}</span>
          <Button variant="outline" className="rounded-full border-2 self-start" onClick={() => void run(() => api.removeHealthContact(c.kind))}>{t("moreApps.remove")}</Button>
        </div>
      ))}
      <p className="m-0 text-[13px] text-muted">{t("moreApps.health.hint")}</p>
    </section>
  );
}

export function CarPanel() {
  const t = useT("privat");
  const { api } = usePrivat();
  const fn = useCallback(() => api.car(), [api]);
  const { data, err, run } = useLoad<CarInfo>(fn);
  const [form, setForm] = useState({ plate: "", inspection_due: "", service_due: "", tire_reminders: false });
  // Fill the form from the server once – typing before the first load answered must not be wiped (notes-PA 17).
  const filled = useRef(false);
  useEffect(() => {
    if (!data || filled.current) return;
    filled.current = true;
    setForm((f) => (f.plate || f.inspection_due || f.service_due ? f
      : { plate: data.plate ?? "", inspection_due: data.inspection_due ?? "", service_due: data.service_due ?? "", tire_reminders: data.tire_reminders }));
  }, [data]);
  return (
    <form className="rounded-[18px] border-[1.5px] border-ink bg-panel p-3.5 flex flex-col gap-2" data-testid="car-panel"
      onSubmit={(e) => { e.preventDefault(); void run(() => api.saveCar({ ...form, plate: form.plate || undefined, inspection_due: form.inspection_due || undefined, service_due: form.service_due || undefined })); }}>
      <Eyebrow>{t("moreApps.car.title")}</Eyebrow>
      <Err err={err} />
      {data?.workshop && <p className="m-0 text-[14px]">{t("moreApps.car.workshop")}: {data.workshop.name} · {data.workshop.phone_display}</p>}
      <label className="text-[13px] text-muted flex flex-col gap-1">{t("moreApps.car.plate")}
        <input value={form.plate} maxLength={12} className={INPUT} onChange={(e) => setForm({ ...form, plate: e.target.value })} />
      </label>
      <label className="text-[13px] text-muted flex flex-col gap-1">{t("moreApps.car.inspection")}
        <input type="date" value={form.inspection_due} className={INPUT} onChange={(e) => setForm({ ...form, inspection_due: e.target.value })} />
      </label>
      <label className="text-[13px] text-muted flex flex-col gap-1">{t("moreApps.car.service")}
        <input type="date" value={form.service_due} className={INPUT} onChange={(e) => setForm({ ...form, service_due: e.target.value })} />
      </label>
      <label className="text-[14px] flex items-center gap-2 min-h-[44px]">
        <input type="checkbox" checked={form.tire_reminders} onChange={(e) => setForm({ ...form, tire_reminders: e.target.checked })} />
        {t("moreApps.car.tyres")}
      </label>
      <Button type="submit" className="rounded-full self-start">{t("moreApps.save")}</Button>
      <p className="m-0 text-[13px] text-muted">{t("moreApps.car.hint")}</p>
    </form>
  );
}

export function ParcelsPanel() {
  const t = useT("privat");
  const { api } = usePrivat();
  const fn = useCallback(() => api.parcels(), [api]);
  const { data, err, run } = useLoad<{ items: Parcel[] }>(fn);
  const [number, setNumber] = useState("");
  const [label, setLabel] = useState("");
  return (
    <div className="flex flex-col gap-3" data-testid="parcels-panel">
      <Err err={err} />
      <Eyebrow>{t("moreApps.parcels.title")}</Eyebrow>
      {data && data.items.length === 0 && <p className="m-0 text-[14px] text-muted">{t("moreApps.parcels.none")}</p>}
      {data?.items.map((p) => (
        <div key={p.number} className={CARD}>
          <span className="font-semibold text-[15px] [overflow-wrap:anywhere]">{p.text}</span>
          {(p.event || p.carrier) && <span className="text-[13px] text-ink-soft">{[p.carrier, p.event].filter(Boolean).join(" · ")}</span>}
          <span className="flex gap-2 flex-wrap">
            {!p.done && <Button variant="outline" className="rounded-full border-2" onClick={() => void run(() => api.refreshParcel(p.number))}>{t("moreApps.parcels.refresh")}</Button>}
            <Button variant="outline" className="rounded-full border-2" onClick={() => void run(() => api.removeParcel(p.number))}>{t("moreApps.parcels.stop")}</Button>
          </span>
          {p.status === "NotFound" && <span className="text-[13px] text-muted">{t("moreApps.parcels.slow")}</span>}
        </div>
      ))}
      <form className="rounded-[18px] border-[1.5px] border-ink bg-panel p-3.5 flex flex-col gap-2"
        onSubmit={(e) => { e.preventDefault(); if (number.trim()) void run(async () => { await api.addParcel({ number: number.trim(), ...(label.trim() ? { label: label.trim() } : {}) }); setNumber(""); setLabel(""); }); }}>
        <input value={number} onChange={(e) => setNumber(e.target.value)} placeholder={t("moreApps.parcels.number")} aria-label={t("moreApps.parcels.number")} maxLength={60} className={INPUT} />
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={t("moreApps.parcels.label")} aria-label={t("moreApps.parcels.label")} maxLength={100} className={INPUT} />
        <Button type="submit" className="rounded-full self-start" disabled={!number.trim()}>{t("moreApps.parcels.follow")}</Button>
        <p className="m-0 text-[13px] text-muted">{t("moreApps.parcels.hint")}</p>
      </form>
    </div>
  );
}
