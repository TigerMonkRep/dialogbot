"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, Select, Textarea, useSubmit } from "@/components/ui";
import { kr } from "../leads/format";
import type { Campaign, Dnc, PhoneNumber } from "./format";
import { useLocale, useRaw, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";


const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

export function Num({ n, dark = false }: { n: number; dark?: boolean }) {
  return <span className={`inline-flex w-10 h-10 shrink-0 rounded-[10px] items-center justify-center font-display font-extrabold text-[20px] ${dark ? "bg-ink text-paper" : "bg-highlight text-ink"}`} aria-hidden>{n}</span>;
}

/** The page only shows campaigns when «ringe kunder op» is chosen; this switches it on (the same setting as in trin 1). */
export function EnableOutbound({ wsId, goals }: { wsId: string; goals: Record<string, unknown> & { version: number } }) {
  const router = useRouter();
  const t = useT("app");
  const on = useSubmit(async () => {
    const { version, ...g } = goals;
    await api(`/workspaces/${wsId}/goals`, { method: "PUT", body: JSON.stringify({ ...g, callback: true, expected_version: version }) });
    router.refresh();
  });
  return <div className="flex flex-col gap-1"><Button type="button" onClick={() => on.run()} disabled={on.pending}>{on.pending ? t("campaigns.enable.pending") : t("campaigns.enable.button")}</Button><ErrorBox error={on.error} /></div>;
}

export function NewCampaign({ wsId }: { wsId: string }) {
  const router = useRouter();
  const t = useT("app");
  const [f, setF] = useState({ name: "", purpose: "" });
  const save = useSubmit(async () => {
    const c = await api<Campaign>(`/workspaces/${wsId}/campaigns`, { method: "POST", body: JSON.stringify(f) });
    router.push(`/app/kampagner/${c.id}`);
  });
  return (
    <form className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <h2 className="font-display text-headline-sm text-ink">{t("campaigns.new.title")}</h2>
      <Field label={t("campaigns.new.name")} error={fieldError(save.error, "name")}><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder={t("campaigns.new.namePlaceholder")} /></Field>
      <Field label={t("campaigns.new.purpose")} hint={t("campaigns.new.purposeHint")}>
        <Textarea value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} />
      </Field>
      <ErrorBox error={save.error} />
      <div><Button type="submit" icon="add" disabled={save.pending || !f.name.trim()}>{t("campaigns.new.create")}</Button></div>
    </form>
  );
}

