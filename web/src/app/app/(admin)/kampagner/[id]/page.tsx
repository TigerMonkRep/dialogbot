import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Breadcrumb } from "@/components/ui";
import { CampaignEditor, ImportContacts, Num, RemoveContact, StartCampaign } from "../client";
import { STATUS, contactLabel, type Campaign, type Contact, type PhoneNumber } from "../format";
import { getLocale, getT } from "@/i18n/server";
import { currencyOr, formatPrice } from "@/lib/markets";

/** C02: one campaign – script, contacts, start/pause and results. */
export default async function CampaignPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ws = await requireWorkspace();
  const t = await getT("app");
  if (ws.role === "reader") return <p className="text-body-md">{t("campaigns.staffOnly")}</p>;
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [c, contacts, list, numbers] = await Promise.all([
    backend<Campaign>(`/workspaces/${ws.id}/campaigns/${id}`),
    backend<{ items: Contact[] }>(`/workspaces/${ws.id}/campaigns/${id}/contacts?limit=500`),
    backend<{ legal_checklist: string[] }>(`/workspaces/${ws.id}/campaigns`),
    backend<{ items: PhoneNumber[] }>(`/workspaces/${ws.id}/phone-numbers`).catch(() => ({ items: [] as PhoneNumber[] })),
  ]);
  const o = c.counts.by_outcome;
  const stats: [string, number][] = [[t("campaigns.stats.contacts"), c.counts.total], [t("campaigns.stats.answered"), c.counts.answered], [t("campaigns.stats.interested"), o.interested ?? 0],
    [t("campaigns.stats.callback"), o.callback ?? 0], [t("campaigns.stats.noAnswer"), c.counts.by_status.no_answer ?? 0], [t("campaigns.stats.left"), c.counts.open]];
  const hasCount = c.counts.total;
  return (
    <div className="flex flex-wrap gap-6 items-start">
      <section className="flex-[999_1_460px] min-w-0 flex flex-col gap-5">
        <Breadcrumb items={[[t("overview.campaigns"), "/app/kampagner"], [c.name]]} />
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-display font-extrabold text-[26px] sm:text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{c.name}</h1>
          <span className={`px-3 py-1 rounded-full text-label-sm font-semibold ${STATUS[c.status]}`}>{t(`campaigns.status.${c.status}`)}</span>
        </div>
        <dl className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">{stats.map(([k, v]) => (
          <div key={k} className="min-w-0 bg-paper rounded-2xl p-3 border-2 border-ink">
            <dt className="text-label-sm text-ink-soft hyphens-auto">{k}</dt>
            <dd className="font-display font-extrabold text-[24px] text-ink">{v}</dd>
          </div>
        ))}</dl>
        <div className="flex flex-col gap-4 rounded-2xl border-2 border-ink bg-paper px-5 py-5">
          <h2 className="flex items-center gap-3 font-display font-extrabold text-[20px] text-ink"><Num n={1} />{t("campaigns.detail.who")}</h2>
          <p className="text-[14px] text-ink-soft">{t("campaigns.detail.contacts", { n: hasCount })}</p>
          {canManage && c.status === "running" && <p className="text-[14px] text-ink-soft">{t("campaigns.import.pauseFirst")}</p>}
          {canManage && c.status !== "completed" && c.status !== "running" && <ImportContacts wsId={ws.id} id={c.id} />}
          {contacts.items.length === 0 ? <p className="text-[14px] text-ink-soft">{t("campaigns.detail.noContacts")}</p> : (
            <ul className="flex flex-col">{contacts.items.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-2 py-2.5 border-t-[1.5px] border-line text-[14px]">
                <span className="font-semibold text-ink">{x.name || x.company || x.phone}</span>
                {x.company && x.name && <span className="text-ink-soft">{x.company}</span>}
                <span className="text-ink-soft">{x.phone}</span>
                <span className="px-2.5 py-0.5 rounded-full bg-panel border-[1.5px] border-line text-[12px] font-semibold">{contactLabel(t, x)}</span>
                {x.consent_source ? <span className="text-[12px] text-ink-soft" title={x.consent_source}>{x.kind === "consumer" ? t("campaigns.detail.private") : t("campaigns.detail.business")} ({t("campaigns.detail.consent")})</span> : <span className="text-[12px] text-danger">{t("campaigns.detail.noConsent")}</span>}
                {x.attempts > 0 && <span className="text-[12px] text-ink-soft">{t("campaigns.detail.attempts", { n: x.attempts })}</span>}
                <span className="ml-auto flex items-center gap-3">
                  {x.lead_id && <Link href={`/app/opkald/henvendelser/${x.lead_id}`} className="font-semibold text-accent hover:underline">{t("bookings.card.lead")}</Link>}
                  {canManage && !x.charged && x.status === "pending" && <RemoveContact wsId={ws.id} campaignId={c.id} id={x.id} />}
                </span>
                {(x.summary || x.error) && <p className="w-full text-[13px] text-ink-soft">{x.summary || x.error}</p>}
              </li>
            ))}</ul>
          )}
        </div>
        <CampaignEditor wsId={ws.id} c={c} numbers={numbers.items.filter((n) => n.active)} canManage={canManage} />
      </section>
      <aside className="flex-[1_1_300px] min-w-0 max-w-[440px] flex flex-col gap-5 lg:sticky lg:top-[88px]">
        {canManage && <StartCampaign wsId={ws.id} c={c} checklist={list.legal_checklist} />}
        <p className="text-[13px] text-muted">{t("campaigns.detail.priceNote", { price: formatPrice(c.pricing.call_net_minor, currencyOr(c.pricing.currency), await getLocale()) })}</p>
      </aside>
    </div>
  );
}
