import Link from "next/link";
import { AdminFrame, NotOperator, dt, kr, load } from "../shared";
import { DecideDispute } from "./decide";

type Money = { net_minor: number };
type Dir = { calls: number; minutes: number; extra_minutes: number; net_minor: number; call_fees_net_minor?: number; pending_reports?: number };
type Usage = { month: string; currency: string; package: { included: number; used: number; remaining: number; over: number };
  inbound: Dir; outbound: Dir; overage_net_minor: number } | null;
type RecLine = { period: string; net_minor: number; description: string };
type Customer = { id: string; name: string; open_disputes: number; usage: Usage;
  agreement: { version: number; currency: string; monthly: Money; included_minutes: number; inbound_extra_minute: Money; outbound_extra_minute: Money;
    outbound_call?: { answered: Money; voicemail: Money; no_answer: Money }; created_at: string } | null;
  invoices: { month: string; status: string; net_minor?: number; tax_minor?: number; gross_minor: number; number: string | null;
    lines?: { kind: string; description?: string; net_minor: number }[]; refunds?: { total_minor: number } }[];
  reconciliation?: { next_invoice_month: string; late_usage: RecLine[]; credits: RecLine[]; net_minor: number } };
type Prices = { version: string; valid_from: string; included_minutes: number; currencies: string[];
  erhverv: Record<string, { monthly: number; extra_minute: number; outbound_extra_minute: number; call_answered: number; call_voicemail: number; call_no_answer: number; setup: number }> };
