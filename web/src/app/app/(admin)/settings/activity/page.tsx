import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";

type Entry = { id: string; actor_user_id: string | null; action: string; object_type: string; object_id: string | null; before: Record<string, unknown> | null; after: Record<string, unknown> | null; request_id: string | null; created_at: string };
type Member = { user_id: string; display_name: string };
const PER_PAGE = 25;

const ACTION_ICON: Record<string, string> = {
  "user.registered": "person_add", "user.password_reset": "key",
  "workspace.created": "add_business", "profile.updated": "edit",
  "category.added": "label", "category.removed": "label_off",
  "goals.updated": "flag", "languages.updated": "translate",
  "knowledge.draft_created": "note_add", "knowledge.draft_edited": "edit_note",
  "knowledge.submitted": "send", "knowledge.approved": "verified", "knowledge.rejected": "block",
  "membership.role_changed": "manage_accounts", "membership.removed": "person_remove",
  "invitation.created": "mail", "invitation.accepted": "how_to_reg", "invitation.revoked": "cancel_schedule_send",
  "setup.task_skipped": "skip_next", "setup.task_unskipped": "undo", "setup.task_assigned": "assignment_ind",
  "lead.created": "person_add", "lead.updated": "edit",
  "lead.approved": "verified", "lead.rejected": "block",
  "task.created": "add_task", "task.updated": "task_alt",
  "conversation.mode_changed": "swap_horiz",
  "telephony.number_added": "add_call", "telephony.number_updated": "call",
  "reports.settings_updated": "bar_chart", "agreement.created": "handshake",
  "webchat.updated": "chat", "webchat.key_rotated": "autorenew",
  "setup.check_run": "fact_check", "setup.checks_run_all": "fact_check",
};

/** S09: workspace audit log (admin+). Shows who changed what, when, with request id for support. */
export default async function ActivityPage({ searchParams }: { searchParams: Promise<{ page?: string }> }) {
  const ws = await requireWorkspace();
  const t = await getT("settings");
  if (ws.role !== "owner" && ws.role !== "admin") {
    return <p className="bg-paper rounded-2xl p-4 border-2 border-ink text-body-md text-ink-soft">{t("activity.onlyAdmins")}</p>;
  }
  const pageNo = Math.max(1, Number((await searchParams).page ?? 1) || 1);
  const [log, members] = await Promise.all([
    backend<{ items: Entry[]; total: number }>(`/workspaces/${ws.id}/audit?limit=${PER_PAGE}&offset=${(pageNo - 1) * PER_PAGE}`),
    backend<Member[]>(`/workspaces/${ws.id}/members`),
  ]);
  const labels = (await getRaw())<Record<string, string>>("settings.activity.actions") ?? {};
  const lang = HTML_LANG[await getLocale()];
  const who = new Map(members.map((m) => [m.user_id, m.display_name]));
  const pages = Math.max(1, Math.ceil(log.total / PER_PAGE));
  return (
    <section className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><span className="eyebrow">{t("activity.eyebrow")}</span><h2 className="font-display text-headline-sm text-ink font-bold">{t("activity.title")}</h2><p className="text-body-sm text-ink-soft">{t("activity.intro", { name: ws.name })}</p></div>
        <span className="px-2.5 py-1 rounded-full bg-panel-deep text-ink-soft text-label-sm font-medium">{t("activity.count", { n: log.total })}</span>
      </div>
      {log.items.length === 0 ? <p className="p-3 rounded-xl bg-panel text-body-sm text-ink-soft">{t("activity.empty")}</p> : (
        <ol className="flex flex-col gap-2">
          {log.items.map((e) => {
            const label = labels[e.action] ?? e.action;
            const icon = ACTION_ICON[e.action] ?? "history";
            return (
              <li key={e.id} className="p-3 rounded-xl bg-panel flex items-start gap-2">
                <div className="w-9 h-9 rounded-full bg-paper text-ink flex items-center justify-center flex-shrink-0 border-2 border-ink"><Icon name={icon} size={18} /></div>
                <div className="min-w-0 flex-1">
                  <p className="text-label-lg text-ink">{label}</p>
                  <p className="text-body-sm text-ink-soft">{e.actor_user_id ? who.get(e.actor_user_id) ?? t("activity.formerMember") : t("activity.system")} · {new Date(e.created_at).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" })}</p>
                </div>
                {e.request_id && <span className="hidden md:inline font-mono text-label-sm text-ink-soft" title={t("activity.supportRef")}>{e.request_id.slice(0, 8)}</span>}
              </li>
            );
          })}
        </ol>
      )}
      {pages > 1 && (
        <nav aria-label={t("activity.pages")} className="flex items-center justify-between">
          {pageNo > 1 ? <Link href={`?page=${pageNo - 1}`} className="px-3 py-1.5 rounded-lg bg-panel-deep text-ink text-label-md font-semibold flex items-center gap-1"><Icon name="chevron_left" size={18} />{t("activity.newer")}</Link> : <span />}
          <span className="text-label-md text-ink-soft">{t("activity.pageOf", { page: pageNo, pages })}</span>
          {pageNo < pages ? <Link href={`?page=${pageNo + 1}`} className="px-3 py-1.5 rounded-lg bg-panel-deep text-ink text-label-md font-semibold flex items-center gap-1">{t("activity.older")}<Icon name="chevron_right" size={18} /></Link> : <span />}
        </nav>
      )}
    </section>
  );
}
