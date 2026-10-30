"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, Select, useSubmit } from "@/components/ui";

const DAYS: [string, string][] = [["mon", "Man"], ["tue", "Tir"], ["wed", "Ons"], ["thu", "Tor"], ["fri", "Fre"], ["sat", "Lør"], ["sun", "Søn"]];
const kr = (minor: number) => `${(minor / 100).toLocaleString("da-DK", { maximumFractionDigits: 2 })} kr.`;

export function NewCampaign() {
  const router = useRouter();
  const [f, setF] = useState({ name: "", budget: "200", call_from: "09:00", call_to: "16:00", max_attempts: 2, days: ["mon", "tue", "wed", "thu", "fri"] });
  const save = useSubmit(async () => {
    const c = await api<{ id: string }>("/operator/salg/campaigns", { method: "POST", body: JSON.stringify({
      name: f.name, budget_net_minor: f.budget.trim() ? Math.round(Number(f.budget.replace(",", ".")) * 100) : null,
      call_days: f.days, call_from: f.call_from, call_to: f.call_to, max_attempts: f.max_attempts }) });
    router.push(`/app/operator/salg/kampagner/${c.id}`);
  });
  return (
    <form className="rounded-2xl bg-surface-container-lowest border-2 border-ink p-space-md flex flex-col gap-space-sm" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <h2 className="font-display font-bold text-[18px]">Ny kampagne</h2>
      <Field label="Navn" error={fieldError(save.error, "name")}><Input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Aarhus frisører, november" /></Field>
      <Field label="Budget (kr. ekskl. moms, hårdt loft)" hint="Opkald + minutter. Tom = intet loft ud over forhåndsvisningens godkendte beløb."><Input value={f.budget} onChange={(e) => setF({ ...f, budget: e.target.value })} inputMode="decimal" /></Field>
      <fieldset className="flex flex-wrap gap-2 text-[14px]"><legend className="font-semibold mb-1">Dage</legend>{DAYS.map(([k, l]) => (
        <label key={k} className="flex items-center gap-1"><input type="checkbox" className="accent-primary" checked={f.days.includes(k)} onChange={(e) => setF({ ...f, days: e.target.checked ? [...f.days, k] : f.days.filter((d) => d !== k) })} />{l}</label>))}
      </fieldset>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Fra (dansk tid)"><Input type="time" value={f.call_from} onChange={(e) => setF({ ...f, call_from: e.target.value })} /></Field>
        <Field label="Til" error={fieldError(save.error, "call_to")}><Input type="time" value={f.call_to} onChange={(e) => setF({ ...f, call_to: e.target.value })} /></Field>
      </div>
      <Field label="Forsøg pr. kontakt"><Select value={f.max_attempts} onChange={(e) => setF({ ...f, max_attempts: Number(e.target.value) })}><option value={1}>1</option><option value={2}>2</option></Select></Field>
      <ErrorBox error={save.error} />
      <Button type="submit" disabled={!f.name.trim() || f.days.length === 0 || save.pending}>Opret kampagne</Button>
    </form>
  );
}

export function BlockForm() {
  const router = useRouter();
  const [f, setF] = useState({ kind: "phone", value: "", reason: "" });
  const save = useSubmit(async () => { await api("/operator/salg/block-list", { method: "POST", body: JSON.stringify(f) }); setF({ ...f, value: "", reason: "" }); router.refresh(); });
  return (
    <form className="grid md:grid-cols-[10rem_1fr_1fr_auto] gap-2 items-end mt-2" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <Field label="Type"><Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="phone">Telefon</option><option value="domain">Domæne</option><option value="cvr">CVR</option></Select></Field>
      <Field label="Værdi" error={fieldError(save.error, "value")}><Input value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} /></Field>
      <Field label="Grund"><Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
      <Button type="submit" variant="secondary" disabled={!f.value.trim() || save.pending}>Spær</Button>
      <div className="md:col-span-4"><ErrorBox error={save.error} /></div>
    </form>
  );
}

type Preview = { counts: Record<string, number>; reasons: Record<string, { count: number; text: string }>; max_cost_net_minor: number; per_attempt_max_net_minor: number; spent_net_minor: number; budget_net_minor: number | null; mode: string };

export function CampaignControls({ id, status, preview }: { id: string; status: string; preview: Preview }) {
  const router = useRouter();
  const [accepted, setAccepted] = useState(false);
  const act = useSubmit(async (what: "start" | "pause" | "stop") => {
    await api(`/operator/salg/campaigns/${id}/${what}`, { method: "POST", body: what === "start" ? JSON.stringify({ accepted_max_net_minor: preview.max_cost_net_minor }) : undefined });
    router.refresh();
  });
  const canCall = preview.mode === "test" || preview.mode === "live";
  return (
    <div className="flex flex-col gap-2">
      {!canCall && <Alert kind="warn">SALES_OUTBOUND_MODE er {preview.mode}: kampagnen kan forberedes, men først startes i test eller live.</Alert>}
      {preview.mode === "test" && <Alert kind="info">Testtilstand: kun numre i SALES_TEST_NUMBERS kan få ALLOW.</Alert>}
      {(status === "draft" || status === "paused") && (
        <label className="flex items-start gap-2 text-[14px]"><input type="checkbox" className="mt-1 accent-primary" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />
          <span>Jeg har set forhåndsvisningen og godkender et omkostningsloft på højst {kr(preview.max_cost_net_minor)} ekskl. moms ({preview.counts.ALLOW} kontakter med ALLOW ringes op; politikken tjekkes igen før hvert opkald).</span></label>
      )}
      <div className="flex flex-wrap gap-2">
        {(status === "draft" || status === "paused") && <Button icon="call" disabled={!accepted || !canCall || preview.counts.ALLOW === 0 || act.pending} onClick={() => act.run("start")}>Start</Button>}
        {status === "running" && <Button variant="secondary" disabled={act.pending} onClick={() => act.run("pause")}>Pause</Button>}
        {status !== "stopped" && status !== "completed" && <Button variant="secondary" disabled={act.pending} onClick={() => act.run("stop")}>Stop</Button>}
      </div>
      <ErrorBox error={act.error} />
    </div>
  );
}
