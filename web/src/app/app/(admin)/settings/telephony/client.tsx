"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, Textarea, useSubmit } from "@/components/ui";

export type PhoneNumber = {
  id: string; e164: string; status: string; label: string; active: boolean; greeting: string; speaking_style: string;
};
type Missing = { key: string; text: string };
export type Telephony = {
  status: { code: "not_started" | "awaiting_info" | "provisioning" | "ready_for_test" | "test_failed" | "active" | "paused";
    label: string; next_step: string; missing: Missing[]; platform_ready: boolean };
  business_number: string | null; verified: boolean; subscription_type: string; carrier: string; forwarding_mode: string;
  wants_new_number: boolean;
  documents: { required: boolean; status: string; company_name: string; cvr: string | null; address: string; uploaded: boolean; note: string };
  agreement_accepted: boolean;
  destination: { e164: string } | null;
  guide: { available: false } | { available: true; kind: "mobile_codes"; destination: string; codes: { label: string; code: string }[]; cancel_code: string; note: string }
    | { available: true; kind: "carrier"; destination: string; steps: string[]; note: string };
  answering: Record<"voice" | "greeting" | "opening_hours" | "no_answer", { done: boolean; href: string; value?: string }>;
  test: { id: string; status: "waiting" | "passed" | "failed" | "expired"; simulated: boolean; expires_at: string; reason: string | null } | null;
  active: boolean;
};

const TONE: Record<Telephony["status"]["code"], string> = {
  not_started: "bg-surface-container-high text-on-surface-variant", awaiting_info: "bg-tertiary-fixed text-on-tertiary-fixed",
  provisioning: "bg-tertiary-fixed text-on-tertiary-fixed", ready_for_test: "bg-primary-fixed text-on-primary-fixed",
  test_failed: "bg-error-container text-on-error-container", active: "bg-secondary-container text-on-secondary-container",
  paused: "bg-surface-container-high text-on-surface-variant",
};
const SUBSCRIPTION = { mobile: "Mobilabonnement", landline: "Fastnet", ip_pbx: "Omstilling eller IP-telefoni", unknown: "Ved ikke" };
const MODE = { busy_or_no_answer: "Når vi ikke tager den, eller linjen er optaget (anbefalet)", no_answer: "Kun når vi ikke tager den", always: "Alle opkald" };

function Step({ n, title, state, children }: { n: number; title: string; state: "done" | "current" | "later"; children: React.ReactNode }) {
  return (
    <section className={`bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm ${state === "current" ? "ring-2 ring-primary" : ""}`}>
      <div className="flex items-center gap-space-sm">
        <span className={`w-8 h-8 shrink-0 rounded-full grid place-items-center font-label-lg text-label-lg ${state === "done" ? "bg-secondary-container text-on-secondary-container" : state === "current" ? "bg-primary text-on-primary" : "bg-surface-container-high text-on-surface-variant"}`}>
          {state === "done" ? <Icon name="check" size={18} /> : n}
        </span>
        <h3 className="font-title-md text-title-md text-primary font-bold">{title}</h3>
      </div>
      <div className={`flex flex-col gap-space-sm ${state === "later" ? "opacity-70" : ""}`}>{children}</div>
    </section>
  );
}

