import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";

/** Dialogbot's own sales channel: only platform operators. What is not built yet is listed honestly on the overview. */
const TABS: [string, string][] = [
  ["/app/operator/salg", "Overblik"], ["/app/operator/salg/find", "Find virksomheder"],
  ["/app/operator/salg/virksomheder", "Virksomheder"], ["/app/operator/salg/kampagner", "Kampagner"],
  ["/app/operator/salg/opkald", "Opkald"], ["/app/operator/salg/statistik", "Statistik"], ["/app/operator/salg/viden", "Viden og tilbud"],
  ["/app/operator/sales", "Demo-opkald"],
];

export function SalgFrame({ active, title, intro, children }: { active: string; title: string; intro?: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="eyebrow">Dialogbots salg · kun operatører</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{title}</h1>
        {intro && <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl mt-1">{intro}</p>}
      </div>
      <nav aria-label="Dialogbots salg" className="flex flex-wrap gap-2">
        {TABS.map(([href, label]) => (
          <Link key={href} href={href} aria-current={href === active ? "page" : undefined}
            className={`px-4 py-2 rounded-full border-2 border-ink text-[14px] font-semibold ${href === active ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-panel"}`}>{label}</Link>
        ))}
      </nav>
      {children}
    </section>
  );
}

/** 403 = not an operator. Anything else is said as it is (e.g. the API is still deploying), never as "not allowed". */
export function NotOperator({ status = 403, message = "" }: { status?: number; message?: string }) {
  const text = status === 403 ? "Dialogbots salg er kun for Dialogbot-operatører."
    : status === 404 ? "Salgskanalen findes ikke på serveren endnu – den er sandsynligvis ved at blive deployet. Prøv igen om et par minutter."
      : `Siden kunne ikke hentes (${status}${message ? `: ${message}` : ""}). Prøv igen om lidt.`;
  return <p className="bg-surface-container-lowest rounded-2xl p-space-lg border-2 border-ink font-body-md text-body-md text-on-surface-variant">{text}</p>;
}

export function ChannelOff({ message }: { message: string }) {
  return <p className="bg-highlight rounded-2xl p-space-md border-2 border-ink font-body-sm text-body-sm text-ink">{message} Se <Link className="underline" href="/app/operator/salg">Overblik</Link>.</p>;
}

type Loaded<T> = { ok: true; data: T } | { ok: false; status: number; message: string };

/** Fetch an operator endpoint; reports 403 (not operator) and 501 (channel off) separately. */
export async function load<T>(path: string): Promise<Loaded<T>> {
  await requireWorkspace();
  try { return { ok: true, data: await backend<T>(path) }; } catch (e) {
    const err = e as { status?: number; message?: string };
    return { ok: false, status: err.status ?? 500, message: err.message ?? "Kunne ikke hentes" };
  }
}

export const dt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Copenhagen" }) : "–");
export const kr = (minor: number) => `${(minor / 100).toLocaleString("da-DK", { maximumFractionDigits: 2 })} kr.`;

export * from "./labels";
