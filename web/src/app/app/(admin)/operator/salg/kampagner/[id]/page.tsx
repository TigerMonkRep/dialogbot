import Link from "next/link";
import { Tag } from "@/components/ui";
import { ChannelOff, NotOperator, SalgFrame, kr, load } from "../../shared";
import { CampaignControls } from "../client";
import { CAMPAIGN_STATUS as STATUS, type SalesCampaign } from "../../labels";

type Member = {
  campaign_contact_id: string; contact_id: string; company: string; phone: string; status: string; attempts: number;
  outcome: string | null; error: string | null;
  decision: { result: string; reasons: string[]; reason_text: string[] } | null;
};
type Detail = SalesCampaign & {
  preview: { counts: Record<string, number>; reasons: Record<string, { count: number; text: string }>; members: Member[]; max_cost_net_minor: number; per_attempt_max_net_minor: number; spent_net_minor: number; budget_net_minor: number | null; mode: string };
};
const CC: Record<string, string> = { pending: "Venter", calling: "Ringer", done: "Gennemført", no_answer: "Intet svar", failed: "Fejlet", opted_out: "Frabedt", skipped: "Sprunget over", unknown: "Uvist – tjek hos Vapi" };
const TONE: Record<string, "neutral" | "secondary" | "tertiary"> = { ALLOW: "tertiary", BLOCK: "secondary", NEEDS_REVIEW: "neutral" };

export default async function CampaignPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const r = await load<Detail>(`/operator/salg/campaigns/${id}`);
  if (!r.ok) {
    if (r.status === 501) return <SalgFrame active="/app/operator/salg/kampagner" title="Kampagne"><ChannelOff message={r.message} /></SalgFrame>;
    if (r.status === 404) return <SalgFrame active="/app/operator/salg/kampagner" title="Kampagne"><p>Kampagnen findes ikke.</p></SalgFrame>;
    return <NotOperator status={r.status} message={r.message} />;
  }
  const c = r.data;
  const p = c.preview;
  return (
    <SalgFrame active="/app/operator/salg/kampagner" title={c.name}>
      <Link href="/app/operator/salg/kampagner" className="text-primary underline text-[14px]">← Alle kampagner</Link>
      <div className="grid lg:grid-cols-[minmax(0,26rem)_1fr] gap-space-lg items-start">
        <section className="rounded-2xl border-2 border-ink bg-paper p-space-md flex flex-col gap-2 text-[14px]">
          <p className="flex gap-2 items-center"><Tag>{STATUS[c.status] ?? c.status}</Tag>{c.is_test && <Tag tone="secondary">Test</Tag>}</p>
          <p>Vindue: {c.call_days.join(", ")} kl. {c.call_from}–{c.call_to} (dansk tid) · højst {c.max_attempts} forsøg</p>
          <p>Brugt {kr(p.spent_net_minor)}{p.budget_net_minor != null ? ` af budget ${kr(p.budget_net_minor)}` : ""} · højst {kr(p.per_attempt_max_net_minor)} pr. forsøg (4 kr. + 2 kr./min, højst 10 min)</p>
          <h2 className="font-display font-bold text-[18px] mt-2">Forhåndsvisning</h2>
          <p><Tag tone="tertiary">ALLOW {p.counts.ALLOW}</Tag> <Tag tone="secondary">BLOCK {p.counts.BLOCK}</Tag> <Tag>NEEDS_REVIEW {p.counts.NEEDS_REVIEW}</Tag></p>
          {Object.keys(p.reasons).length > 0 && <ul className="list-disc pl-5 text-muted">{Object.entries(p.reasons).map(([k, v]) => <li key={k}>{v.text}: {v.count}</li>)}</ul>}
          <p>Omkostningsloft fra nu: <strong>{kr(p.max_cost_net_minor)}</strong> ekskl. moms</p>
          <CampaignControls id={c.id} status={c.status} preview={p} />
        </section>
        <section className="rounded-2xl border-2 border-ink bg-paper p-space-md min-w-0">
          <h2 className="font-display font-bold text-[18px] mb-2">Kontakter ({p.members.length})</h2>
          {p.members.length === 0 ? <p className="text-muted text-[14px]">Ingen endnu. Åbn en virksomhed under Virksomheder og vælg &quot;Tilføj til kampagne&quot;.</p> : (
            <div className="overflow-x-auto"><table className="w-full text-[14px]">
              <thead className="text-left text-muted"><tr><th className="pr-2">Virksomhed</th><th className="pr-2">Nummer</th><th className="pr-2">Politik</th><th className="pr-2">Status</th><th>Forsøg</th></tr></thead>
              <tbody>{p.members.map((m) => (
                <tr key={m.campaign_contact_id} className="border-t border-line align-top">
                  <td className="pr-2 py-1">{m.company}</td><td className="pr-2 tabular-nums">{m.phone}</td>
                  <td className="pr-2">{m.decision ? <><Tag tone={TONE[m.decision.result]}>{m.decision.result}</Tag>{m.decision.reason_text.length > 0 && <span className="block text-[12px] text-muted">{m.decision.reason_text.join(", ")}</span>}</> : "–"}</td>
                  <td className="pr-2">{CC[m.status] ?? m.status}{m.error && <span className="block text-[12px] text-muted">{m.error}</span>}</td>
                  <td>{m.attempts}{m.attempts > 0 && <Link className="block underline text-[12px]" href={`/app/operator/salg/opkald/${m.campaign_contact_id}`}>Se opkald</Link>}</td>
                </tr>))}</tbody>
            </table></div>
          )}
        </section>
      </div>
    </SalgFrame>
  );
}
