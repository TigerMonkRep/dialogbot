import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { kr } from "../leads/format";
import { AddCard, InvoiceMonth } from "./client";

type Statement = {
  month: string; timezone: string; agreement: { version: number; model: string } | null; approved_leads: number; billable_leads: number;
  lines: { kind: string; lead_id?: string; description: string; approved_at?: string; net_minor: number }[];
  totals: { net_minor: number; tax_minor: number; gross_minor: number };
};

type Account = { configured: boolean; card: { brand: string; last4: string; exp: string | null } | null; can_manage: boolean };
type Inv = { id: string; month: string; status: string; number: string | null; gross_minor: number; hosted_invoice_url: string | null; invoice_pdf: string | null; note: string | null };
const INV_STATUS: Record<string, string> = { creating: "Oprettes", open: "Afventer betaling", paid: "Betalt", payment_failed: "Betaling fejlede", failed: "Ikke betalt", void: "Annulleret" };

const monthLabel = (ym: string) => { const s = new Date(`${ym}-15T12:00:00`).toLocaleDateString("da-DK", { month: "long", year: "numeric" }); return s.charAt(0).toUpperCase() + s.slice(1); };
const shift = (ym: string, d: number) => { const [y, m] = ym.split("-").map(Number); const t = new Date(Date.UTC(y, m - 1 + d, 1)); return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}`; };

/** Card (Stripe), invoices and the running month's statement. Honest about what is and is not charged. */
export default async function BillingPage({ searchParams }: { searchParams: Promise<{ month?: string; card?: string }> }) {
  const ws = await requireWorkspace();
  if (ws.role !== "owner" && ws.role !== "admin") return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Afregning kan ses af ejere og administratorer.</p>;
  const sp = await searchParams;
  const want = sp.month;
  const [s, acc, invoices] = await Promise.all([
    backend<Statement>(`/workspaces/${ws.id}/billing/statement${want && /^\d{4}-\d{2}$/.test(want) ? `?month=${want}` : ""}`),
    backend<Account>(`/workspaces/${ws.id}/billing/account`),
    backend<{ items: Inv[] }>(`/workspaces/${ws.id}/billing/invoices`),
  ]);
  const current = new Date().toISOString().slice(0, 7);
  const previous = shift(current, -1);
  const invoicedPrevious = invoices.items.some((i) => i.month === previous);
  return (
    <div className="flex flex-col gap-space-lg max-w-4xl">
      <div className="flex flex-col gap-space-xs">
        <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary tracking-tight">Afregning</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant">Oversigt over, hvad måneden koster efter jeres prisaftale. Beløb i kr. med to decimaler, moms 25 %.</p>
      </div>
      {sp.card === "saved" && <p role="status" className="p-space-sm rounded-lg bg-secondary-container text-on-secondary-container font-body-sm text-body-sm">Tak – kortet er gemt hos Stripe. Det kan tage et øjeblik, før det vises her.</p>}
      <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
        <h2 className="font-headline-sm text-headline-sm text-primary">Betaling</h2>
        {!acc.configured ? (
          <p className="font-body-md text-body-md text-on-surface-variant">Kortbetaling er ikke sat op endnu. Indtil da er oversigten nedenfor kun en forhåndsvisning, og der trækkes ingen betaling.</p>
        ) : (
          <>
            <p className="font-body-md text-body-md">{acc.card ? <>Betalingskort: <strong className="capitalize">{acc.card.brand}</strong> •••• {acc.card.last4}{acc.card.exp ? ` (udløber ${acc.card.exp})` : ""}. Hver måned faktureres bagud og trækkes automatisk på kortet.</> : "Der er intet betalingskort. Uden kort bliver måneden ikke faktureret."}</p>
            {acc.can_manage ? <AddCard wsId={ws.id} hasCard={!!acc.card} /> : <p className="font-body-sm text-body-sm text-on-surface-variant">Kun ejeren kan ændre betalingskortet.</p>}
            {acc.can_manage && acc.card && !invoicedPrevious && <InvoiceMonth wsId={ws.id} month={previous} label={monthLabel(previous).toLowerCase()} />}
          </>
        )}
        <p className="font-body-sm text-body-sm text-on-surface-variant">Betaling starter aldrig opkald. Kampagner startes kun af en administrator.</p>
      </section>
      {invoices.items.length > 0 && (
        <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
          <h2 className="font-headline-sm text-headline-sm text-primary">Fakturaer</h2>
          <ul className="flex flex-col gap-space-xs">{invoices.items.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center gap-space-sm p-space-sm rounded-lg bg-surface-container-low font-body-md text-body-md">
              <span className="font-label-lg text-label-lg">{monthLabel(i.month)}</span>
              {i.number && <span className="text-on-surface-variant">{i.number}</span>}
              <span className="px-2 py-0.5 rounded-full bg-surface-container-high font-label-sm text-label-sm">{INV_STATUS[i.status] ?? i.status}</span>
              <span className="tabular-nums">{kr(i.gross_minor)} inkl. moms</span>
              <span className="ml-auto flex gap-space-sm">
                {i.hosted_invoice_url && <a href={i.hosted_invoice_url} target="_blank" rel="noopener noreferrer" className="text-primary underline">Se faktura</a>}
                {i.invoice_pdf && <a href={i.invoice_pdf} target="_blank" rel="noopener noreferrer" className="text-primary underline">PDF</a>}
              </span>
            </li>
          ))}</ul>
        </section>
      )}
      <p className="p-space-sm rounded-lg bg-tertiary-fixed text-on-tertiary-fixed font-body-sm text-body-sm flex items-start gap-space-xs"><Icon name="info" size={18} />Oversigten nedenfor viser, hvad måneden koster indtil videre. Den faktureres først, når måneden er slut{acc.configured ? "" : " og kortbetaling er sat op"}.</p>
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
