import Link from "next/link";
import { AdminFrame, NotOperator, dt, load } from "../shared";
import { CATEGORY, PRIORITY, PriorityPill, STATUS, StatusPill, type QueueItem } from "./labels";

type Queue = { items: QueueItem[]; counts: Record<string, number>; workspaces: { id: string; name: string }[] };
type Search = { status?: string; assigned?: string; workspace_id?: string; priority?: string; category?: string; q?: string };

/** The tabs over the queue: [label, status, assigned]. «Aktive» is everything not resolved. */
const VIEWS: [string, string, string, string][] = [
  ["Aktive", "active", "", "active"], ["Tildelt mig", "active", "me", "mine"], ["Ikke tildelt", "active", "none", ""],
  ["Hos Dialogbot", "open", "", "open"], ["Afventer kunde", "waiting_customer", "", "waiting_customer"], ["Løst", "resolved", "", "resolved"], ["Alle", "", "", "all"],
];
const sel = "min-h-[44px] px-3 rounded-xl bg-paper border-2 border-ink text-[14px]";

/** M06 «Support»: every workspace's support tickets – filter, open one to assign, reply or write an internal note. */
export default async function SupportQueue({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams;
  const status = sp.status ?? "active";
  const qs = new URLSearchParams(Object.entries({ ...sp, status }).filter(([, v]) => v) as [string, string][]);
  const data = await load<Queue>(`/operator/support/tickets?${qs}`);
  if (!data) return <NotOperator />;
  const href = (st: string, as: string) => {
    const p = new URLSearchParams(Object.entries({ ...sp, status: st || "", assigned: as }).filter(([, v]) => v) as [string, string][]);
    if (!st) p.set("status", "");
    return `/app/operator/admin/support?${p}`;
  };
  return (
    <AdminFrame active="/app/operator/admin/support" eyebrow="Admin · supportkø" title="Support"
      intro="Kundernes supportsager på tværs af arbejdsrum. Et kundesynligt svar vises i kundens sag (H01) og sendes som e-mail til den, der oprettede sagen. Interne noter ses kun af operatører – aldrig af kunden.">
      <nav aria-label="Køvisning" className="flex flex-wrap gap-2">
        {VIEWS.map(([label, st, as, count]) => {
          const on = (sp.status ?? "active") === st && (sp.assigned ?? "") === as;
          return (
            <Link key={label} href={href(st, as)} aria-current={on ? "true" : undefined}
              className={`px-3 py-2 min-h-[44px] inline-flex items-center gap-2 rounded-xl border-2 border-ink text-[14px] font-semibold ${on ? "bg-highlight" : "bg-paper hover:bg-panel"}`}>
              {label}{count && <span className="tabular-nums text-muted">{data.counts[count] ?? 0}</span>}
            </Link>
          );
        })}
      </nav>
      <form method="get" className="flex flex-wrap gap-2 items-end" aria-label="Filtre">
        <input type="hidden" name="status" value={status} />
        {sp.assigned && <input type="hidden" name="assigned" value={sp.assigned} />}
        <label className="flex flex-col text-[13px] font-semibold">Arbejdsrum
          <select name="workspace_id" defaultValue={sp.workspace_id ?? ""} className={sel}><option value="">Alle arbejdsrum</option>{data.workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select>
        </label>
        <label className="flex flex-col text-[13px] font-semibold">Prioritet
          <select name="priority" defaultValue={sp.priority ?? ""} className={sel}><option value="">Alle</option>{Object.entries(PRIORITY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        </label>
        <label className="flex flex-col text-[13px] font-semibold">Kategori
          <select name="category" defaultValue={sp.category ?? ""} className={sel}><option value="">Alle</option>{Object.entries(CATEGORY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        </label>
        <label className="flex flex-col text-[13px] font-semibold grow min-w-[180px]">Søg
          <input name="q" defaultValue={sp.q ?? ""} placeholder="Emne, kunde eller #nummer" className={sel} />
        </label>
        <button type="submit" className="min-h-[44px] px-4 rounded-xl bg-ink text-paper font-semibold">Filtrér</button>
      </form>
      <section aria-labelledby="koe" className="rounded-2xl bg-paper border-2 border-ink p-3 md:p-4 flex flex-col gap-3">
        <h2 id="koe" className="font-display font-extrabold text-[20px]">Sager i køen ({data.items.length})</h2>
        {data.items.length === 0 ? <p className="text-muted text-[14px]">Ingen sager i denne visning.</p> : (
          <ul className="flex flex-col gap-2">
            {data.items.map((s) => (
              <li key={s.id} data-ticket={s.id}>
                <Link href={`/app/operator/admin/support/${s.id}`} className="flex flex-col md:flex-row md:items-center gap-1 md:gap-4 rounded-xl border-[1.5px] border-ink p-3 hover:bg-panel">
                  <span className="flex-1 min-w-0">
                    <span className="flex flex-wrap items-center gap-2 text-[13px]"><span className="font-semibold">#{s.number}</span><PriorityPill p={s.priority} /><span className="text-muted">{dt(s.updated_at)}</span></span>
                    <span className="block font-semibold text-ink">{s.workspace.name}</span>
                    <span className="block text-[14px] text-ink-soft truncate">{s.subject}</span>
                    <span className="block text-[13px] text-muted">{CATEGORY[s.category] ?? s.category} · Tildelt: {s.assigned_to?.name ?? "fælleskøen"}</span>
                  </span>
                  <StatusPill s={s.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <p className="text-[13px] text-muted">Statusser: {Object.values(STATUS).join(" · ")}</p>
    </AdminFrame>
  );
}
