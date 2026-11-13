"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, Textarea, useSubmit } from "@/components/ui";
import { useLocale, useT } from "@/i18n/client";
import { HTML_LANG, LANGUAGES, LOCALE_NAMES } from "@/i18n/config";

export type PhoneNumber = {
  id: string; e164: string; status: string; label: string; active: boolean; greeting: string; speaking_style: string;
  record_calls?: boolean; recording_retention_days?: number; recording_available?: boolean;
};

const RETENTION = [7, 30, 90, 180, 365];

/** «Optag opkald»: off by default. When on, callers hear it in the greeting and the team can listen under «Opkald». */
function Recording({ wsId, number }: { wsId: string; number: PhoneNumber }) {
  const router = useRouter();
  const tr = useT("settings");
  const [on, setOn] = useState(!!number.record_calls);
  const [days, setDays] = useState(number.recording_retention_days ?? 90);
  const save = useSubmit(async (next: { record_calls: boolean; recording_retention_days: number }) => {
    await api(`/workspaces/${wsId}/phone-numbers/${number.id}`, { method: "PATCH", body: JSON.stringify(next) });
    setOn(next.record_calls); setDays(next.recording_retention_days); router.refresh();
  });
  const off = number.recording_available === false;
  return (
    <div data-testid="record-calls" className="flex flex-col gap-2 rounded-lg bg-panel p-3">
      <label className="flex items-start gap-3 cursor-pointer">
        <input type="checkbox" className="mt-1 h-5 w-5" checked={on} disabled={off || save.pending}
          onChange={(e) => save.run({ record_calls: e.target.checked, recording_retention_days: days })} />
        <span className="flex flex-col gap-0.5">
          <span className="text-label-lg">{tr("telephony.recording.title")}</span>
          <span className="text-body-sm text-ink-soft">{off ? tr("telephony.recording.unavailable") : tr("telephony.recording.hint")}</span>
        </span>
      </label>
      {on && (
        <Field label={tr("telephony.recording.keep")}>
          <Select value={days} disabled={save.pending} onChange={(e) => save.run({ record_calls: true, recording_retention_days: Number(e.target.value) })}>
            {RETENTION.map((d) => <option key={d} value={d}>{tr("telephony.recording.days", { n: d })}</option>)}
          </Select>
        </Field>
      )}
      <ErrorBox error={save.error} />
    </div>
  );
}
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
/** The workspace's languages (GET/PUT /workspaces/{id}/languages). Peter's phone language is default_conversation_language. */
export type Languages = { version: number; interface_language: string; default_conversation_language: string; enabled_conversation_languages: string[]; report_language: string };

const TONE: Record<Telephony["status"]["code"], string> = {
  not_started: "bg-line text-ink-soft", awaiting_info: "bg-accent-soft text-accent-deep",
  provisioning: "bg-accent-soft text-accent-deep", ready_for_test: "bg-panel text-ink",
  test_failed: "bg-danger-soft text-danger", active: "bg-success-soft text-success",
  paused: "bg-line text-ink-soft",
};
const SUBSCRIPTION = ["mobile", "landline", "ip_pbx", "unknown"];
const MODE = ["busy_or_no_answer", "no_answer", "always"];

function Step({ n, title, state, children }: { n: number; title: string; state: "done" | "current" | "later"; children: React.ReactNode }) {
  return (
    <section className={`bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2 ${state === "current" ? "ring-2 ring-accent" : ""}`}>
      <div className="flex items-center gap-2">
        <span className={`w-8 h-8 shrink-0 rounded-full grid place-items-center text-label-lg ${state ==="done"?"bg-success-soft text-success": state ==="current"?"bg-ink text-paper":"bg-line text-ink-soft"}`}>
          {state === "done" ? <Icon name="check" size={18} /> : n}
        </span>
        <h3 className="font-title-md text-title-md text-ink font-bold">{title}</h3>
      </div>
      <div className={`flex flex-col gap-2 ${state === "later" ? "opacity-70" : ""}`}>{children}</div>
    </section>
  );
}

