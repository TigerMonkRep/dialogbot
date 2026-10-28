"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Button, ErrorBox, inputCls, useSubmit } from "@/components/ui";
import { BILL, PIPE, QUAL, kr, type Lead } from "./format";

export function NewLeadButton({ wsId }: { wsId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [need, setNeed] = useState("");
  const create = useSubmit(async () => {
    const l = await api<Lead>(`/workspaces/${wsId}/leads`, { method: "POST", body: JSON.stringify({ contact_name: name, need_summary: need }) });
    router.push(`/app/leads/${l.id}`);
  });
  if (!open) return <Button icon="add" variant="tonal" onClick={() => setOpen(true)}>Ny henvendelse</Button>;
  return (
    <form className="w-full md:w-96 bg-paper rounded-2xl p-3 border-2 border-ink flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); create.run(); }}>
      <label className="text-label-md font-semibold" htmlFor="nl-name">Navn</label>
      <input id="nl-name" className={inputCls} value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} />
      <label className="text-label-md font-semibold" htmlFor="nl-need">Behov</label>
      <textarea id="nl-need" className={inputCls} rows={2} value={need} onChange={(e) => setNeed(e.target.value)} maxLength={4000} />
      <ErrorBox error={create.error} />
      <div className="flex gap-2"><Button type="submit" disabled={create.pending}>Opret</Button><Button type="button" variant="ghost" onClick={() => setOpen(false)}>Annullér</Button></div>
    </form>
  );
}

export function LeadEditor({ wsId, lead }: { wsId: string; lead: Lead }) {
  const router = useRouter();
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
      <h2 className="font-display text-headline-sm text-ink">Kunde og behov</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">{field("contact_name", "Navn")}{field("contact_email", "E-mail", "email")}{field("contact_phone", "Telefon", "tel")}</div>
      <div><label htmlFor="l-need" className="block text-label-md font-semibold mb-1">Behov</label><textarea id="l-need" rows={3} className={inputCls} value={form.need_summary} onChange={set("need_summary")} /></div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div><label htmlFor="l-qual" className="block text-label-md font-semibold mb-1">Kvalificering</label>
          <select id="l-qual" className={inputCls} value={form.qualification_status} onChange={set("qualification_status")} disabled={decided}>{Object.entries(QUAL).map(([k, [lab]]) => <option key={k} value={k}>{lab}</option>)}</select>
          {decided && <p className="text-body-sm text-ink-soft mt-1">Låst, fordi afregningen er afgjort.</p>}</div>
        <div><label htmlFor="l-reason" className="block text-label-md font-semibold mb-1">Begrundelse</label><input id="l-reason" className={inputCls} value={form.qualification_reason} onChange={set("qualification_reason")} maxLength={500} /></div>
        <div><label htmlFor="l-pipe" className="block text-label-md font-semibold mb-1">Forløb</label>
          <select id="l-pipe" className={inputCls} value={form.pipeline_status} onChange={set("pipeline_status")}>{Object.entries(PIPE).map(([k, lab]) => <option key={k} value={k}>{lab}</option>)}</select></div>
      </div>
      <ErrorBox error={save.error} />
      <div><Button type="submit" icon="save" disabled={save.pending}>{save.pending ? "Gemmer…" : "Gem"}</Button></div>
    </form>
  );
}

