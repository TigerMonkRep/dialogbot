import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Breadcrumb } from "@/components/ui";
import { CampaignEditor, ImportContacts, RemoveContact, StartCampaign } from "../client";
import { CONTACT_STATUS, OUTCOME, STATUS, type Campaign, type Contact, type PhoneNumber } from "../format";

/** C02: one campaign – script, contacts, start/pause and results. */
export default async function CampaignPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="font-body-md text-body-md">Kampagner kan ses af medarbejdere, administratorer og ejere.</p>;
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
  return (
    <section className="flex flex-col gap-space-lg">
      <Breadcrumb items={[["Kampagner", "/app/campaigns"], [c.name]]} />
      <div className="flex flex-wrap items-center gap-space-sm">
        <h1 className="font-headline-md text-headline-md text-primary font-bold">{c.name}</h1>
        <span className={`px-3 py-1 rounded-full font-label-sm text-label-sm font-semibold ${STATUS[c.status][1]}`}>{STATUS[c.status][0]}</span>
      </div>
      <dl className="grid grid-cols-3 md:grid-cols-6 gap-space-sm">{stats.map(([k, v]) => (
        <div key={k} className="bg-surface-container-lowest rounded-xl p-space-sm shadow-sm">
          <dt className="font-label-sm text-label-sm text-on-surface-variant">{k}</dt>
          <dd className="font-headline-sm text-headline-sm text-primary">{v}</dd>
        </div>
      ))}</dl>
      {canManage && <StartCampaign wsId={ws.id} c={c} checklist={list.legal_checklist} />}
      <CampaignEditor wsId={ws.id} c={c} numbers={numbers.items.filter((n) => n.active)} canManage={canManage} />
      {canManage && c.status !== "completed" && <ImportContacts wsId={ws.id} id={c.id} />}
      <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
        <h2 className="font-headline-sm text-headline-sm text-primary">Kontakter</h2>
        {contacts.items.length === 0 ? <p className="font-body-md text-body-md text-on-surface-variant">Ingen kontakter endnu.</p> : (
          <ul className="flex flex-col gap-space-xs">{contacts.items.map((x) => (
            <li key={x.id} className="flex flex-wrap items-center gap-space-sm p-space-sm rounded-lg bg-surface-container-low font-body-md text-body-md">
              <span className="font-label-lg text-label-lg text-on-surface">{x.name || x.company || x.phone}</span>
              {x.company && x.name && <span className="text-on-surface-variant">{x.company}</span>}
              <span className="text-on-surface-variant">{x.phone}</span>
              <span className="px-2 py-0.5 rounded-full bg-surface-container-high font-label-sm text-label-sm">{x.outcome ? OUTCOME[x.outcome] ?? x.outcome : CONTACT_STATUS[x.status] ?? x.status}</span>
              {x.kind === "consumer" && <span className="font-label-sm text-label-sm text-on-surface-variant" title={x.consent_source}>Privat (samtykke)</span>}
              {x.attempts > 0 && <span className="font-label-sm text-label-sm text-on-surface-variant">{x.attempts} forsøg</span>}
              <span className="ml-auto flex items-center gap-space-sm">
                {x.lead_id && <Link href={`/app/leads/${x.lead_id}`} className="font-label-md text-label-md text-primary underline">Henvendelse</Link>}
                {canManage && !x.charged && x.status === "pending" && <RemoveContact wsId={ws.id} campaignId={c.id} id={x.id} />}
              </span>
              {(x.summary || x.error) && <p className="w-full font-body-sm text-body-sm text-on-surface-variant">{x.summary || x.error}</p>}
            </li>
          ))}</ul>
        )}
      </div>
    </section>
  );
}
