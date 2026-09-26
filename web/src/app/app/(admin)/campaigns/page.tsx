import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { kr } from "../leads/format";
import { DoNotCallList, NewCampaign } from "./client";
import { STATUS, type Campaign, type Dnc } from "./format";

type List = { items: Campaign[]; package: { net_minor: number; max_attempts: number; max_connected_seconds: number } };

/** C01: campaigns (outbound calls), new campaign, and the do-not-call list. */
export default async function CampaignsPage() {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Kampagner kan ses af medarbejdere, administratorer og ejere.</p>;
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [list, dnc] = await Promise.all([
    backend<List>(`/workspaces/${ws.id}/campaigns`),
    backend<{ items: Dnc[] }>(`/workspaces/${ws.id}/do-not-call`),
  ]);
  const p = list.package;
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Kampagner</span>
        <h1 className="font-headline-md text-headline-md text-primary font-bold">Udgående opkald</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">
          Jeres digitale assistent ringer til en liste af kontakter med jeres budskab og sender de interesserede videre som henvendelser.
          Pris: {kr(p.net_minor)} + moms pr. kontakt – op til {p.max_attempts} forsøg og i alt {p.max_connected_seconds / 60} minutters samtale. Der ringes først, når en administrator trykker Start.
        </p>
      </div>
      <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
        <h2 className="font-headline-sm text-headline-sm text-primary">Jeres kampagner</h2>
        {list.items.length === 0 ? <p className="font-body-md text-body-md text-on-surface-variant">Ingen kampagner endnu.</p> : (
          <ul className="flex flex-col gap-space-xs">{list.items.map((c) => (
            <li key={c.id}>
              <Link href={`/app/campaigns/${c.id}`} className="flex flex-wrap items-center gap-space-sm p-space-sm rounded-lg bg-surface-container-low hover:bg-surface-container">
                <Icon name="campaign" size={20} className="text-primary" />
                <span className="font-label-lg text-label-lg text-primary">{c.name}</span>
                <span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm ${STATUS[c.status][1]}`}>{STATUS[c.status][0]}</span>
                <span className="font-body-sm text-body-sm text-on-surface-variant">{c.counts.total} kontakter · {c.counts.by_outcome.interested ?? 0} interesserede · {c.counts.open} tilbage</span>
                <Icon name="chevron_right" size={20} className="ml-auto text-on-surface-variant" />
              </Link>
            </li>
          ))}</ul>
        )}
      </div>
      {canManage ? <NewCampaign wsId={ws.id} /> : <p className="font-body-sm text-body-sm text-on-surface-variant">Kun administratorer og ejere kan oprette og starte kampagner.</p>}
      <DoNotCallList wsId={ws.id} items={dnc.items} canManage={canManage} />
    </section>
  );
}