export function CampaignEditor({ wsId, c, numbers, canManage }: { wsId: string; c: Campaign; numbers: PhoneNumber[]; canManage: boolean }) {
  const router = useRouter();
  const t = useT("app");
  const raw = useRaw();
  const wd = raw<string[]>("app.time.weekdaysShort");
  const [f, setF] = useState({ name: c.name, purpose: c.purpose, opening: c.opening, questions: c.questions.join("\n"), success: c.success,
    phone_number_id: c.phone_number_id ?? "", call_days: c.call_days, call_from: c.call_from, call_to: c.call_to });
  const [note, setNote] = useState<string | null>(null);
  const locked = !canManage || c.status === "running" || c.status === "completed";
  const suggest = useSubmit(async () => {
    const s = await api<{ opening: string; questions: string[]; success: string }>(`/workspaces/${wsId}/campaigns/script-suggestions`, { method: "POST", body: JSON.stringify({ purpose: f.purpose }) });
    setF((cur) => ({ ...cur, opening: s.opening, questions: s.questions.join("\n"), success: s.success }));
    setNote(t("campaigns.editor.suggested"));
  });
  const asked = useRef(false);
  useEffect(() => {
    if (!asked.current && !locked && !c.opening && c.questions.length === 0) { asked.current = true; suggest.run(); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useSubmit(async () => {
    await api(`/workspaces/${wsId}/campaigns/${c.id}`, { method: "PUT", body: JSON.stringify({ ...f, expected_version: c.version,
      phone_number_id: f.phone_number_id || null, questions: f.questions.split("\n").map((q) => q.trim()).filter(Boolean) }) });
    setNote(t("campaigns.editor.saved")); router.refresh();
  });
  const set = (k: "name" | "purpose" | "opening" | "questions" | "success" | "call_from" | "call_to" | "phone_number_id") =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => { setNote(null); setF({ ...f, [k]: e.target.value }); };
  return (
    <form className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-3 font-display font-extrabold text-[20px] text-ink"><Num n={2} />{t("campaigns.editor.what")}</h2>
        {!locked && <Button type="button" variant="tonal" icon="auto_awesome" onClick={() => suggest.run()} disabled={suggest.pending}>{suggest.pending ? t("campaigns.editor.suggesting") : t("campaigns.editor.suggest")}</Button>}
      </div>
      {c.status === "running" && <Alert kind="info">{t("campaigns.editor.running")}</Alert>}
      {note && <Alert kind="ok">{note}</Alert>}
      <fieldset disabled={locked} className="flex flex-col gap-2">
        <Field label={t("leads.editor.name")}><Input value={f.name} onChange={set("name")} /></Field>
        <Field label={t("campaigns.editor.purpose")} error={fieldError(save.error, "purpose")}><Textarea value={f.purpose} onChange={set("purpose")} /></Field>
        <Field label={t("campaigns.editor.opening")} hint={t("campaigns.editor.openingHint")}>
          <Textarea value={f.opening} onChange={set("opening")} />
        </Field>
        <Field label={t("campaigns.editor.questions")}><Textarea value={f.questions} onChange={set("questions")} /></Field>
        <Field label={t("campaigns.editor.success")}><Input value={f.success} onChange={set("success")} /></Field>
        <Field label={t("campaigns.editor.fromNumber")} hint={numbers.length === 0 ? t("campaigns.editor.addNumber") : undefined}>
          <Select value={f.phone_number_id} onChange={set("phone_number_id")}>
            <option value="">{t("campaigns.editor.chooseNumber")}</option>
            {numbers.map((n) => <option key={n.id} value={n.id}>{n.e164}{n.label ? ` (${n.label})` : ""}</option>)}
          </Select>
        </Field>
        <h2 className="flex items-center gap-3 font-display font-extrabold text-[20px] text-ink mt-2"><Num n={3} />{t("campaigns.editor.when")}</h2>
        <p className="text-body-sm text-ink-soft">{t("campaigns.editor.whenSub")}</p>
        <div className="flex flex-col gap-1">
          <span className="text-label-md font-semibold">{t("campaigns.editor.onlyCalls")}</span>
          <div className="flex flex-wrap gap-2">{DAYS.map((k, i) => (
            <label key={k} className="flex items-center gap-1 text-body-md">
              <input type="checkbox" className="w-4 h-4 accent-ink" checked={f.call_days.includes(k)}
                onChange={(e) => setF({ ...f, call_days: e.target.checked ? [...f.call_days, k] : f.call_days.filter((d) => d !== k) })} />{wd[i]}
            </label>
          ))}</div>
          <div className="grid grid-cols-2 gap-2 max-w-xs">
            <Field label={t("campaigns.editor.from")}><Input type="time" value={f.call_from} onChange={set("call_from")} /></Field>
            <Field label={t("campaigns.editor.to")} error={fieldError(save.error, "call_to")}><Input type="time" value={f.call_to} onChange={set("call_to")} /></Field>
          </div>
        </div>
      </fieldset>
      <ErrorBox error={save.error ?? suggest.error} />
      {!locked && <div><Button type="submit" icon="save" disabled={save.pending}>{save.pending ? t("common.saving") : t("campaigns.editor.save")}</Button></div>}
    </form>
  );
}

type ImportResult = { added: number; duplicates: number; blocked: number; invalid_count: number; invalid: { row: number; value: string; reason: string }[] };

export function ImportContacts({ wsId, id }: { wsId: string; id: string }) {
  const router = useRouter();
  const t = useT("app");
  const [f, setF] = useState({ csv: "", kind: "business", consent_source: "" });
  const [res, setRes] = useState<ImportResult | null>(null);
  const run = useSubmit(async () => {
    const r = await api<ImportResult>(`/workspaces/${wsId}/campaigns/${id}/contacts/import`, { method: "POST", body: JSON.stringify(f) });
    setRes(r); setF({ ...f, csv: "" }); router.refresh();
  });
  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => { const file = e.target.files?.[0]; if (file) setF({ ...f, csv: await file.text() }); };
  return (
    <form className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); run.run(); }}>
      <h2 className="font-display text-headline-sm text-ink">{t("campaigns.import.title")}</h2>
      <p className="text-body-sm text-ink-soft">{t("campaigns.import.intro")}</p>
      {res && <Alert kind="ok">{t("campaigns.import.added", { n: res.added })}{res.duplicates ? `, ${t("campaigns.import.duplicates", { n: res.duplicates })}` : ""}{res.blocked ? `, ${t("campaigns.import.blocked", { n: res.blocked })}` : ""}{res.invalid_count ? `, ${t("campaigns.import.invalid", { n: res.invalid_count, rows: res.invalid.map((x) => x.row).slice(0, 5).join(", ") })}` : ""}.</Alert>}
      <Field label={t("campaigns.import.file")}><input type="file" accept=".csv,text/csv,text/plain" onChange={onFile} className="block w-full min-w-0 text-body-md" /></Field>
      <Field label={t("campaigns.import.paste")} error={fieldError(run.error, "csv")}><Textarea value={f.csv} onChange={(e) => setF({ ...f, csv: e.target.value })} placeholder={t("campaigns.import.pastePlaceholder")} /></Field>
      <fieldset className="flex flex-col gap-1">
        <legend className="text-label-md font-semibold mb-1">{t("campaigns.import.who")}</legend>
        <label className="flex items-start gap-1 text-body-md"><input type="radio" name="kind" className="mt-1 accent-ink" checked={f.kind === "business"} onChange={() => setF({ ...f, kind: "business" })} />{t("campaigns.import.businesses")}</label>
        <label className="flex items-start gap-1 text-body-md"><input type="radio" name="kind" className="mt-1 accent-ink" checked={f.kind === "consumer"} onChange={() => setF({ ...f, kind: "consumer" })} />{t("campaigns.import.consumers")}</label>
      </fieldset>
      <Field label={t("campaigns.import.consent")} error={fieldError(run.error, "consent_source")} hint={t("campaigns.import.consentHint")}>
        <Input value={f.consent_source} onChange={(e) => setF({ ...f, consent_source: e.target.value })} placeholder={t("campaigns.import.consentPlaceholder")} />
      </Field>
      <ErrorBox error={run.error} />
      <div><Button type="submit" icon="upload" disabled={run.pending || !f.csv.trim() || f.consent_source.trim().length < 5}>{run.pending ? t("campaigns.import.importing") : t("campaigns.import.title")}</Button></div>
    </form>
  );
}