function BusinessNumber({ wsId, t, canManage }: { wsId: string; t: Telephony; canManage: boolean }) {
  const router = useRouter();
  const tr = useT("settings");
  const [f, setF] = useState({ e164: t.business_number ?? "", subscription_type: t.subscription_type, carrier: t.carrier,
    forwarding_mode: t.forwarding_mode, wants_new_number: t.wants_new_number });
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const save = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/business-number`, { method: "PUT", body: JSON.stringify(f) }); router.refresh(); });
  const call = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/verify`, { method: "POST" }); setSent(true); });
  const confirm = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/verify/confirm`, { method: "POST", body: JSON.stringify({ code }) }); router.refresh(); });
  return (
    <>
      <p className="text-body-md">{tr("telephony.number.intro")}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <Field label={tr("telephony.number.label")}><Input value={f.e164} onChange={(e) => setF({ ...f, e164: e.target.value })} placeholder={tr("telephony.number.placeholder")} inputMode="tel" disabled={!canManage} /></Field>
        <Field label={tr("telephony.number.subscriptionType")}>
          <Select value={f.subscription_type} onChange={(e) => setF({ ...f, subscription_type: e.target.value })} disabled={!canManage}>
            {SUBSCRIPTION.map((k) => <option key={k} value={k}>{tr(`telephony.subscription.${k}`)}</option>)}
          </Select>
        </Field>
        <Field label={tr("telephony.number.carrier")}><Input value={f.carrier} onChange={(e) => setF({ ...f, carrier: e.target.value })} placeholder={tr("telephony.number.carrierPlaceholder")} disabled={!canManage} /></Field>
        <Field label={tr("telephony.number.when")}>
          <Select value={f.forwarding_mode} onChange={(e) => setF({ ...f, forwarding_mode: e.target.value })} disabled={!canManage}>
            {MODE.map((k) => <option key={k} value={k}>{tr(`telephony.mode.${k}`)}</option>)}
          </Select>
        </Field>
      </div>
      <label className="flex items-start gap-2 text-body-sm">
        <input type="checkbox" className="mt-0.5 w-5 h-5" checked={f.wants_new_number} onChange={(e) => setF({ ...f, wants_new_number: e.target.checked })} disabled={!canManage} />
        {tr("telephony.number.wantsNew")}
      </label>
      {canManage && <div><Button type="button" onClick={() => save.run()} disabled={save.pending || !f.e164}>{tr("telephony.number.save")}</Button></div>}
      <ErrorBox error={save.error} />
      {t.business_number && !t.verified && canManage && (
        <div className="rounded-lg bg-panel p-3 flex flex-col gap-2">
          <p className="text-body-md"><strong>{tr("telephony.number.confirmTitle")}</strong> {tr("telephony.number.confirmText", { number: t.business_number })}</p>
          <div className="flex flex-wrap gap-2 items-end">
            <Button type="button" variant="tonal" icon="phone_callback" onClick={() => call.run()} disabled={call.pending}>{sent ? tr("telephony.number.callAgain") : tr("telephony.number.callMe")}</Button>
            <Field label={tr("telephony.number.code")}><Input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={6} className="w-32" /></Field>
            <Button type="button" onClick={() => confirm.run()} disabled={confirm.pending || code.length < 6}>{tr("telephony.number.confirm")}</Button>
          </div>
          {sent && <p className="text-body-sm text-ink-soft">{tr("telephony.number.sent")}</p>}
          <ErrorBox error={call.error} /><ErrorBox error={confirm.error} />
        </div>
      )}
      {t.business_number && t.verified && <Alert kind="ok">{tr("telephony.number.verified", { number: t.business_number })}</Alert>}
    </>
  );
}

function Documents({ wsId, t, canManage }: { wsId: string; t: Telephony; canManage: boolean }) {
  const router = useRouter();
  const tr = useT("settings");
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
  const text = ["missing", "submitted", "approved", "rejected", "not_required"].includes(d.status) ? tr(`telephony.docs.status.${d.status}`) : d.status;
  return (
    <div className="rounded-lg bg-panel p-3 flex flex-col gap-2">
      <p className="text-body-md"><strong>{tr("telephony.docs.title")}</strong> {tr("telephony.docs.intro")} <strong>{text}</strong></p>
      {d.status === "rejected" && d.note && <Alert kind="warn">{d.note}</Alert>}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <Field label={tr("telephony.docs.company")}><Input value={f.company_name} onChange={(e) => setF({ ...f, company_name: e.target.value })} disabled={!canManage} /></Field>
        <Field label={tr("telephony.docs.cvr")}><Input value={f.cvr} onChange={(e) => setF({ ...f, cvr: e.target.value })} inputMode="numeric" maxLength={8} disabled={!canManage} /></Field>
        <Field label={tr("telephony.docs.address")}><Input value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} disabled={!canManage} /></Field>
      </div>
      <Field label={d.uploaded ? tr("telephony.docs.uploaded") : tr("telephony.docs.upload")}>
        <input type="file" accept="application/pdf,image/png,image/jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} disabled={!canManage} className="text-body-sm" />
      </Field>
      {canManage && <div><Button type="button" variant="tonal" onClick={() => save.run()} disabled={save.pending}>{tr("telephony.docs.save")}</Button></div>}
      <ErrorBox error={save.error} />
    </div>
  );
}

function Guide({ t }: { t: Telephony }) {
  const tr = useT("settings");
  const g = t.guide;
  if (!g.available) return null;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-body-md">{tr("telephony.guide.yourNumber")}</p>
      <p className="font-display text-headline-sm text-ink font-bold tabular-nums">{g.destination}</p>
      {g.kind === "mobile_codes" ? (
        <>
          <p className="text-body-md">{tr("telephony.guide.dialCode")}</p>
          <ul className="flex flex-col gap-1">{g.codes.map((c) => (
            <li key={c.code} className="flex flex-wrap gap-2 items-baseline"><span className="text-body-sm w-56">{c.label}</span><code className="px-2 py-1 rounded bg-panel text-label-lg select-all">{c.code}</code></li>
          ))}</ul>
          <p className="text-body-sm text-ink-soft">{tr("telephony.guide.cancelAll")} <code className="select-all">{g.cancel_code}</code>. {g.note}</p>
        </>
      ) : (
        <>
          <ol className="list-decimal pl-5 text-body-md">{g.steps.map((s) => <li key={s}>{s}</li>)}</ol>
          <p className="text-body-sm text-ink-soft">{g.note}</p>
        </>
      )}
    </div>
  );
}

function Connect({ wsId, t, canManage }: { wsId: string; t: Telephony; canManage: boolean }) {
  const router = useRouter();
  const tr = useT("settings");
  const go = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/connect`, { method: "POST" }); router.refresh(); });
  if (t.destination) return <Guide t={t} />;
  const missing = t.status.missing;
  return (
    <>
      {t.status.code === "provisioning"
        ? <Alert kind="info" icon="hourglass_top">{t.status.next_step}</Alert>
        : <p className="text-body-md">{tr("telephony.connect.intro")}</p>}
      {missing.length > 0 && (
        <ul className="list-disc pl-5 text-body-sm">{missing.map((m) => (
          <li key={m.key}>{m.key === "agreement" ? <Link href="/app/settings/agreement" className="text-ink underline">{m.text}</Link> : m.text}</li>
        ))}</ul>
      )}
      {canManage && t.status.code !== "provisioning" && <div><Button type="button" icon="link" onClick={() => go.run()} disabled={go.pending || missing.length > 0}>{tr("telephony.connect.button")}</Button></div>}
      <ErrorBox error={go.error} />
    </>
  );
}

