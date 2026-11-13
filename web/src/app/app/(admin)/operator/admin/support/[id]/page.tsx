import Link from "next/link";
import { notFound } from "next/navigation";
import { AdminFrame, NotOperator, dt, load } from "../../shared";
import { CATEGORY, PriorityPill, StatusPill, type QueueItem } from "../labels";
import { Composer, Triage } from "./client";

type Detail = QueueItem & {
  messages: { id: string; author_kind: "customer" | "operator"; visibility: "public" | "internal"; author_name: string; body: string; created_at: string;
    attachments: { id: string; filename: string; content_type: string; size_bytes: number }[] }[];
  operators: { id: string; name: string }[];
};
const box = "rounded-2xl bg-paper border-2 border-ink p-3 md:p-4";

/** M06 ticket workbench: who/what/where, triage (status, priority, category, assignee), the full thread including
 *  internal notes, and the composer (client-visible reply or internal note). */
export default async function SupportTicket({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const d = await load<Detail>(`/operator/support/tickets/${id}`);
  if (!d) return <NotOperator />;
  return (
    <AdminFrame active="/app/operator/admin/support" eyebrow={`Admin · support · #${d.number}`} title={d.subject}
      intro={`${d.workspace.name} · ${CATEGORY[d.category] ?? d.category} · oprettet ${dt(d.created_at)}${d.created_by ? ` af ${d.created_by.name} (${d.created_by.email})` : ""}`}>
      <p><Link className="underline" href="/app/operator/admin/support">← Supportkøen</Link></p>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px] items-start">
        <div className="flex flex-col gap-4 min-w-0">
          <section aria-labelledby="traad" className={`${box} flex flex-col gap-3`}>
            <h2 id="traad" className="font-display font-extrabold text-[20px] flex flex-wrap items-center gap-2">Sagsforløb <StatusPill s={d.status} /><PriorityPill p={d.priority} /></h2>
            <ol className="flex flex-col gap-3">
              {d.messages.map((m) => {
                const internal = m.visibility === "internal";
                return (
                  <li key={m.id} data-visibility={m.visibility} className={`rounded-xl border-[1.5px] p-3 ${internal ? "border-dashed border-ink bg-highlight/40" : m.author_kind === "operator" ? "border-accent bg-accent-soft/40" : "border-ink bg-paper"}`}>
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-[13px]">
                      <span className="font-semibold">{m.author_name || "Ukendt"} · {internal ? "Intern note – kun operatører" : m.author_kind === "operator" ? "Kundesynligt svar" : "Kunde"}</span>
                      <span className="text-muted">{dt(m.created_at)}</span>
                    </div>
                    <p className="mt-1 text-[15px] whitespace-pre-wrap break-words">{m.body}</p>
                    {m.attachments.length > 0 && (
                      <ul className="mt-2 flex flex-wrap gap-2">{m.attachments.map((a) => (
                        <li key={a.id}><a className="inline-flex items-center min-h-[44px] px-3 rounded-xl border-[1.5px] border-ink bg-paper text-[14px] underline break-all" download={a.filename}
                          href={`/api/backend/operator/support/tickets/${d.id}/attachments/${a.id}`}>{a.filename} ({Math.max(1, Math.round(a.size_bytes / 1024))} KB)</a></li>
                      ))}</ul>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
          <section aria-labelledby="svar" className={box}>
            <h2 id="svar" className="font-display font-extrabold text-[20px] mb-2">Svar eller notér</h2>
            <Composer id={d.id} workspace={d.workspace.name} />
          </section>
        </div>
        <aside className="flex flex-col gap-4">
          <section aria-labelledby="kunde" className={box}>
            <h2 id="kunde" className="font-display font-bold text-[18px] mb-1">Arbejdsrum</h2>
            <p className="text-[14px]"><Link className="underline font-semibold" href={`/app/operator/admin/kunder/${d.workspace.id}`}>{d.workspace.name}</Link></p>
            {d.context_path && <p className="text-[13px] text-muted mt-1">Kom fra: {d.context_path}</p>}
            {d.resolved_at && <p className="text-[13px] text-muted mt-1">Løst {dt(d.resolved_at)}</p>}
          </section>
          <section aria-labelledby="triage" className={box}>
            <h2 id="triage" className="font-display font-bold text-[18px] mb-2">Behandling</h2>
            <Triage id={d.id} status={d.status} priority={d.priority} category={d.category} assigned={d.assigned_to?.id ?? ""} operators={d.operators} />
          </section>
        </aside>
      </div>
    </AdminFrame>
  );
}