function BusinessNumber({ wsId, t, canManage }: { wsId: string; t: Telephony; canManage: boolean }) {
  const router = useRouter();
  const [f, setF] = useState({ e164: t.business_number ?? "", subscription_type: t.subscription_type, carrier: t.carrier,
    forwarding_mode: t.forwarding_mode, wants_new_number: t.wants_new_number });
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const save = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/business-number`, { method: "PUT", body: JSON.stringify(f) }); router.refresh(); });
  const call = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/verify`, { method: "POST" }); setSent(true); });
  const confirm = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/verify/confirm`, { method: "POST", body: JSON.stringify({ code }) }); router.refresh(); });
  return (
    <>
      <p className="font-body-md text-body-md">Jeres nummer bliver hos jeres nuværende teleselskab. I viderestiller bare opkald til et nummer, som Dialogbot tildeler jer.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-sm">
        <Field label="Virksomhedens telefonnummer"><Input value={f.e164} onChange={(e) => setF({ ...f, e164: e.target.value })} placeholder="+45 12 34 56 78" inputMode="tel" disabled={!canManage} /></Field>
        <Field label="Hvilken type abonnement er det?">
          <Select value={f.subscription_type} onChange={(e) => setF({ ...f, subscription_type: e.target.value })} disabled={!canManage}>
            {Object.entries(SUBSCRIPTION).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </Field>
        <Field label="Teleselskab (valgfrit)"><Input value={f.carrier} onChange={(e) => setF({ ...f, carrier: e.target.value })} placeholder="Fx TDC, Telenor, Telia, 3" disabled={!canManage} /></Field>
        <Field label="Hvornår skal assistenten tage telefonen?">
          <Select value={f.forwarding_mode} onChange={(e) => setF({ ...f, forwarding_mode: e.target.value })} disabled={!canManage}>
            {Object.entries(MODE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </Field>
      </div>
      <label className="flex items-start gap-2 font-body-sm text-body-sm">
        <input type="checkbox" className="mt-0.5 w-5 h-5" checked={f.wants_new_number} onChange={(e) => setF({ ...f, wants_new_number: e.target.checked })} disabled={!canManage} />
        Vi vil hellere have et helt nyt nummer eller flytte vores nummer til Dialogbot. Det tilbyder vi ikke med det samme. Vi kontakter jer, og I kan bruge viderestilling imens.
      </label>
      {canManage && <div><Button type="button" onClick={() => save.run()} disabled={save.pending || !f.e164}>Gem nummer</Button></div>}
      <ErrorBox error={save.error} />
      {t.business_number && !t.verified && canManage && (
        <div className="rounded-lg bg-surface-container-low p-space-md flex flex-col gap-space-sm">
          <p className="font-body-md text-body-md"><strong>Bekræft nummeret.</strong> Vi ringer til {t.business_number} og læser en kode på 6 cifre op. Tast koden herunder.</p>
          <div className="flex flex-wrap gap-space-sm items-end">
            <Button type="button" variant="tonal" icon="phone_callback" onClick={() => call.run()} disabled={call.pending}>{sent ? "Ring igen" : "Ring mig op med en kode"}</Button>
            <Field label="Kode"><Input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={6} className="w-32" /></Field>
            <Button type="button" onClick={() => confirm.run()} disabled={confirm.pending || code.length < 6}>Bekræft</Button>
          </div>
          {sent && <p className="font-body-sm text-body-sm text-on-surface-variant">Opkaldet er på vej. Koden gælder i 10 minutter.</p>}
          <ErrorBox error={call.error} /><ErrorBox error={confirm.error} />
        </div>
      )}
      {t.business_number && t.verified && <Alert kind="ok">{t.business_number} er bekræftet.</Alert>}
    </>
  );
}

function Documents({ wsId, t, canManage }: { wsId: string; t: Telephony; canManage: boolean }) {
  const router = useRouter();
  const d = t.documents;
  const [f, setF] = useState({ company_name: d.company_name, cvr: d.cvr ?? "", address: d.address });
  const [file, setFile] = useState<File | null>(null);
  const save = useSubmit(async () => {
    await api(`/workspaces/${wsId}/telephony/company`, { method: "PUT", body: JSON.stringify(f) });
    if (file) {
      const r = await fetch(`/api/backend/workspaces/${wsId}/telephony/documents`, { method: "PUT", body: file, credentials: "same-origin",
        headers: { "content-type": file.type || "application/octet-stream", "x-requested-with": "dialogbot" } });
      if (!r.ok) throw await r.json();
    }
    router.refresh();
  });
  const text = { missing: "Mangler", submitted: "Sendt – Dialogbot gennemgår", approved: "Godkendt", rejected: "Afvist", not_required: "Ikke nødvendig" }[d.status] ?? d.status;
  return (
    <div className="rounded-lg bg-surface-container-low p-space-md flex flex-col gap-space-sm">
      <p className="font-body-md text-body-md"><strong>Virksomhedsoplysninger.</strong> For at tildele jer et dansk nummer skal teleleverandøren kende virksomheden. Dialogbot sender oplysningerne videre. I skal ikke oprette nogen konto. Status: <strong>{text}</strong></p>
      {d.status === "rejected" && d.note && <Alert kind="warn">{d.note}</Alert>}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-space-sm">
        <Field label="Virksomhedens navn"><Input value={f.company_name} onChange={(e) => setF({ ...f, company_name: e.target.value })} disabled={!canManage} /></Field>
        <Field label="CVR-nummer"><Input value={f.cvr} onChange={(e) => setF({ ...f, cvr: e.target.value })} inputMode="numeric" maxLength={8} disabled={!canManage} /></Field>
        <Field label="Adresse i Danmark"><Input value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} disabled={!canManage} /></Field>
      </div>
      <Field label={d.uploaded ? "Dokumentation (uploadet – vælg en ny fil for at erstatte)" : "Udskrift fra CVR-registeret med dansk adresse (PDF, PNG eller JPG)"}>
        <input type="file" accept="application/pdf,image/png,image/jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} disabled={!canManage} className="font-body-sm text-body-sm" />
      </Field>
      {canManage && <div><Button type="button" variant="tonal" onClick={() => save.run()} disabled={save.pending}>Gem virksomhedsoplysninger</Button></div>}
      <ErrorBox error={save.error} />
    </div>
  );
}

function Guide({ t }: { t: Telephony }) {
  const g = t.guide;
  if (!g.available) return null;
  return (
    <div className="flex flex-col gap-space-sm">
      <p className="font-body-md text-body-md">Jeres Dialogbot-nummer er</p>
      <p className="font-headline-sm text-headline-sm text-primary font-bold tabular-nums">{g.destination}</p>
      {g.kind === "mobile_codes" ? (
        <>
          <p className="font-body-md text-body-md">Tast koden på telefonen med jeres nummer, og tryk ring op:</p>
          <ul className="flex flex-col gap-1">{g.codes.map((c) => (
            <li key={c.code} className="flex flex-wrap gap-space-sm items-baseline"><span className="font-body-sm text-body-sm w-56">{c.label}</span><code className="px-2 py-1 rounded bg-surface-container-low font-label-lg text-label-lg select-all">{c.code}</code></li>
          ))}</ul>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Slå al viderestilling fra igen med <code className="select-all">{g.cancel_code}</code>. {g.note}</p>
        </>
      ) : (
        <>
          <ol className="list-decimal pl-5 font-body-md text-body-md">{g.steps.map((s) => <li key={s}>{s}</li>)}</ol>
          <p className="font-body-sm text-body-sm text-on-surface-variant">{g.note}</p>
        </>
      )}
    </div>
  );
}

function Connect({ wsId, t, canManage }: { wsId: string; t: Telephony; canManage: boolean }) {
  const router = useRouter();
  const go = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/connect`, { method: "POST" }); router.refresh(); });
  if (t.destination) return <Guide t={t} />;
  const missing = t.status.missing;
  return (
    <>
      {t.status.code === "provisioning"
        ? <Alert kind="info" icon="hourglass_top">{t.status.next_step}</Alert>
        : <p className="font-body-md text-body-md">Når nummeret er bekræftet, klargør Dialogbot et nummer til jer, som I viderestiller til. Det sker hos Dialogbot. I skal ikke oprette konti eller indtaste tekniske oplysninger.</p>}
      {missing.length > 0 && (
        <ul className="list-disc pl-5 font-body-sm text-body-sm">{missing.map((m) => (
          <li key={m.key}>{m.key === "agreement" ? <Link href="/app/settings/agreement" className="text-primary underline">{m.text}</Link> : m.text}</li>
        ))}</ul>
      )}
      {canManage && t.status.code !== "provisioning" && <div><Button type="button" icon="link" onClick={() => go.run()} disabled={go.pending || missing.length > 0}>Forbind telefonen</Button></div>}
      <ErrorBox error={go.error} />
    </>
  );
}

