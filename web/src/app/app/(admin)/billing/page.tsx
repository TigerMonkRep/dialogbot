import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { kr } from "../leads/format";

type Statement = {
  month: string; timezone: string; agreement: { version: number; model: string } | null; approved_leads: number; billable_leads: number;
  lines: { kind: string; lead_id?: string; description: string; approved_at?: string; net_minor: number }[];
  totals: { net_minor: number; tax_minor: number; gross_minor: number };
};

const monthLabel = (ym: string) => { const s = new Date(`${ym}-15T12:00:00`).toLocaleDateString("da-DK", { month: "long", year: "numeric" }); return s.charAt(0).toUpperCase() + s.slice(1); };
const shift = (ym: string, d: number) => { const [y, m] = ym.split("-").map(Number); const t = new Date(Date.UTC(y, m - 1 + d, 1)); return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}`; };

/** Monthly statement preview. Honest: nothing is invoiced or charged in this stage. */
export default async function BillingPage({ searchParams }: { searchParams: Promise<{ month?: string }> }) {
  const ws = await requireWorkspace();
  if (ws.role !== "owner" && ws.role !== "admin") return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Afregning kan ses af ejere og administratorer.</p>;
  const want = (await searchParams).month;
  const s = await backend<Statement>(`/workspaces/${ws.id}/billing/statement${want && /^\d{4}-\d{2}$/.test(want) ? `?month=${want}` : ""}`);
  return (
    <div className="flex flex-col gap-space-lg max-w-4xl">
      <div className="flex flex-col gap-space-xs">
        <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary tracking-tight">Afregning</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant">Oversigt over, hvad måneden koster efter jeres prisaftale. Beløb i kr. med to decimaler, moms 25 %.</p>
      </div>
      <p className="p-space-sm rounded-lg bg-tertiary-fixed text-on-tertiary-fixed font-body-sm text-body-sm flex items-start gap-space-xs"><Icon name="info" size={18} />Dette er en forhåndsvisning – ikke en faktura. Der faktureres og trækkes ingen betaling endnu.</p>
      <div className="flex items-center justify-between gap-space-sm">
        <Link href={`/app/billing?month=${shift(s.month, -1)}`} className="font-label-lg text-label-lg text-primary flex items-center gap-1"><Icon name="chevron_left" size={20} />Forrige</Link>
        <h2 className="font-headline-md text-headline-md text-primary">{monthLabel(s.month)}</h2>
        <Link href={`/app/billing?month=${shift(s.month, 1)}`} className="font-label-lg text-label-lg text-primary flex items-center gap-1">Næste<Icon name="chevron_right" size={20} /></Link>
      </div>
      <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
        <p className="font-body-md text-body-md">{s.agreement ? <>Prisaftale: <strong>model {s.agreement.model}</strong> (version {s.agreement.version}). {s.approved_leads} godkendte henvendelser, heraf {s.billable_leads} med gebyr.</> : <>Ingen prisaftale i denne måned. <Link href="/app/settings/agreement" className="text-primary underline">Vælg model</Link>.</>}</p>
        {s.lines.length === 0 ? <p className="font-body-sm text-body-sm text-on-surface-variant">Ingen poster i denne måned.</p> : (
          <table className="w-full font-body-sm text-body-sm">
            <thead><tr className="text-left text-on-surface-variant"><th className="py-space-xs font-label-md text-label-md">Post</th><th className="py-space-xs font-label-md text-label-md text-right">Netto</th></tr></thead>
            <tbody>
              {s.lines.map((l, i) => (
                <tr key={l.lead_id ?? `${l.kind}-${i}`} className="border-t border-surface-container">
                  <td className="py-space-xs">{l.lead_id ? <Link href={`/app/leads/${l.lead_id}`} className="text-primary hover:underline">{l.description}</Link> : l.description}{l.approved_at && <span className="text-on-surface-variant"> · {new Date(l.approved_at).toLocaleDateString("da-DK")}</span>}</td>
                  <td className="py-space-xs text-right tabular-nums">{kr(l.net_minor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <dl className="grid grid-cols-2 gap-x-space-md gap-y-1 self-end min-w-64 font-body-md text-body-md border-t border-surface-container pt-space-sm">
          <dt className="text-on-surface-variant">Netto</dt><dd className="text-right tabular-nums">{kr(s.totals.net_minor)}</dd>
          <dt className="text-on-surface-variant">Moms 25 %</dt><dd className="text-right tabular-nums">{kr(s.totals.tax_minor)}</dd>
          <dt className="font-semibold">I alt</dt><dd className="text-right tabular-nums font-bold text-primary">{kr(s.totals.gross_minor)}</dd>
        </dl>
      </section>
    </div>
  );
}
