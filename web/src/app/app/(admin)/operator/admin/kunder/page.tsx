import Link from "next/link";
import { AdminFrame, NotOperator, dt, load } from "../shared";

type Row = { id: string; name: string; status: string; product_intent: string; created_at: string; owner_email: string | null; members: number; calls_30d: number; last_seen_at: string | null };

export default async function Customers({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = "" } = await searchParams;
  const data = await load<{ items: Row[] }>(`/operator/admin/customers?q=${encodeURIComponent(q)}`);
  if (!data) return <NotOperator />;
  return (
    <AdminFrame active="/app/operator/admin/kunder" title="Kunder" intro="Søg på firmanavn, navn eller e-mail. Åbn en kunde for medlemmer, fakturaer, opkald og alle rå data – og tryk &quot;Se som&quot; for at se præcis det kunden ser.">
      <form className="flex gap-2 max-w-xl" role="search">
        <input name="q" defaultValue={q} placeholder="Søg kunde, navn eller e-mail" aria-label="Søg" className="flex-1 min-h-[46px] px-3.5 rounded-xl bg-paper border-2 border-ink" />
        <button className="px-5 rounded-xl bg-ink text-paper font-semibold">Søg</button>
      </form>
      <div className="rounded-2xl bg-paper border-2 border-ink overflow-x-auto">
        <table className="w-full text-[14px]">
          <thead><tr className="text-left eyebrow"><th className="p-3">Kunde</th><th className="p-3">Ejer</th><th className="p-3">Medl.</th><th className="p-3">Opkald 30 d</th><th className="p-3">Sidst set</th><th className="p-3">Oprettet</th></tr></thead>
          <tbody>
            {data.items.map((c) => (
              <tr key={c.id} className="border-t border-line hover:bg-panel">
                <td className="p-3 font-semibold"><Link className="underline" href={`/app/operator/admin/kunder/${c.id}`}>{c.name}</Link>{c.status !== "active" && <span className="ml-2 text-danger">({c.status})</span>}</td>
                <td className="p-3">{c.owner_email ?? "–"}</td><td className="p-3 tabular-nums">{c.members}</td><td className="p-3 tabular-nums">{c.calls_30d}</td>
                <td className="p-3">{dt(c.last_seen_at)}</td><td className="p-3">{dt(c.created_at)}</td>
              </tr>
            ))}
            {data.items.length === 0 && <tr><td className="p-3 text-muted" colSpan={6}>Ingen kunder matcher.</td></tr>}
          </tbody>
        </table>
      </div>
    </AdminFrame>
  );
}