/** Minor units → «2.495,00» (the currency is in the table's column header). */
const amt = (m: number) => (m / 100).toLocaleString("da-DK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
type Dispute = { id: string; workspace_id: string; workspace_name: string; kind: "inbound" | "outbound"; call_at: string; period: string;
  minutes: number; reason: string; status: string; invoiced: boolean; created_at: string };

/** M04 «Fakturering»: complaints about calls to decide, and per customer the agreement (package snapshot), this
 *  month's usage (inbound/outbound, package used/left, overage), invoices and open complaints. */
export default async function Billing() {
  const [data, disputes, prices] = await Promise.all([
    load<{ items: Customer[] }>("/operator/admin/billing"), load<{ items: Dispute[] }>("/operator/admin/disputes?status=open"),
    load<Prices>("/operator/admin/prices"),
  ]);
  if (!data || !disputes || !prices) return <NotOperator />;
  return (
    <AdminFrame active="/app/operator/admin/fakturering" eyebrow="Admin · fakturering" title="Fakturering"
      intro="Klager over opkald afgøres her – minutter krediteres kun efter en godkendt klage. Godkendes en klage i en måned, der ikke er faktureret, går minutterne tilbage i pakken; er måneden faktureret, krediteres beløbet på næste faktura. Afvises den, ændres intet.">
      <section className="rounded-2xl bg-paper border-2 border-ink p-4 flex flex-col gap-3" aria-labelledby="klager">
        <h2 id="klager" className="font-display font-extrabold text-[20px]">Åbne klager ({disputes.items.length})</h2>
        {disputes.items.length === 0 ? <p className="text-muted text-[14px]">Ingen åbne klager.</p> : (
          <ul className="flex flex-col gap-3">{disputes.items.map((d) => (
            <li key={d.id} className="rounded-xl border-[1.5px] border-ink p-3 text-[14px] flex flex-col gap-1" data-dispute={d.id}>
              <span className="font-semibold"><Link className="underline" href={`/app/operator/admin/kunder/${d.workspace_id}`}>{d.workspace_name}</Link> · {d.kind === "inbound" ? "Indgående" : "Kampagne"} · {dt(d.call_at)} · {d.minutes} min</span>
              <span className="text-ink-soft">«{d.reason}» · klaget {dt(d.created_at)} · {d.invoiced ? "måneden er faktureret – godkendelse giver kredit på næste faktura" : "måneden er ikke faktureret – godkendelse giver minutterne tilbage i pakken"}</span>
              <DecideDispute id={d.id} />
            </li>
          ))}</ul>
        )}
      </section>
      <section className="rounded-2xl bg-paper border-2 border-ink p-4 flex flex-col gap-2 overflow-x-auto" aria-labelledby="prisliste" data-testid="price-list">
        <h2 id="prisliste" className="font-display font-extrabold text-[20px]">Prisliste (version {prices.version}, gælder fra {prices.valid_from})</h2>
        <p className="text-[14px] text-ink-soft">Ekskl. moms. Én plan med {prices.included_minutes} minutter pr. måned til ind- og udgående opkald. Aftaler gemmer prisen, de blev indgået til – en ny liste ændrer ingen eksisterende aftale. Prisen ændres i koden (app/modules/billing/prices.py, markets.py).</p>
        <table className="w-full text-[14px] tabular-nums">
          <thead><tr className="text-left eyebrow"><th className="p-2">Valuta</th><th className="p-2">Abonnement/md.</th><th className="p-2">Ind pr. min over pakken</th><th className="p-2">Ud pr. min over pakken</th><th className="p-2">Opkald efter pakken: besvaret / telefonsvarer / ubesvaret</th><th className="p-2">Specialist-opsætning</th></tr></thead>
          <tbody>{prices.currencies.map((cur) => { const p = prices.erhverv[cur]; return p ? (
            <tr key={cur} className="border-t border-line" data-currency={cur}><td className="p-2 font-semibold">{cur}</td><td className="p-2">{amt(p.monthly)}</td><td className="p-2">{amt(p.extra_minute)}</td><td className="p-2">{amt(p.outbound_extra_minute)}</td><td className="p-2">{amt(p.call_answered)} / {amt(p.call_voicemail)} / {amt(p.call_no_answer)}</td><td className="p-2">{amt(p.setup)}</td></tr>
          ) : null; })}</tbody>
        </table>
      </section>
      <div className="rounded-2xl bg-paper border-2 border-ink overflow-x-auto">
        <table className="w-full text-[14px]">
          <thead><tr className="text-left eyebrow"><th className="p-3">Kunde</th><th className="p-3">Aftale</th><th className="p-3">Pakke denne måned</th><th className="p-3">Ind / ud</th><th className="p-3">Overforbrug</th><th className="p-3">Fakturaer</th><th className="p-3">Afstemning til næste faktura</th><th className="p-3">Klager</th></tr></thead>
          <tbody>{data.items.map((c) => (
            <tr key={c.id} className="border-t border-line align-top" data-customer={c.id}>
              <td className="p-3 font-semibold"><Link className="underline" href={`/app/operator/admin/kunder/${c.id}`}>{c.name}</Link></td>
              <td className="p-3">{c.agreement ? <>v{c.agreement.version} · {kr(c.agreement.monthly.net_minor)}/md. · {c.agreement.included_minutes} min · ind {kr(c.agreement.inbound_extra_minute.net_minor)} / ud {kr(c.agreement.outbound_extra_minute.net_minor)}{c.agreement.outbound_call ? ` · opkald ${kr(c.agreement.outbound_call.answered.net_minor)}/${kr(c.agreement.outbound_call.voicemail.net_minor)}/${kr(c.agreement.outbound_call.no_answer.net_minor)}` : ""} ({c.agreement.currency})</> : "Ingen aftale"}</td>
              <td className="p-3 tabular-nums">{c.usage ? `${c.usage.package.used} af ${c.usage.package.included} min · ${c.usage.package.remaining} tilbage` : "–"}</td>
              <td className="p-3 tabular-nums">{c.usage ? <>{c.usage.inbound.calls} opkald, {c.usage.inbound.minutes} min ind<br />{c.usage.outbound.calls} kampagneopkald, {c.usage.outbound.minutes} min ud{c.usage.outbound.pending_reports ? ` · ${c.usage.outbound.pending_reports} afventer rapport` : ""}</> : "–"}</td>
              <td className="p-3 tabular-nums">{c.usage ? <>{c.usage.package.over} min · {kr(c.usage.overage_net_minor)}{c.usage.outbound.call_fees_net_minor ? <><br />heraf opkaldspriser {kr(c.usage.outbound.call_fees_net_minor)}</> : null}</> : "–"}</td>
              <td className="p-3">{c.invoices.length === 0 ? "–" : c.invoices.map((i) => (
                <details key={i.month} className="mb-1"><summary className="cursor-pointer">{i.number ?? i.month} · {i.month} · {i.status} · {kr(i.gross_minor)}{(i.refunds?.total_minor ?? 0) > 0 ? ` · refunderet ${kr(i.refunds!.total_minor)}` : ""}</summary>
                  <ul className="text-[13px] text-ink-soft">{(i.lines ?? []).map((l, n) => <li key={n}>{l.description ?? l.kind}: {kr(l.net_minor)}</li>)}</ul>
                  {i.net_minor !== undefined && <p className="text-[13px]">{kr(i.net_minor)} ekskl. moms · moms {kr(i.tax_minor ?? 0)} · i alt {kr(i.gross_minor)}</p>}
                </details>))}</td>
              <td className="p-3 text-[13px]" data-testid="reconciliation">{!c.reconciliation || (c.reconciliation.late_usage.length + c.reconciliation.credits.length) === 0 ? "Ingen afvigelser" : <>
                {[...c.reconciliation.late_usage, ...c.reconciliation.credits].map((x, n) => <div key={n}>{x.description}: {kr(x.net_minor)}</div>)}
                <div className="font-semibold">I alt på {c.reconciliation.next_invoice_month}: {kr(c.reconciliation.net_minor)}</div></>}</td>
              <td className="p-3 tabular-nums">{c.open_disputes}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </AdminFrame>
  );
}
