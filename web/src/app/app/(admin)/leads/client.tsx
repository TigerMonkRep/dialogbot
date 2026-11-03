"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Button, ErrorBox, inputCls, useSubmit } from "@/components/ui";
import { BILL, PIPE, QUAL, kr, type Lead } from "./format";
import { useLocale, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";

export function LeadEditor({ wsId, lead }: { wsId: string; lead: Lead }) {
  const router = useRouter();
  const t = useT("app");
  const [l, setL] = useState(lead);
  const [form, setForm] = useState({ contact_name: lead.contact_name, contact_email: lead.contact_email ?? "", contact_phone: lead.contact_phone ?? "",
    need_summary: lead.need_summary, qualification_status: lead.qualification_status, qualification_reason: lead.qualification_reason ?? "", pipeline_status: lead.pipeline_status });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });
  const decided = l.billing_status !== "pending";
  const save = useSubmit(async () => {
    const body: Record<string, unknown> = { expected_version: l.version, ...form, contact_email: form.contact_email || null, contact_phone: form.contact_phone || null, qualification_reason: form.qualification_reason || null };
    if (decided) delete body.qualification_status;
    const next = await api<Lead>(`/workspaces/${wsId}/leads/${l.id}`, { method: "PATCH", body: JSON.stringify(body) });
    setL(next); router.refresh();
  });
  const field = (id: keyof typeof form, label: string, type = "text") => (
    <div><label htmlFor={`l-${id}`} className="block text-label-md font-semibold mb-1">{label}</label><input id={`l-${id}`} type={type} className={inputCls} value={form[id]} onChange={set(id)} /></div>
  );
  return (
    <form className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <h2 className="font-display text-headline-sm text-ink">{t("leads.editor.title")}</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">{field("contact_name", t("leads.editor.name"))}{field("contact_email", t("leads.editor.email"), "email")}{field("contact_phone", t("leads.editor.phone"), "tel")}</div>
      <div><label htmlFor="l-need" className="block text-label-md font-semibold mb-1">{t("leads.editor.need")}</label><textarea id="l-need" rows={3} className={inputCls} value={form.need_summary} onChange={set("need_summary")} /></div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div><label htmlFor="l-qual" className="block text-label-md font-semibold mb-1">{t("leads.editor.qualification")}</label>
          <select id="l-qual" className={inputCls} value={form.qualification_status} onChange={set("qualification_status")} disabled={decided}>{Object.keys(QUAL).map((k) => <option key={k} value={k}>{t(`leads.qual.${k}`)}</option>)}</select>
          {decided && <p className="text-body-sm text-ink-soft mt-1">{t("leads.editor.locked")}</p>}</div>
        <div><label htmlFor="l-reason" className="block text-label-md font-semibold mb-1">{t("leads.editor.reason")}</label><input id="l-reason" className={inputCls} value={form.qualification_reason} onChange={set("qualification_reason")} maxLength={500} /></div>
        <div><label htmlFor="l-pipe" className="block text-label-md font-semibold mb-1">{t("leads.editor.pipeline")}</label>
          <select id="l-pipe" className={inputCls} value={form.pipeline_status} onChange={set("pipeline_status")}>{PIPE.map((k) => <option key={k} value={k}>{t(`leads.pipe.${k}`)}</option>)}</select></div>
      </div>
      <ErrorBox error={save.error} />
      <div><Button type="submit" icon="save" disabled={save.pending}>{save.pending ? t("common.saving") : t("common.save")}</Button></div>
    </form>
  );
}