function Answering({ t, number, wsId, canManage }: { t: Telephony; number: PhoneNumber | null; wsId: string; canManage: boolean }) {
  const router = useRouter();
  const tr = useT("settings");
  const a = t.answering;
  const [f, setF] = useState({ greeting: number?.greeting ?? "", speaking_style: number?.speaking_style ?? "" });
  const save = useSubmit(async () => { if (number) { await api(`/workspaces/${wsId}/phone-numbers/${number.id}`, { method: "PATCH", body: JSON.stringify(f) }); router.refresh(); } });
  const rows: [keyof Telephony["answering"], string, string][] = [
    ["voice", tr("telephony.answering.voice"), tr("telephony.answering.voiceHint")], ["greeting", tr("telephony.answering.greeting"), tr("telephony.answering.greetingHint")],
    ["opening_hours", tr("telephony.answering.hours"), tr("telephony.answering.hoursHint")],
    ["no_answer", tr("telephony.answering.noAnswer"), a.no_answer.value === "transfer" ? tr("telephony.answering.transfer") : tr("telephony.answering.fallback")],
  ];
  return (
    <>
      <ul className="flex flex-col gap-1">{rows.map(([k, label, hint]) => (
        <li key={k} className="flex flex-wrap items-center gap-2">
          <Icon name={a[k].done ? "check_circle" : "radio_button_unchecked"} size={20} className={a[k].done ? "text-muted" : "text-ink-soft"} />
          <span className="text-label-lg w-40">{label}</span>
          <Link href={a[k].href} className="text-body-sm text-ink underline">{hint}</Link>
        </li>
      ))}</ul>
      {number && canManage && <Recording wsId={wsId} number={number} />}
      {number && canManage && (
        <details className="rounded-lg bg-panel p-2">
          <summary className="text-label-lg cursor-pointer">{tr("telephony.answering.special")}</summary>
          <div className="flex flex-col gap-2 mt-2">
            <Field label={tr("telephony.answering.phoneGreeting")}><Textarea value={f.greeting} maxLength={500} onChange={(e) => setF({ ...f, greeting: e.target.value })} /></Field>
            <Field label={tr("telephony.answering.style")}><Textarea value={f.speaking_style} maxLength={1000} onChange={(e) => setF({ ...f, speaking_style: e.target.value })} /></Field>
            <div><Button type="button" variant="tonal" onClick={() => save.run()} disabled={save.pending}>{tr("telephony.answering.save")}</Button></div>
            <ErrorBox error={save.error} />
          </div>
        </details>
      )}
    </>
  );
}

