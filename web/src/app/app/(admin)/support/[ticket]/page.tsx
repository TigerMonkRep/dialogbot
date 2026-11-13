import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, orNotFound } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Breadcrumb, Icon } from "@/components/ui";
import { getLocale, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";
import { TicketActions } from "../client";
import { StatusPill, size, when, type Ticket } from "../shared";

/** H01 «Sag #n»: subject, status (and what it means), the thread with attachments, and the customer's actions.
 *  Only what the API's customer serializer returns is shown – internal notes never reach this page (DB-016). */
export default async function TicketPage({ params }: { params: Promise<{ ticket: string }> }) {
  const { ticket } = await params;
  if (!/^\d{1,9}$/.test(ticket)) notFound();
  const ws = await requireWorkspace();
  const t = await getT("app");
  const lang = HTML_LANG[await getLocale()];
  let d: Ticket;
  try { d = await orNotFound(backend<Ticket>(`/workspaces/${ws.id}/support/tickets/${ticket}`)); } catch (e) {
    if ((e as { status?: number }).status === 403) {
      return <p className="bg-paper rounded-2xl p-4 border-2 border-ink text-body-md text-ink-soft">{t("support.noAccess")}</p>;
    }
    throw e;
  }
  const files = `/api/backend/workspaces/${ws.id}/support/tickets/${d.number}/attachments`;
  return (
    <section className="flex flex-col gap-4 max-w-4xl">
      <div className="flex flex-col gap-1">
        <Breadcrumb items={[[t("shell.help"), "/app/hjaelp"], [t("support.title"), "/app/support"], [t("support.ticket.number", { n: d.number })]]} />
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-display font-extrabold text-[24px] sm:text-[28px] md:text-[32px] leading-[1.1] tracking-[-0.6px] text-ink break-words min-w-0">{d.subject}</h1>
          <StatusPill status={d.status} label={t(`support.status.${d.status}`)} />
        </div>
        <p className="text-body-sm text-muted">
          {t("support.ticket.number", { n: d.number })} · {t(`support.category.${d.category}`)} · {d.created_by ? t("support.ticket.meta", { date: when(lang, d.created_at), name: d.created_by }) : t("support.ticket.metaNoName", { date: when(lang, d.created_at) })}
        </p>
      </div>
      <p role="status" className={`rounded-xl border-[1.5px] border-ink p-3 text-body-sm ${d.status === "waiting_customer" ? "bg-highlight" : "bg-panel"}`}>{t(`support.statusHelp.${d.status}`)}</p>

      <section aria-labelledby="samtale" className="bg-paper rounded-2xl p-4 border-2 border-ink flex flex-col gap-3">
        <h2 id="samtale" className="font-display text-headline-sm text-ink flex items-center gap-1"><Icon name="forum" size={22} className="text-muted" />{t("support.ticket.thread")}</h2>
        <ol className="flex flex-col gap-3">
          {d.messages.map((m) => {
            const ops = m.author_kind === "operator";
            return (
              <li key={m.id} data-author={m.author_kind} className={`rounded-xl border-[1.5px] p-3 ${ops ? "border-accent bg-accent-soft/40 sm:ml-8" : "border-ink bg-paper sm:mr-8"}`}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-label-md">
                  <span className="font-semibold text-ink flex items-center gap-1">{ops && <Icon name="verified" size={16} className="text-accent" />}{ops ? (m.author_name ? t("support.ticket.supportNamed", { name: m.author_name }) : t("support.ticket.support")) : m.author_name}</span>
                  <time dateTime={m.created_at} className="text-muted">{when(lang, m.created_at)}</time>
                </div>
                <p className="mt-1 text-body-md text-ink whitespace-pre-wrap break-words">{m.body}</p>
                {m.attachments.length > 0 && (
                  <ul aria-label={t("support.ticket.attachments")} className="mt-2 flex flex-wrap gap-2">
                    {m.attachments.map((a) => (
                      <li key={a.id}>
                        <a href={`${files}/${a.id}`} download={a.filename} className="inline-flex items-center gap-1.5 min-h-[44px] px-3 rounded-xl border-[1.5px] border-ink bg-paper text-[14px] hover:bg-panel">
                          <Icon name={a.content_type.startsWith("image/") ? "image" : "description"} size={18} />
                          <span className="font-semibold break-all">{a.filename}</span><span className="text-muted">{size(lang, a.size_bytes)}</span>
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ol>
      </section>

      <section className="bg-paper rounded-2xl p-4 border-2 border-ink">
        <TicketActions wsId={ws.id} number={d.number} status={d.status} max={3} />
      </section>
      <p><Link href="/app/support" className="underline text-ink">← {t("support.ticket.back")}</Link></p>
    </section>
  );
}
