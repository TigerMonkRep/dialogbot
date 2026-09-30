import { date, kr, monthLabel, type Statement } from "../shared";

/** Afregningsbilag: who is paid, for which customers and months, and how it is taxed. Printable. */
export function PayoutStatement({ s }: { s: Statement }) {
  const a = s.ambassador;
  const vat = s.income_type === "invoice" && a.vat_registered ? Math.round(s.amount_minor / 4) : 0;
  return (
    <article className="rounded-xl bg-surface-container-lowest p-space-lg md:p-space-xl shadow-sm space-y-space-lg max-w-3xl print:shadow-none">
      <header className="flex flex-wrap items-start justify-between gap-space-md">
        <div>
          <p className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-bold">Afregningsbilag</p>
          <h1 className="font-headline-md text-headline-md text-primary font-bold">Nr. {s.number}</h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Oprettet {date(s.created_at)} · {s.status === "paid" ? `Udbetalt ${date(s.paid_at)}${s.reference ? ` (${s.reference})` : ""}` : s.status === "cancelled" ? "Annulleret" : "Under udbetaling"}</p>
        </div>
        <div className="text-right font-body-sm text-body-sm">
          <p className="font-semibold">Dialogbot</p>
          <p className="text-on-surface-variant">Ambassadørprogrammet</p>
        </div>
      </header>
      <section className="grid sm:grid-cols-2 gap-space-md font-body-sm text-body-sm">
        <div><p className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-bold">Modtager</p><p className="font-semibold">{a.kind === "company" ? a.company_name : a.full_name}</p>{a.kind === "company" && <p>CVR {a.cvr}</p>}{a.kind === "company" && <p>Att. {a.full_name}</p>}</div>
        <div><p className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-bold">Udbetales til</p><p>Bankkonto der slutter på {a.bank_last4 ?? "–"}</p></div>
      </section>
      <div className="overflow-x-auto">
        <table className="w-full text-left font-body-sm text-body-sm">
          <thead className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider border-b border-outline-variant"><tr><th className="py-2 pr-2">Post</th><th className="py-2 pr-2">Kunde</th><th className="py-2 pr-2">Måned</th><th className="py-2 text-right">Beløb</th></tr></thead>
          <tbody>{s.lines.map((l) => (
            <tr key={l.id} className="border-b border-outline-variant/40"><td className="py-2 pr-2">{l.label}</td><td className="py-2 pr-2">{l.company}</td><td className="py-2 pr-2">{monthLabel(l.month)}</td><td className="py-2 text-right tabular-nums">{kr(l.amount_minor)}</td></tr>
          ))}</tbody>
          <tfoot className="font-semibold">
            {vat > 0 && <><tr><td colSpan={3} className="pt-2">Beløb ekskl. moms</td><td className="pt-2 text-right tabular-nums">{kr(s.amount_minor)}</td></tr><tr><td colSpan={3}>Moms 25 %</td><td className="text-right tabular-nums">{kr(vat)}</td></tr></>}
            <tr><td colSpan={3} className="pt-2 text-primary">I alt {s.status === "paid" ? "udbetalt" : "til udbetaling"}</td><td className="pt-2 text-right tabular-nums text-primary font-bold">{kr(s.amount_minor + vat)}</td></tr>
          </tfoot>
        </table>
      </div>
      <p className="rounded-lg bg-surface-container-low p-space-md font-body-sm text-body-sm">{s.tax_note}</p>
    </article>
  );
}