function TestCall({ wsId, t, canManage }: { wsId: string; t: Telephony; canManage: boolean }) {
  const router = useRouter();
  const tr = useT("settings");
  const locale = useLocale();
  const [own, setOwn] = useState(true);
  const start = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/tests`, { method: "POST", body: JSON.stringify({ called_business_number: own }) }); router.refresh(); });
  const waiting = t.test?.status === "waiting";
  useEffect(() => {
    if (!waiting) return;
    const id = setInterval(() => router.refresh(), 5000);
    return () => clearInterval(id);
  }, [waiting, router]);
  if (!t.destination) return <p className="text-body-sm text-ink-soft">{tr("telephony.test.notYet")}</p>;
  return (
    <>
      <p className="text-body-md">{tr("telephony.test.introBefore")} <strong>{tr("telephony.test.ownNumber")}</strong> {tr("telephony.test.introAfter", { number: t.business_number ?? "" })}</p>
      {t.test?.status === "passed" && <Alert kind="ok">{tr("telephony.test.passed")}{t.test.simulated ? tr("telephony.test.simulated") : ""}</Alert>}
      {(t.test?.status === "failed" || t.test?.status === "expired") && <Alert kind="warn">{t.test.reason ?? tr("telephony.test.failed")}</Alert>}
      {waiting && <Alert kind="info" icon="phone_in_talk">{tr("telephony.test.waiting", { time: new Date(t.test!.expires_at).toLocaleTimeString(HTML_LANG[locale], { hour: "2-digit", minute: "2-digit" }) })}</Alert>}
      {canManage && !waiting && (
        <>
          <label className="flex items-start gap-2 text-body-sm">
            <input type="checkbox" className="mt-0.5 w-5 h-5" checked={own} onChange={(e) => setOwn(e.target.checked)} />
            {tr("telephony.test.own")}
          </label>
          <div><Button type="button" icon="call" onClick={() => start.run()} disabled={start.pending}>{t.test ? tr("telephony.test.again") : tr("telephony.test.start")}</Button></div>
        </>
      )}
      <ErrorBox error={start.error} />
    </>
  );
}

function Activate({ wsId, t, canManage }: { wsId: string; t: Telephony; canManage: boolean }) {
  const router = useRouter();
  const tr = useT("settings");
  const on = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/activate`, { method: "POST" }); router.refresh(); });
  const off = useSubmit(async () => { await api(`/workspaces/${wsId}/telephony/pause`, { method: "POST" }); router.refresh(); });
  const ready = t.test?.status === "passed" && t.agreement_accepted;
  if (t.active) return (
    <>
      <Alert kind="ok">{tr("telephony.activate.active")}</Alert>
      {canManage && <div><Button type="button" variant="tonal" icon="pause" onClick={() => off.run()} disabled={off.pending}>{tr("telephony.activate.pause")}</Button></div>}
      <ErrorBox error={off.error} />
    </>
  );
  return (
    <>
      <p className="text-body-md">{ready ? tr("telephony.activate.ready") : tr("telephony.activate.notReady")}</p>
      {canManage && <div><Button type="button" icon="power_settings_new" onClick={() => on.run()} disabled={!ready || on.pending}>{tr("telephony.activate.button")}</Button></div>}
      <ErrorBox error={on.error} />
    </>
  );
}

