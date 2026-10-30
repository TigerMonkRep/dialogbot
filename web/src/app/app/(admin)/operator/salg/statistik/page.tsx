import { ChannelOff, NotOperator, SalgFrame, kr, load } from "../shared";

type Metric = { key: string; label: string; value: number | null; numerator: number; denominator: number | null; unit: string; definition: string };
type Stats = { from: string; to: string; excluded: string; metrics: Metric[] };

function show(m: Metric): string {
  if (m.denominator !== null && m.key !== "cost_per_customer") return m.value === null ? "–" : `${Math.round(m.value * 1000) / 10} %`;
  if (m.value === null) return "–";
  if (m.unit === "minor") return kr(m.value);
  if (m.unit === "usd_micros") return `$${(m.value / 1_000_000).toLocaleString("da-DK", { maximumFractionDigits: 2 })}`;
  return m.value.toLocaleString("da-DK");
}

export default async function StatsPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const qs = new URLSearchParams();
  for (const k of ["from", "to"]) if (sp[k]) qs.set(k, sp[k] as string);
  const r = await load<Stats>(`/operator/salg/stats?${qs}`);
  if (!r.ok) {
    if (r.status === 501) return <SalgFrame active="/app/operator/salg/statistik" title="Statistik"><ChannelOff message={r.message} /></SalgFrame>;
    return <NotOperator status={r.status} message={r.message} />;
  }
  const s = r.data;
  return (
    <SalgFrame active="/app/operator/salg/statistik" title="Statistik" intro={`Periode ${s.from} til ${s.to}. ${s.excluded} Hver tal viser tæller og nævner, så du kan se, hvad det bygger på.`}>
      <form method="get" className="flex flex-wrap gap-2 items-end">
        <label className="text-[13px]">Fra<input type="date" name="from" defaultValue={s.from} className="block min-h-[42px] px-3 rounded-xl border-2 border-ink bg-paper" /></label>
        <label className="text-[13px]">Til<input type="date" name="to" defaultValue={s.to} className="block min-h-[42px] px-3 rounded-xl border-2 border-ink bg-paper" /></label>
        <button className="min-h-[42px] px-4 rounded-xl bg-ink text-paper font-semibold">Vis</button>
      </form>
      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-space-md">
        {s.metrics.map((m) => (
          <li key={m.key} className="rounded-2xl border-2 border-ink bg-surface-container-lowest p-space-md">
            <span className="block text-[13px] text-muted">{m.label}</span>
            <span className="font-display font-extrabold text-[28px] tabular-nums">{show(m)}</span>
            {m.denominator !== null && <span className="block text-[13px] tabular-nums">{m.numerator.toLocaleString("da-DK")} af {m.denominator.toLocaleString("da-DK")}</span>}
            <span className="block text-[12px] text-muted mt-1">{m.definition}</span>
          </li>
        ))}
      </ul>
    </SalgFrame>
  );
}
