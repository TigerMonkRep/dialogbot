import { notFound } from "next/navigation";
import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";

/** Shared frame for the operator admin: the tabs, one heading. Everything here is read-only, except «Ønsker», where
 *  operators set a status and a note on the customers' wishes, «Support» (M06), where they work the support queue, and
 *  «Fakturering», where they decide complaints about calls. */
const TABS: [string, string][] = [
  ["/app/operator/admin", "Overblik"], ["/app/operator/admin/kunder", "Kunder"], ["/app/operator/admin/brugere", "Brugere"],
  ["/app/operator/oensker", "Ønsker"], ["/app/operator/admin/support", "Support"], ["/app/operator/admin/drift", "Drift"], ["/app/operator/admin/hjemmeside", "Hjemmeside"],
  ["/app/operator/admin/rabatkoder", "Rabatkoder"], ["/app/operator/admin/fakturering", "Fakturering"], ["/app/operator/admin/vaerktoejer", "Værktøjer"], ["/app/operator/privat", "Privat"],
];

export function AdminFrame({ active, title, intro, eyebrow = "Admin · kun læsning", children }: { active: string; title: string; intro?: string; eyebrow?: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{title}</h1>
        {intro && <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl mt-1">{intro}</p>}
      </div>
      <nav aria-label="Admin" className="flex flex-wrap gap-2">
        {TABS.map(([href, label]) => (
          <Link key={href} href={href} aria-current={href === active ? "page" : undefined}
            className={`px-4 py-2 rounded-full border-2 border-ink text-[14px] font-semibold ${href === active ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-panel"}`}>{label}</Link>
        ))}
      </nav>
      {children}
    </section>
  );
}

export function NotOperator() {
  return <p className="bg-surface-container-lowest rounded-2xl p-space-lg border-2 border-ink font-body-md text-body-md text-on-surface-variant">Admin er kun for Dialogbot-operatører.</p>;
}

/** Fetch an operator endpoint; null ONLY when the caller is not an operator (401/403). An unknown customer (404) or a
 *  backend failure is thrown, so the page shows «findes ikke» / the error page instead of «kun for operatører». */
export async function load<T>(path: string): Promise<T | null> {
  await requireWorkspace();
  try { return await backend<T>(path); } catch (e) {
    const status = (e as { status?: number }).status;
    if (status === 401 || status === 403 || status === 501) return null;  // not an operator / feature switched off
    if (status === 404) notFound();
    throw e;
  }
}

export const dt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Copenhagen" }) : "–");
export const kr = (minor: number) => `${(minor / 100).toLocaleString("da-DK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kr.`;

/** The "avanceret" block: every raw row, folded away until it is needed. */
export function Advanced({ data, label = "Vis alle detaljer (avanceret)" }: { data: unknown; label?: string }) {
  return (
    <details className="rounded-2xl border-2 border-ink bg-paper">
      <summary className="cursor-pointer px-space-md py-3 font-semibold text-ink">{label}</summary>
      <pre className="overflow-x-auto p-space-md text-[12px] leading-5 border-t-2 border-ink bg-panel rounded-b-2xl">{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}
