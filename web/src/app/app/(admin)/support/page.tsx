import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Breadcrumb, Icon } from "@/components/ui";
import { getLocale, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";
import { NewTicketForm } from "./client";
import { StatusPill, when, type List } from "./shared";

/** Only a path inside the app may be passed on as the ticket's context (where the person came from). */
const appPath = (p?: string) => (p && p.startsWith("/app") && !p.startsWith("//") ? p.slice(0, 200) : undefined);

/** H01 «Support»: the workspace's tickets (open first) and «Opret ny sag». Staff and up; a reader is told who can. */
export default async function SupportPage({ searchParams }: { searchParams: Promise<{ fra?: string }> }) {
  const ws = await requireWorkspace();
  const t = await getT("app");
  const lang = HTML_LANG[await getLocale()];
  const { fra } = await searchParams;
  let list: List | null = null;
  try { list = await backend<List>(`/workspaces/${ws.id}/support/tickets`); } catch (e) {
    if ((e as { status?: number }).status !== 403) throw e;
  }
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Breadcrumb items={[[t("shell.help"), "/app/hjaelp"], [t("support.title")]]} />
        <h1 className="font-display font-extrabold text-[26px] sm:text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{t("support.title")}</h1>
        <p className="text-body-sm text-ink-soft max-w-3xl">{t("support.intro")}</p>
      </div>
      {!list ? (
        <p className="bg-paper rounded-2xl p-4 border-2 border-ink text-body-md text-ink-soft">{t("support.noAccess")}</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)] items-start">
          <section aria-labelledby="sager" className={`bg-paper rounded-2xl p-4 border-2 border-ink flex flex-col gap-3 ${list.items.length ? "order-1" : "order-2"} lg:order-1`}>
            <h2 id="sager" className="font-display text-headline-sm text-ink">{t("support.list.title")}</h2>
            {list.items.length === 0 ? <p className="text-body-sm text-muted">{t("support.list.empty")}</p> : (
              <ul className="flex flex-col gap-2">
                {list.items.map((s) => (
                  <li key={s.number}>
                    <Link href={`/app/support/${s.number}`} className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 rounded-xl border-[1.5px] border-ink p-3 hover:bg-panel min-h-[44px]">
                      <span className="flex-1 min-w-0">
                        <span className="block text-label-md text-muted">{t("support.ticket.number", { n: s.number })} · {t(`support.category.${s.category}`)}</span>
                        <span className="block font-semibold text-ink truncate">{s.subject}</span>
                        <span className="block text-body-sm text-muted">{t("support.list.updated", { date: when(lang, s.updated_at) })}</span>
                      </span>
                      <span className="self-start sm:self-center"><StatusPill status={s.status} label={t(`support.status.${s.status}`)} /></span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section aria-labelledby="ny-sag" className={`bg-paper rounded-2xl p-4 border-2 border-ink flex flex-col gap-3 ${list.items.length ? "order-2" : "order-1"} lg:order-2`}>
            <h2 id="ny-sag" className="font-display text-headline-sm text-ink flex items-center gap-1"><Icon name="add_task" size={22} className="text-muted" />{t("support.new.title")}</h2>
            <NewTicketForm wsId={ws.id} categories={list.categories} max={list.max_files} context={appPath(fra)} />
          </section>
        </div>
      )}
    </section>
  );
}
