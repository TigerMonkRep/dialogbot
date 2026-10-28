import Link from "next/link";
import { AdminFrame, NotOperator, dt, load } from "./shared";

type Overview = {
  status: "green" | "amber" | "red"; environment: string; schema: { ok: boolean; database: string | null; code: string };
  tiles: Record<string, number>; attention: { level: "red" | "amber" | "blue"; title: string; detail: string; href: string }[];
};
const LABEL: Record<string, string> = {
  workspaces: "Kunder", users: "Brugere", new_workspaces_7d: "Nye kunder (7 dage)", calls_7d: "Opkald (7 dage)", conversations_7d: "Samtaler (7 dage)",
  leads_7d: "Henvendelser (7 dage)", campaigns_running: "Kampagner i gang", ambassadors_active: "Aktive ambassadører", queue: "Opgaver i kø",
};
const LIGHT = { green: ["bg-success-soft text-success", "Alt kører"], amber: ["bg-highlight text-ink", "Noget bør kigges på"], red: ["bg-danger-soft text-danger", "Der er en fejl"] } as const;
const DOT = { red: "bg-danger", amber: "bg-highlight border border-ink", blue: "bg-accent" } as const;

export default async function AdminOverview() {
  const ov = await load<Overview>("/operator/admin/overview");
  if (!ov) return <NotOperator />;
  const [cls, text] = LIGHT[ov.status];
  return (
    <AdminFrame active="/app/operator/admin" title="Overblik" intro="Først: er alt i orden, og hvad kræver dig? Under det de vigtigste tal. Alt kan klikkes videre til detaljer.">
      <div className={`rounded-2xl border-2 border-ink p-space-md flex flex-wrap items-center justify-between gap-3 ${cls}`}>
        <p className="font-display font-extrabold text-[22px]">{text}</p>
        <p className="text-[13px]">Miljø: {ov.environment} · database {ov.schema.database ?? "?"} {ov.schema.ok ? "= kode" : `≠ kode (${ov.schema.code})`}</p>
      </div>
      <section aria-label="Kræver opmærksomhed" className="rounded-2xl bg-paper border-2 border-ink">
        <h2 className="px-space-md pt-space-md font-display font-bold text-[18px]">Kræver opmærksomhed</h2>
        {ov.attention.length === 0 ? <p className="p-space-md text-on-surface-variant">Intet lige nu.</p> : (
          <ul className="divide-y divide-line">
            {ov.attention.map((a, i) => (
              <li key={i}><Link href={a.href} className="flex items-start gap-3 px-space-md py-3 hover:bg-panel">
                <span className={`mt-1.5 w-3 h-3 rounded-full shrink-0 ${DOT[a.level]}`} />
                <span><span className="font-semibold text-ink">{a.title}</span>{a.detail && <span className="block text-[13px] text-muted">{/^\d{4}-/.test(a.detail) ? dt(a.detail) : a.detail}</span>}</span>
              </Link></li>
            ))}
          </ul>
        )}
      </section>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-space-md">
        {Object.entries(ov.tiles).map(([k, v]) => (
          <div key={k} className="rounded-2xl bg-paper border-2 border-ink p-space-md"><p className="eyebrow">{LABEL[k] ?? k}</p><p className="font-display font-extrabold text-[32px] tabular-nums">{v}</p></div>
        ))}
      </div>
      <p className="text-[14px] text-muted">Vil du se en kunde som kunden selv? Gå til <Link className="underline font-semibold text-ink" href="/app/operator/admin/kunder">Kunder</Link> og tryk &quot;Se som&quot; ud for en person.</p>
    </AdminFrame>
  );
}
