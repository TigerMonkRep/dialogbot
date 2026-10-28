import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Breadcrumb } from "@/components/ui";
import { CampaignEditor, ImportContacts, Num, RemoveContact, StartCampaign } from "../client";
import { CONTACT_STATUS, OUTCOME, STATUS, type Campaign, type Contact, type PhoneNumber } from "../format";

/** C02: one campaign – script, contacts, start/pause and results. */
export default async function CampaignPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="text-body-md">Kampagner kan ses af medarbejdere, administratorer og ejere.</p>;
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [c, contacts, list, numbers] = await Promise.all([
    backend<Campaign>(`/workspaces/${ws.id}/campaigns/${id}`),
    backend<{ items: Contact[] }>(`/workspaces/${ws.id}/campaigns/${id}/contacts?limit=500`),
    backend<{ legal_checklist: string[] }>(`/workspaces/${ws.id}/campaigns`),
    backend<{ items: PhoneNumber[] }>(`/workspaces/${ws.id}/phone-numbers`).catch(() => ({ items: [] as PhoneNumber[] })),
  ]);
  const o = c.counts.by_outcome;
  const stats: [string, number][] = [["Kontakter", c.counts.total], ["Talt med", c.counts.by_status.done ?? 0], ["Interesserede", o.interested ?? 0],
    ["Ring tilbage", o.callback ?? 0], ["Intet svar", c.counts.by_status.no_answer ?? 0], ["Tilbage", c.counts.open]];
  const hasCount = c.counts.total;
  return (
    <div className="flex flex-wrap gap-6 items-start">
      <section className="flex-[999_1_460px] min-w-0 flex flex-col gap-5">
        <Breadcrumb items={[["Kampagner", "/app/kampagner"], [c.name]]} />
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{c.name}</h1>
          <span className={`px-3 py-1 rounded-full text-label-sm font-semibold ${STATUS[c.status][1]}`}>{STATUS[c.status][0]}</span>
        </div>
        <dl className="grid grid-cols-3 md:grid-cols-6 gap-2">{stats.map(([k, v]) => (
          <div key={k} className="bg-paper rounded-2xl p-3 border-2 border-ink">
            <dt className="text-label-sm text-ink-soft">{k}</dt>
            <dd className="font-display font-extrabold text-[24px] text-ink">{v}</dd>
          </div>
        ))}</dl>
        <div className="flex flex-col gap-4 rounded-2xl border-2 border-ink bg-paper px-5 py-5">
          <h2 className="flex items-center gap-3 font-display font-extrabold text-[20px] text-ink"><Num n={1} />Hvem skal den ringe til?</h2>
          <p className="text-[14px] text-ink-soft">{hasCount} kontakter. Numre på spærrelisten springes over. Dialogbot bruger kun navn og nummer.</p>
          {canManage && c.status !== "completed" && <ImportContacts wsId={ws.id} id={c.id} />}
          {contacts.items.length === 0 ? <p className="text-[14px] text-ink-soft">Ingen kontakter endnu.</p> : (
            <ul className="flex flex-col">{contacts.items.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-2 py-2.5 border-t-[1.5px] border-line text-[14px]">
                <span className="font-semibold text-ink">{x.name || x.company || x.phone}</span>
                {x.company && x.name && <span className="text-ink-soft">{x.company}</span>}
                <span className="text-ink-soft">{x.phone}</span>
                <span className="px-2.5 py-0.5 rounded-full bg-panel border-[1.5px] border-line text-[12px] font-semibold">{x.outcome ? OUTCOME[x.outcome] ?? x.outcome : CONTACT_STATUS[x.status] ?? x.status}</span>
                {x.consent_source ? <span className="text-[12px] text-ink-soft" title={x.consent_source}>{x.kind === "consumer" ? "Privat" : "Erhverv"} (samtykke)</span> : <span className="text-[12px] text-danger">Mangler samtykke – ringes ikke op</span>}
                {x.attempts > 0 && <span className="text-[12px] text-ink-soft">{x.attempts} forsøg</span>}
                <span className="ml-auto flex items-center gap-3">
                  {x.lead_id && <Link href={`/app/opkald/henvendelser/${x.lead_id}`} className="font-semibold text-accent hover:underline">Henvendelse</Link>}
                  {canManage && !x.charged && x.status === "pending" && <RemoveContact wsId={ws.id} campaignId={c.id} id={x.id} />}
                </span>
                {(x.summary || x.error) && <p className="w-full text-[13px] text-ink-soft">{x.summary || x.error}</p>}
              </li>
            ))}</ul>
          )}
        </div>
        <CampaignEditor wsId={ws.id} c={c} numbers={numbers.items.filter((n) => n.active)} canManage={canManage} />
      </section>
      <aside className="flex-[1_1_300px] min-w-0 max-w-[440px] flex flex-col gap-5 lg:sticky lg:top-[88px]">
        {canManage && <StartCampaign wsId={ws.id} c={c} checklist={list.legal_checklist} />}
        <p className="text-[13px] text-muted">{c.pricing.call_net_minor / 100} kr. pr. opkald ekskl. moms. Du betaler kun for de opkald, der går ud. Stop når som helst.</p>
      </aside>
    </div>
  );
}
