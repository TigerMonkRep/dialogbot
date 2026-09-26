import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";

type Activity = { id: string; kind: string; title: string; body: string; href: string; at: string };
type Overview = { kpis: Record<string, number>; activity: Activity[] };
type Plan = { progress: { required_total: number; required_complete: number }; next_action: { title: string } | null };

const ICON: Record<string, string> = { lead: "contact_support", call: "call", task: "task_alt", conversation: "chat", knowledge: "menu_book", import: "travel_explore" };

/** Overview: what needs attention today, recent activity and setup progress. */
export default async function OverviewPage() {
  const ws = await requireWorkspace();
  const [ov, plan] = await Promise.all([
    backend<Overview>(`/workspaces/${ws.id}/overview`),
    backend<Plan>(`/workspaces/${ws.id}/setup/plan`).catch(() => null),
  ]);
  const k = ov.kpis;
  const staff = ws.role !== "reader";
  const tiles: [string, number, string, string, boolean][] = [
    ["Nye henvendelser (24 t)", k.new_leads_24h, "/app/leads", "contact_support", staff],
    ["Åbne henvendelser", k.open_leads, "/app/leads", "inbox", staff],
    ["Opgaver – heraf overskredet", k.open_tasks, "/app/tasks", "task_alt", staff],
    ["Kunder der venter på svar", k.awaiting_staff, "/app/inbox", "chat", staff],
    ["Samtaler (24 t)", k.conversations_24h, "/app/inbox", "forum", staff],
    ["Opkald (24 t)", k.calls_24h, "/app/reception", "call", staff],
  ];
  const pct = plan ? Math.round((100 * plan.progress.required_complete) / Math.max(1, plan.progress.required_total)) : null;
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Overblik</span>
        <h1 className="font-headline-md text-headline-md text-primary font-bold">{ws.name}</h1>
      </div>
      {plan && pct !== null && pct < 100 && (
        <Link href="/app/setup" className="rounded-xl bg-primary-container text-on-primary p-space-md flex items-center justify-between gap-space-md hover:brightness-105">
          <div>
            <p className="font-label-lg text-label-lg font-bold">Opsætningen er {pct}% færdig</p>
            {plan.next_action && <p className="font-body-sm text-body-sm text-primary-fixed-dim">Næste: {plan.next_action.title}</p>}
          </div>
          <Icon name="arrow_forward" size={22} className="text-secondary-fixed" />
        </Link>
      )}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-space-md">
        {tiles.filter((t) => t[4]).map(([label, value, href, icon]) => (
          <Link key={label} href={href} className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm hover:bg-surface-container-low flex flex-col gap-1">
            <Icon name={icon} size={20} className="text-secondary" />
            <span className="font-headline-md text-headline-md text-primary font-bold">{value}{label.startsWith("Opgaver") && k.overdue_tasks ? <span className="font-label-md text-label-md text-error"> · {k.overdue_tasks} overskredet</span> : null}</span>
            <span className="font-label-md text-label-md text-on-surface-variant">{label.replace(" – heraf overskredet", "")}</span>
          </Link>
        ))}
        {k.drafts > 0 && (
          <Link href="/app/knowledge?tab=k05" className="bg-tertiary-fixed text-on-tertiary-fixed rounded-xl p-space-md shadow-sm flex flex-col gap-1">
            <Icon name="rule" size={20} />
            <span className="font-headline-md text-headline-md font-bold">{k.drafts}</span>
            <span className="font-label-md text-label-md">Vidensemner venter på godkendelse</span>
          </Link>
        )}
      </div>
      <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
        <div className="flex items-center justify-between"><h2 className="font-headline-sm text-headline-sm text-primary">Seneste aktivitet</h2><Link href="/app/notifications" className="font-label-md text-label-md text-primary underline">Alle notifikationer</Link></div>
        {ov.activity.length === 0 ? <p className="font-body-sm text-body-sm text-on-surface-variant">Ingen aktivitet de seneste 14 dage.</p> : (
          <ul className="flex flex-col">{ov.activity.map((a) => (
            <li key={a.id}><Link href={a.href} className="flex items-start gap-space-sm p-space-sm rounded-lg hover:bg-surface-container-low">
              <Icon name={ICON[a.kind] ?? "notifications"} size={20} className="text-primary mt-0.5" />
              <span className="flex-1 min-w-0"><span className="block font-label-lg text-label-lg text-on-surface">{a.title}</span>{a.body && <span className="block font-body-sm text-body-sm text-on-surface-variant truncate">{a.body}</span>}</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant shrink-0">{new Date(a.at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" })}</span>
            </Link></li>
          ))}</ul>
        )}
      </div>
    </section>
  );
}
