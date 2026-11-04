"use client";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { ErrorBox, Field, Input, Select, useSubmit } from "@/components/ui";

export type Code = {
  id: string; code: string; audience: "erhverv" | "privat" | "begge"; percent_off: number | null; amount_off_minor: number | null;
  duration: "once" | "repeating" | "forever"; duration_months: number | null; max_redemptions: number | null; redemptions: number;
  starts_at: string | null; ends_at: string | null; active: boolean; note: string; text: string; stripe: boolean; created_at: string;
};

const dt = (iso: string) => new Date(iso).toLocaleDateString("da-DK", { dateStyle: "short", timeZone: "Europe/Copenhagen" });
const AUD: Record<Code["audience"], string> = { erhverv: "Erhverv", privat: "Privat", begge: "Erhverv + Privat" };
const BTN = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper text-[14px] font-semibold text-ink hover:bg-panel disabled:opacity-50";
const BTN_PRIMARY = "inline-flex items-center justify-center min-h-[44px] px-5 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-50";

export function DiscountCodes({ initial, stripe }: { initial: Code[]; stripe: boolean }) {
  const [items, setItems] = useState(initial);
  const [form, setForm] = useState({ code: "", audience: "begge", kind: "percent", value: "", duration: "once", months: "3", max: "", ends: "", note: "" });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });
  const create = useSubmit(async () => {
    const v = Number(form.value.replace(",", "."));
    const body = {
      code: form.code, audience: form.audience, duration: form.duration, note: form.note,
      percent_off: form.kind === "percent" ? Math.round(v) : null,
      amount_off_minor: form.kind === "amount" ? Math.round(v * 100) : null,
      duration_months: form.duration === "repeating" ? Number(form.months) : null,
      max_redemptions: form.max ? Number(form.max) : null,
      ends_at: form.ends ? new Date(`${form.ends}T23:59:59`).toISOString() : null,
    };
    const made = await api<Code>("/operator/admin/rabatkoder", { method: "POST", body: JSON.stringify(body) });
    setItems([made, ...items]);
    setForm({ ...form, code: "", value: "", max: "", ends: "", note: "" });
  });
  const off = useSubmit(async (id: string) => {
    const r = await api<Code>(`/operator/admin/rabatkoder/${id}/deaktiver`, { method: "POST", body: "{}" });
    setItems(items.map((x) => (x.id === id ? r : x)));
  });
  return (
    <div className="flex flex-col gap-space-lg">
      <form onSubmit={(e) => { e.preventDefault(); create.run(); }} className="rounded-2xl bg-paper border-2 border-ink p-space-md flex flex-col gap-3">
        <h2 className="font-display font-bold text-[18px]">Ny rabatkode</h2>
        {!stripe && <p className="rounded-xl bg-highlight px-4 py-2 text-[13px] text-ink">Stripe er ikke sat op på serveren: Privat-koder bliver gemt, men kan først bruges på betalingssiden, når STRIPE_SECRET_KEY er sat.</p>}
        <div className="grid md:grid-cols-3 gap-3">
          <Field label="Kode" error={fieldError(create.error, "code")} hint="3-20 bogstaver/tal. Gemmes med store bogstaver."><Input required value={form.code} onChange={set("code")} placeholder="Fx VELKOMMEN20" className="uppercase" /></Field>
          <Field label="Gælder for"><Select value={form.audience} onChange={set("audience")}><option value="begge">Erhverv + Privat</option><option value="erhverv">Kun Erhverv</option><option value="privat">Kun Privat</option></Select></Field>
          <Field label="Note (kun for jer)"><Input value={form.note} onChange={set("note")} placeholder="Fx Messen i Herning" /></Field>
          <Field label="Rabat"><Select value={form.kind} onChange={set("kind")}><option value="percent">Procent</option><option value="amount">Fast beløb i kr.</option></Select></Field>
          <Field label={form.kind === "percent" ? "Procent (1-100)" : "Beløb i kr. (Erhverv: ekskl. moms · Privat: inkl. moms)"} error={fieldError(create.error, "percent_off") ?? fieldError(create.error, "amount_off_minor")}>
            <Input required inputMode="decimal" value={form.value} onChange={set("value")} placeholder={form.kind === "percent" ? "20" : "500"} /></Field>
          <Field label="Varighed" error={fieldError(create.error, "duration_months")}>
            <div className="flex gap-2">
              <Select value={form.duration} onChange={set("duration")} className="flex-1"><option value="once">Én gang (første måned)</option><option value="repeating">Et antal måneder</option><option value="forever">Altid</option></Select>
              {form.duration === "repeating" && <Input type="number" min={1} max={36} value={form.months} onChange={set("months")} className="!w-24" aria-label="Antal måneder" />}
            </div>
          </Field>
          <Field label="Maks. antal kunder (tomt = ubegrænset)" error={fieldError(create.error, "max_redemptions")}><Input type="number" min={1} value={form.max} onChange={set("max")} /></Field>
          <Field label="Kan bruges til og med (tomt = ingen slutdato)" error={fieldError(create.error, "ends_at")}><Input type="date" value={form.ends} onChange={set("ends")} /></Field>
        </div>
        <ErrorBox error={create.error} />
        <button type="submit" className={`${BTN_PRIMARY} self-start`} disabled={create.pending}>{create.pending ? "Opretter…" : "Opret rabatkode"}</button>
      </form>

      <section className="rounded-2xl bg-paper border-2 border-ink" aria-label="Alle rabatkoder">
        <h2 className="px-space-md pt-space-md font-display font-bold text-[18px]">Alle koder</h2>
        {items.length === 0 ? <p className="p-space-md text-on-surface-variant">Ingen koder endnu.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[14px] mt-3">
              <thead><tr className="text-[12px] uppercase tracking-[0.08em] text-muted"><th className="px-space-md pb-2 font-semibold">Kode</th><th className="pb-2 pr-3 font-semibold">Rabat</th><th className="pb-2 pr-3 font-semibold">Gælder for</th><th className="pb-2 pr-3 font-semibold">Brugt</th><th className="pb-2 pr-3 font-semibold">Udløber</th><th className="pb-2 pr-3 font-semibold">Status</th><th className="pb-2 pr-3 font-semibold">Note</th><th /></tr></thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id} className="border-t-[1.5px] border-line align-top">
                    <td className="px-space-md py-2.5 font-mono font-bold text-[15px]">{c.code}</td>
                    <td className="py-2.5 pr-3">{c.text}</td>
                    <td className="py-2.5 pr-3">{AUD[c.audience]}{c.audience !== "erhverv" && !c.stripe && <span className="block text-[12px] text-danger">Ikke på Stripe endnu</span>}</td>
                    <td className="py-2.5 pr-3 tabular-nums">{c.redemptions}{c.max_redemptions ? ` / ${c.max_redemptions}` : ""}</td>
                    <td className="py-2.5 pr-3 whitespace-nowrap">{c.ends_at ? dt(c.ends_at) : "–"}</td>
                    <td className="py-2.5 pr-3">{c.active ? <span className="inline-flex px-2 py-0.5 rounded-full bg-success-soft text-success text-[12px] font-semibold">Aktiv</span> : <span className="inline-flex px-2 py-0.5 rounded-full bg-panel text-muted text-[12px] font-semibold">Deaktiveret</span>}</td>
                    <td className="py-2.5 pr-3 text-muted max-w-[220px]">{c.note}</td>
                    <td className="py-2.5 pr-space-md text-right">{c.active && <button type="button" className={BTN} disabled={off.pending} onClick={() => off.run(c.id)}>Deaktivér</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <ErrorBox error={off.error} />
        <p className="px-space-md pb-space-md pt-2 text-[13px] text-muted">Link til Privat med koden sat på forhånd: <code>dialogbot.app/privat/konto?plan=plus&amp;kode=KODEN</code>. En deaktiveret kode gælder stadig for kunder, der allerede har brugt den.</p>
      </section>
    </div>
  );
}
