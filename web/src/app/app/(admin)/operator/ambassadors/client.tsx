"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, useSubmit } from "@/components/ui";
import { STATUS, date, kr } from "@/app/ambassador/shared";

export type OpRow = {
  id: string; full_name: string; email: string; status: keyof typeof STATUS; kind: "private" | "company"; minor: boolean; parent_confirmed: boolean;
  slug: string; code: string; created_at: string; customers: number; clicks_30d: number; payout_blockers: string[];
  held_minor: number; payable_minor: number; in_payout_minor: number; paid_minor: number; min_payout_minor: number;
};
export type OpList = { items: OpRow[]; totals: { pending: number; payable_minor: number; held_minor: number; in_payout_minor: number } };
export type OpPayout = { id: string; number: number; status: "pending" | "paid" | "cancelled"; amount_minor: number; income_type: string; reference: string; paid_at: string | null; created_at: string; ambassador_id: string; ambassador_name: string; bank_last4: string | null };

export function AmbassadorAdmin({ list, payouts }: { list: OpList; payouts: OpPayout[] }) {
  const router = useRouter();
  const [filter, setFilter] = useState<string>(list.totals.pending ? "pending" : "");
  const [result, setResult] = useState<{ created: number; skipped: { name: string; reason: string; amount_minor: number }[] } | null>(null);
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const create = useSubmit(async () => {
    const r = await api<{ created: unknown[]; skipped: { name: string; reason: string; amount_minor: number }[] }>("/operator/ambassadors/payouts", { method: "POST", body: "{}" });
    setResult({ created: r.created.length, skipped: r.skipped }); router.refresh();
  });
  const rows = list.items.filter((r) => !filter || r.status === filter);
  const pendingPayouts = payouts.filter((p) => p.status === "pending");
  return (
    <div className="flex flex-col gap-space-lg">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-space-md">
        {[["Venter på godkendelse", String(list.totals.pending), "how_to_reg"], ["Klar til udbetaling", kr(list.totals.payable_minor), "payments"], ["Optjent (30 dages hold)", kr(list.totals.held_minor), "hourglass_top"], ["Under udbetaling", kr(list.totals.in_payout_minor), "account_balance"]].map(([l, v, i]) => (
          <div key={l} className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm"><p className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-bold flex items-center gap-1"><Icon name={i} size={16} />{l}</p><p className="font-headline-md text-headline-md text-primary font-bold tabular-nums mt-1">{v}</p></div>
        ))}
      </div>

      <section className="rounded-xl bg-surface-container-lowest shadow-sm">
        <header className="flex flex-wrap items-center justify-between gap-space-sm p-space-md">
          <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Ambassadører ({list.items.length})</h2>
          <div className="w-full sm:w-60">
            <Select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filtrér status">
              <option value="">Alle</option>{Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </Select>
          </div>
        </header>
        {rows.length === 0 ? <p className="px-space-md pb-space-md font-body-sm text-body-sm text-on-surface-variant">Ingen ambassadører {filter ? "med den status" : "endnu"}. Del tilmeldingssiden: /ambassador/bliv</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left font-body-sm text-body-sm">
              <thead className="bg-surface-container-low font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider"><tr><th className="p-space-sm">Navn</th><th className="p-space-sm">Status</th><th className="p-space-sm">Kunder</th><th className="p-space-sm text-right">Optjent</th><th className="p-space-sm text-right">Klar</th><th className="p-space-sm">Udbetaling</th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.id} className="border-t border-outline-variant/40 hover:bg-surface-container-low">
                  <td className="p-space-sm"><Link href={`/app/operator/ambassadors/${r.id}`} className="font-semibold text-primary underline">{r.full_name}</Link><span className="block font-label-sm text-label-sm text-on-surface-variant">{r.email} · {r.kind === "company" ? "CVR" : r.minor ? "Privat, under 18" : "Privat"}</span></td>
                  <td className="p-space-sm"><span className={`inline-flex px-2 py-0.5 rounded-full font-label-sm text-label-sm ${STATUS[r.status].tone}`}>{STATUS[r.status].label}</span>{r.minor && !r.parent_confirmed && <span className="block font-label-sm text-label-sm text-on-surface-variant">Forælder mangler</span>}</td>
                  <td className="p-space-sm tabular-nums">{r.customers}<span className="block font-label-sm text-label-sm text-on-surface-variant">{r.clicks_30d} besøg/30 d</span></td>
                  <td className="p-space-sm text-right tabular-nums">{kr(r.held_minor)}</td>
                  <td className="p-space-sm text-right tabular-nums font-semibold">{kr(r.payable_minor)}</td>
                  <td className="p-space-sm font-label-sm text-label-sm">{r.status !== "active" ? "–" : r.payout_blockers.length ? <span className="text-error">{r.payout_blockers[0]}</span> : r.payable_minor >= r.min_payout_minor ? <span className="text-secondary font-semibold">Klar</span> : "Under 500 kr."}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-xl bg-surface-container-lowest shadow-sm p-space-md space-y-space-md">
        <div className="flex flex-wrap items-start justify-between gap-space-sm">
          <div>
            <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Udbetalinger</h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">1) Opret udbetalinger (alle klar-saldi ≥ 500 kr.). 2) Åbn ambassadøren, vis bankoplysninger og overfør beløbet i netbanken. 3) Markér som betalt med bankens reference – så får ambassadøren besked og et afregningsbilag.</p>
          </div>
          <Button icon="add_card" disabled={create.pending} onClick={() => create.run()}>{create.pending ? "Opretter…" : "Opret udbetalinger"}</Button>
        </div>
        <ErrorBox error={create.error} />
        {result && (
          <Alert kind={result.created ? "ok" : "info"}>
            {result.created ? `${result.created} udbetaling(er) oprettet.` : "Ingen nye udbetalinger."}
            {result.skipped.length > 0 && <ul className="mt-1 list-disc pl-5">{result.skipped.map((s) => <li key={s.name}>{s.name}: {kr(s.amount_minor)} – {s.reason}</li>)}</ul>}
          </Alert>
        )}
        {pendingPayouts.length > 0 && <ul className="space-y-space-sm">{pendingPayouts.map((p) => <PendingPayout key={p.id} p={p} />)}</ul>}
        {payouts.filter((p) => p.status !== "pending").length > 0 && (
          <details className="font-body-sm text-body-sm">
            <summary className="cursor-pointer font-label-md text-label-md text-primary">Tidligere udbetalinger</summary>
            <ul className="mt-space-sm divide-y divide-outline-variant/40">{payouts.filter((p) => p.status !== "pending").map((p) => (
              <li key={p.id} className="py-2 flex justify-between gap-space-sm"><span>Nr. {p.number} · {p.ambassador_name} · {p.status === "paid" ? `betalt ${date(p.paid_at)} (${p.reference})` : "annulleret"}</span><span className="tabular-nums font-semibold">{kr(p.amount_minor)}</span></li>
            ))}</ul>
          </details>
        )}
      </section>

      <section className="rounded-xl bg-surface-container-lowest shadow-sm p-space-md space-y-space-sm">
        <h2 className="font-headline-sm text-headline-sm text-primary font-bold">B-indkomst til Skattestyrelsen</h2>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Udbetalt bonus til private ambassadører (uden CVR) skal indberettes som B-indkomst i eIndkomst senest 20. januar året efter. Filen indeholder navn, CPR og beløb. Hentningen logges.</p>
        <div className="flex flex-wrap items-end gap-space-sm">
          <Field label="År"><Input type="number" min={2025} max={2100} value={year} onChange={(e) => setYear(e.target.value)} className="w-28" /></Field>
          <a href={`/api/backend/operator/ambassadors/b-income.csv?year=${encodeURIComponent(year)}`} className="inline-flex items-center gap-space-xs rounded-xl px-space-lg py-2.5 bg-surface-container-low text-primary font-label-lg text-label-lg"><Icon name="download" size={18} />Hent CSV</a>
        </div>
      </section>
    </div>
  );
}

function PendingPayout({ p }: { p: OpPayout }) {
  const router = useRouter();
  const [ref, setRef] = useState("");
  const paid = useSubmit(async () => { await api(`/operator/ambassadors/payouts/${p.id}/paid`, { method: "POST", body: JSON.stringify({ reference: ref }) }); router.refresh(); });
  const cancel = useSubmit(async () => { await api(`/operator/ambassadors/payouts/${p.id}/cancel`, { method: "POST" }); router.refresh(); });
  return (
    <li className="rounded-lg bg-surface-container-low p-space-md flex flex-col md:flex-row md:items-end gap-space-sm">
      <div className="flex-1">
        <p className="font-label-lg text-label-lg font-semibold">Nr. {p.number} · <Link href={`/app/operator/ambassadors/${p.ambassador_id}`} className="underline text-primary">{p.ambassador_name}</Link></p>
        <p className="font-label-sm text-label-sm text-on-surface-variant">{p.income_type === "b_income" ? "B-indkomst (privat)" : "Virksomhed – tjek moms på ambassadørens side"} · konto …{p.bank_last4}</p>
        <p className="font-headline-sm text-headline-sm font-bold tabular-nums text-primary">{kr(p.amount_minor)}</p>
        <ErrorBox error={paid.error ?? cancel.error} />
      </div>
      <Field label="Bankens reference"><Input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="Fx overførsel 01.10" /></Field>
      <div className="flex gap-space-xs">
        <Button icon="check" disabled={paid.pending || !ref.trim()} onClick={() => paid.run()}>Markér betalt</Button>
        <Button variant="ghost" disabled={cancel.pending} onClick={() => cancel.run()}>Annullér</Button>
      </div>
    </li>
  );
}
