import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { MarkSeen } from "./seen";

type Item = { id: string; kind: string; title: string; body: string; href: string; at: string; unread: boolean };
const ICON: Record<string, string> = { lead: "contact_support", call: "call", task: "task_alt", conversation: "chat", knowledge: "menu_book", import: "travel_explore" };

/** Notifications from the last 14 days, derived from real events. Opening the page marks them as read. */
export default async function NotificationsPage() {
  const ws = await requireWorkspace();
  const n = await backend<{ items: Item[]; unread: number }>(`/workspaces/${ws.id}/notifications`);
  return (
    <section className="flex flex-col gap-space-lg max-w-3xl">
      <MarkSeen wsId={ws.id} unread={n.unread} />
      <div>
        <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Notifikationer</span>
        <h1 className="font-headline-md text-headline-md text-primary font-bold">{n.unread ? `${n.unread} nye` : "Ingen nye"}</h1>
      </div>
      <div className="bg-surface-container-lowest rounded-xl p-space-sm md:p-space-md shadow-sm">
        {n.items.length === 0 ? <p className="p-space-md font-body-sm text-body-sm text-on-surface-variant">Intet de seneste 14 dage.</p> : (
          <ul className="flex flex-col">{n.items.map((i) => (
            <li key={i.id}><Link href={i.href} className={`flex items-start gap-space-sm p-space-sm rounded-lg hover:bg-surface-container-low ${i.unread ? "bg-secondary-container/40" : ""}`}>
              <Icon name={ICON[i.kind] ?? "notifications"} size={20} className="text-primary mt-0.5" />
              <span className="flex-1 min-w-0"><span className="block font-label-lg text-label-lg text-on-surface">{i.unread && <span className="sr-only">Ny: </span>}{i.title}</span>{i.body && <span className="block font-body-sm text-body-sm text-on-surface-variant">{i.body}</span>}</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant shrink-0">{new Date(i.at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" })}</span>
            </Link></li>
          ))}</ul>
        )}
      </div>
    </section>
  );
}
