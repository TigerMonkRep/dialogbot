"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, Select, Tag, Textarea, useSubmit } from "@/components/ui";

type Basis = { id: string; channel: string; purpose: string; kind: string; text: string; source: string; granted_at: string; valid_until: string | null; withdrawn_at: string | null; valid: boolean };
type Policy = { result: string; reasons: string[]; reason_text: string[] } | null;
export type ContactRow = { id: string; name: string | null; role: string | null; phone_e164: string | null; email: string | null; is_main_number: boolean; status: string; basis?: Basis[]; policy?: Policy };
const TONE: Record<string, "neutral" | "secondary" | "tertiary"> = { ALLOW: "tertiary", BLOCK: "secondary", NEEDS_REVIEW: "neutral" };
const SOURCE: Record<string, string> = { web_form: "Formular på hjemmesiden", seller: "Sælger i telefonen", lead: "Henvendelse", import: "Import", test: "Test (eget nummer)" };
const dt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Copenhagen" }) : "–");

function BasisForm({ contactId, onDone }: { contactId: string; onDone: () => void }) {
  const [f, setF] = useState({ kind: "request", source: "seller", purpose: "Opkald fra Peter om Dialogbot", text: "", evidence_ref: "" });
  const save = useSubmit(async () => { await api(`/operator/salg/contacts/${contactId}/basis`, { method: "POST", body: JSON.stringify({ ...f, channel: "ai_call", text_version: "operator-v1" }) }); onDone(); });
  return (
    <form className="flex flex-col gap-2 rounded-xl bg-panel p-3" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Art"><Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="request">Anmodning (de bad om opkald)</option><option value="consent">Samtykke</option></Select></Field>
        <Field label="Kilde"><Select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}><option value="seller">Sælger i telefonen</option><option value="web_form">Formular på hjemmesiden</option><option value="lead">Henvendelse</option><option value="import">Import</option></Select></Field>
      </div>
      <Field label="Formål"><Input value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} /></Field>
      <Field label="Den fulde tekst, kontakten sagde ja til" error={fieldError(save.error, "text")} hint="Fx: «Ja, Peter fra Dialogbot (en AI-assistent) må ringe mig op om Dialogbot.»"><Textarea value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} /></Field>
      <Field label="Dokumentation (valgfri)" hint="Fx tidspunkt for samtalen, link til henvendelsen"><Input value={f.evidence_ref} onChange={(e) => setF({ ...f, evidence_ref: e.target.value })} /></Field>
      <ErrorBox error={save.error} />
      <Button type="submit" variant="secondary" disabled={f.text.trim().length < 20 || save.pending}>Registrér kontaktgrundlag</Button>
    </form>
  );
}

