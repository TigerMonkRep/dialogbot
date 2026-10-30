import { Tag } from "@/components/ui";
import { ChannelOff, NotOperator, SalgFrame, kr, load } from "../shared";
import { IntegrationNote } from "./client";

type Reg = { system: string; label: string; status: string; source: string; note: string };
type Knowledge = {
  sales_workspace: { id: string; name: string; knowledge_revision: number } | null;
  items: { item_id: string; kind: string; title: string; audience: string; version_no: number }[];
  open_drafts: number;
  prices: { monthly_net_minor: number; campaign_call_net_minor: number; specialist_setup_net_minor: number; tax_basis_points: number; terms_version: string };
  scripts: { script_version: string; status: string; count: number }[];
  fallback_features: Record<string, string>; integrations: Reg[];
};
const AUDIENCE: Record<string, string> = { public: "Offentlig", customer_docs: "Kundedokumentation", internal: "Intern (aldrig i prompt)" };
const STATUS_TEXT: Record<string, string> = { AKTIV: "Aktiv", KRÆVER_OPSÆTNING: "Kræver opsætning", PLANLAGT: "Planlagt", UKENDT: "Ukendt" };

export default async function KnowledgePage() {
  const r = await load<Knowledge>("/operator/salg/knowledge");
  if (!r.ok) {
    if (r.status === 501) return <SalgFrame active="/app/operator/salg/viden" title="Viden og tilbud"><ChannelOff message={r.message} /></SalgFrame>;
    return <NotOperator />;
  }
  const k = r.data;
  return (
    <SalgFrame active="/app/operator/salg/viden" title="Viden og tilbud" intro="Peter bruger kun godkendt viden fra salgsarbejdsrummet (målgruppe offentlig og kundedokumentation) og prislisten. Intern viden kommer aldrig i en prompt.">
      <div className="grid lg:grid-cols-2 gap-space-md">
        <section className="rounded-2xl border-2 border-ink bg-paper p-space-md">
          <h2 className="font-display font-bold text-[18px]">Godkendt salgsviden</h2>
          {!k.sales_workspace ? <p className="text-muted text-[14px]">SALES_WORKSPACE_ID er ikke sat.</p> : (
            <>
              <p className="text-[13px] text-muted">{k.sales_workspace.name} · revision {k.sales_workspace.knowledge_revision} · {k.open_drafts} udkast venter på godkendelse (godkendes under Viden i salgsarbejdsrummet).</p>
              {k.items.length === 0 ? (
                <div className="text-[14px] mt-2"><p>Ingen godkendt viden – manuskripterne bruger reservelisten nedenfor. Kør <code>python -m scripts.seed_sales_knowledge</code> og godkend udkastene.</p>
                  <ul className="list-disc pl-5 text-muted">{Object.values(k.fallback_features).map((f) => <li key={f}>{f}</li>)}</ul></div>
              ) : <ul className="text-[14px] mt-2 flex flex-col gap-1">{k.items.map((i) => <li key={i.item_id}>{i.title} <Tag tone={i.audience === "internal" ? "secondary" : "neutral"}>{AUDIENCE[i.audience] ?? i.audience}</Tag></li>)}</ul>}
            </>
          )}
        </section>
        <section className="rounded-2xl border-2 border-ink bg-paper p-space-md text-[14px]">
          <h2 className="font-display font-bold text-[18px]">Prisliste ({k.prices.terms_version})</h2>
          <ul className="flex flex-col gap-1 mt-1">
            <li>Abonnement: {kr(k.prices.monthly_net_minor)} om måneden ekskl. moms, uden binding</li>
            <li>Udgående kampagneopkald: {kr(k.prices.campaign_call_net_minor)} pr. opkald ekskl. moms</li>
            <li>Specialist-opsætning: {kr(k.prices.specialist_setup_net_minor)} én gang ekskl. moms (gør-det-selv er med i abonnementet)</li>
            <li>Moms: {k.prices.tax_basis_points / 100} %</li>
          </ul>
          <p className="text-muted mt-2">Tilbud med egen version kommer i fase 3. Manuskripter bruger kun disse beløb; alt andet afvises ved valideringen.</p>
          <h3 className="font-semibold mt-3">Manuskriptversioner</h3>
          <ul>{k.scripts.length === 0 ? <li className="text-muted">Ingen endnu</li> : k.scripts.map((s) => <li key={s.script_version + s.status}>{s.script_version}: {s.count} {s.status}</li>)}</ul>
        </section>
      </div>
      <section className="rounded-2xl border-2 border-ink bg-paper p-space-md">
        <h2 className="font-display font-bold text-[18px]">Integrationsregister</h2>
        <p className="text-[13px] text-muted">Hvad Peter må sige om et system. Ukendte systemer er altid &quot;ukendt&quot;.</p>
        <div className="overflow-x-auto"><table className="w-full text-[14px] mt-2">
          <thead className="text-left text-muted"><tr><th className="pr-2">System</th><th className="pr-2">Status</th><th className="pr-2">Kilde</th><th>Note</th></tr></thead>
          <tbody>{k.integrations.map((i) => <tr key={i.system} className="border-t border-line"><td className="pr-2 py-1">{i.label}</td><td className="pr-2">{STATUS_TEXT[i.status] ?? i.status}</td><td className="pr-2">{i.source === "operator" ? "Operatør" : "Connectors"}</td><td className="text-muted">{i.note}</td></tr>)}</tbody>
        </table></div>
        <IntegrationNote />
      </section>
    </SalgFrame>
  );
}