function Answering({ t, number, wsId, canManage }: { t: Telephony; number: PhoneNumber | null; wsId: string; canManage: boolean }) {
  const router = useRouter();
  const a = t.answering;
  const [f, setF] = useState({ greeting: number?.greeting ?? "", speaking_style: number?.speaking_style ?? "" });
  const save = useSubmit(async () => { if (number) { await api(`/workspaces/${wsId}/phone-numbers/${number.id}`, { method: "PATCH", body: JSON.stringify(f) }); router.refresh(); } });
  const rows: [keyof Telephony["answering"], string, string][] = [
    ["voice", "Stemme", "Vælg en dansk stemme"], ["greeting", "Velkomst", "Skriv hvordan assistenten hilser"],
    ["opening_hours", "Åbningstider", "Godkend jeres åbningstider i Viden"],
    ["no_answer", "Hvis stemmen fejler", a.no_answer.value === "transfer" ? "Opkaldet stilles videre" : "Reservestemme tager over"],
  ];
  return (
    <>
      <ul className="flex flex-col gap-1">{rows.map(([k, label, hint]) => (
        <li key={k} className="flex flex-wrap items-center gap-space-sm">
          <Icon name={a[k].done ? "check_circle" : "radio_button_unchecked"} size={20} className={a[k].done ? "text-secondary" : "text-on-surface-variant"} />
          <span className="font-label-lg text-label-lg w-40">{label}</span>
          <Link href={a[k].href} className="font-body-sm text-body-sm text-primary underline">{hint}</Link>
        </li>
      ))}</ul>
      {number && canManage && (
        <details className="rounded-lg bg-surface-container-low p-space-sm">
          <summary className="font-label-lg text-label-lg cursor-pointer">Særlig hilsen og talestil for telefonen</summary>
          <div className="flex flex-col gap-space-sm mt-space-sm">
            <Field label="Hilsen i telefonen (tom = receptionens velkomst)"><Textarea value={f.greeting} maxLength={500} onChange={(e) => setF({ ...f, greeting: e.target.value })} /></Field>
            <Field label="Talestil (fx 'Vi siger du til kunderne')"><Textarea value={f.speaking_style} maxLength={1000} onChange={(e) => setF({ ...f, speaking_style: e.target.value })} /></Field>
            <div><Button type="button" variant="tonal" onClick={() => save.run()} disabled={save.pending}>Gem</Button></div>
            <ErrorBox error={save.error} />
          </div>
        </details>
      )}
    </>
  );
}