export function StartCampaign({ wsId, c, checklist }: { wsId: string; c: Campaign; checklist: string[] }) {
  const router = useRouter();
  const t = useT("app");
  const lang = HTML_LANG[useLocale()];
  const [checked, setChecked] = useState<boolean[]>(checklist.map(() => false));
  const start = useSubmit(async () => {
    await api(`/workspaces/${wsId}/campaigns/${c.id}/start`, { method: "POST", body: JSON.stringify({ expected_version: c.version, legal_confirmed: checked.every(Boolean), accept_max_net_minor: c.max_cost.net_minor }) });
    router.refresh();
  });
  const pause = useSubmit(async () => { await api(`/workspaces/${wsId}/campaigns/${c.id}/pause`, { method: "POST", body: "{}" }); router.refresh(); });
  if (c.status === "completed") return <Alert kind="ok">{t("campaigns.start.completed")}</Alert>;
  if (c.status === "running") return (
    <div className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-wrap items-center gap-2">
      <p className="text-body-md grow">{t("campaigns.start.running")}</p>
      <Button type="button" variant="tonal" icon="pause" onClick={() => pause.run()} disabled={pause.pending}>{t("campaigns.start.pause")}</Button>
      <ErrorBox error={pause.error} />
    </div>
  );
  const pending = c.counts.by_status.pending ?? 0;
  return (
    <div className="bg-highlight rounded-2xl p-4 md:p-5 border-2 border-ink flex flex-col gap-2">
      <span className="eyebrow !text-ink">{t("campaigns.start.before")}</span>
      <h2 className="font-display font-extrabold text-[20px] text-ink">{c.status === "paused" ? t("campaigns.start.resumeTitle") : t("campaigns.start.heading", { n: pending, max: kr(c.max_cost.net_minor, lang, c.pricing.currency) })}</h2>
      {c.outbound_problem && <Alert kind="warn">{c.outbound_problem}</Alert>}
      <p className="text-body-md">{t("campaigns.start.body", { n: pending, max: kr(c.max_cost.net_minor, lang, c.pricing.currency), gross: kr(c.max_cost.gross_minor, lang, c.pricing.currency), withPackage: kr(c.max_cost_with_package.net_minor, lang, c.pricing.currency), maxMinutes: c.max_minutes, remaining: c.package.remaining, included: c.package.included, minute: kr(c.pricing.minute_net_minor, lang, c.pricing.currency), attempts: c.pricing.max_attempts, minutes: Math.round(c.pricing.max_connected_seconds / 60) })}</p>
      <fieldset className="flex flex-col gap-1">
        <legend className="text-label-md font-semibold mb-1">{t("campaigns.start.confirm")}</legend>
        {checklist.map((item, i) => (
          <label key={i} className="flex items-start gap-1 text-body-md">
            <input type="checkbox" className="mt-1 w-4 h-4 accent-ink" checked={checked[i]} onChange={(e) => setChecked(checked.map((v, j) => (j === i ? e.target.checked : v)))} />{item}
          </label>
        ))}
      </fieldset>
      <ErrorBox error={start.error} />
      <div><Button type="button" icon="call" onClick={() => start.run()} disabled={start.pending || !checked.every(Boolean) || pending === 0 || !!c.outbound_problem}>{start.pending ? t("campaigns.start.starting") : c.status === "paused" ? t("campaigns.start.resume") : t("campaigns.start.start")}</Button></div>
    </div>
  );
}

