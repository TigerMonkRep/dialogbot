import Link from "next/link";
import { Tag } from "@/components/ui";
import { ChannelOff, ISSUE, NotOperator, RESEARCH, SOURCE, SalgFrame, dt, load, type Company } from "../shared";

type Page = { items: Company[]; total: number; limit: number; offset: number };
const FILTERS = ["q", "industry", "postal", "research_status", "source", "quality", "sort", "search_job", "offset"] as const;

export default async function CompaniesPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const qs = new URLSearchParams();
  for (const k of FILTERS) if (sp[k]) qs.set(k, sp[k] as string);
  qs.set("limit", "50");
  const [r, ind] = await Promise.all([
    load<Page>(`/operator/salg/companies?${qs}`),
    load<{ items: { key: string; label: string }[] }>("/operator/salg/industries"),
  ]);
  if (!r.ok) {
    if (r.status === 501) return <SalgFrame active="/app/operator/salg/virksomheder" title="Virksomheder"><ChannelOff message={r.message} /></SalgFrame>;
    return <NotOperator status={r.status} message={r.message} />;
  }
  const { items, total, offset } = r.data;
  const next = new URLSearchParams(qs); next.set("offset", String(offset + 50));
  const prev = new URLSearchParams(qs); prev.set("offset", String(Math.max(0, offset - 50)));
  return (
    <SalgFrame active="/app/operator/salg/virksomheder" title="Virksomheder" intro="&quot;Fundet&quot; og &quot;må ringes op&quot; er to forskellige ting. Kontaktpolitikken (fase 2) afgør, hvem der må ringes til; indtil da står ingen som tilladt.">
      <form className="grid grid-cols-2 md:grid-cols-6 gap-2 items-end" method="get">
        <label className="col-span-2 text-[13px]">Søg<input name="q" defaultValue={sp.q ?? ""} placeholder="Navn, by, domæne eller CVR" className="w-full min-h-[42px] px-3 rounded-xl border-2 border-ink bg-paper" /></label>
        <label className="text-[13px]">Branche<select name="industry" defaultValue={sp.industry ?? ""} className="w-full min-h-[42px] px-2 rounded-xl border-2 border-ink bg-paper"><option value="">Alle</option>{ind.ok && ind.data.items.map((i) => <option key={i.key} value={i.key}>{i.label}</option>)}</select></label>
        <label className="text-[13px]">Postnr.<input name="postal" defaultValue={sp.postal ?? ""} className="w-full min-h-[42px] px-3 rounded-xl border-2 border-ink bg-paper" /></label>
        <label className="text-[13px]">Status<select name="research_status" defaultValue={sp.research_status ?? ""} className="w-full min-h-[42px] px-2 rounded-xl border-2 border-ink bg-paper"><option value="">Alle</option>{Object.entries(RESEARCH).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="text-[13px]">Datakvalitet<select name="quality" defaultValue={sp.quality ?? ""} className="w-full min-h-[42px] px-2 rounded-xl border-2 border-ink bg-paper"><option value="">Alle</option><option value="issues">Med mangler</option><option value="duplicates">Mulige dubletter</option></select></label>
        <label className="text-[13px]">Kilde<select name="source" defaultValue={sp.source ?? ""} className="w-full min-h-[42px] px-2 rounded-xl border-2 border-ink bg-paper"><option value="">Alle</option>{Object.entries(SOURCE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="text-[13px]">Sortér<select name="sort" defaultValue={sp.sort ?? "newest"} className="w-full min-h-[42px] px-2 rounded-xl border-2 border-ink bg-paper"><option value="newest">Nyeste</option><option value="name">Navn</option><option value="relevance">Relevans</option><option value="updated">Senest ændret</option></select></label>
        {sp.search_job && <input type="hidden" name="search_job" value={sp.search_job} />}
        <button className="min-h-[42px] px-4 rounded-xl bg-ink text-paper font-semibold">Vis</button>
      </form>
      <p className="text-[13px] text-muted">{total} virksomheder{sp.search_job ? " fra den valgte søgning" : ""}.</p>
      {items.length === 0 ? <p className="text-muted">Ingen virksomheder. <Link className="underline" href="/app/operator/salg/find">Find virksomheder</Link>.</p> : (
        <>
          <ul className="md:hidden flex flex-col gap-2">{items.map((c) => (
            <li key={c.id} className="rounded-xl border-2 border-ink bg-paper p-3">
              <Link href={`/app/operator/salg/virksomheder/${c.id}`} className="font-semibold underline">{c.display_name}</Link>
              <p className="text-[13px] text-muted">{[c.postal_code, c.city].filter(Boolean).join(" ")} · {c.industry_text ?? "ukendt branche"} · {SOURCE[c.source]}</p>
              <p className="text-[13px]">Fundet: {RESEARCH[c.research_status]} · Må ringes op: {c.contactable.result === "BLOCK" ? `nej (${c.contactable.reasons.join(", ")})` : "ikke afgjort"}</p>
            </li>))}</ul>
          <div className="hidden md:block overflow-x-auto rounded-2xl border-2 border-ink bg-paper">
            <table className="w-full text-[14px]">
              <thead className="text-left text-muted"><tr><th className="p-2">Virksomhed</th><th className="p-2">Område</th><th className="p-2">Branche</th><th className="p-2">Fundet</th><th className="p-2">Må ringes op</th><th className="p-2">Datakvalitet</th><th className="p-2">Kilde</th><th className="p-2">Først set</th></tr></thead>
              <tbody>{items.map((c) => (
                <tr key={c.id} className="border-t border-line align-top">
                  <td className="p-2"><Link href={`/app/operator/salg/virksomheder/${c.id}`} className="font-semibold underline">{c.display_name}</Link>{c.duplicate_reason && <span className="block text-[12px] text-danger">{c.duplicate_reason}</span>}{c.existing_customer && <span className="block text-[12px]">Eksisterende kunde</span>}</td>
                  <td className="p-2">{[c.postal_code, c.city].filter(Boolean).join(" ") || "–"}</td>
                  <td className="p-2">{c.industry_text ?? "–"}</td>
                  <td className="p-2">{RESEARCH[c.research_status]}</td>
                  <td className="p-2">{c.contactable.result === "BLOCK" ? <span className="text-danger">Nej: {c.contactable.reasons.join(", ")}</span> : <span className="text-muted">Ikke afgjort (fase 2)</span>}</td>
                  <td className="p-2">{(c.data_quality.issues ?? []).length === 0 ? "OK" : (c.data_quality.issues ?? []).map((i) => <Tag key={i}>{ISSUE[i] ?? i}</Tag>)}</td>
                  <td className="p-2">{SOURCE[c.source]}</td>
                  <td className="p-2 whitespace-nowrap tabular-nums">{dt(c.first_seen_at)}</td>
                </tr>))}</tbody>
            </table>
          </div>
          <div className="flex gap-3 text-[14px]">
            {offset > 0 && <Link className="underline" href={`?${prev}`}>← Forrige</Link>}
            {offset + 50 < total && <Link className="underline" href={`?${next}`}>Næste →</Link>}
          </div>
        </>
      )}
    </SalgFrame>
  );
}