/** «Sprog over for jeres kunder»: the language Peter answers, recognises speech and greets in. Saved as the workspace's
 *  default conversation language (the only enabled one) via PUT /workspaces/{id}/languages, keeping the other fields. */
function CustomerLanguage({ wsId, languages, canManage }: { wsId: string; languages: Languages; canManage: boolean }) {
  const router = useRouter();
  const tr = useT("settings");
  const [cur, setCur] = useState(languages);
  const [saved, setSaved] = useState(false);
  const save = useSubmit(async (code: string) => {
    setSaved(false);
    const next = await api<Languages>(`/workspaces/${wsId}/languages`, { method: "PUT", body: JSON.stringify({
      expected_version: cur.version, interface_language: cur.interface_language, report_language: cur.report_language,
      default_conversation_language: code, enabled_conversation_languages: [code] }) });
    setCur(next); setSaved(true); router.refresh();
  });
  return (
    <div className="flex flex-col gap-2">
      <Field label={tr("telephony.language.label")} hint={tr("telephony.language.help")}>
        <Select value={cur.default_conversation_language} disabled={!canManage || save.pending} onChange={(e) => save.run(e.target.value)}>
          {LANGUAGES.map((l) => <option key={l} value={l}>{LOCALE_NAMES[l]}</option>)}
          {!(LANGUAGES as readonly string[]).includes(cur.default_conversation_language) && <option value={cur.default_conversation_language}>{cur.default_conversation_language}</option>}
        </Select>
      </Field>
      {saved && <Alert kind="ok">{tr("telephony.language.saved")}</Alert>}
      {save.error && (save.error.code === "version_conflict" ? <Alert>{tr("telephony.language.conflict")}</Alert> : <ErrorBox error={save.error} />)}
    </div>
  );
}

export function TelephonySetup({ wsId, t, numbers, canManage, languages = null }: { wsId: string; t: Telephony; numbers: PhoneNumber[]; canManage: boolean; languages?: Languages | null }) {
  const tr = useT("settings");
  const c = t.status.code;
  const s1 = t.verified && (!t.documents.required || ["submitted", "approved"].includes(t.documents.status)) ? "done" : "current";
  const s2 = t.destination ? "done" : s1 === "done" ? "current" : "later";
  const s3 = Object.values(t.answering).every((x) => x.done) ? "done" : t.destination ? "current" : "later";
  const s4 = t.test?.status === "passed" ? "done" : t.destination ? "current" : "later";
  const s5 = t.active ? "done" : t.test?.status === "passed" ? "current" : "later";
  const dest = numbers.find((n) => n.e164 === t.destination?.e164) ?? null;
  return (
    <div className="flex flex-col gap-3">
      <div className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1 max-w-2xl">
          <span className="eyebrow">{tr("telephony.setup.eyebrow")}</span>
          <h2 className="font-display text-headline-sm text-ink font-bold">{tr("telephony.setup.title")}</h2>
          <p className="text-body-md"><strong>{tr("telephony.setup.nextStep")}</strong> {t.status.next_step}</p>
          <p className="text-body-sm text-ink-soft">{tr("telephony.setup.introBefore")} <Link href="/app/inbox" className="text-ink underline">{tr("telephony.setup.inbox")}</Link>{tr("telephony.setup.introAfter")}</p>
        </div>
        <span className={`px-3 py-1 rounded-full text-label-lg font-semibold ${TONE[c]}`}>{t.status.label}</span>
      </div>
      <Step n={1} title={tr("telephony.setup.step1")} state={s1}>
        <BusinessNumber wsId={wsId} t={t} canManage={canManage} />
        {t.documents.required && t.business_number && <Documents wsId={wsId} t={t} canManage={canManage} />}
      </Step>
      <Step n={2} title={tr("telephony.setup.step2")} state={s2}><Connect wsId={wsId} t={t} canManage={canManage} /></Step>
      <Step n={3} title={tr("telephony.setup.step3")} state={s3}>{languages && <CustomerLanguage wsId={wsId} languages={languages} canManage={canManage} />}<Answering t={t} number={dest} wsId={wsId} canManage={canManage} /></Step>
      <Step n={4} title={tr("telephony.setup.step4")} state={s4}><TestCall wsId={wsId} t={t} canManage={canManage} /></Step>
      <Step n={5} title={tr("telephony.setup.step5")} state={s5}><Activate wsId={wsId} t={t} canManage={canManage} /></Step>
    </div>
  );
}

