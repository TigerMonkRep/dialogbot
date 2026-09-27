import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { TelephonySetup, type PhoneNumber, type Telephony } from "./client";

type Calls = { items: { id: string; from_number: string | null; started_at: string | null; duration_seconds: number | null; summary: string; conversation_id: string | null }[] };

/** S03: telephony run by Dialogbot. The customer keeps their number at their own carrier and forwards it to a
 *  destination Dialogbot provisions; no provider accounts, ids, keys or webhooks are shown here. */
export default async function TelephonyPage() {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Telefoni kan ses af medarbejdere, administratorer og ejere.</p>;
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [t, nums, calls, me] = await Promise.all([
    backend<Telephony>(`/workspaces/${ws.id}/telephony`),
    backend<{ items: PhoneNumber[] }>(`/workspaces/${ws.id}/phone-numbers`),
    backend<Calls>(`/workspaces/${ws.id}/calls?limit=10`),
    backend<{ is_platform_operator?: boolean }>(`/auth/me`).catch(() => ({ is_platform_operator: false })),
  ]);
  return (
    <section className="flex flex-col gap-space-lg">
      <TelephonySetup wsId={ws.id} t={t} numbers={nums.items} canManage={canManage} />
      {me.is_platform_operator && <Link href="/app/operator/telephony" className="flex items-center gap-1 font-label-lg text-label-lg text-primary underline w-fit"><Icon name="admin_panel_settings" size={18} />Operatørvisning (kun Dialogbot)</Link>}
      <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
        <h3 className="font-headline-sm text-headline-sm text-primary">Seneste opkald</h3>
        {calls.items.length === 0 ? <p className="font-body-sm text-body-sm text-on-surface-variant">Ingen opkald endnu.</p> : (
          <ul className="flex flex-col gap-space-xs">{calls.items.map((c) => (
            <li key={c.id}>
              <Link href={c.conversation_id ? `/app/inbox/${c.conversation_id}` : "#"} className="flex flex-wrap items-center gap-space-sm p-space-sm rounded-lg hover:bg-surface-container-low">
                <Icon name="call" size={18} className="text-primary" />
                <span className="font-label-lg text-label-lg text-primary">{c.from_number ?? "Skjult nummer"}</span>
                <span className="font-body-sm text-body-sm text-on-surface-variant">{c.started_at ? new Date(c.started_at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" }) : ""}{c.duration_seconds != null ? ` · ${Math.floor(c.duration_seconds / 60)}:${String(c.duration_seconds % 60).padStart(2, "0")} min` : ""}</span>
                <span className="w-full font-body-sm text-body-sm text-on-surface truncate">{c.summary}</span>
              </Link>
            </li>
          ))}</ul>
        )}
      </div>
    </section>
  );
}
