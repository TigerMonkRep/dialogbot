import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { getLocale, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";
import { TelephonySetup, type Languages, type PhoneNumber, type Telephony } from "./client";

type Calls = { items: { id: string; from_number: string | null; started_at: string | null; duration_seconds: number | null; summary: string; conversation_id: string | null }[] };

/** S03: telephony run by Dialogbot. The customer keeps their number at their own carrier and forwards it to a
 *  destination Dialogbot provisions; no provider accounts, ids, keys or webhooks are shown here. */
export default async function TelephonyPage() {
  const ws = await requireWorkspace();
  const tr = await getT("settings");
  const lang = HTML_LANG[await getLocale()];
  if (ws.role === "reader") return <p className="bg-paper rounded-2xl p-4 border-2 border-ink text-body-md text-ink-soft">{tr("telephony.readersBlocked")}</p>;
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [t, nums, calls, me, languages] = await Promise.all([
    backend<Telephony>(`/workspaces/${ws.id}/telephony`),
    backend<{ items: PhoneNumber[] }>(`/workspaces/${ws.id}/phone-numbers`),
    backend<Calls>(`/workspaces/${ws.id}/calls?limit=10`),
    backend<{ is_platform_operator?: boolean }>(`/auth/me`).catch(() => ({ is_platform_operator: false })),
    backend<Languages>(`/workspaces/${ws.id}/languages`).catch(() => null),
  ]);
  return (
    <section className="flex flex-col gap-4">
      <TelephonySetup wsId={ws.id} t={t} numbers={nums.items} canManage={canManage} languages={languages} />
      {me.is_platform_operator && <Link href="/app/operator/telephony" className="flex items-center gap-1 text-label-lg text-ink underline w-fit"><Icon name="admin_panel_settings" size={18} />{tr("telephony.operatorView")}</Link>}
      <div className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
        <h3 className="font-display text-headline-sm text-ink">{tr("telephony.recentCalls")}</h3>
        {calls.items.length === 0 ? <p className="text-body-sm text-ink-soft">{tr("telephony.noCalls")}</p> : (
          <ul className="flex flex-col gap-1">{calls.items.map((c) => (
            <li key={c.id}>
              <Link href={c.conversation_id ? `/app/inbox/${c.conversation_id}` : "#"} className="flex flex-wrap items-center gap-2 p-2 rounded-lg hover:bg-panel">
                <Icon name="call" size={18} className="text-ink" />
                <span className="text-label-lg text-ink">{c.from_number ?? tr("telephony.hiddenNumber")}</span>
                <span className="text-body-sm text-ink-soft">{c.started_at ? new Date(c.started_at).toLocaleString(lang, { dateStyle: "short", timeStyle: "short" }) : ""}{c.duration_seconds != null ? tr("telephony.duration", { m: Math.floor(c.duration_seconds / 60), s: String(c.duration_seconds % 60).padStart(2, "0") }) : ""}</span>
                <span className="w-full text-body-sm text-ink truncate">{c.summary}</span>
              </Link>
            </li>
          ))}</ul>
        )}
      </div>
    </section>
  );
}