export function RemoveContact({ wsId, campaignId, id }: { wsId: string; campaignId: string; id: string }) {
  const router = useRouter();
  const t = useT("app");
  const r = useSubmit(async () => { await api(`/workspaces/${wsId}/campaigns/${campaignId}/contacts/${id}`, { method: "DELETE" }); router.refresh(); });
  return <button type="button" onClick={() => r.run()} disabled={r.pending} className="text-label-md text-danger hover:underline disabled:opacity-50">{t("campaigns.remove")}</button>;
}

export function DoNotCallList({ wsId, items, canManage }: { wsId: string; items: Dnc[]; canManage: boolean }) {
  const router = useRouter();
  const t = useT("app");
  const [f, setF] = useState({ phone: "", reason: "" });
  const add = useSubmit(async () => { await api(`/workspaces/${wsId}/do-not-call`, { method: "POST", body: JSON.stringify(f) }); setF({ phone: "", reason: "" }); router.refresh(); });
  const del = useSubmit(async (id: string) => { await api(`/workspaces/${wsId}/do-not-call/${id}`, { method: "DELETE" }); router.refresh(); });
  return (
    <div className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
      <h2 className="font-display text-headline-sm text-ink">{t("campaigns.dnc.title")}</h2>
      <p className="text-body-sm text-ink-soft">{t("campaigns.dnc.intro")}</p>
      {items.length > 0 && <ul className="flex flex-col gap-1">{items.map((d) => (
        <li key={d.id} className="flex flex-wrap items-center gap-2 p-2 rounded-lg bg-panel text-body-md">
          <span className="text-label-lg">{d.phone}</span>
          <span className="text-ink-soft">{d.reason || (d.source === "call" ? t("campaigns.dnc.optedOut") : "")}</span>
          {canManage && d.source !== "call" && <button type="button" className="ml-auto text-label-md text-danger hover:underline" onClick={() => del.run(d.id)}>{t("campaigns.remove")}</button>}
        </li>
      ))}</ul>}
      <form className="grid grid-cols-1 md:grid-cols-[1fr_2fr_auto] gap-2 items-end" onSubmit={(e) => { e.preventDefault(); add.run(); }}>
        <Field label={t("campaigns.dnc.phone")} error={fieldError(add.error, "phone")}><Input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label={t("campaigns.dnc.reason")}><Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
        <Button type="submit" variant="tonal" icon="block" disabled={add.pending || !f.phone.trim()}>{t("campaigns.dnc.block")}</Button>
      </form>
      <ErrorBox error={del.error} />
    </div>
  );
}
