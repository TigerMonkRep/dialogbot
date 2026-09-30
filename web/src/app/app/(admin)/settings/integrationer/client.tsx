"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, useSubmit } from "@/components/ui";

type Action = { name: string; label: string; description: string; confirm: boolean; channels: string[] };
type Connector = {
  key: string; label: string; description: string; category: string; auth_kind: "oauth" | "api_key" | "secret" | "builtin";
  availability: "ready" | "coming" | "via_zapier"; zapier_note: string; docs_url: string; events: string[];
  config_schema: { properties?: Record<string, { description?: string; maxLength?: number }> }; actions: Action[];
  status: "not_connected" | "connected" | "error" | "not_implemented"; reason: string | null; error: string | null;
  simulated: boolean; account_label: string; config: Record<string, string>; version: number | null;
  connected_at: string | null; last_ok_at: string | null;
};
export type ActionRun = {
  id: string; conversation_id: string | null; channel: string; connector: string; action: string; label: string;
  status: "ok" | "failed" | "refused"; error: string | null; simulated: boolean; created_at: string;
};
export type Catalogue = { items: Connector[]; recent_actions: ActionRun[]; simulated: boolean };

const STATUS: Record<Connector["status"], [string, string]> = {
  connected: ["Forbundet", "bg-secondary-container text-on-secondary-container"],
  not_connected: ["Ikke forbundet", "bg-surface-container-high text-on-surface-variant"],
  error: ["Fejl", "bg-error-container text-on-error-container"],
  not_implemented: ["Ikke tilgængelig", "bg-surface-container-highest text-on-surface-variant"],
};
const RUN: Record<ActionRun["status"], [string, string]> = {
  ok: ["Udført", "bg-secondary-container text-on-secondary-container"],
  failed: ["Fejlede", "bg-error-container text-on-error-container"],
  refused: ["Afvist", "bg-tertiary-fixed text-on-tertiary-fixed"],
};
const CHANNEL: Record<string, string> = { phone: "Telefon", webchat: "Webchat", test: "Test", system: "System" };
const ICON: Record<string, string> = { calendar: "calendar_month", messaging: "sms", automation: "webhook", crm: "contacts",
  accounting: "receipt_long", booking: "event_available", field_service: "construction", staffing: "badge" };
const LABEL: Record<string, string> = { google_calendar: "Google Kalender", microsoft_calendar: "Microsoft 365-kalender" };
const key = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Math.random()));

export function Integrations({ wsId, data, canManage }: { wsId: string; data: Catalogue; canManage: boolean }) {
  const params = useSearchParams();
  const router = useRouter();
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  useEffect(() => {
    const ok = params.get("connected"), err = params.get("error");
    if (!ok && !err) return;
    const name = LABEL[params.get("connector") ?? ok ?? ""] ?? ok ?? params.get("connector") ?? "Forbindelsen";
    setNotice(ok ? { kind: "ok", text: `${LABEL[ok] ?? ok} er forbundet.` }
      : { kind: "error", text: `${name} blev ikke forbundet (${err}). Prøv igen, eller kontakt Dialogbot.` });
    router.replace("/app/settings/integrationer");
  }, [params, router]);

  const ready = data.items.filter((c) => c.availability === "ready");
  const zapier = data.items.filter((c) => c.availability !== "ready" && c.zapier_note);
  const coming = data.items.filter((c) => c.availability !== "ready" && !c.zapier_note);
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Integrationer</span>
        <h1 className="font-headline-md text-headline-md text-primary font-bold">Handlinger i jeres egne systemer</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">Når et system er forbundet, kan assistenten udføre handlinger dér under et opkald eller i webchatten – fx booke en tid i jeres kalender eller sende en SMS-bekræftelse. Kunden bekræfter altid først, og hver handling vises i samtalen i indbakken. Kun forbundne systemer bruges.</p>
      </div>
      {data.simulated && <Alert kind="warn">Testmiljø: forbindelser og handlinger er simulerede. Intet sendes til rigtige kalendere, telefoner eller webhooks.</Alert>}
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      {!canManage && <Alert kind="info">Kun administratorer kan forbinde systemer.</Alert>}

      <h2 className="font-headline-sm text-headline-sm text-primary">Klar</h2>
      <ul className="grid gap-space-md lg:grid-cols-2">{ready.map((c) => <ConnectorCard key={c.key} wsId={wsId} c={c} canManage={canManage} />)}</ul>

      {zapier.length > 0 && <>
        <h2 className="font-headline-sm text-headline-sm text-primary">Via Zapier eller Make</h2>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">Disse systemer har ingen direkte forbindelse endnu. Forbind Zapier eller Make ovenfor, så kan hændelser fra Dialogbot (ny henvendelse, booking, udført handling) starte jeres egne automatiseringer dér.</p>
        <ul className="grid gap-space-sm md:grid-cols-2 lg:grid-cols-3">{zapier.map((c) => <Coming key={c.key} c={c} />)}</ul>
      </>}
      {coming.length > 0 && <>
        <h2 className="font-headline-sm text-headline-sm text-primary">På vej</h2>
        <ul className="grid gap-space-sm md:grid-cols-2 lg:grid-cols-3">{coming.map((c) => <Coming key={c.key} c={c} />)}</ul>
      </>}

      <Runs runs={data.recent_actions} items={data.items} />
    </section>
  );
}

