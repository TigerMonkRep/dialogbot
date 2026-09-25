import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { SOURCE, callbackWindow, type Lead, when } from "../format";
import { BillingPanel, LeadEditor, TaskList } from "../client";

type Agreement = { current: { version: number; model: string; lead_fee: { net_minor: number } } | null };

export default async function LeadPage({ params }: { params: Promise<{ id: string }> }) {
  const ws = await requireWorkspace();
  const { id } = await params;
  const canApprove = ws.role === "owner" || ws.role === "admin";
  const [lead, agreement] = await Promise.all([
    backend<Lead>(`/workspaces/${ws.id}/leads/${encodeURIComponent(id)}`),
    canApprove ? backend<Agreement>(`/workspaces/${ws.id}/agreement`) : Promise.resolve({ current: null } as Agreement),
  ]);
  return (
    <div className="flex flex-col gap-space-lg">
      <Link href="/app/leads" className="self-start font-label-md text-label-md text-primary flex items-center gap-1"><Icon name="arrow_back" size={18} />Henvendelser</Link>
      <div className="flex flex-wrap items-end justify-between gap-space-sm">
        <div>
          <h1 className="font-headline-md text-headline-md text-primary">{lead.contact_name || "(uden navn)"}</h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant">{SOURCE[lead.source] ?? lead.source} · oprettet {when(lead.created_at)}</p>
          {lead.callback_from && lead.callback_to && <p className="mt-1 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-tertiary-fixed text-on-tertiary-fixed font-label-md text-label-md"><Icon name="phone_callback" size={16} />Ønsker opkald {callbackWindow(lead.callback_from, lead.callback_to)}</p>}
        </div>
        {lead.conversation_id && <Link href={`/app/inbox/${lead.conversation_id}`} className="font-label-lg text-label-lg text-primary flex items-center gap-1"><Icon name="forum" size={18} />Se samtalen</Link>}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        <div className="lg:col-span-8 flex flex-col gap-space-lg">
          <LeadEditor key={lead.version} wsId={ws.id} lead={lead} />
          <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
            <h2 className="font-headline-sm text-headline-sm text-primary">Opgaver</h2>
            <TaskList wsId={ws.id} leadId={lead.id} tasks={lead.tasks ?? []} />
          </section>
        </div>
        <div className="lg:col-span-4"><BillingPanel wsId={ws.id} lead={lead} canApprove={canApprove} agreement={agreement.current} /></div>
      </div>
    </div>
  );
}
