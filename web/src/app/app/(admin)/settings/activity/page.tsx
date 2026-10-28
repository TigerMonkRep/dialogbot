import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";

type Entry = { id: string; actor_user_id: string | null; action: string; object_type: string; object_id: string | null; before: Record<string, unknown> | null; after: Record<string, unknown> | null; request_id: string | null; created_at: string };
type Member = { user_id: string; display_name: string };
const PER_PAGE = 25;

const ACTION: Record<string, [string, string]> = {
  "user.registered": ["Konto oprettet", "person_add"], "user.password_reset": ["Adgangskode nulstillet", "key"],
  "workspace.created": ["Arbejdsrum oprettet", "add_business"], "profile.updated": ["Virksomhedsprofil ændret", "edit"],
  "category.added": ["Kategori tilføjet", "label"], "category.removed": ["Kategori fjernet", "label_off"],
  "goals.updated": ["Mål ændret", "flag"], "languages.updated": ["Sprog ændret", "translate"],
  "knowledge.draft_created": ["Kladde oprettet", "note_add"], "knowledge.draft_edited": ["Kladde ændret", "edit_note"],
  "knowledge.submitted": ["Sendt til gennemgang", "send"], "knowledge.approved": ["Viden godkendt", "verified"], "knowledge.rejected": ["Viden afvist", "block"],
  "membership.role_changed": ["Rolle ændret", "manage_accounts"], "membership.removed": ["Medlem fjernet", "person_remove"],
  "invitation.created": ["Invitation sendt", "mail"], "invitation.accepted": ["Invitation accepteret", "how_to_reg"], "invitation.revoked": ["Invitation tilbagekaldt", "cancel_schedule_send"],
  "setup.task_skipped": ["Trin sprunget over", "skip_next"], "setup.task_unskipped": ["Spring fortrudt", "undo"], "setup.task_assigned": ["Trin tildelt", "assignment_ind"],
  "lead.created": ["Henvendelse oprettet", "person_add"], "lead.updated": ["Henvendelse ændret", "edit"],
  "lead.approved": ["Henvendelse godkendt", "verified"], "lead.rejected": ["Henvendelse afvist", "block"],
  "task.created": ["Opgave oprettet", "add_task"], "task.updated": ["Opgave ændret", "task_alt"],
  "conversation.mode_changed": ["Samtale overtaget/givet tilbage", "swap_horiz"],
  "telephony.number_added": ["Telefonnummer tilknyttet", "add_call"], "telephony.number_updated": ["Telefonnummer ændret", "call"],
  "reports.settings_updated": ["Rapportindstillinger ændret", "bar_chart"], "agreement.created": ["Abonnement bekræftet", "handshake"],
  "webchat.updated": ["Webchat ændret", "chat"], "webchat.key_rotated": ["Ny widgetnøgle", "autorenew"],
  "setup.check_run": ["Tjek kørt", "fact_check"], "setup.checks_run_all": ["Alle tjek kørt", "fact_check"],
};

/** S09: workspace audit log (admin+). Shows who changed what, when, with request id for support. */
export default async function ActivityPage({ searchParams }: { searchParams: Promise<{ page?: string }> }) {
  const ws = await requireWorkspace();
  if (ws.role !== "owner" && ws.role !== "admin") {
    return <p className="bg-paper rounded-2xl p-4 border-2 border-ink text-body-md text-ink-soft">Aktivitetsloggen kan kun ses af ejere og administratorer.</p>;
  }
  const pageNo = Math.max(1, Number((await searchParams).page ?? 1) || 1);
  const [log, members] = await Promise.all([
    backend<{ items: Entry[]; total: number }>(`/workspaces/${ws.id}/audit?limit=${PER_PAGE}&offset=${(pageNo - 1) * PER_PAGE}`),
    backend<Member[]>(`/workspaces/${ws.id}/members`),
  ]);
  const who = new Map(members.map((m) => [m.user_id, m.display_name]));
  const pages = Math.max(1, Math.ceil(log.total / PER_PAGE));
  return (
    <section className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><span className="eyebrow">Indstillinger</span><h2 className="font-display text-headline-sm text-ink font-bold">Aktivitetslog</h2><p className="text-body-sm text-ink-soft">Alle ændringer i {ws.name}, nyeste først. Loggen kan ikke redigeres.</p></div>
        <span className="px-2.5 py-1 rounded-full bg-panel-deep text-ink-soft text-label-sm font-medium">{log.total} hændelser</span>
      </div>
      {log.items.length === 0 ? <p className="p-3 rounded-xl bg-panel text-body-sm text-ink-soft">Ingen aktivitet endnu.</p> : (
        <ol className="flex flex-col gap-2">
          {log.items.map((e) => {
            const [label, icon] = ACTION[e.action] ?? [e.action, "history"];
            return (
              <li key={e.id} className="p-3 rounded-xl bg-panel flex items-start gap-2">
                <div className="w-9 h-9 rounded-full bg-paper text-ink flex items-center justify-center flex-shrink-0 border-2 border-ink"><Icon name={icon} size={18} /></div>
                <div className="min-w-0 flex-1">
                  <p className="text-label-lg text-ink">{label}</p>
                  <p className="text-body-sm text-ink-soft">{e.actor_user_id ? who.get(e.actor_user_id) ?? "Tidligere medlem" : "System"} · {new Date(e.created_at).toLocaleString("da-DK", { dateStyle: "medium", timeStyle: "short" })}</p>
                </div>
                {e.request_id && <span className="hidden md:inline font-mono text-label-sm text-ink-soft" title="Reference til support">{e.request_id.slice(0, 8)}</span>}
              </li>
            );
          })}
        </ol>
      )}
      {pages > 1 && (
        <nav aria-label="Sider" className="flex items-center justify-between">
          {pageNo > 1 ? <Link href={`?page=${pageNo - 1}`} className="px-3 py-1.5 rounded-lg bg-panel-deep text-ink text-label-md font-semibold flex items-center gap-1"><Icon name="chevron_left" size={18} />Nyere</Link> : <span />}
          <span className="text-label-md text-ink-soft">Side {pageNo} af {pages}</span>
          {pageNo < pages ? <Link href={`?page=${pageNo + 1}`} className="px-3 py-1.5 rounded-lg bg-panel-deep text-ink text-label-md font-semibold flex items-center gap-1">Ældre<Icon name="chevron_right" size={18} /></Link> : <span />}
        </nav>
      )}
    </section>
  );
}
