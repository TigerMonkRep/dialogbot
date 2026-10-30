"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { Alert, Badge, Button, ErrorBox, Field, Input, Tag, useSubmit } from "@/components/ui";
import { type Company, ISSUE, RESEARCH, SOURCE } from "../../labels";
import { type ContactRow, ContactsPanel } from "./contacts";

type Fact = { id: string; field: string; value: string; url_or_ref: string; source: string; fetched_at: string; evidence: string; confidence: string };
type Contact = ContactRow;
type Profile = { id: string; version: number; facts: { field: string; text: string; source: string }[]; hypotheses: { question: string }[]; relevant_service: string; why_relevant: string; created_at: string };
type Script = { id: string; version: number; script_version: string; status: string; rendered_prompt: string; validation: { ok: boolean; errors: string[]; warnings: string[] }; body: Record<string, unknown>; created_at: string; approved_at: string | null };
type Sim = { id: string; script_id: string; persona: string; transcript: { speaker: string; text: string }[]; outcome: string | null; partial_accepts: { no: number; result: string; quote: string | null }[]; would_call: { tool: string; input: unknown }[]; error: string | null; simulated: boolean; created_at: string };
export type Detail = Company & { facts: Fact[]; contacts: Contact[]; profiles: Profile[]; scripts: Script[]; simulations: Sim[]; timeline: { at: string; kind: string; text: string }[]; quality_text: string[]; research_started_at: string | null };

const FIELD: Record<string, string> = {
  name: "Navn", address: "Adresse", google_types: "Google-typer", business_status: "Driftsstatus", website: "Hjemmeside",
  phone_e164: "Telefon", opening_hours: "Åbningstider", service: "Ydelse", customer_type: "Kundetype", service_area: "Område",
  booking_system: "Bookingsystem", contact_role: "Rolle", email: "E-mail", cvr: "CVR", legal_name: "Juridisk navn",
  cvr_status: "CVR-status", advertising_protected: "Reklamebeskyttet", postal_code: "Postnummer",
};
const OUTCOME: Record<string, string> = { interested: "Interesseret", meeting: "Vil have møde", order_interest: "Vil bestille", callback: "Ring tilbage", not_interested: "Ikke interesseret", opt_out: "Frabad sig kontakt", unclear: "Uafklaret" };
const ACCEPT = ["", "Problemet forstået", "Gør en forskel", "Rette form for hjælp", "Integration passer", "Prisen giver mening"];
const dt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Copenhagen" }) : "–");

