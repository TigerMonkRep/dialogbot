"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, useSubmit } from "@/components/ui";
import { useLocale, useRaw, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";

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

const STATUS: Record<Connector["status"], string> = {
  connected: "bg-success-soft text-success",
  not_connected: "bg-line text-ink-soft",
  error: "bg-danger-soft text-danger",
  not_implemented: "bg-panel-deep text-ink-soft",
};
const RUN: Record<ActionRun["status"], string> = {
  ok: "bg-success-soft text-success",
  failed: "bg-danger-soft text-danger",
  refused: "bg-accent-soft text-accent-deep",
};
const ICON: Record<string, string> = { calendar: "calendar_month", messaging: "sms", automation: "webhook", crm: "contacts",
  accounting: "receipt_long", booking: "event_available", field_service: "construction", staffing: "badge" };
const key = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Math.random()));

export function Integrations({ wsId, data, canManage }: { wsId: string; data: Catalogue; canManage: boolean }) {
  const params = useSearchParams();
  const router = useRouter();
  const t = useT("settings");
  const raw = useRaw();
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  useEffect(() => {
    const ok = params.get("connected"), err = params.get("error");
    if (!ok && !err) return;
    const LABEL = raw<Record<string, string>>("settings.integrations.label") ?? {};
    const name = LABEL[params.get("connector") ?? ok ?? ""] ?? ok ?? params.get("connector") ?? t("integrations.theConnection");
    setNotice(ok ? { kind: "ok", text: t("integrations.connectedNotice", { name: LABEL[ok] ?? ok }) }
      : { kind: "error", text: t("integrations.errorNotice", { name, error: err ?? "" }) });
    router.replace("/app/settings/integrationer");
  }, [params, router, t, raw]);

  const ready = data.items.filter((c) => c.availability === "ready");
  const zapier = data.items.filter((c) => c.availability !== "ready" && c.zapier_note);
  const coming = data.items.filter((c) => c.availability !== "ready" && !c.zapier_note);
  return (
    <section className="flex flex-col gap-4">
      <div>
        <span className="eyebrow">{t("integrations.eyebrow")}</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{t("integrations.title")}</h1>
        <p className="text-body-sm text-ink-soft max-w-3xl">{t("integrations.intro")}</p>
      </div>
      {data.simulated && <Alert kind="warn">{t("integrations.simulated")}</Alert>}
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      {!canManage && <Alert kind="info">{t("integrations.onlyAdmins")}</Alert>}

      <h2 className="font-display text-headline-sm text-ink">{t("integrations.ready")}</h2>
      <ul className="grid gap-3 lg:grid-cols-2">{ready.map((c) => <ConnectorCard key={c.key} wsId={wsId} c={c} canManage={canManage} />)}</ul>

      {zapier.length > 0 && <>
        <h2 className="font-display text-headline-sm text-ink">{t("integrations.viaZapier")}</h2>
        <p className="text-body-sm text-ink-soft max-w-3xl">{t("integrations.viaZapierIntro")}</p>
        <ul className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">{zapier.map((c) => <Coming key={c.key} c={c} />)}</ul>
      </>}
      {coming.length > 0 && <>
        <h2 className="font-display text-headline-sm text-ink">{t("integrations.coming")}</h2>
        <ul className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">{coming.map((c) => <Coming key={c.key} c={c} />)}</ul>
      </>}

      <Runs runs={data.recent_actions} items={data.items} />
    </section>
  );
}

function Coming({ c }: { c: Connector }) {
  const t = useT("settings");
  return (
    <li className="rounded-xl bg-panel p-3 flex flex-col gap-1">
      <span className="flex items-center gap-1 text-label-lg text-ink"><Icon name={ICON[c.category] ?? "extension"} size={18} />{c.label}</span>
      <span className="text-body-sm text-ink-soft">{c.description}</span>
      <span className="text-label-sm text-ink-soft">{c.zapier_note || t("integrations.comingNote")}</span>
    </li>
  );
}

