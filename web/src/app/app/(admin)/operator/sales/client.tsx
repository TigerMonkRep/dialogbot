"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError, type ApiError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, useSubmit } from "@/components/ui";

export type SalesInfo = { available: boolean; problem: string | null; demo_number: string | null; hours: { from: string; to: string } };
export type DemoRow = {
  id: string; source: "web" | "seller"; phone: string; name: string; company: string; cvr: string | null; status: string;
  outcome: string | null; summary: string; error: string | null; note: string; lead_id: string | null; created_at: string | null;
};
type Cvr = { cvr: string; legal_name: string; city: string | null; industry: string | null; status: string | null; advertising_protected: boolean | null };

const STATUS: Record<string, string> = { calling: "Ringer", done: "Gennemført", no_answer: "Intet svar", failed: "Fejlede", skipped: "Sprunget over (spærreliste)" };
const OUTCOME: Record<string, string> = { interested: "Interesseret", callback: "Ring tilbage", not_interested: "Ikke interesseret", opt_out: "Frabad sig opkald" };

export function SellerDemoCall({ info, calls }: { info: SalesInfo; calls: DemoRow[] }) {
  const router = useRouter();
  const [f, setF] = useState({ phone: "", name: "", company: "", cvr: "", note: "", consent_confirmed: false });
  const [cvr, setCvr] = useState<Cvr | null>(null);
  const [cvrError, setCvrError] = useState<ApiError | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const call = useSubmit(async () => {
    await api("/operator/sales/demo-calls", { method: "POST", body: JSON.stringify({ ...f, cvr: f.cvr || null }) });
    setSent(f.company); setF({ phone: "", name: "", company: "", cvr: "", note: "", consent_confirmed: false }); setCvr(null);
    router.refresh();
  });
  const check = async () => {
    setCvrError(null); setCvr(null);
    try {
      const r = await api<Cvr>(`/operator/sales/cvr/${encodeURIComponent(f.cvr)}`);
      setCvr(r);
      if (!f.company) setF((x) => ({ ...x, company: r.legal_name }));
    } catch (e) { setCvrError(e as ApiError); }
  };
  const protectedCo = cvr?.advertising_protected === true;
  return (
    <div className="grid lg:grid-cols-[minmax(0,28rem)_1fr] gap-space-lg items-start">
      <form className="rounded-xl bg-surface-container-lowest shadow-sm p-space-md flex flex-col gap-space-sm" onSubmit={(e) => { e.preventDefault(); call.run(); }}>
        {!info.available && <Alert kind="warn">Demo-opkald kan ikke foretages endnu: {info.problem}</Alert>}
        <Field label="CVR-nummer (tjek før du ringer)" hint="Viser om virksomheden er reklamebeskyttet.">
          <div className="flex gap-space-sm">
            <Input value={f.cvr} inputMode="numeric" onChange={(e) => { setF({ ...f, cvr: e.target.value }); setCvr(null); }} placeholder="12345678" />
            <Button type="button" variant="secondary" onClick={check} disabled={f.cvr.replace(/\D/g, "").length !== 8}>Tjek</Button>
          </div>
        </Field>
        {cvrError && <Alert kind={cvrError.code === "cvr_not_configured" ? "info" : "error"}>{cvrError.code === "cvr_not_configured" ? "CVR-opslag er ikke sat op. Tjek reklamebeskyttelsen på datacvr.virk.dk, før du ringer." : cvrError.message}</Alert>}
        {cvr && (protectedCo
          ? <Alert kind="error">{cvr.legal_name} er reklamebeskyttet. Du må ikke ringe til dem for at sælge.</Alert>
          : <Alert kind={cvr.advertising_protected === false ? "ok" : "warn"}>{cvr.legal_name}{cvr.city ? `, ${cvr.city}` : ""}{cvr.industry ? ` · ${cvr.industry}` : ""} · {cvr.advertising_protected === false ? "ikke reklamebeskyttet" : "reklamebeskyttelse ukendt – tjek datacvr.virk.dk"}</Alert>)}
        <Field label="Virksomhed" error={fieldError(call.error, "company")}><Input required value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} placeholder="Hansen Byg ApS" /></Field>
        <Field label="Kontaktens fornavn"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Mette" /></Field>
        <Field label="Telefonnummer" error={fieldError(call.error, "phone")}><Input required type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} placeholder="20 30 40 50" /></Field>
        <Field label="Note (valgfri)"><Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="Sagde ja kl. 10.15, vil høre om booking" /></Field>
        <label className="flex items-start gap-space-sm font-body-sm text-body-sm">
          <input type="checkbox" className="mt-1 w-4 h-4 accent-primary" checked={f.consent_confirmed} onChange={(e) => setF({ ...f, consent_confirmed: e.target.checked })} />
          <span>Kontakten har lige sagt ja i telefonen til, at Dialogbots AI ringer op nu.</span>
        </label>
        <ErrorBox error={call.error} />
        {sent && !call.error && <Alert kind="ok">AI&apos;en ringer nu til {sent}. Du kan lægge på.</Alert>}
        <Button type="submit" icon="call" disabled={!info.available || !f.consent_confirmed || protectedCo || call.pending || !f.company || !f.phone}>{call.pending ? "Ringer op…" : "Lad AI'en ringe op nu"}</Button>
      </form>

      <div className="rounded-xl bg-surface-container-lowest shadow-sm p-space-md flex flex-col gap-space-sm min-w-0">
        <h2 className="font-title-md text-title-md text-primary font-bold">Seneste demo-opkald</h2>
        {calls.length === 0 ? <p className="font-body-sm text-body-sm text-on-surface-variant">Ingen endnu.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full font-body-sm text-body-sm">
              <thead><tr className="text-left text-on-surface-variant"><th className="pr-3">Tid</th><th className="pr-3">Kilde</th><th className="pr-3">Kontakt</th><th className="pr-3">Status</th><th>Udfald</th></tr></thead>
              <tbody>{calls.map((c) => (
                <tr key={c.id} className="align-top border-t border-outline-variant/40">
                  <td className="pr-3 py-1 tabular-nums whitespace-nowrap">{c.created_at ? new Date(c.created_at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" }) : "–"}</td>
                  <td className="pr-3 py-1">{c.source === "web" ? "Hjemmeside" : "Sælger"}</td>
                  <td className="pr-3 py-1">{[c.name, c.company].filter(Boolean).join(" · ") || "–"}<br /><span className="tabular-nums text-on-surface-variant">{c.phone}</span></td>
                  <td className="pr-3 py-1">{STATUS[c.status] ?? c.status}{c.error ? <><br /><span className="text-error">{c.error}</span></> : null}</td>
                  <td className="py-1">{c.outcome ? OUTCOME[c.outcome] ?? c.outcome : "–"}{c.summary ? <><br /><span className="text-on-surface-variant">{c.summary}</span></> : null}{c.lead_id ? <><br /><a className="text-primary underline" href={`/app/leads/${c.lead_id}`}>Henvendelse</a></> : null}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
