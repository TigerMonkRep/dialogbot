import Link from "next/link";
import { AdminFrame, NotOperator, dt, kr, load } from "../shared";
import { DecideDispute } from "./decide";

type Money = { net_minor: number };
type Usage = { month: string; currency: string; package: { included: number; used: number; remaining: number; over: number };
  inbound: { calls: number; minutes: number; extra_minutes: number; net_minor: number };
  outbound: { calls: number; minutes: number; extra_minutes: number; net_minor: number }; overage_net_minor: number } | null;
type Customer = { id: string; name: string; open_disputes: number; usage: Usage;
  agreement: { version: number; currency: string; monthly: Money; included_minutes: number; inbound_extra_minute: Money; outbound_extra_minute: Money; created_at: string } | null;
  invoices: { month: string; status: string; gross_minor: number; number: string | null }[] };
type Dispute = { id: string; workspace_id: string; workspace_name: string; kind: "inbound" | "outbound"; call_at: string; period: string;
  minutes: number; reason: string; status: string; invoiced: boolean; created_at: string };

/** M04 «Fakturering»: complaints about calls to decide, and per customer the agreement (package snapshot), this
 *  month's usage (inbound/outbound, package used/left, overage), invoices and open complaints. */
export default async function Billing() {
  const [data, disputes] = await Promise.all([
    load<{ items: Customer[] }>("/operator/admin/billing"), load<{ items: Dispute[] }>("/operator/admin/disputes?status=open"),
  ]);
  if (!data || !disputes) return <NotOperator />;
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
      <div className="rounded-2xl bg-paper border-2 border-ink overflow-x-auto">
        <table className="w-full text-[14px]">
          <thead><tr className="text-left eyebrow"><th className="p-3">Kunde</th><th className="p-3">Aftale</th><th className="p-3">Pakke denne måned</th><th className="p-3">Ind / ud</th><th className="p-3">Overforbrug</th><th className="p-3">Fakturaer</th><th className="p-3">Klager</th></tr></thead>
          <tbody>{data.items.map((c) => (
            <tr key={c.id} className="border-t border-line align-top" data-customer={c.id}>
              <td className="p-3 font-semibold"><Link className="underline" href={`/app/operator/admin/kunder/${c.id}`}>{c.name}</Link></td>
              <td className="p-3">{c.agreement ? <>v{c.agreement.version} · {kr(c.agreement.monthly.net_minor)}/md. · {c.agreement.included_minutes} min · ind {kr(c.agreement.inbound_extra_minute.net_minor)} / ud {kr(c.agreement.outbound_extra_minute.net_minor)} ({c.agreement.currency})</> : "Ingen aftale"}</td>
              <td className="p-3 tabular-nums">{c.usage ? `${c.usage.package.used} af ${c.usage.package.included} min · ${c.usage.package.remaining} tilbage` : "–"}</td>
              <td className="p-3 tabular-nums">{c.usage ? `${c.usage.inbound.minutes} / ${c.usage.outbound.minutes} min` : "–"}</td>
              <td className="p-3 tabular-nums">{c.usage ? `${c.usage.package.over} min · ${kr(c.usage.overage_net_minor)}` : "–"}</td>
              <td className="p-3">{c.invoices.length === 0 ? "–" : c.invoices.map((i) => <div key={i.month}>{i.month} · {i.status} · {kr(i.gross_minor)}</div>)}</td>
              <td className="p-3 tabular-nums">{c.open_disputes}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </AdminFrame>
  );
}
