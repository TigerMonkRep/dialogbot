import Link from "next/link";
import { Alert } from "@/components/ui";
import { NotOperator, SalgFrame, load, type Status } from "./shared";

type Overview = Status & {
  tiles: Record<string, number>; definitions: Record<string, string>;
  needs_you: { kind: string; id: string; text: string }[]; not_built: string[];
};

const TILES: [string, string][] = [
  ["companies_new_30d", "Nye virksomheder (30 dage)"], ["companies_total", "Virksomheder i alt"], ["researched", "Undersøgt"],
  ["scripts_approved", "Godkendte manuskripter"], ["simulations_30d", "Simulationer (30 dage)"], ["searches_running", "Søgninger i gang"],
  ["calls_today", "Opkald i dag"],
];
const MODE: Record<string, string> = {
  off: "Slået fra", research: "Research", simulation: "Simulation", test: "Test (kun testnumre)", live: "Live",
};

export default async function SalesOverview() {
  const r = await load<Overview>("/operator/salg");
  if (!r.ok) return <NotOperator status={r.status} message={r.message} />;
  const o = r.data;
  return (
    <SalgFrame active="/app/operator/salg" title="Dialogbots salg" intro="Find virksomheder, undersøg deres egen hjemmeside, byg en profil og et personligt manuskript til Peter, prøv samtalen som simulation – og lad Peter ringe, når kontaktpolitikken tillader det (testopkald til dine egne testnumre, eller kampagner med dokumenteret kontaktgrundlag).">
      <div className="grid md:grid-cols-3 gap-space-md">
        <div className="rounded-2xl border-2 border-ink bg-paper p-space-md"><span className="eyebrow">Tilstand</span><p className="font-display font-bold text-[22px]">{MODE[o.mode] ?? o.mode}</p><p className="text-[13px] text-muted">SALES_OUTBOUND_MODE – ændres i miljøet, ikke her.</p></div>
        <div className="rounded-2xl border-2 border-ink bg-paper p-space-md"><span className="eyebrow">Virksomhedssøgning</span><p className="font-display font-bold text-[22px]">{o.places === "google" ? "Google Places" : "Demo-data"}</p><p className="text-[13px] text-muted">{o.places === "google" ? `Højst ${o.limits.search_daily_request_cap} forespørgsler pr. dag.` : "Fiktive virksomheder – ingen rigtige data."}</p></div>
        <div className="rounded-2xl border-2 border-ink bg-paper p-space-md"><span className="eyebrow">Salgsarbejdsrum</span><p className="font-display font-bold text-[22px]">{o.sales_workspace?.name ?? "Ikke sat"}</p><p className="text-[13px] text-muted">CVR-opslag: {o.cvr_configured ? "sat op" : "ikke sat op (reklamebeskyttelse ukendt)"}</p></div>
      </div>
      {o.missing.length > 0 && <Alert kind="warn"><p className="font-semibold">Mangler</p><ul className="list-disc pl-5">{o.missing.map((m) => <li key={m}>{m}</li>)}</ul></Alert>}
      <ul className="grid grid-cols-2 md:grid-cols-3 gap-space-md">
        {TILES.map(([k, label]) => (
          <li key={k} title={o.definitions[k]} className="rounded-2xl border-2 border-ink bg-surface-container-lowest p-space-md">
            <span className="block text-[13px] text-muted">{label}</span>
            <span className="font-display font-extrabold text-[30px] tabular-nums">{o.tiles[k] ?? 0}</span>
            <span className="block text-[12px] text-muted mt-1">{o.definitions[k]}</span>
          </li>
        ))}
      </ul>
      <div className="rounded-2xl border-2 border-ink bg-paper p-space-md">
        <h2 className="font-display font-bold text-[20px] mb-2">Kræver dig</h2>
        {o.needs_you.length === 0 ? <p className="text-muted text-[14px]">Intet lige nu.</p> : (
          <ul className="flex flex-col gap-2">{o.needs_you.map((n, i) => (
            <li key={i} className="text-[14px]">
              {n.kind.startsWith("search") ? <Link className="underline" href="/app/operator/salg/find">{n.text}</Link>
                : n.kind.startsWith("call") ? <Link className="underline" href={`/app/operator/salg/opkald/${n.id}`}>{n.text}</Link>
                : <Link className="underline" href={`/app/operator/salg/virksomheder/${n.id}`}>{n.text}</Link>}
            </li>))}</ul>
        )}
      </div>
      <p className="text-[13px] text-muted">Ikke bygget endnu (senere faser): {o.not_built.join(", ")}. Demo-opkald fra hjemmesiden findes under fanen Demo-opkald.</p>
    </SalgFrame>
  );
}