export function BillingPanel({ wsId, lead, canApprove, agreement }: { wsId: string; lead: Lead; canApprove: boolean; agreement: { version: number; model: string; lead_fee: { net_minor: number } } | null }) {
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [key] = useState(() => crypto.randomUUID());
  const decide = useSubmit(async (d: "approve" | "reject") => {
    await api(`/workspaces/${wsId}/leads/${lead.id}/${d}`, { method: "POST", headers: { "Idempotency-Key": `${key}-${d}` }, body: JSON.stringify({ reason: reason || null }) });
    router.refresh();
  });
  const [label, cls] = BILL[lead.billing_status];
  return (
    <section className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2"><h2 className="font-display text-headline-sm text-ink">Afregning</h2><span className={`px-2 py-0.5 rounded-full text-label-sm font-semibold ${cls}`}>{label}</span></div>
      {lead.fee_snapshot && (lead.fee_snapshot.net_minor > 0
        ? <p className="text-body-md">Pris for denne henvendelse (ældre aftale): <strong>{kr(lead.fee_snapshot.net_minor)}</strong> ekskl. moms (aftale v{lead.fee_snapshot.agreement_version}).</p>
        : <p className="text-body-md">Godkendt. Ingen pris pr. henvendelse – den er med i abonnementet (aftale v{lead.fee_snapshot.agreement_version}).</p>)}
      {lead.billing_status === "rejected" && <p className="text-body-sm text-ink-soft">Begrundelse: {lead.billing_reason}</p>}
      {lead.billing_status === "pending" && (canApprove ? (
        <>
          <p className="text-body-sm text-ink-soft">{agreement ? (agreement.model === "B" ? `Ældre aftale v${agreement.version}: en godkendt henvendelse koster ${kr(agreement.lead_fee.net_minor)} ekskl. moms.` : `Aftale v${agreement.version}: abonnementet dækker henvendelsen – der er ingen pris pr. henvendelse.`) : "Abonnementet er ikke bekræftet endnu – ejeren bekræfter det under Indstillinger → Aftale."} Godkendte henvendelser vises på månedens oversigt (se Fakturering).</p>
          <label htmlFor="b-reason" className="text-label-md font-semibold">Begrundelse (kræves ved afvisning)</label>
          <input id="b-reason" className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
          <ErrorBox error={decide.error} />
          <div className="flex flex-wrap gap-2">
            <Button type="button" icon="verified" disabled={decide.pending || lead.qualification_status !== "qualified" || !agreement} onClick={() => decide.run("approve")}>Godkend henvendelse</Button>
            <Button type="button" variant="outline" icon="block" disabled={decide.pending} onClick={() => decide.run("reject")}>Afvis</Button>
          </div>
          {lead.qualification_status !== "qualified" && <p className="text-body-sm text-ink-soft">Kun kvalificerede henvendelser kan godkendes.</p>}
        </>
      ) : <p className="text-body-sm text-ink-soft">Ejere og administratorer godkender henvendelser.</p>)}
    </section>
  );
}

export function TaskList({ wsId, leadId, tasks }: { wsId: string; leadId?: string; tasks: { id: string; title: string; status: string; due_at: string | null }[] }) {
  const router = useRouter();
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
      {tasks.length === 0 ? <p className="text-body-sm text-ink-soft">Ingen opgaver.</p> : (
        <ul className="flex flex-col gap-1" aria-label="Opgaver">
          {tasks.map((t) => (
            <li key={t.id} className="flex items-center gap-2 p-2 rounded-lg bg-panel">
              <input type="checkbox" aria-label={`Færdig: ${t.title}`} checked={statusOf(t) === "done"} onChange={() => toggle.run(t)} className="w-5 h-5 rounded text-ink focus:ring-ink" />
              <span className={`flex-1 text-body-md ${statusOf(t) ==="done"?"line-through text-ink-soft":"text-ink"}`}>{t.title}</span>
              {t.due_at && <span className="text-label-sm text-ink-soft">Frist {new Date(t.due_at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" })}</span>}
            </li>
          ))}
        </ul>
      )}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (title.trim()) add.run(); }}>
        <label htmlFor={`t-new-${leadId ?? "all"}`} className="sr-only">Ny opgave</label>
        <input id={`t-new-${leadId ?? "all"}`} className={inputCls} placeholder="Ny opgave…" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
        <Button type="submit" variant="tonal" icon="add" disabled={add.pending || !title.trim()}>Tilføj</Button>
      </form>
      <ErrorBox error={toggle.error ?? add.error} />
    </div>
  );
}
