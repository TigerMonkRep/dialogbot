"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, Select, Tag, Textarea, useSubmit } from "@/components/ui";

export type Industry = { key: string; label: string; google_types: string[]; search_terms: string[]; active: boolean; source: string };
export type Job = {
  id: string; industry_keys: string[]; google_types: string[]; keywords: string[]; geo_kind: string; geo: Record<string, unknown>;
  max_results: number; source: "google" | "demo" | "import"; status: string; error: string | null; steps: number; cursor: number;
  progress: { examined?: number; found?: number; skipped?: number; incomplete?: number; duplicates?: number; requests_used?: number; details_used?: number; estimated_cost_minor?: number; reasons?: Record<string, number> };
  budget: { estimate?: { search_requests_max: number; details_requests_max: number; cost_minor_max: number; price_note: string } };
  created_at: string | null; finished_at: string | null; dry_run?: boolean;
};

const STATUS: Record<string, string> = { queued: "I kø", running: "Kører", paused: "På pause", done: "Færdig", failed: "Fejlet", cancelled: "Stoppet" };
const REASON: Record<string, string> = { already_known: "kendt i forvejen", not_relevant: "ikke relevant", existing_customer: "eksisterende kunde", missing_name: "mangler navn" };
const SOURCE: Record<string, string> = { google: "Google", demo: "Demo-data", import: "Importeret" };
const kr = (minor = 0) => `${(minor / 100).toLocaleString("da-DK", { maximumFractionDigits: 2 })} kr.`;
const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export function FindCompanies({ industries, googleTypes, jobs, requestsToday }: { industries: Industry[]; googleTypes: { type: string; term: string }[]; jobs: Job[]; requestsToday: number }) {
  const router = useRouter();
  const [keys, setKeys] = useState<string[]>([]);
  const [types, setTypes] = useState("");
  const [keywords, setKeywords] = useState("");
  const [geoKind, setGeoKind] = useState<"place" | "postal_codes" | "radius">("place");
  const [place, setPlace] = useState("Aarhus C");
  const [postal, setPostal] = useState("");
  const [radius, setRadius] = useState({ lat: "56.1535", lng: "10.2034", km: "5" });
  const [max, setMax] = useState(20);
  const [exclude, setExclude] = useState(true);
  const [preview, setPreview] = useState<Job | null>(null);
  const [csv, setCsv] = useState("");

  const body = () => ({
    industry_keys: keys, google_types: split(types), keywords: split(keywords), geo_kind: geoKind, max_results: max,
    exclude_existing_customers: exclude,
    geo: geoKind === "place" ? { text: place } : geoKind === "postal_codes" ? { postal_codes: split(postal) } : { lat: Number(radius.lat), lng: Number(radius.lng), km: Number(radius.km) },
  });
  const estimate = useSubmit(async () => setPreview(await api<Job>("/operator/salg/search-jobs?dry_run=true", { method: "POST", body: JSON.stringify(body()) })));
  const start = useSubmit(async () => { await api<Job>("/operator/salg/search-jobs", { method: "POST", body: JSON.stringify(body()) }); setPreview(null); router.refresh(); });
  const act = useSubmit(async (id: string, what: "cancel" | "resume") => { await api(`/operator/salg/search-jobs/${id}/${what}`, { method: "POST" }); router.refresh(); });
  const imp = useSubmit(async () => { await api("/operator/salg/companies/import", { method: "POST", body: JSON.stringify({ csv, industry_key: keys[0] ?? null }) }); setCsv(""); router.refresh(); });

  const running = jobs.some((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => router.refresh(), 5000);
    return () => clearInterval(t);
  }, [running, router]);

  return (
    <div className="grid lg:grid-cols-[minmax(0,30rem)_1fr] gap-space-lg items-start">
      <div className="flex flex-col gap-space-md">
        <form className="rounded-2xl bg-surface-container-lowest border-2 border-ink p-space-md flex flex-col gap-space-sm" onSubmit={(e) => { e.preventDefault(); estimate.run(); }}>
          <fieldset className="flex flex-col gap-1">
            <legend className="font-semibold text-[14px] mb-1">Branche</legend>
            {industries.filter((i) => i.active).map((i) => (
              <label key={i.key} className="flex items-start gap-2 text-[14px]">
                <input type="checkbox" className="mt-1 w-4 h-4 accent-primary" checked={keys.includes(i.key)} onChange={(e) => setKeys(e.target.checked ? [...keys, i.key] : keys.filter((k) => k !== i.key))} />
                <span>{i.label}<span className="block text-[12px] text-muted">Google-typer: {i.google_types.join(", ") || "–"}</span></span>
              </label>
            ))}
          </fieldset>
          <Field label="Egne Google-typer (valgfri, kommasepareret)" hint={`Fx ${googleTypes.slice(0, 4).map((g) => g.type).join(", ")}`}><Input value={types} onChange={(e) => setTypes(e.target.value)} /></Field>
          <Field label="Søgeord (valgfri, kommasepareret)" hint="Fritekst, fx VVS"><Input value={keywords} onChange={(e) => setKeywords(e.target.value)} /></Field>
          <Field label="Område">
            <Select value={geoKind} onChange={(e) => setGeoKind(e.target.value as typeof geoKind)}>
              <option value="place">By eller bydel</option><option value="postal_codes">Postnumre</option><option value="radius">Radius</option>
            </Select>
          </Field>
          {geoKind === "place" && <Field label="By eller bydel" error={fieldError(estimate.error ?? start.error, "geo.text")}><Input value={place} onChange={(e) => setPlace(e.target.value)} placeholder="Aarhus C" /></Field>}
          {geoKind === "postal_codes" && <Field label="Postnumre (kommasepareret)" error={fieldError(estimate.error ?? start.error, "geo.postal_codes")}><Input value={postal} onChange={(e) => setPostal(e.target.value)} placeholder="8000, 8200" /></Field>}
          {geoKind === "radius" && (
            <div className="grid grid-cols-3 gap-2">
              <Field label="Bredde"><Input value={radius.lat} onChange={(e) => setRadius({ ...radius, lat: e.target.value })} /></Field>
              <Field label="Længde"><Input value={radius.lng} onChange={(e) => setRadius({ ...radius, lng: e.target.value })} /></Field>
              <Field label="Km (≤ 50)" error={fieldError(estimate.error ?? start.error, "geo.km")}><Input value={radius.km} onChange={(e) => setRadius({ ...radius, km: e.target.value })} /></Field>
            </div>
          )}
          <Field label="Højst antal virksomheder" error={fieldError(estimate.error ?? start.error, "max_results")}><Input type="number" min={1} value={max} onChange={(e) => setMax(Number(e.target.value))} /></Field>
          <label className="flex items-center gap-2 text-[14px]"><input type="checkbox" className="w-4 h-4 accent-primary" checked={exclude} onChange={(e) => setExclude(e.target.checked)} />Spring eksisterende kunder over</label>
          <ErrorBox error={estimate.error ?? start.error} />
          {preview && (
            <Alert kind="info">
              <p className="font-semibold">Overslag ({SOURCE[preview.source]})</p>
              <p>{preview.steps} søgninger (områder × typer), højst {preview.budget.estimate?.search_requests_max} søgeforespørgsler og {preview.budget.estimate?.details_requests_max} detaljeopslag – højst ca. {kr(preview.budget.estimate?.cost_minor_max)}.</p>
              <p className="text-[12px] mt-1">{preview.source === "demo" ? "Demo-data koster intet." : preview.budget.estimate?.price_note} I dag er der brugt {requestsToday} forespørgsler.</p>
            </Alert>
          )}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="secondary" disabled={estimate.pending}>Beregn forbrug</Button>
            <Button type="button" icon="search" disabled={!preview || start.pending} onClick={() => start.run()}>{start.pending ? "Starter…" : "Start søgning"}</Button>
          </div>
        </form>
        <details className="rounded-2xl border-2 border-ink bg-paper">
          <summary className="cursor-pointer px-space-md py-3 font-semibold">Importér egen liste (CSV)</summary>
          <form className="p-space-md flex flex-col gap-space-sm" onSubmit={(e) => { e.preventDefault(); imp.run(); }}>
            <Field label="CSV med kolonnerne navn, cvr, hjemmeside, telefon, e-mail, postnr" hint="Mærkes som importeret. Branche = den første valgte ovenfor."><Textarea value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={"navn;cvr;hjemmeside;telefon;e-mail;postnr"} /></Field>
            <ErrorBox error={imp.error} />
            <Button type="submit" variant="secondary" disabled={!csv.trim() || imp.pending}>Importér</Button>
          </form>
        </details>
      </div>

      <div className="rounded-2xl bg-surface-container-lowest border-2 border-ink p-space-md flex flex-col gap-space-sm min-w-0">
        <h2 className="font-display font-bold text-[20px]">Søgninger</h2>
        {jobs.length === 0 ? <p className="text-muted text-[14px]">Ingen endnu.</p> : (
          <ul className="flex flex-col gap-3">{jobs.map((j) => {
            const p = j.progress;
            const reasons = Object.entries(p.reasons ?? {}).map(([k, n]) => `${n} ${REASON[k] ?? k}`).join(", ");
            return (
              <li key={j.id} className="rounded-xl border-[1.5px] border-ink bg-paper p-3 text-[14px]">
                <div className="flex flex-wrap items-center gap-2 justify-between">
                  <span className="font-semibold">{[...j.industry_keys, ...j.google_types, ...j.keywords].join(", ") || "Import"} · {j.geo_kind === "place" ? String(j.geo.text ?? "") : j.geo_kind === "postal_codes" ? ((j.geo.postal_codes as string[]) ?? []).join(", ") : j.geo_kind === "radius" ? `${j.geo.km} km` : ""}</span>
                  <Tag tone={j.status === "done" ? "tertiary" : j.status === "paused" || j.status === "failed" ? "secondary" : "neutral"}>{STATUS[j.status] ?? j.status}</Tag>
                </div>
                <p className="text-muted">{SOURCE[j.source]} · fundet {p.found ?? 0} af højst {j.max_results} · undersøgt {p.examined ?? 0} · sprunget over {p.skipped ?? 0}{reasons ? ` (${reasons})` : ""} · ufuldstændige {p.incomplete ?? 0} · mulige dubletter {p.duplicates ?? 0}</p>
                {j.source !== "import" && <p className="text-muted">Trin {j.cursor}/{j.steps} · {p.requests_used ?? 0} søgeforespørgsler + {p.details_used ?? 0} detaljeopslag · ca. {kr(p.estimated_cost_minor)}{j.source === "demo" ? " (demo: gratis)" : ""}</p>}
                {j.error && <p className="text-danger">{j.error}</p>}
                <div className="flex flex-wrap gap-2 mt-2">
                  <Link className="underline" href={`/app/operator/salg/virksomheder?search_job=${j.id}`}>Se virksomheder</Link>
                  {(j.status === "queued" || j.status === "running") && <Button variant="secondary" onClick={() => act.run(j.id, "cancel")}>Stop</Button>}
                  {(j.status === "paused" || j.status === "failed") && <Button variant="secondary" onClick={() => act.run(j.id, "resume")}>Genoptag</Button>}
                </div>
              </li>
            );
          })}</ul>
        )}
        <ErrorBox error={act.error} />
      </div>
    </div>
  );
}
