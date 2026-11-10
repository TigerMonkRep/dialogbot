import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { kr } from "../leads/format";
import { DoNotCallList, EnableOutbound, NewCampaign } from "./client";
import { STATUS, type Campaign, type Dnc } from "./format";
import { getLocale, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";

type List = { items: Campaign[]; pricing: { call_net_minor: number; minute_net_minor: number; max_attempts: number; max_connected_seconds: number; currency?: string } };
type Goals = Record<string, unknown> & { version: number; product_intent: string };

/** «Kampagner»: ring to your own customers, one campaign at a time. Shown when «ringe kunder op» is chosen in trin 1. */
export default async function KampagnerPage() {
  const ws = await requireWorkspace();
  const t = await getT("app");
  const lang = HTML_LANG[await getLocale()];
  if (ws.role === "reader") return <p className="rounded-2xl border-2 border-ink bg-paper p-6 text-[15px] text-ink-soft">{t("campaigns.staffOnly")}</p>;
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [list, dnc, goals, me] = await Promise.all([
    backend<List>(`/workspaces/${ws.id}/campaigns`),
    backend<{ items: Dnc[] }>(`/workspaces/${ws.id}/do-not-call`),
    backend<Goals>(`/workspaces/${ws.id}/goals`),
    backend<{ is_platform_operator?: boolean }>(`/auth/me`).catch(() => ({ is_platform_operator: false })),
  ]);
  const p = list.pricing;
  // «Ringe kunder op» (trin 1) = product_intent campaigns/both. Not the reception's callback flag, which the API refuses
  // for a campaigns-only workspace (F-E2C-01-C02).
  if (goals.product_intent === "reception" && list.items.length === 0) {
    return (
      <div className="flex flex-col gap-4 max-w-[640px] rounded-2xl border-2 border-ink bg-paper px-6 py-6 shadow-block">
        <span className="eyebrow">{t("campaigns.eyebrow")}</span>
        <h1 className="font-display font-extrabold text-[28px] leading-[1.05] tracking-[-0.8px] text-ink">{t("campaigns.enable.title")}</h1>
        <p className="text-[15px] leading-relaxed text-ink-soft">{t("campaigns.enable.body", { price: kr(p.call_net_minor, lang, p.currency) })}</p>
        {canManage ? <EnableOutbound wsId={ws.id} goals={goals} /> : <p className="text-[14px] text-muted">{t("campaigns.enable.onlyAdmins")}</p>}
        <p className="text-[14px] text-ink-soft">{t("campaigns.enable.ask")}</p>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-6 items-start">
      <section className="flex-[999_1_460px] min-w-0 flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <span className="eyebrow">{t("campaigns.eyebrowPrice", { price: kr(p.call_net_minor, lang, p.currency) })}</span>
          <h1 className="font-display font-extrabold text-[26px] sm:text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{t("campaigns.title")}</h1>
          <p className="text-[15px] leading-relaxed text-ink-soft max-w-[640px]">
            {t("campaigns.intro", { price: kr(p.call_net_minor, lang, p.currency), attempts: p.max_attempts, minutes: p.max_connected_seconds / 60 })}
          </p>
          {me.is_platform_operator && <Link href="/app/operator/sales" className="text-[14px] font-semibold text-accent hover:underline">{t("campaigns.salesCalls")} →</Link>}
        </div>
        {canManage ? (
          <div className="flex flex-col gap-3 rounded-2xl border-2 border-ink bg-paper px-5 py-5">
            <span className="eyebrow">{t("campaigns.need.title")}</span>
            <ul className="text-[14px] text-ink-soft list-disc pl-5"><li>{t("campaigns.need.list")}</li><li>{t("campaigns.need.sentence")}</li></ul>
            <NewCampaign wsId={ws.id} />
          </div>
        ) : <p className="text-[14px] text-muted">{t("campaigns.onlyAdmins")}</p>}
      </section>
      <aside className="flex-[1_1_300px] min-w-0 max-w-[440px] flex flex-col gap-5">
        <div className="flex flex-col gap-3 rounded-2xl border-2 border-ink bg-paper px-5 py-5 shadow-block">
          <h2 className="font-display font-extrabold text-[20px] text-ink">{t("campaigns.previous")}</h2>
          {list.items.length === 0 ? <p className="text-[14px] text-ink-soft">{t("campaigns.none")}</p> : (
            <ul className="flex flex-col">
              {list.items.map((c) => {
                const o = c.counts.by_outcome;
                const answered = c.counts.answered;
                return (
                  <li key={c.id} className="border-t-[1.5px] border-line first:border-0">
                    <Link href={`/app/kampagner/${c.id}`} className="flex flex-col gap-0.5 py-3 hover:bg-panel -mx-2 px-2 rounded-lg">
                      <span className="flex flex-wrap items-center gap-2"><b className="text-[15px] text-ink">{c.name}</b><span className={`px-2.5 py-0.5 rounded-full text-[12px] font-semibold ${STATUS[c.status]}`}>{t(`campaigns.status.${c.status}`)}</span></span>
                      <span className="text-[13px] text-ink-soft">{t("campaigns.summary", { calls: c.counts.calls, answered, interested: o.interested ?? 0, open: c.counts.open })}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <DoNotCallList wsId={ws.id} items={dnc.items} canManage={canManage} />
      </aside>
    </div>
  );
}
