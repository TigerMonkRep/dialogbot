import Link from "next/link";
import { Tag } from "@/components/ui";
import { ChannelOff, NotOperator, SalgFrame, dt, kr, load } from "../shared";
import { CAMPAIGN_STATUS as STATUS, type SalesCampaign } from "../labels";
import { BlockForm, NewCampaign } from "./client";

type Block = { id: string; kind: string; value: string; reason: string; source: string; created_at: string | null };

export default async function CampaignsPage() {
  const [r, b] = await Promise.all([load<{ items: SalesCampaign[] }>("/operator/salg/campaigns"), load<{ items: Block[] }>("/operator/salg/block-list")]);
  if (!r.ok) {
    if (r.status === 501) return <SalgFrame active="/app/operator/salg/kampagner" title="Kampagner"><ChannelOff message={r.message} /></SalgFrame>;
    return <NotOperator status={r.status} message={r.message} />;
  }
  const items = r.data.items;
  return (
    <SalgFrame active="/app/operator/salg/kampagner" title="Kampagner" intro="Peter ringer kun til kontakter, som kontaktpolitikken tillader: dokumenteret kontaktgrundlag, ikke spærret, ikke reklamebeskyttet, inden for vinduet og budgettet. Politikken tjekkes, når kontakten tilføjes, og igen lige før hvert opkald.">
      <div className="grid lg:grid-cols-[minmax(0,26rem)_1fr] gap-space-lg items-start">
        <NewCampaign />
        <section className="rounded-2xl border-2 border-ink bg-paper p-space-md min-w-0">
          <h2 className="font-display font-bold text-[18px] mb-2">Interne kampagner</h2>
          {items.length === 0 ? <p className="text-muted text-[14px]">Ingen endnu. Tilføj virksomheder fra deres side under Virksomheder.</p> : (
            <ul className="flex flex-col gap-2">{items.map((c) => (
              <li key={c.id} className="rounded-xl border-[1.5px] border-ink p-3 text-[14px]">
                <div className="flex flex-wrap gap-2 items-center justify-between">
                  <Link className="font-semibold underline" href={`/app/operator/salg/kampagner/${c.id}`}>{c.name}</Link>
                  <span className="flex gap-2">{c.is_test && <Tag tone="secondary">Test</Tag>}<Tag>{STATUS[c.status] ?? c.status}</Tag></span>
                </div>
                <p className="text-muted">{c.counts.total} kontakter · {c.counts.open} åbne · {c.counts.calls} opkald · brugt {kr(c.spent_net_minor)}{c.budget_net_minor != null ? ` af ${kr(c.budget_net_minor)}` : ""} · oprettet {dt(c.created_at)}</p>
              </li>))}</ul>
          )}
        </section>
      </div>
      <section className="rounded-2xl border-2 border-ink bg-paper p-space-md">
        <h2 className="font-display font-bold text-[18px]">Spærreliste for Dialogbots salg</h2>
        <p className="text-[13px] text-muted">Gælder alle interne kampagner og testopkald. Frabedelser i opkald kommer automatisk herind.</p>
        <BlockForm />
        {b.ok && b.data.items.length > 0 && (
          <ul className="text-[14px] mt-2">{b.data.items.map((x) => <li key={x.id}>{x.kind === "phone" ? "Telefon" : x.kind === "domain" ? "Domæne" : "CVR"}: <span className="tabular-nums">{x.value}</span> <span className="text-muted">· {x.reason || "–"} · {x.source === "call" ? "fra opkald" : x.source === "dispute" ? "indsigelse" : "manuelt"} · {dt(x.created_at)}</span></li>)}</ul>
        )}
      </section>
    </SalgFrame>
  );
}
