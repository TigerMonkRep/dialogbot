"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, useSubmit } from "@/components/ui";

type Num = { id: string; e164: string; source: string; status: string; provider_number_id: string | null; provider_sid: string | null; outbound_allowed: boolean };
type Row = {
  workspace_id: string; workspace: string; status: { code: string; label: string; next_step: string }; state: string;
  business_number: string | null; verified_by: string | null; documents_status: string; document_uploaded: boolean;
  company_name: string; cvr: string | null; company_address: string; regulatory_bundle_sid: string | null; wants_new_number: boolean;
  job: { status: string; step: string; waiting_for: string; attempts: number; last_error: string; next_attempt_at: string | null } | null;
  test: { status: string; simulated: boolean } | null; numbers: Num[]; provider_cost_usd: number;
};
export type OpTelephony = { configuration: Record<string, boolean | string>; workspaces: Row[] };

const CONFIG_LABELS: Record<string, string> = {
  mode: "Tilstand", twilio_account: "Twilio-hovedkonto", twilio_credentials: "Twilio-legitimation", vapi_api_key: "Vapi API-nøgle",
  vapi_server_secret: "Webhook-hemmelighed", vapi_org_id: "Vapi-org-kontrol", verification_number: "Nummer til kontrolopkald",
  number_country: "Land", number_type: "Nummertype", ready: "Klar til klargøring",
};