function Coming({ c }: { c: Connector }) {
  return (
    <li className="rounded-xl bg-surface-container-low p-space-md flex flex-col gap-1">
      <span className="flex items-center gap-space-xs font-label-lg text-label-lg text-on-surface"><Icon name={ICON[c.category] ?? "extension"} size={18} />{c.label}</span>
      <span className="font-body-sm text-body-sm text-on-surface-variant">{c.description}</span>
      <span className="font-label-sm text-label-sm text-on-surface-variant">{c.zapier_note || "På vej – ikke tilgængelig endnu."}</span>
    </li>
  );
}

function ConnectorCard({ wsId, c, canManage }: { wsId: string; c: Connector; canManage: boolean }) {
  const router = useRouter();
  const base = `/workspaces/${wsId}/integrations/${c.key}`;
  const [url, setUrl] = useState(c.config.url ?? "");
  const [sender, setSender] = useState(c.config.sender ?? "");
  const [secret, setSecret] = useState<string | null>(null);
  const [test, setTest] = useState<{ ok: boolean; error?: string } | null>(null);
  const [confirmOff, setConfirmOff] = useState(false);
  const isSink = ["webhook", "zapier", "make"].includes(c.key);

  const connect = useSubmit(async () => {
    const config = isSink ? { url } : c.key === "twilio_sms" ? (sender.trim() ? { sender: sender.trim() } : {}) : {};
    const r = await api<{ status: string; authorize_url?: string; signing_secret?: string }>(`${base}/connect`,
      { method: "POST", headers: { "Idempotency-Key": key() }, body: JSON.stringify({ config, secrets: {} }) });
    if (r.status === "authorize" && r.authorize_url) { window.location.href = r.authorize_url; return; }
    if (r.signing_secret) setSecret(r.signing_secret);
    router.refresh();
  });
  const runTest = useSubmit(async () => {
    setTest(await api<{ ok: boolean; error?: string }>(`${base}/test`, { method: "POST", headers: { "Idempotency-Key": key() } }));
    router.refresh();
  });
  const save = useSubmit(async () => {
    const config = isSink ? { url } : c.key === "twilio_sms" ? (sender.trim() ? { sender: sender.trim() } : {}) : c.config;
    await api(base, { method: "PUT", body: JSON.stringify({ config, expected_version: c.version }) });
    router.refresh();
  });
  const off = useSubmit(async () => { await api(base, { method: "DELETE" }); setConfirmOff(false); setSecret(null); router.refresh(); });
  const [label, cls] = STATUS[c.status];
  const connected = c.status === "connected" || c.status === "error";
  const err = connect.error ?? runTest.error ?? save.error ?? off.error;

  return (
    <li className="rounded-xl bg-surface-container-lowest shadow-sm p-space-md flex flex-col gap-space-sm" data-connector={c.key}>
      <div className="flex flex-wrap items-center gap-space-sm">
        <Icon name={ICON[c.category] ?? "extension"} size={22} className="text-primary" />
        <h3 className="font-title-md text-title-md text-primary font-bold">{c.label}</h3>
        <span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm ${cls}`}>{label}{connected && c.simulated ? " (simuleret)" : ""}</span>
      </div>
      <p className="font-body-sm text-body-sm text-on-surface-variant">{c.description}</p>
      {c.account_label && connected && <p className="font-body-sm text-body-sm">Forbundet som <strong>{c.account_label}</strong>{c.last_ok_at ? ` · sidst bekræftet ${new Date(c.last_ok_at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" })}` : ""}</p>}
      {c.reason && <p className="font-body-sm text-body-sm text-on-surface-variant">{c.reason}{c.key === "bookings" && <> <Link href="/app/bookings" className="text-primary underline">Gå til Bookinger</Link></>}</p>}
      {c.error && <Alert kind="error">{c.error}</Alert>}
      {c.actions.length > 0 && (
        <ul className="flex flex-wrap gap-space-xs" aria-label="Handlinger">
          {c.actions.map((a) => <li key={a.name} title={a.description} className="px-2 py-0.5 rounded-lg bg-surface-container-low font-label-sm text-label-sm">{a.label}{a.confirm ? " · kræver kundens ja" : ""}</li>)}
        </ul>
      )}
      {c.events.length > 0 && <p className="font-label-sm text-label-sm text-on-surface-variant">Hændelser: ny henvendelse, booking oprettet/aflyst, udført handling, afsluttet samtale.</p>}

      {secret && (
        <div className="rounded-lg bg-tertiary-fixed text-on-tertiary-fixed p-space-sm flex flex-col gap-1" role="status">
          <span className="font-label-md text-label-md font-semibold">Hemmelighed til signaturen</span>
          <code className="break-all select-all font-mono text-body-sm">{secret}</code>
          <span className="font-body-sm text-body-sm">Vises kun én gang – gem den, hvis I vil verificere signaturen (X-Dialogbot-Signature).</span>
          <Button variant="tonal" className="self-start" onClick={() => navigator.clipboard?.writeText(secret).catch(() => undefined)}>Kopiér</Button>
        </div>
      )}

      {canManage && c.status !== "not_implemented" && c.key !== "bookings" && (
        <div className="flex flex-col gap-space-sm">
          {isSink && (
            <Field label={c.key === "zapier" ? "Adresse fra Zapiers \"Catch Hook\"" : c.key === "make" ? "Adresse fra Makes \"Custom webhook\"" : "Webhook-adresse (https)"}>
              <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder={c.key === "make" ? "https://hook.eu1.make.com/…" : c.key === "zapier" ? "https://hooks.zapier.com/hooks/catch/…" : "https://jeres-system.dk/dialogbot"} />
            </Field>
          )}
          {c.key === "twilio_sms" && (
            <Field label="Afsendernavn (valgfrit)" hint="Højst 11 bogstaver eller tal. Tomt = virksomhedens navn.">
              <Input value={sender} maxLength={16} onChange={(e) => setSender(e.target.value)} />
            </Field>
          )}
          <div className="flex flex-wrap gap-space-sm">
            {!connected && <Button icon="link" disabled={connect.pending || (isSink && !url.trim())} onClick={() => connect.run()}>{connect.pending ? "Forbinder…" : "Forbind"}</Button>}
            {connected && <Button variant="tonal" icon="network_check" disabled={runTest.pending} onClick={() => runTest.run()}>{runTest.pending ? "Tester…" : "Test forbindelse"}</Button>}
            {connected && (isSink || c.key === "twilio_sms") && <Button variant="outline" icon="save" disabled={save.pending} onClick={() => save.run()}>Gem opsætning</Button>}
            {connected && !confirmOff && <Button variant="ghost" icon="link_off" onClick={() => setConfirmOff(true)}>Afbryd</Button>}
            {confirmOff && <>
              <Button variant="danger" disabled={off.pending} onClick={() => off.run()}>Ja, afbryd {c.label}</Button>
              <Button variant="ghost" onClick={() => setConfirmOff(false)}>Fortryd</Button>
            </>}
          </div>
          {test && (test.ok ? <Alert kind="ok">Forbindelsen virker{c.simulated ? " (simuleret)" : ""}.</Alert> : <Alert kind="error">{test.error}</Alert>)}
          {err && (err.code === "version_conflict" ? <Alert>Opsætningen er ændret af en anden. Genindlæs siden.</Alert> : <ErrorBox error={err} />)}
        </div>
      )}
    </li>
  );
}

function Runs({ runs, items }: { runs: ActionRun[]; items: Connector[] }) {
  const name = (k: string) => items.find((c) => c.key === k)?.label ?? k;
  return (
    <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
      <h2 className="font-headline-sm text-headline-sm text-primary">Seneste handlinger</h2>
      {runs.length === 0 ? <p className="font-body-sm text-body-sm text-on-surface-variant">Ingen handlinger endnu.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full font-body-sm text-body-sm">
            <thead><tr className="text-left text-on-surface-variant"><th className="pr-3">Tid</th><th className="pr-3">Kanal</th><th className="pr-3">System</th><th className="pr-3">Handling</th><th>Status</th></tr></thead>
            <tbody>{runs.map((r) => (
              <tr key={r.id} className="align-top border-t border-outline-variant/40">
                <td className="pr-3 py-1 tabular-nums whitespace-nowrap">{new Date(r.created_at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" })}</td>
                <td className="pr-3 py-1">{CHANNEL[r.channel] ?? r.channel}</td>
                <td className="pr-3 py-1">{name(r.connector)}</td>
                <td className="pr-3 py-1">{r.conversation_id ? <Link className="text-primary underline" href={`/app/inbox/${r.conversation_id}`}>{r.label}</Link> : r.label}{r.simulated ? " (simuleret)" : ""}{r.error ? <><br /><span className="text-on-surface-variant">{r.error}</span></> : null}</td>
                <td className="py-1"><span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm ${RUN[r.status][1]}`}>{RUN[r.status][0]}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