export function ContactsPanel({ companyId, contacts, approvedScriptId, mode, advertisingProtected }: { companyId: string; contacts: ContactRow[]; approvedScriptId: string | null; mode: string; advertisingProtected: boolean | null }) {
  const router = useRouter();
  const [openBasis, setOpenBasis] = useState<string | null>(null);
  const [nc, setNc] = useState({ role: "", name: "", phone: "" });
  const [campaigns, setCampaigns] = useState<{ id: string; name: string; status: string }[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [testPhone, setTestPhone] = useState("");
  const [testOk, setTestOk] = useState(false);
  const [testRecord, setTestRecord] = useState(false);
  const [testResult, setTestResult] = useState<{ status: string; error: string | null; campaign_contact_id: string } | null>(null);
  const [adv, setAdv] = useState({ value: "false", note: "" });
  useEffect(() => {
    api<{ items: { id: string; name: string; status: string; is_test: boolean }[] }>("/operator/salg/campaigns")
      .then((r) => setCampaigns(r.items.filter((c) => !c.is_test && (c.status === "draft" || c.status === "paused")))).catch(() => setCampaigns([]));
  }, []);
  const add = useSubmit(async () => { await api(`/operator/salg/companies/${companyId}/contacts`, { method: "POST", body: JSON.stringify({ ...nc, name: nc.name || null, role: nc.role || null }) }); setNc({ role: "", name: "", phone: "" }); router.refresh(); });
  const withdraw = useSubmit(async (id: string) => { await api(`/operator/salg/basis/${id}/withdraw`, { method: "POST", body: JSON.stringify({ reason: "Trukket tilbage af operatør" }) }); router.refresh(); });
  const toCampaign = useSubmit(async () => { await api(`/operator/salg/campaigns/${campaignId}/members`, { method: "POST", body: JSON.stringify({ contact_ids: contacts.filter((x) => x.phone_e164).map((x) => x.id) }) }); router.push(`/app/operator/salg/kampagner/${campaignId}`); });
  const test = useSubmit(async () => { setTestResult(await api(`/operator/salg/test-calls`, { method: "POST", body: JSON.stringify({ company_id: companyId, script_id: approvedScriptId, phone: testPhone, accepted_test: testOk, record: testRecord }) })); router.refresh(); });
  const advCheck = useSubmit(async () => { await api(`/operator/salg/companies/${companyId}/advertising-check`, { method: "POST", body: JSON.stringify({ advertising_protected: adv.value === "true", note: adv.note }) }); router.refresh(); });
  const canCall = mode === "test" || mode === "live";

  return (
    <section className="rounded-2xl border-2 border-ink bg-paper p-space-md flex flex-col gap-3 min-w-0">
      <h2 className="font-display font-bold text-[18px]">Kontakter, kontaktgrundlag og opkald</h2>
      <p className="text-[13px] text-muted">Peter må kun ringe til et nummer med dokumenteret kontaktgrundlag (anmodning eller samtykke til et AI-opkald). Politikken vises pr. kontakt og tjekkes igen lige før hvert opkald.</p>
      {contacts.length === 0 ? <p className="text-muted text-[14px]">Ingen kontakter endnu.</p> : (
        <ul className="flex flex-col gap-2">{contacts.map((x) => (
          <li key={x.id} className="rounded-xl border-[1.5px] border-ink p-3 text-[14px] flex flex-col gap-1">
            <div className="flex flex-wrap gap-2 items-center justify-between">
              <span><span className="font-semibold">{x.role ?? x.name ?? "Kontakt"}</span>{x.name && x.role ? ` (${x.name})` : ""}: <span className="tabular-nums">{x.phone_e164 ?? x.email ?? "–"}</span> {x.is_main_number && <Tag>Hovednummer</Tag>}</span>
              {x.policy && <span><Tag tone={TONE[x.policy.result]}>{x.policy.result}</Tag></span>}
            </div>
            {x.policy && x.policy.reason_text.length > 0 && <p className="text-[13px] text-muted">{x.policy.reason_text.join(" · ")}</p>}
            {(x.basis ?? []).map((b) => (
              <div key={b.id} className={`text-[13px] rounded-lg p-2 ${b.valid ? "bg-success-soft" : "bg-panel"}`}>
                <span className="font-semibold">{b.kind === "request" ? "Anmodning" : "Samtykke"}</span> · {SOURCE[b.source] ?? b.source} · {dt(b.granted_at)}{b.withdrawn_at ? ` · trukket tilbage ${dt(b.withdrawn_at)}` : b.valid ? "" : " · udløbet"}
                <span className="block">&quot;{b.text}&quot;</span>
                {b.valid && <button className="underline text-[12px]" onClick={() => withdraw.run(b.id)}>Træk tilbage</button>}
              </div>
            ))}
            {x.phone_e164 && (openBasis === x.id ? <BasisForm contactId={x.id} onDone={() => { setOpenBasis(null); router.refresh(); }} />
              : <button className="self-start underline text-[13px]" onClick={() => setOpenBasis(x.id)}>Registrér kontaktgrundlag</button>)}
          </li>))}</ul>
      )}
      <ErrorBox error={withdraw.error} />
      <details className="rounded-xl border-[1.5px] border-ink">
        <summary className="cursor-pointer px-3 py-2 font-semibold text-[14px]">Tilføj kontakt</summary>
        <form className="grid md:grid-cols-3 gap-2 p-3 items-end" onSubmit={(e) => { e.preventDefault(); add.run(); }}>
          <Field label="Rolle"><Input value={nc.role} onChange={(e) => setNc({ ...nc, role: e.target.value })} placeholder="Indehaver" /></Field>
          <Field label="Navn (valgfrit)"><Input value={nc.name} onChange={(e) => setNc({ ...nc, name: e.target.value })} /></Field>
          <Field label="Telefon" error={fieldError(add.error, "phone")}><Input value={nc.phone} onChange={(e) => setNc({ ...nc, phone: e.target.value })} placeholder="20 30 40 50" /></Field>
          <div className="md:col-span-3"><ErrorBox error={add.error} /><Button type="submit" variant="secondary" disabled={!nc.phone.trim() || add.pending}>Tilføj</Button></div>
        </form>
      </details>
      {advertisingProtected === null && (
        <details className="rounded-xl border-[1.5px] border-ink" open>
          <summary className="cursor-pointer px-3 py-2 font-semibold text-[14px]">Reklamebeskyttelse er ukendt – registrér manuelt tjek</summary>
          <form className="grid md:grid-cols-[12rem_1fr_auto] gap-2 p-3 items-end" onSubmit={(e) => { e.preventDefault(); advCheck.run(); }}>
            <Field label="Reklamebeskyttet?"><Select value={adv.value} onChange={(e) => setAdv({ ...adv, value: e.target.value })}><option value="false">Nej</option><option value="true">Ja</option></Select></Field>
            <Field label="Hvor er det tjekket?" hint="Fx «datacvr.virk.dk 30/10, CVR 12345678»"><Input value={adv.note} onChange={(e) => setAdv({ ...adv, note: e.target.value })} /></Field>
            <Button type="submit" variant="secondary" disabled={adv.note.trim().length < 5 || advCheck.pending}>Gem</Button>
            <div className="md:col-span-3"><ErrorBox error={advCheck.error} /></div>
          </form>
        </details>
      )}
      <div className="grid md:grid-cols-2 gap-3">
        <div className="rounded-xl border-[1.5px] border-ink p-3 flex flex-col gap-2">
          <h3 className="font-semibold">Tilføj til kampagne</h3>
          {campaigns.length === 0 ? <p className="text-[13px] text-muted">Ingen kampagner i kladde eller på pause. <Link className="underline" href="/app/operator/salg/kampagner">Opret en kampagne</Link>.</p> : (
            <>
              <Select value={campaignId} onChange={(e) => setCampaignId(e.target.value)}><option value="">Vælg kampagne</option>{campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
              <Button variant="secondary" disabled={!campaignId || toCampaign.pending} onClick={() => toCampaign.run()}>Tilføj kontakter og se forhåndsvisning</Button>
              <ErrorBox error={toCampaign.error} />
            </>
          )}
        </div>
        <form className="rounded-xl border-[1.5px] border-ink p-3 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); test.run(); }}>
          <h3 className="font-semibold">Testopkald til dit eget nummer</h3>
          {!canCall && <Alert kind="info">Kræver SALES_OUTBOUND_MODE=test (nu: {mode}) og dit nummer i SALES_TEST_NUMBERS.</Alert>}
          {!approvedScriptId && <Alert kind="info">Godkend et manuskript først.</Alert>}
          <Field label="Dit testnummer" error={fieldError(test.error, "phone")}><Input value={testPhone} onChange={(e) => setTestPhone(e.target.value)} placeholder="20 30 40 50" /></Field>
          <label className="flex items-start gap-2 text-[13px]"><input type="checkbox" className="mt-1 accent-primary" checked={testOk} onChange={(e) => setTestOk(e.target.checked)} /><span>Nummeret er mit eget testnummer, og Peter (AI-assistent) må ringe til det nu. Det er et rigtigt opkald, der koster som et kampagneopkald.</span></label>
          <ErrorBox error={test.error} />
          {testResult && <Alert kind={testResult.status === "calling" ? "ok" : "warn"}>{testResult.status === "calling" ? "Peter ringer nu." : `Ikke ringet op: ${testResult.error ?? testResult.status}`} <Link className="underline" href={`/app/operator/salg/opkald/${testResult.campaign_contact_id}`}>Se opkaldet</Link></Alert>}
          <label className="flex items-start gap-2 text-[13px]"><input type="checkbox" className="mt-1 accent-primary" checked={testRecord} onChange={(e) => setTestRecord(e.target.checked)} /><span>Optag opkaldet (kun hvis lydlager er sat op)</span></label>
          <Button type="submit" icon="call" disabled={!canCall || !approvedScriptId || !testOk || !testPhone.trim() || test.pending}>{test.pending ? "Ringer op…" : "Ring til mig"}</Button>
        </form>
      </div>
    </section>
  );
}