function Workspace({ r }: { r: Row }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [bundle, setBundle] = useState(r.regulatory_bundle_sid ?? "");
  const [map, setMap] = useState({ e164: "", provider_number_id: "" });
  const base = `/operator/telephony/workspaces/${r.workspace_id}`;
  const act = useSubmit(async (path: string, body?: unknown, method: string = "POST") => {
    await api(path, { method, body: body === undefined ? undefined : JSON.stringify(body) }); router.refresh();
  });
  return (
    <li className="rounded-xl bg-surface-container-lowest shadow-sm p-space-md flex flex-col gap-space-sm">
      <div className="flex flex-wrap items-center gap-space-sm">
        <h2 className="font-title-md text-title-md text-primary font-bold">{r.workspace}</h2>
        <span className="px-2 py-0.5 rounded-full bg-surface-container-high font-label-sm text-label-sm">{r.status.label}</span>
        <span className="ml-auto font-body-sm text-body-sm text-on-surface-variant">Leverandøromkostning: ${r.provider_cost_usd.toFixed(2)} (intern)</span>
      </div>
      <dl className="grid grid-cols-1 md:grid-cols-3 gap-x-space-md gap-y-1 font-body-sm text-body-sm">
        <div><dt className="text-on-surface-variant">Kundens nummer</dt><dd>{r.business_number ?? "–"} {r.verified_by ? `(bekræftet: ${r.verified_by.startsWith("operator") ? "operatør" : "kontrolopkald"})` : "(ikke bekræftet)"}</dd></div>
        <div><dt className="text-on-surface-variant">Dokumentation</dt><dd>{r.documents_status}{r.document_uploaded ? " · fil uploadet" : ""} · {r.company_name} · CVR {r.cvr ?? "–"}</dd></div>
        <div><dt className="text-on-surface-variant">Ønsker nyt nummer/flytning</dt><dd>{r.wants_new_number ? "Ja" : "Nej"}</dd></div>
        <div><dt className="text-on-surface-variant">Klargøring</dt><dd>{r.job ? `${r.job.status} · trin ${r.job.step}${r.job.waiting_for ? ` · venter på ${r.job.waiting_for}` : ""} · forsøg ${r.job.attempts}` : "–"}</dd></div>
        <div><dt className="text-on-surface-variant">Prøveopkald</dt><dd>{r.test ? `${r.test.status}${r.test.simulated ? " (simuleret)" : ""}` : "–"}</dd></div>
      </dl>
      {r.job?.last_error && <Alert kind="warn">{r.job.last_error}</Alert>}
      {r.numbers.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full font-body-sm text-body-sm"><thead><tr className="text-left text-on-surface-variant"><th>Nummer</th><th>Kilde</th><th>Status</th><th>Vapi-id</th><th>Twilio-SID</th><th>Afsender</th></tr></thead>
            <tbody>{r.numbers.map((n) => (
              <tr key={n.id}><td className="tabular-nums">{n.e164}</td><td>{n.source}</td><td>{n.status}</td><td className="break-all">{n.provider_number_id}</td><td className="break-all">{n.provider_sid}</td>
                <td><label className="flex items-center gap-1"><input type="checkbox" checked={n.outbound_allowed} disabled={note.length < 10 || act.pending}
                  onChange={(e) => act.run(`/operator/telephony/numbers/${n.id}`, { outbound_allowed: e.target.checked, note }, "PATCH")} />tilladt</label></td></tr>
            ))}</tbody></table>
        </div>
      )}
      <details className="rounded-lg bg-surface-container-low p-space-sm">
        <summary className="font-label-lg text-label-lg cursor-pointer">Handlinger</summary>
        <div className="flex flex-col gap-space-sm mt-space-sm">
          <Field label="Begrundelse (auditeres, mindst 10 tegn)"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <div className="flex flex-wrap gap-space-sm">
            <Button type="button" variant="tonal" disabled={note.length < 10 || !r.business_number || act.pending} onClick={() => act.run(`${base}/verify-manually`, { note })}>Bekræft nummer manuelt</Button>
            <Button type="button" variant="tonal" disabled={act.pending || !r.job} onClick={() => act.run(`${base}/jobs/run`)}>Kør klargøring nu</Button>
            {r.document_uploaded && <a className="font-label-lg text-label-lg text-primary underline self-center" href={`/api/backend${base}/documents`} target="_blank" rel="noreferrer">Se dokument</a>}
          </div>
          <div className="flex flex-wrap gap-space-sm items-end">
            <Field label="Godkendt Twilio-bundle (BU…)"><Input value={bundle} onChange={(e) => setBundle(e.target.value)} /></Field>
            <Button type="button" disabled={note.length < 10 || act.pending} onClick={() => act.run(`${base}/documents/review`, { status: "approved", note, regulatory_bundle_sid: bundle || null })}>Godkend dokumentation</Button>
            <Button type="button" variant="tonal" disabled={note.length < 10 || act.pending} onClick={() => act.run(`${base}/documents/review`, { status: "rejected", note })}>Afvis</Button>
          </div>
          <div className="flex flex-wrap gap-space-sm items-end">
            <Field label="Eksisterende nummer i Dialogbots Vapi"><Input value={map.e164} onChange={(e) => setMap({ ...map, e164: e.target.value })} placeholder="+45…" /></Field>
            <Field label="Vapi nummer-id"><Input value={map.provider_number_id} onChange={(e) => setMap({ ...map, provider_number_id: e.target.value })} /></Field>
            <Button type="button" variant="tonal" disabled={note.length < 10 || act.pending} onClick={() => act.run(`${base}/numbers`, { ...map, note, activate: false })}>Tilknyt (migrering)</Button>
          </div>
          <ErrorBox error={act.error} />
        </div>
      </details>
    </li>
  );
}

export function OperatorTelephony({ data }: { data: OpTelephony }) {
  return (
    <div className="flex flex-col gap-space-md">
      <section className="rounded-xl bg-surface-container-lowest shadow-sm p-space-md">
        <h2 className="font-title-md text-title-md text-primary font-bold mb-space-sm">Platformkonfiguration</h2>
        <ul className="grid grid-cols-1 md:grid-cols-3 gap-1 font-body-sm text-body-sm">
          {Object.entries(data.configuration).map(([k, v]) => (
            <li key={k}><span className="text-on-surface-variant">{CONFIG_LABELS[k] ?? k}:</span> {typeof v === "boolean" ? (v ? "sat" : "mangler") : v}</li>
          ))}
        </ul>
      </section>
      {data.workspaces.length === 0 ? <p className="font-body-md text-body-md text-on-surface-variant">Ingen arbejdsrum har startet telefoniopsætning.</p>
        : <ul className="flex flex-col gap-space-sm">{data.workspaces.map((r) => <Workspace key={r.workspace_id} r={r} />)}</ul>}
    </div>
  );
}
