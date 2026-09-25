import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { BILL, PIPE, QUAL, SOURCE, type Lead, when } from "./format";
import { LeadsHeader } from "./tabs";
import { NewLeadButton } from "./client";

const FILTERS: [string, string, string][] = [["", "Alle", ""], ["new", "Nye", "pipeline=new"], ["qualified", "Kvalificerede", "qualification=qualified"], ["pending", "Afventer godkendelse", "billing=pending"], ["approved", "Godkendte", "billing=approved"]];

export default async function LeadsPage({ searchParams }: { searchParams: Promise<{ f?: string }> }) {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Henvendelser kan ses af medarbejdere, administratorer og ejere.</p>;
  const f = (await searchParams).f ?? "";
  const q = FILTERS.find(([k]) => k === f)?.[2] ?? "";
  const list = await backend<{ items: Lead[]; total: number }>(`/workspaces/${ws.id}/leads?limit=100${q ? `&${q}` : ""}`);
  return (
    <div className="flex flex-col gap-space-lg">
      <div className="flex flex-wrap items-end justify-between gap-space-md"><LeadsHeader active="leads" /><NewLeadButton wsId={ws.id} /></div>
      <div className="flex flex-wrap gap-space-xs" role="list" aria-label="Filtre">
        {FILTERS.map(([k, label]) => (
          <Link role="listitem" key={k} href={k ? `/app/leads?f=${k}` : "/app/leads"} aria-current={f === k ? "true" : undefined}
            className={`px-3 py-1.5 rounded-full font-label-md text-label-md ${f === k ? "bg-primary text-on-primary" : "bg-surface-container-low text-on-surface-variant hover:bg-surface-container"}`}>{label}</Link>
        ))}
      </div>
      <section className="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
        {list.items.length === 0 ? <p className="p-space-lg font-body-md text-body-md text-on-surface-variant">Ingen henvendelser{f ? " i dette filter" : " endnu"}. Kunder kan bede om at blive kontaktet via webchatten.</p> : (
          <ul aria-label="Henvendelser">
            {list.items.map((l) => (
              <li key={l.id} className="border-b border-surface-container last:border-0">
                <Link href={`/app/leads/${l.id}`} className="flex flex-col md:flex-row md:items-center gap-space-sm p-space-md hover:bg-surface-container-low transition-colors">
                  <span className="flex-1 min-w-0">
                    <span className="flex items-center gap-space-xs font-label-lg text-label-lg text-primary">{l.contact_name || "(uden navn)"}<span className="font-label-sm text-label-sm text-on-surface-variant font-normal">· {SOURCE[l.source] ?? l.source} · {when(l.created_at)}</span></span>
                    <span className="block font-body-sm text-body-sm text-on-surface truncate">{l.need_summary || "(intet behov angivet)"}</span>
                  </span>
                  <span className="flex flex-wrap gap-space-xs">
                    <Chip cls={QUAL[l.qualification_status][1]}>{QUAL[l.qualification_status][0]}</Chip>
                    <Chip cls="bg-surface-container text-primary">{PIPE[l.pipeline_status]}</Chip>
                    <Chip cls={BILL[l.billing_status][1]}>{BILL[l.billing_status][0]}</Chip>
                  </span>
                  <Icon name="chevron_right" size={20} className="hidden md:block text-outline" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Chip({ cls, children }: { cls: string; children: React.ReactNode }) {
  return <span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm font-semibold ${cls}`}>{children}</span>;
}