function TestCall({ wsId, t, canManage }: { wsId: string; t: Telephony; canManage: boolean }) {
  const router = useRouter();
  const [own, setOwn] = useState(true);
  const start = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/tests`, { method: "POST", body: JSON.stringify({ called_business_number: own }) }); router.refresh(); });
  const waiting = t.test?.status === "waiting";
  useEffect(() => {
    if (!waiting) return;
    const id = setInterval(() => router.refresh(), 5000);
    return () => clearInterval(id);
  }, [waiting, router]);
  if (!t.destination) return <p className="font-body-sm text-body-sm text-on-surface-variant">Kan startes, når telefonen er forbundet.</p>;
  return (
    <>
      <p className="font-body-md text-body-md">Når viderestillingen er slået til: start prøveopkaldet, og ring inden for 15 minutter fra en anden telefon til <strong>jeres eget nummer</strong> {t.business_number}. Hvis I kun viderestiller ubesvarede opkald, så lad være med at tage telefonen. Assistenten siger "Dette er et prøveopkald", og samtalen lander i indbakken.</p>
      {t.test?.status === "passed" && <Alert kind="ok">Prøveopkaldet ramte jeres assistent og blev gemt i indbakken.{t.test.simulated ? " (Simuleret)" : ""}</Alert>}
      {(t.test?.status === "failed" || t.test?.status === "expired") && <Alert kind="warn">{t.test.reason ?? "Prøveopkaldet fejlede."}</Alert>}
      {waiting && <Alert kind="info" icon="phone_in_talk">Venter på opkaldet … (gælder til {new Date(t.test!.expires_at).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" })})</Alert>}
      {canManage && !waiting && (
        <>
          <label className="flex items-start gap-2 font-body-sm text-body-sm">
            <input type="checkbox" className="mt-0.5 w-5 h-5" checked={own} onChange={(e) => setOwn(e.target.checked)} />
            Jeg ringer til vores eget nummer, så viderestillingen bliver testet.
          </label>
          <div><Button type="button" icon="call" onClick={() => start.run()} disabled={start.pending}>{t.test ? "Nyt prøveopkald" : "Start prøveopkald"}</Button></div>
        </>
      )}
      <ErrorBox error={start.error} />
    </>
  );
}

function Activate({ wsId, t, canManage }: { wsId: string; t: Telephony; canManage: boolean }) {
  const router = useRouter();
  const on = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/activate`, { method: "POST" }); router.refresh(); });
  const off = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/pause`, { method: "POST" }); router.refresh(); });
  const ready = t.test?.status === "passed" && t.agreement_accepted;
  if (t.active) return (
    <>
      <Alert kind="ok">Assistenten tager telefonen. Opkald lander i indbakken.</Alert>
      {canManage && <div><Button type="button" variant="tonal" icon="pause" onClick={() => off.run()} disabled={off.pending}>Sæt på pause</Button></div>}
      <ErrorBox error={off.error} />
    </>
  );
  return (
    <>
      <p className="font-body-md text-body-md">{ready ? "Alt er klar. Når I aktiverer, besvarer assistenten de opkald, I viderestiller." : "Kan aktiveres efter et bestået prøveopkald og en valgt prisaftale."}</p>
      {canManage && <div><Button type="button" icon="power_settings_new" onClick={() => on.run()} disabled={!ready || on.pending}>Aktivér telefonen</Button></div>}
      <ErrorBox error={on.error} />
    </>
  );
}

export function TelephonySetup({ wsId, t, numbers, canManage }: { wsId: string; t: Telephony; numbers: PhoneNumber[]; canManage: boolean }) {
  const c = t.status.code;
  const s1 = t.verified && (!t.documents.required || ["submitted", "approved"].includes(t.documents.status)) ? "done" : "current";
  const s2 = t.destination ? "done" : s1 === "done" ? "current" : "later";
  const s3 = Object.values(t.answering).every((x) => x.done) ? "done" : t.destination ? "current" : "later";
  const s4 = t.test?.status === "passed" ? "done" : t.destination ? "current" : "later";
  const s5 = t.active ? "done" : t.test?.status === "passed" ? "current" : "later";
  const dest = numbers.find((n) => n.e164 === t.destination?.e164) ?? null;
  return (
    <div className="flex flex-col gap-space-md">
      <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-wrap items-start justify-between gap-space-md">
        <div className="flex flex-col gap-1 max-w-2xl">
          <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Indstillinger</span>
          <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Telefoni</h2>
          <p className="font-body-md text-body-md"><strong>Næste skridt:</strong> {t.status.next_step}</p>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Dialogbot står for telefonforbindelsen. I skal ikke oprette konti hos teleleverandører eller indtaste tekniske nøgler. Opkald lander i <Link href="/app/inbox" className="text-primary underline">indbakken</Link>.</p>
        </div>
        <span className={`px-3 py-1 rounded-full font-label-lg text-label-lg font-semibold ${TONE[c]}`}>{t.status.label}</span>
      </div>
      <Step n={1} title="Dit nuværende nummer" state={s1}>
        <BusinessNumber wsId={wsId} t={t} canManage={canManage} />
        {t.documents.required && t.business_number && <Documents wsId={wsId} t={t} canManage={canManage} />}
      </Step>
      <Step n={2} title="Forbind telefonen" state={s2}><Connect wsId={wsId} t={t} canManage={canManage} /></Step>
      <Step n={3} title="Sådan skal vi svare" state={s3}><Answering t={t} number={dest} wsId={wsId} canManage={canManage} /></Step>
      <Step n={4} title="Test forbindelsen" state={s4}><TestCall wsId={wsId} t={t} canManage={canManage} /></Step>
      <Step n={5} title="Aktivér" state={s5}><Activate wsId={wsId} t={t} canManage={canManage} /></Step>
    </div>
  );
}

