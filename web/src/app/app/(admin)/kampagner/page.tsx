import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { kr } from "../leads/format";
import { DoNotCallList, EnableOutbound, NewCampaign } from "./client";
import { STATUS, type Campaign, type Dnc } from "./format";

type List = { items: Campaign[]; pricing: { call_net_minor: number; minute_net_minor: number; max_attempts: number; max_connected_seconds: number } };
type Goals = Record<string, unknown> & { version: number; callback: boolean };

/** «Kampagner»: ring to your own customers, one campaign at a time. Shown when «ringe kunder op» is chosen in trin 1. */
export default async function KampagnerPage() {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="rounded-2xl border-2 border-ink bg-paper p-6 text-[15px] text-ink-soft">Kampagner kan ses af medarbejdere, administratorer og ejere.</p>;
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [list, dnc, goals, me] = await Promise.all([
    backend<List>(`/workspaces/${ws.id}/campaigns`),
    backend<{ items: Dnc[] }>(`/workspaces/${ws.id}/do-not-call`),
    backend<Goals>(`/workspaces/${ws.id}/goals`),
    backend<{ is_platform_operator?: boolean }>(`/auth/me`).catch(() => ({ is_platform_operator: false })),
  ]);
  const p = list.pricing;
  if (!goals.callback && list.items.length === 0) {
    return (
      <div className="flex flex-col gap-4 max-w-[640px] rounded-2xl border-2 border-ink bg-paper px-6 py-6 shadow-block">
        <span className="eyebrow">I dag → Kampagner</span>
        <h1 className="font-display font-extrabold text-[28px] leading-[1.05] tracking-[-0.8px] text-ink">Vil I også ringe ud?</h1>
        <p className="text-[15px] leading-relaxed text-ink-soft">Dialogbot kan ringe til jeres egne kunder med et budskab – fx et tilbud – og sende de interesserede videre til jer. Det koster {kr(p.call_net_minor)} pr. udgående opkald ekskl. moms. Der ringes først, når I har godkendt.</p>
        {canManage ? <EnableOutbound wsId={ws.id} goals={goals} /> : <p className="text-[14px] text-muted">Kun ejere og administratorer kan slå udgående opkald til.</p>}
        <p className="text-[14px] text-ink-soft">Du kan også sige det til assistenten.</p>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-6 items-start">
      <section className="flex-[999_1_460px] min-w-0 flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <span className="eyebrow">I dag → Kampagner · udgående opkald · {kr(p.call_net_minor)} pr. opkald ekskl. moms</span>
          <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Ring til jeres kunder – én kampagne ad gangen</h1>
          <p className="text-[15px] leading-relaxed text-ink-soft max-w-[640px]">
            Tre trin: du vælger, hvem den skal ringe til, hører hvad den siger, og godkender prisen, før første opkald går ud. Prisen er {kr(p.call_net_minor)} + moms pr. udgående opkald – hvert opkald tæller, også et nyt forsøg. Højst {p.max_attempts} forsøg og i alt {p.max_connected_seconds / 60} minutters samtale pr. kontakt. Dialogbot ringer aldrig til nogen på spærrelisten.
          </p>
          {me.is_platform_operator && <Link href="/app/operator/sales" className="text-[14px] font-semibold text-accent hover:underline">Salgsopkald: lad AI&apos;en ringe op (kun Dialogbot) →</Link>}
        </div>
        {canManage ? (
          <div className="flex flex-col gap-3 rounded-2xl border-2 border-ink bg-paper px-5 py-5">
            <span className="eyebrow">Du skal bruge</span>
            <ul className="text-[14px] text-ink-soft list-disc pl-5"><li>en liste med navn og nummer (CSV eller indsat fra Excel)</li><li>én sætning om, hvorfor I ringer</li></ul>
            <NewCampaign wsId={ws.id} />
          </div>
        ) : <p className="text-[14px] text-muted">Kun administratorer og ejere kan oprette og starte kampagner.</p>}
      </section>
      <aside className="flex-[1_1_300px] min-w-0 max-w-[440px] flex flex-col gap-5">
        <div className="flex flex-col gap-3 rounded-2xl border-2 border-ink bg-paper px-5 py-5 shadow-block">
          <h2 className="font-display font-extrabold text-[20px] text-ink">Tidligere kampagner</h2>
          {list.items.length === 0 ? <p className="text-[14px] text-ink-soft">Ingen kampagner endnu.</p> : (
            <ul className="flex flex-col">
              {list.items.map((c) => {
                const o = c.counts.by_outcome;
                const answered = c.counts.by_status.done ?? 0;
                return (
                  <li key={c.id} className="border-t-[1.5px] border-line first:border-0">
                    <Link href={`/app/kampagner/${c.id}`} className="flex flex-col gap-0.5 py-3 hover:bg-panel -mx-2 px-2 rounded-lg">
                      <span className="flex flex-wrap items-center gap-2"><b className="text-[15px] text-ink">{c.name}</b><span className={`px-2.5 py-0.5 rounded-full text-[12px] font-semibold ${STATUS[c.status][1]}`}>{STATUS[c.status][0]}</span></span>
                      <span className="text-[13px] text-ink-soft">{c.counts.calls} opkald · {answered} talt med · {o.interested ?? 0} interesserede · {c.counts.open} tilbage</span>
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
