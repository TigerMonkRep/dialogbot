import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { kr } from "../leads/format";
import { ReportSettingsForm } from "./client";

type Report = {
  status: "final" | "preliminary" | "not_generated"; date: string; timezone: string; generated_at: string | null;
  conversations: { started: number; visitor_messages: number };
  ai: { calls: number; ok: number; refused: number; error: number; input_tokens: number; output_tokens: number; est_cost_usd_micros?: number };
  leads: { new: number; approved: number; rejected: number; approved_fee_net_minor?: number; new_items: { id: string; contact_name: string; need_summary: string; source: string }[] };
  tasks: { created: number; completed: number; open_overdue_at_end: number };
};
type List = { timezone: string; today: string; items: { date: string; summary: { conversations: number; new_leads: number; approved_leads: number } }[] };

const dayLabel = (iso: string) => {
  const s = new Date(`${iso}T12:00:00`).toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long" });
  return s.charAt(0).toUpperCase() + s.slice(1); // Danish: only the first letter, never "September"
};

/** Daily report: finished days are immutable snapshots; today is live and marked preliminary. */
export default async function ReportsPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Rapporter kan ses af medarbejdere, administratorer og ejere.</p>;
  const isAdmin = ws.role === "owner" || ws.role === "admin";
  const list = await backend<List>(`/workspaces/${ws.id}/reports?limit=30`);
  const wanted = (await searchParams).date;
  const day = wanted && /^\d{4}-\d{2}-\d{2}$/.test(wanted) && wanted <= list.today ? wanted : list.today;
  const [r, settings] = await Promise.all([
    backend<Report>(`/workspaces/${ws.id}/reports/${day}`),
    backend<{ email_enabled: boolean; send_hour_local: number; timezone: string }>(`/workspaces/${ws.id}/reports/settings`),
  ]);
  const days = [list.today, ...list.items.map((i) => i.date).filter((d) => d !== list.today)];
  return (
    <div className="flex flex-col gap-space-lg">
      <div className="flex flex-col gap-space-xs">
        <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary tracking-tight">Rapporter</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant">Én rapport pr. dag i jeres tidszone ({list.timezone}). En afsluttet dag gemmes og ændres ikke; i dag er foreløbig.</p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        <nav className="lg:col-span-3 bg-surface-container-lowest rounded-xl shadow-sm p-space-sm flex lg:flex-col gap-space-xs overflow-x-auto no-scrollbar" aria-label="Dage">
          {days.map((d) => (
            <Link key={d} href={`/app/reports?date=${d}`} aria-current={d === day ? "page" : undefined}
              className={`shrink-0 px-space-md py-space-sm rounded-lg font-label-md text-label-md ${d === day ? "bg-primary-container text-on-primary" : "text-on-surface-variant hover:bg-surface-container-low"}`}>
              {d === list.today ? "I dag" : dayLabel(d)}
            </Link>
          ))}
        </nav>
        <section className="lg:col-span-9 flex flex-col gap-space-md">
          <div className="flex flex-wrap items-center justify-between gap-space-sm">
            <h2 className="font-headline-md text-headline-md text-primary">{dayLabel(r.date)}</h2>
            <span className={`px-3 py-1 rounded-full font-label-sm text-label-sm font-semibold ${r.status === "final" ? "bg-secondary-container text-on-secondary-container" : "bg-tertiary-fixed text-on-tertiary-fixed"}`}>
              {r.status === "final" ? "Endelig" : r.status === "preliminary" ? "Foreløbig – dagen er ikke slut" : "Beregnet nu – ikke gemt"}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-space-md">
            <Stat icon="forum" label="Samtaler" value={r.conversations.started} sub={`${r.conversations.visitor_messages} kundebeskeder`} />
            <Stat icon="contact_support" label="Nye henvendelser" value={r.leads.new} sub={`${r.leads.approved} godkendt · ${r.leads.rejected} afvist`} />
            <Stat icon="task_alt" label="Opgaver løst" value={r.tasks.completed} sub={`${r.tasks.created} oprettet · ${r.tasks.open_overdue_at_end} over frist`} />
            <Stat icon="smart_toy" label="AI-svar" value={r.ai.ok} sub={`${r.ai.refused} afvist · ${r.ai.error} fejl`} />
          </div>
          {isAdmin && (
            <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm grid grid-cols-1 md:grid-cols-2 gap-space-md">
              <p className="font-body-md text-body-md"><span className="block font-label-md text-label-md text-on-surface-variant">Godkendte henvendelser (pris ekskl. moms)</span><strong className="font-headline-sm text-headline-sm text-primary">{kr(r.leads.approved_fee_net_minor ?? 0)}</strong></p>
              <p className="font-body-md text-body-md"><span className="block font-label-md text-label-md text-on-surface-variant">AI-forbrug</span><strong className="font-headline-sm text-headline-sm text-primary">≈ ${((r.ai.est_cost_usd_micros ?? 0) / 1_000_000).toFixed(2)}</strong> <span className="font-body-sm text-body-sm text-on-surface-variant">({r.ai.input_tokens} ind / {r.ai.output_tokens} ud tokens)</span></p>
            </div>
          )}
          <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
            <h3 className="font-headline-sm text-headline-sm text-primary">Nye henvendelser</h3>
            {r.leads.new_items.length === 0 ? <p className="font-body-sm text-body-sm text-on-surface-variant">Ingen nye henvendelser denne dag.</p> : (
              <ul className="flex flex-col gap-space-xs">{r.leads.new_items.map((l) => (
                <li key={l.id}><Link href={`/app/leads/${l.id}`} className="flex items-center gap-space-sm p-space-sm rounded-lg hover:bg-surface-container-low"><Icon name="person" size={18} className="text-primary" /><span className="font-label-lg text-label-lg text-primary">{l.contact_name || "(uden navn)"}</span><span className="font-body-sm text-body-sm text-on-surface-variant truncate">{l.need_summary}</span></Link></li>
              ))}</ul>
            )}
          </div>
          {isAdmin && <ReportSettingsForm wsId={ws.id} initial={settings} canEdit />}
        </section>
      </div>
    </div>
  );
}

function Stat({ icon, label, value, sub }: { icon: string; label: string; value: number; sub: string }) {
  return (
    <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm flex flex-col gap-1">
      <span className="flex items-center gap-space-xs font-label-md text-label-md text-on-surface-variant"><Icon name={icon} size={18} className="text-primary" />{label}</span>
      <span className="font-headline-md text-headline-md text-primary font-bold">{value}</span>
      <span className="font-body-sm text-body-sm text-on-surface-variant">{sub}</span>
    </div>
  );
}