function ConnectorCard({ wsId, c, canManage }: { wsId: string; c: Connector; canManage: boolean }) {
  const router = useRouter();
  const t = useT("settings");
  const locale = useLocale();
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
  const label = t(`integrations.status.${c.status}`);
  const cls = STATUS[c.status];
  const connected = c.status === "connected" || c.status === "error";
  const err = connect.error ?? runTest.error ?? save.error ?? off.error;

  return (
    <li className="rounded-2xl bg-paper border-2 border-ink p-3 flex flex-col gap-2" data-connector={c.key}>
      <div className="flex flex-wrap items-center gap-2">
        <Icon name={ICON[c.category] ?? "extension"} size={22} className="text-ink" />
        <h3 className="font-title-md text-title-md text-ink font-bold">{c.label}</h3>
        <span className={`px-2 py-0.5 rounded-full text-label-sm ${cls}`}>{label}{connected && c.simulated ? t("integrations.simulatedSuffix") : ""}</span>
      </div>
      <p className="text-body-sm text-ink-soft">{c.description}</p>
      {c.account_label && connected && <p className="text-body-sm">{t("integrations.connectedAs")} <strong>{c.account_label}</strong>{c.last_ok_at ? t("integrations.lastConfirmed", { when: new Date(c.last_ok_at).toLocaleString(HTML_LANG[locale], { dateStyle: "short", timeStyle: "short" }) }) : ""}</p>}
      {c.reason && <p className="text-body-sm text-ink-soft">{c.reason}{c.key === "bookings" && <> <Link href="/app/bookings" className="text-ink underline">{t("integrations.goToBookings")}</Link></>}</p>}
      {c.error && <Alert kind="error">{c.error}</Alert>}
      {c.actions.length > 0 && (
        <ul className="flex flex-wrap gap-1" aria-label={t("integrations.actionsAria")}>
          {c.actions.map((a) => <li key={a.name} title={a.description} className="px-2 py-0.5 rounded-lg bg-panel text-label-sm">{a.label}{a.confirm ? t("integrations.needsYes") : ""}</li>)}
        </ul>
      )}
      {c.events.length > 0 && <p className="text-label-sm text-ink-soft">{t("integrations.events")}</p>}

      {secret && (
        <div className="rounded-lg bg-accent-soft text-accent-deep p-2 flex flex-col gap-1" role="status">
          <span className="text-label-md font-semibold">{t("integrations.secretTitle")}</span>
          <code className="break-all select-all font-mono text-body-sm">{secret}</code>
          <span className="text-body-sm">{t("integrations.secretNote")}</span>
          <Button variant="tonal" className="self-start" onClick={() => navigator.clipboard?.writeText(secret).catch(() => undefined)}>{t("integrations.copy")}</Button>
        </div>
      )}

      {canManage && c.status !== "not_implemented" && c.key !== "bookings" && (
        <div className="flex flex-col gap-2">
          {isSink && (
            <Field label={c.key === "zapier" ? t("integrations.zapierUrl") : c.key === "make" ? t("integrations.makeUrl") : t("integrations.webhookUrl")}>
              <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder={c.key === "make" ? "https://hook.eu1.make.com/…" : c.key === "zapier" ? "https://hooks.zapier.com/hooks/catch/…" : t("integrations.webhookPlaceholder")} />
            </Field>
          )}
          {c.key === "twilio_sms" && (
            <Field label={t("integrations.sender")} hint={t("integrations.senderHint")}>
              <Input value={sender} maxLength={16} onChange={(e) => setSender(e.target.value)} />
            </Field>
          )}
          <div className="flex flex-wrap gap-2">
            {!connected && <Button icon="link" disabled={connect.pending || (isSink && !url.trim())} onClick={() => connect.run()}>{connect.pending ? t("integrations.connecting") : t("integrations.connect")}</Button>}
            {connected && <Button variant="tonal" icon="network_check" disabled={runTest.pending} onClick={() => runTest.run()}>{runTest.pending ? t("integrations.testing") : t("integrations.test")}</Button>}
            {connected && (isSink || c.key === "twilio_sms") && <Button variant="outline" icon="save" disabled={save.pending} onClick={() => save.run()}>{t("integrations.saveSetup")}</Button>}
            {connected && !confirmOff && <Button variant="ghost" icon="link_off" onClick={() => setConfirmOff(true)}>{t("integrations.disconnect")}</Button>}
            {confirmOff && <>
              <Button variant="danger" disabled={off.pending} onClick={() => off.run()}>{t("integrations.confirmDisconnect", { name: c.label })}</Button>
              <Button variant="ghost" onClick={() => setConfirmOff(false)}>{t("integrations.undo")}</Button>
            </>}
          </div>
          {test && (test.ok ? <Alert kind="ok">{t("integrations.works", { suffix: c.simulated ? t("integrations.simulatedSuffix") : "" })}</Alert> : <Alert kind="error">{test.error}</Alert>)}
          {err && (err.code === "version_conflict" ? <Alert>{t("integrations.conflict")}</Alert> : <ErrorBox error={err} />)}
        </div>
      )}
    </li>
  );
}

function Runs({ runs, items }: { runs: ActionRun[]; items: Connector[] }) {
  const t = useT("settings");
  const locale = useLocale();
  const name = (k: string) => items.find((c) => c.key === k)?.label ?? k;
  return (
    <div className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
      <h2 className="font-display text-headline-sm text-ink">{t("integrations.recent")}</h2>
      {runs.length === 0 ? <p className="text-body-sm text-ink-soft">{t("integrations.noRuns")}</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-body-sm">
            <thead><tr className="text-left text-ink-soft"><th className="pr-3">{t("integrations.th.time")}</th><th className="pr-3">{t("integrations.th.channel")}</th><th className="pr-3">{t("integrations.th.system")}</th><th className="pr-3">{t("integrations.th.action")}</th><th>{t("integrations.th.status")}</th></tr></thead>
            <tbody>{runs.map((r) => (
              <tr key={r.id} className="align-top border-t border-line/40">
                <td className="pr-3 py-1 tabular-nums whitespace-nowrap">{new Date(r.created_at).toLocaleString(HTML_LANG[locale], { dateStyle: "short", timeStyle: "short" })}</td>
                <td className="pr-3 py-1">{["phone", "webchat", "test", "system"].includes(r.channel) ? t(`integrations.channel.${r.channel}`) : r.channel}</td>
                <td className="pr-3 py-1">{name(r.connector)}</td>
                <td className="pr-3 py-1">{r.conversation_id ? <Link className="text-ink underline" href={`/app/inbox/${r.conversation_id}`}>{r.label}</Link> : r.label}{r.simulated ? t("integrations.simulatedSuffix") : ""}{r.error ? <><br /><span className="text-ink-soft">{r.error}</span></> : null}</td>
                <td className="py-1"><span className={`px-2 py-0.5 rounded-full text-label-sm ${RUN[r.status]}`}>{t(`integrations.run.${r.status}`)}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
