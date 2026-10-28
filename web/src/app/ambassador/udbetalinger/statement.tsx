import { date, kr, monthLabel, type Statement } from "../shared";

/** Afregningsbilag: who is paid, for which customers and months, and how it is taxed. Printable. */
export function PayoutStatement({ s }: { s: Statement }) {
  const a = s.ambassador;
  const vat = s.income_type === "invoice" && a.vat_registered ? Math.round(s.amount_minor / 4) : 0;
  return (
    <article className="rounded-[20px] bg-white border-2 border-ink p-6 md:p-8 flex flex-col gap-6 max-w-3xl print:border print:border-ink">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <p className="m-0 eyebrow">Afregningsbilag</p>
          <h1 className="m-0 font-display font-extrabold text-[clamp(26px,3vw,32px)] leading-[1.1] tracking-[-0.5px] text-ink">Nr. {s.number}</h1>
          <p className="m-0 text-[15px] text-ink-soft">Oprettet {date(s.created_at)} · {s.status === "paid" ? `Udbetalt ${date(s.paid_at)}${s.reference ? ` (${s.reference})` : ""}` : s.status === "cancelled" ? "Annulleret" : "Under udbetaling"}</p>
        </div>
        <div className="text-right text-[15px]">
          <p className="m-0 font-display font-extrabold text-ink">Dialogbot</p>
          <p className="m-0 text-muted">Ambassadørprogrammet</p>
        </div>
      </header>
      <section className="grid sm:grid-cols-2 gap-4 text-[15px] text-ink">
        <div className="rounded-xl border-[1.5px] border-ink bg-panel p-4"><p className="m-0 eyebrow mb-1">Modtager</p><p className="m-0 font-semibold">{a.kind === "company" ? a.company_name : a.full_name}</p>{a.kind === "company" && <p>CVR {a.cvr}</p>}{a.kind === "company" && <p>Att. {a.full_name}</p>}</div>
        <div className="rounded-xl border-[1.5px] border-ink bg-panel p-4"><p className="m-0 eyebrow mb-1">Udbetales til</p><p className="m-0">Bankkonto der slutter på {a.bank_last4 ?? "–"}</p></div>
      </section>
      <div className="overflow-x-auto rounded-xl border-[1.5px] border-ink">
        <table className="w-full text-left text-[15px] text-ink">
          <thead className="bg-panel text-[12px] font-semibold text-muted uppercase tracking-[0.12em] border-b-[1.5px] border-ink"><tr><th className="px-3 py-2.5">Post</th><th className="px-3 py-2.5">Kunde</th><th className="px-3 py-2.5">Måned</th><th className="px-3 py-2.5 text-right">Beløb</th></tr></thead>
          <tbody>{s.lines.map((l) => (
            <tr key={l.id} className="border-b-[1.5px] border-line"><td className="px-3 py-2.5">{l.label}</td><td className="px-3 py-2.5">{l.company}</td><td className="px-3 py-2.5">{monthLabel(l.month)}</td><td className="px-3 py-2.5 text-right tabular-nums">{kr(l.amount_minor)}</td></tr>
          ))}</tbody>
          <tfoot className="font-semibold">
            {vat > 0 && <><tr><td colSpan={3} className="px-3 pt-3">Beløb ekskl. moms</td><td className="px-3 pt-3 text-right tabular-nums">{kr(s.amount_minor)}</td></tr><tr><td colSpan={3} className="px-3 py-1">Moms 25 %</td><td className="px-3 py-1 text-right tabular-nums">{kr(vat)}</td></tr></>}
            <tr><td colSpan={3} className="px-3 py-3 font-display font-extrabold text-[17px]">I alt {s.status === "paid" ? "udbetalt" : "til udbetaling"}</td><td className="px-3 py-3 text-right tabular-nums font-display font-extrabold text-[17px]">{kr(s.amount_minor + vat)}</td></tr>
          </tfoot>
        </table>
      </div>
      <p className="m-0 rounded-xl border-[1.5px] border-ink bg-panel p-4 text-[15px] leading-normal text-ink-soft">{s.tax_note}</p>
    </article>
  );
}
