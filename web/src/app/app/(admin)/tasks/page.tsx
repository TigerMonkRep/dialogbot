import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { type TaskItem } from "../leads/format";
import { LeadsHeader } from "../leads/tabs";
import { TaskList } from "../leads/client";

export default async function TasksPage({ searchParams }: { searchParams: Promise<{ status?: string; mine?: string }> }) {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Opgaver kan ses af medarbejdere, administratorer og ejere.</p>;
  const sp = await searchParams;
  const status = sp.status === "done" ? "done" : "open";
  const mine = sp.mine === "1";
  const list = await backend<{ items: TaskItem[]; total: number }>(`/workspaces/${ws.id}/tasks?limit=200&status=${status}${mine ? "&mine=true" : ""}`);
  const link = (s: string, m: boolean) => `/app/tasks?status=${s}${m ? "&mine=1" : ""}`;
  const chip = (href: string, on: boolean, label: string) => <Link href={href} aria-current={on ? "true" : undefined} className={`px-3 py-1.5 rounded-full font-label-md text-label-md ${on ? "bg-primary text-on-primary" : "bg-surface-container-low text-on-surface-variant hover:bg-surface-container"}`}>{label}</Link>;
  return (
    <div className="flex flex-col gap-space-lg">
      <LeadsHeader active="tasks" />
      <div className="flex flex-wrap gap-space-xs">
        {chip(link("open", mine), status === "open", "Åbne")}{chip(link("done", mine), status === "done", "Færdige")}
        {chip(link(status, !mine), mine, mine ? "Kun mine ✓" : "Kun mine")}
      </div>
      <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm">
        <TaskList wsId={ws.id} tasks={list.items} />
      </section>
    </div>
  );
}