export function BillingPanel({ wsId, lead, canApprove, agreement }: { wsId: string; lead: Lead; canApprove: boolean; agreement: { version: number; model: string; lead_fee: { net_minor: number } } | null }) {
  const router = useRouter();
  const t = useT("app");
  const lang = HTML_LANG[useLocale()];
  const [reason, setReason] = useState("");
  const [key] = useState(() => crypto.randomUUID());
  const decide = useSubmit(async (d: "approve" | "reject") => {
    await api(`/workspaces/${wsId}/leads/${lead.id}/${d}`, { method: "POST", headers: { "Idempotency-Key": `${key}-${d}` }, body: JSON.stringify({ reason: reason || null }) });
    router.refresh();
  });
  const label = t(`leads.bill.${lead.billing_status}`), cls = BILL[lead.billing_status];
  return (
    <section className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2"><h2 className="font-display text-headline-sm text-ink">{t("leads.billing.title")}</h2><span className={`px-2 py-0.5 rounded-full text-label-sm font-semibold ${cls}`}>{label}</span></div>
      {lead.fee_snapshot && (lead.fee_snapshot.net_minor > 0
        ? <p className="text-body-md">{t("leads.billing.price.before")} <strong>{kr(lead.fee_snapshot.net_minor, lang)}</strong> {t("leads.billing.price.after", { v: lead.fee_snapshot.agreement_version })}</p>
        : <p className="text-body-md">{t("leads.billing.included", { v: lead.fee_snapshot.agreement_version })}</p>)}
      {lead.billing_status === "rejected" && <p className="text-body-sm text-ink-soft">{t("leads.billing.reason", { reason: lead.billing_reason ?? "" })}</p>}
      {lead.billing_status === "pending" && (canApprove ? (
        <>
          <p className="text-body-sm text-ink-soft">{agreement ? (agreement.model === "B" ? t("leads.billing.modelB", { v: agreement.version, price: kr(agreement.lead_fee.net_minor, lang) }) : t("leads.billing.modelA", { v: agreement.version })) : t("leads.billing.noAgreement")} {t("leads.billing.monthly")}</p>
          <label htmlFor="b-reason" className="text-label-md font-semibold">{t("leads.billing.reasonLabel")}</label>
          <input id="b-reason" className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
          <ErrorBox error={decide.error} />
          <div className="flex flex-wrap gap-2">
            <Button type="button" icon="verified" disabled={decide.pending || lead.qualification_status !== "qualified" || !agreement} onClick={() => decide.run("approve")}>{t("leads.billing.approve")}</Button>
            <Button type="button" variant="outline" icon="block" disabled={decide.pending} onClick={() => decide.run("reject")}>{t("leads.billing.reject")}</Button>
          </div>
          {lead.qualification_status !== "qualified" && <p className="text-body-sm text-ink-soft">{t("leads.billing.onlyQualified")}</p>}
        </>
      ) : <p className="text-body-sm text-ink-soft">{t("leads.billing.adminsApprove")}</p>)}
    </section>
  );
}

export function TaskList({ wsId, leadId, tasks }: { wsId: string; leadId?: string; tasks: { id: string; title: string; status: string; due_at: string | null }[] }) {
  const router = useRouter();
  const tr = useT("app");
  const lang = HTML_LANG[useLocale()];
  const [title, setTitle] = useState("");
  // Optimistic status so the checkbox reacts immediately; rolled back if the server refuses.
  const [local, setLocal] = useState<Record<string, string>>({});
  const statusOf = (t: { id: string; status: string }) => local[t.id] ?? t.status;
  const toggle = useSubmit(async (t: { id: string; status: string }) => {
    const next = statusOf(t) === "open" ? "done" : "open";
    setLocal((m) => ({ ...m, [t.id]: next }));
    try {
      await api(`/workspaces/${wsId}/tasks/${t.id}`, { method: "PATCH", body: JSON.stringify({ status: next }) });
    } catch (e) {
      setLocal((m) => { const { [t.id]: _, ...rest } = m; return rest; });
      throw e;
    }
    router.refresh();
  });
  const add = useSubmit(async () => {
    await api(`/workspaces/${wsId}/tasks`, { method: "POST", body: JSON.stringify({ title, lead_id: leadId ?? null }) });
    setTitle(""); router.refresh();
  });
  return (
    <div className="flex flex-col gap-2">
      {tasks.length === 0 ? <p className="text-body-sm text-ink-soft">{tr("leads.tasks.none")}</p> : (
        <ul className="flex flex-col gap-1" aria-label={tr("leads.tasks.title")}>
          {tasks.map((t) => (
            <li key={t.id} className="flex items-center gap-2 p-2 rounded-lg bg-panel">
              <input type="checkbox" aria-label={tr("leads.tasks.doneAria", { title: t.title })} checked={statusOf(t) === "done"} onChange={() => toggle.run(t)} className="w-5 h-5 rounded text-ink focus:ring-ink" />
              <span className={`flex-1 text-body-md ${statusOf(t) ==="done"?"line-through text-ink-soft":"text-ink"}`}>{t.title}</span>
              {t.due_at && <span className="text-label-sm text-ink-soft">{tr("leads.tasks.due", { at: new Date(t.due_at).toLocaleString(lang, { dateStyle: "short", timeStyle: "short" }) })}</span>}
            </li>
          ))}
        </ul>
      )}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (title.trim()) add.run(); }}>
        <label htmlFor={`t-new-${leadId ?? "all"}`} className="sr-only">{tr("leads.tasks.new")}</label>
        <input id={`t-new-${leadId ?? "all"}`} className={inputCls} placeholder={tr("leads.tasks.newPlaceholder")} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
        <Button type="submit" variant="tonal" icon="add" disabled={add.pending || !title.trim()}>{tr("leads.tasks.add")}</Button>
      </form>
      <ErrorBox error={toggle.error ?? add.error} />
    </div>
  );
}