function Box({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="rounded-2xl border-2 border-ink bg-paper p-space-md flex flex-col gap-2 min-w-0"><h2 className="font-display font-bold text-[18px]">{title}</h2>{children}</section>;
}

export function CompanyDetail({ c, canSimulate, mode }: { c: Detail; canSimulate: boolean; mode: string }) {
  const router = useRouter();
  const [persona, setPersona] = useState("Ejer, travl, har onlinebooking");
  const [researching, setResearching] = useState(Boolean(c.research_started_at));
  const run = useSubmit(async (path: string, body?: unknown) => { await api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }); router.refresh(); });
  const research = useSubmit(async () => { await api(`/operator/salg/companies/${c.id}/research`, { method: "POST" }); setResearching(true); });
  useEffect(() => {
    if (!researching) return;
    const t = setInterval(() => router.refresh(), 3000);
    const stop = setTimeout(() => setResearching(false), 120_000);
    return () => { clearInterval(t); clearTimeout(stop); };
  }, [researching, router]);
  useEffect(() => { if (!c.research_started_at) setResearching(false); }, [c.research_started_at]);

  const latestScript = c.scripts[0];
  const approved = c.scripts.find((s) => s.status === "approved");
  return (
    <div className="flex flex-col gap-space-md">
      <div className="flex flex-wrap gap-2 items-center text-[14px]">
        <Tag>{SOURCE[c.source]}</Tag><Tag tone="tertiary">{RESEARCH[c.research_status]}</Tag>
        {c.industry_text && <Tag>{c.industry_text}</Tag>}
        {c.existing_customer && <Tag tone="secondary">Eksisterende kunde</Tag>}
        {c.duplicate_reason && <Tag tone="secondary">{c.duplicate_reason}</Tag>}
        <span className="text-muted">Må ringes op: {c.contactable.result === "BLOCK" ? `nej – ${c.contactable.reasons.join(", ")}` : "ikke afgjort (kontaktpolitik kommer i fase 2)"}</span>
      </div>
      {c.source === "demo" && <Alert kind="info">Demo-data: virksomheden er fiktiv.</Alert>}
      <div className="flex flex-wrap gap-2">
        <Button icon="travel_explore" disabled={!c.website_url || researching || research.pending} onClick={() => research.run()}>{researching ? "Undersøger hjemmesiden…" : "Undersøg hjemmeside"}</Button>
        <Button variant="secondary" disabled={run.pending} onClick={() => run.run(`/operator/salg/companies/${c.id}/profile`)}>Byg profil</Button>
        <Button variant="secondary" disabled={run.pending || c.profiles.length === 0} onClick={() => run.run(`/operator/salg/companies/${c.id}/scripts`, {})}>Lav manuskript</Button>
      </div>
      <ErrorBox error={research.error ?? run.error} />
      {c.research_error && <Alert kind="warn">Research: {c.research_error}</Alert>}

      <div className="grid gap-space-md">
        <Box title="Stamdata">
          <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1 text-[14px]">
            <dt className="text-muted">Adresse</dt><dd>{[c.address_line, c.postal_code, c.city].filter(Boolean).join(", ") || "ikke fundet"}</dd>
            <dt className="text-muted">Hjemmeside</dt><dd className="break-all">{c.website_url ?? "ikke fundet"}</dd>
            <dt className="text-muted">Hovednummer</dt><dd>{c.main_phone_e164 ?? "ikke fundet"}</dd>
            <dt className="text-muted">CVR</dt><dd>{c.cvr ?? "ikke fundet"}{c.legal_name ? ` · ${c.legal_name}` : ""}</dd>
            <dt className="text-muted">Reklamebeskyttet</dt><dd>{c.advertising_protected === null ? "ukendt" : c.advertising_protected ? "ja – må ikke kontaktes" : "nej"}</dd>
            <dt className="text-muted">Google</dt><dd>{c.google.business_status ?? "–"}{c.google.rating ? ` · ${c.google.rating} (${c.google.user_rating_count})` : ""} · hentet {dt(c.google.fetched_at)}{c.google.maps_uri && <> · <a className="underline" href={c.google.maps_uri} target="_blank" rel="noreferrer">Kort (Google)</a></>}</dd>
            <dt className="text-muted">Datakvalitet</dt><dd>{(c.data_quality.issues ?? []).length ? (c.data_quality.issues ?? []).map((i) => ISSUE[i] ?? i).join(", ") : "OK"}</dd>
          </dl>
        </Box>
      </div>

      <ContactsPanel companyId={c.id} contacts={c.contacts} approvedScriptId={approved?.id ?? null} mode={mode} advertisingProtected={c.advertising_protected} />

      <Box title={`Fakta og kilder (${c.facts.length})`}>
        {c.facts.length === 0 ? <p className="text-muted text-[14px]">Ingen endnu.</p> : (
          <div className="overflow-x-auto"><table className="w-full text-[13px]">
            <thead className="text-left text-muted"><tr><th className="pr-2">Felt</th><th className="pr-2">Værdi</th><th className="pr-2">Kilde</th><th className="pr-2">Uddrag</th><th className="pr-2">Sikkerhed</th><th>Hentet</th></tr></thead>
            <tbody>{c.facts.map((f) => (
              <tr key={f.id} className="border-t border-line align-top">
                <td className="pr-2 py-1">{FIELD[f.field] ?? f.field}</td><td className="pr-2 py-1">{f.value}</td>
                <td className="pr-2 py-1 break-all">{f.source === "google" ? "Google" : f.source === "website" ? <a className="underline" href={f.url_or_ref} target="_blank" rel="noreferrer">{f.url_or_ref}</a> : f.url_or_ref}</td>
                <td className="pr-2 py-1 text-muted">{f.evidence || "–"}</td><td className="pr-2 py-1">{f.confidence}</td><td className="py-1 whitespace-nowrap">{dt(f.fetched_at)}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </Box>

      <Box title="Profil">
        {c.profiles.length === 0 ? <p className="text-muted text-[14px]">Ingen profil endnu. Tryk &quot;Byg profil&quot;.</p> : (() => {
          const p = c.profiles[0];
          return (
            <div className="text-[14px] flex flex-col gap-1">
              <p className="text-muted">Version {p.version} · {dt(p.created_at)}</p>
              <p><span className="font-semibold">Fakta Peter må konstatere:</span></p>
              <ul className="list-disc pl-5">{p.facts.length ? p.facts.map((f, i) => <li key={i}>{f.text} <span className="text-muted">({f.source})</span></li>) : <li className="text-muted">ingen</li>}</ul>
              <p><span className="font-semibold">Hypoteser (kun som spørgsmål):</span></p>
              <ul className="list-disc pl-5">{p.hypotheses.map((h, i) => <li key={i}>{h.question}</li>)}</ul>
              <p><span className="font-semibold">Relevant ydelse:</span> {p.relevant_service}</p>
              <p className="text-muted">{p.why_relevant}</p>
            </div>
          );
        })()}
      </Box>

      <Box title="Manuskript til Peter">
        {!latestScript ? <p className="text-muted text-[14px]">Intet manuskript endnu.</p> : (
          <div className="flex flex-col gap-2 text-[14px]">
            {c.scripts.map((s) => (
              <details key={s.id} open={s.id === latestScript.id} className="rounded-xl border-[1.5px] border-ink p-2">
                <summary className="cursor-pointer flex flex-wrap items-center gap-2"><span className="font-semibold">v{s.version} · {s.script_version}</span><Badge status={s.status} /><span className="text-muted">{dt(s.created_at)}</span></summary>
                {s.validation.errors.length > 0 && <Alert kind="error"><ul className="list-disc pl-5">{s.validation.errors.map((e) => <li key={e}>{e}</li>)}</ul></Alert>}
                {s.validation.warnings.length > 0 && <Alert kind="warn"><ul className="list-disc pl-5">{s.validation.warnings.map((e) => <li key={e}>{e}</li>)}</ul></Alert>}
                <pre className="whitespace-pre-wrap text-[13px] bg-panel rounded-xl p-3 mt-2 max-h-96 overflow-y-auto">{s.rendered_prompt}</pre>
                {s.status === "draft" && <Button className="mt-2" disabled={!s.validation.ok || run.pending} onClick={() => run.run(`/operator/salg/scripts/${s.id}/approve`)}>Godkend manuskript</Button>}
              </details>
            ))}
          </div>
        )}
      </Box>

      <Box title="Simulation (intet opkald)">
        {!canSimulate ? <p className="text-muted text-[14px]">Simulation kræver SALES_OUTBOUND_MODE=simulation (eller test/live).</p> : (
          <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); run.run(`/operator/salg/companies/${c.id}/simulate`, { script_id: (approved ?? latestScript)?.id, persona }); }}>
            <Field label="Kundepersona" hint="Kort beskrivelse af den fiktive kunde, Peter taler med."><Input value={persona} onChange={(e) => setPersona(e.target.value)} maxLength={500} /></Field>
            <Button type="submit" variant="secondary" disabled={!latestScript || run.pending}>{run.pending ? "Simulerer…" : `Simulér samtale (${approved ? "godkendt" : "seneste"} manuskript)`}</Button>
          </form>
        )}
        {c.simulations.map((s) => (
          <details key={s.id} className="rounded-xl border-[1.5px] border-ink p-2 text-[14px]">
            <summary className="cursor-pointer"><Tag tone="secondary">Simuleret</Tag> {dt(s.created_at)} · {OUTCOME[s.outcome ?? "unclear"] ?? s.outcome} · {s.persona}</summary>
            {s.error && <Alert kind="error">{s.error}</Alert>}
            <ol className="flex flex-col gap-1 mt-2">{s.transcript.map((t, i) => <li key={i} className={t.speaker === "peter" ? "" : "pl-6"}><span className="font-semibold">{t.speaker === "peter" ? "Peter" : "Kunde"}:</span> {t.text}</li>)}</ol>
            <p className="font-semibold mt-2">Delaccepter</p>
            <ul>{s.partial_accepts.map((a) => <li key={a.no}>{a.no}. {ACCEPT[a.no]}: {a.result}{a.quote ? ` – "${a.quote}"` : ""}</li>)}</ul>
            {s.would_call.length > 0 && <p className="text-muted mt-1">Ville have kaldt (ikke udført): {s.would_call.map((w) => w.tool).join(", ")}</p>}
          </details>
        ))}
      </Box>

      <Box title="Tidslinje">
        <ul className="text-[14px]">{c.timeline.map((e, i) => <li key={i}><span className="tabular-nums text-muted">{dt(e.at)}</span> · {e.text}</li>)}</ul>
      </Box>
      <details className="rounded-2xl border-2 border-ink bg-paper"><summary className="cursor-pointer px-space-md py-3 font-semibold">Vis alle detaljer (avanceret)</summary><pre className="overflow-x-auto p-space-md text-[12px] bg-panel">{JSON.stringify(c, null, 2)}</pre></details>
    </div>
  );
}
