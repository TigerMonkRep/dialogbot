"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, Select, Textarea, useSubmit } from "@/components/ui";
import { kr } from "../leads/format";
import type { Campaign, Dnc, PhoneNumber } from "./format";


const DAYS: [string, string][] = [["mon", "Man"], ["tue", "Tir"], ["wed", "Ons"], ["thu", "Tor"], ["fri", "Fre"], ["sat", "Lør"], ["sun", "Søn"]];

export function NewCampaign({ wsId }: { wsId: string }) {
  const router = useRouter();
  const [f, setF] = useState({ name: "", purpose: "" });
  const save = useSubmit(async () => {
    const c = await api<Campaign>(`/workspaces/${wsId}/campaigns`, { method: "POST", body: JSON.stringify(f) });
    router.push(`/app/campaigns/${c.id}`);
  });
  return (
    <form className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <h2 className="font-headline-sm text-headline-sm text-primary">Ny kampagne</h2>
      <Field label="Navn på kampagnen" error={fieldError(save.error, "name")}><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Forårstilbud 2027" /></Field>
      <Field label="Hvad skal opkaldet handle om?" hint="Fx &quot;Tilbyde gulvafslibning til tidligere kunder inden sommerferien&quot;. AI'en foreslår manuskriptet ud fra det og jeres viden.">
        <Textarea value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} />
      </Field>
      <ErrorBox error={save.error} />
      <div><Button type="submit" icon="add" disabled={save.pending || !f.name.trim()}>Opret kampagne</Button></div>
    </form>
  );
}

export function CampaignEditor({ wsId, c, numbers, canManage }: { wsId: string; c: Campaign; numbers: PhoneNumber[]; canManage: boolean }) {
  const router = useRouter();
  const [f, setF] = useState({ name: c.name, purpose: c.purpose, opening: c.opening, questions: c.questions.join("\n"), success: c.success,
    phone_number_id: c.phone_number_id ?? "", call_days: c.call_days, call_from: c.call_from, call_to: c.call_to });
  const [note, setNote] = useState<string | null>(null);
  const locked = !canManage || c.status === "running" || c.status === "completed";
  const suggest = useSubmit(async () => {
    const s = await api<{ opening: string; questions: string[]; success: string }>(`/workspaces/${wsId}/campaigns/script-suggestions`, { method: "POST", body: JSON.stringify({ purpose: f.purpose }) });
    setF((cur) => ({ ...cur, opening: s.opening, questions: s.questions.join("\n"), success: s.success }));
    setNote("Forslag fra AI er sat ind. Ret det til, og tryk Gem.");
  });
  const asked = useRef(false);
  useEffect(() => {
    if (!asked.current && !locked && !c.opening && c.questions.length === 0) { asked.current = true; suggest.run(); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useSubmit(async () => {
    await api(`/workspaces/${wsId}/campaigns/${c.id}`, { method: "PUT", body: JSON.stringify({ ...f, expected_version: c.version,
      phone_number_id: f.phone_number_id || null, questions: f.questions.split("\n").map((q) => q.trim()).filter(Boolean) }) });
    setNote("Gemt."); router.refresh();
  });
  const set = (k: "name" | "purpose" | "opening" | "questions" | "success" | "call_from" | "call_to" | "phone_number_id") =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => { setNote(null); setF({ ...f, [k]: e.target.value }); };
  return (
    <form className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <div className="flex flex-wrap items-center justify-between gap-space-sm">
        <h2 className="font-headline-sm text-headline-sm text-primary">Manuskript og tidsrum</h2>
        {!locked && <Button type="button" variant="tonal" icon="auto_awesome" onClick={() => suggest.run()} disabled={suggest.pending}>{suggest.pending ? "Foreslår…" : "Foreslå med AI"}</Button>}
      </div>
      {c.status === "running" && <Alert kind="info">Kampagnen kører. Sæt den på pause for at ændre manuskriptet.</Alert>}
      {note && <Alert kind="ok">{note}</Alert>}
      <fieldset disabled={locked} className="flex flex-col gap-space-sm">
        <Field label="Navn"><Input value={f.name} onChange={set("name")} /></Field>
        <Field label="Formål med opkaldet" error={fieldError(save.error, "purpose")}><Textarea value={f.purpose} onChange={set("purpose")} /></Field>
        <Field label="Første replik" hint="{navn} bliver kontaktens fornavn og {virksomhed} jeres navn. Assistenten siger altid, at den er en digital assistent.">
          <Textarea value={f.opening} onChange={set("opening")} />
        </Field>
        <Field label="Spørgsmål (ét pr. linje)"><Textarea value={f.questions} onChange={set("questions")} /></Field>
        <Field label="Hvornår er kontakten interesseret?"><Input value={f.success} onChange={set("success")} /></Field>
        <Field label="Ring fra nummer" hint={numbers.length === 0 ? "Tilføj jeres nummer under Indstillinger → Telefoni." : undefined}>
          <Select value={f.phone_number_id} onChange={set("phone_number_id")}>
            <option value="">Vælg nummer</option>
            {numbers.map((n) => <option key={n.id} value={n.id}>{n.e164}{n.label ? ` (${n.label})` : ""}</option>)}
          </Select>
        </Field>
        <div className="flex flex-col gap-space-xs">
          <span className="font-label-md text-label-md font-semibold">Der ringes kun</span>
          <div className="flex flex-wrap gap-space-sm">{DAYS.map(([k, l]) => (
            <label key={k} className="flex items-center gap-1 font-body-md text-body-md">
              <input type="checkbox" className="w-4 h-4 accent-primary" checked={f.call_days.includes(k)}
                onChange={(e) => setF({ ...f, call_days: e.target.checked ? [...f.call_days, k] : f.call_days.filter((d) => d !== k) })} />{l}
            </label>
          ))}</div>
          <div className="grid grid-cols-2 gap-space-sm max-w-xs">
            <Field label="Fra kl."><Input type="time" value={f.call_from} onChange={set("call_from")} /></Field>
            <Field label="Til kl." error={fieldError(save.error, "call_to")}><Input type="time" value={f.call_to} onChange={set("call_to")} /></Field>
          </div>
        </div>
      </fieldset>
      <ErrorBox error={save.error ?? suggest.error} />
      {!locked && <div><Button type="submit" icon="save" disabled={save.pending}>{save.pending ? "Gemmer…" : "Gem kampagne"}</Button></div>}
    </form>
  );
}

type ImportResult = { added: number; duplicates: number; blocked: number; invalid_count: number; invalid: { row: number; value: string; reason: string }[] };

export function ImportContacts({ wsId, id }: { wsId: string; id: string }) {
  const router = useRouter();
  const [f, setF] = useState({ csv: "", kind: "business", consent_source: "" });
  const [res, setRes] = useState<ImportResult | null>(null);
  const run = useSubmit(async () => {
    const r = await api<ImportResult>(`/workspaces/${wsId}/campaigns/${id}/contacts/import`, { method: "POST", body: JSON.stringify(f) });
    setRes(r); setF({ ...f, csv: "" }); router.refresh();
  });
  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => { const file = e.target.files?.[0]; if (file) setF({ ...f, csv: await file.text() }); };
  return (
    <form className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm" onSubmit={(e) => { e.preventDefault(); run.run(); }}>
      <h2 className="font-headline-sm text-headline-sm text-primary">Tilføj kontakter</h2>
      <p className="font-body-sm text-body-sm text-on-surface-variant">Upload en CSV-fil (fx gemt fra Excel) eller indsæt listen. Kolonner: navn, telefon og evt. firma og e-mail. Danske numre må skrives uden +45. Numre på spærrelisten springes over.</p>
      {res && <Alert kind="ok">{res.added} kontakter tilføjet{res.duplicates ? `, ${res.duplicates} fandtes allerede` : ""}{res.blocked ? `, ${res.blocked} står på spærrelisten` : ""}{res.invalid_count ? `, ${res.invalid_count} ugyldige numre (fx række ${res.invalid.map((x) => x.row).slice(0, 5).join(", ")})` : ""}.</Alert>}
      <Field label="CSV-fil"><input type="file" accept=".csv,text/csv,text/plain" onChange={onFile} className="font-body-md text-body-md" /></Field>
      <Field label="Eller indsæt listen" error={fieldError(run.error, "csv")}><Textarea value={f.csv} onChange={(e) => setF({ ...f, csv: e.target.value })} placeholder={"Navn;Telefon;Firma\nMette Hansen;20 30 40 50;Hansen Byg ApS"} /></Field>
      <fieldset className="flex flex-col gap-space-xs">
        <legend className="font-label-md text-label-md font-semibold mb-1">Hvem er kontakterne?</legend>
        <label className="flex items-start gap-space-xs font-body-md text-body-md"><input type="radio" name="kind" className="mt-1 accent-primary" checked={f.kind === "business"} onChange={() => setF({ ...f, kind: "business" })} />Virksomheder (erhvervsnumre)</label>
        <label className="flex items-start gap-space-xs font-body-md text-body-md"><input type="radio" name="kind" className="mt-1 accent-primary" checked={f.kind === "consumer"} onChange={() => setF({ ...f, kind: "consumer" })} />Privatpersoner, der har givet samtykke til at blive ringet op</label>
      </fieldset>
      {f.kind === "consumer" && (
        <Field label="Hvor og hvornår har de givet samtykke?" error={fieldError(run.error, "consent_source")} hint="Markedsføringsloven § 10: Privatpersoner må kun ringes op med reklame, hvis de på forhånd har bedt om det. Uden samtykke må I ikke ringe.">
          <Input value={f.consent_source} onChange={(e) => setF({ ...f, consent_source: e.target.value })} placeholder="Tilmelding på hjemmesiden, marts 2026" />
        </Field>
      )}
      <ErrorBox error={run.error} />
      <div><Button type="submit" icon="upload" disabled={run.pending || !f.csv.trim()}>{run.pending ? "Importerer…" : "Tilføj kontakter"}</Button></div>
    </form>
  );
}

export function StartCampaign({ wsId, c, checklist }: { wsId: string; c: Campaign; checklist: string[] }) {
  const router = useRouter();
  const [checked, setChecked] = useState<boolean[]>(checklist.map(() => false));
  const start = useSubmit(async () => {
    await api(`/workspaces/${wsId}/campaigns/${c.id}/start`, { method: "POST", body: JSON.stringify({ expected_version: c.version, legal_confirmed: checked.every(Boolean), accept_max_net_minor: c.max_cost.net_minor }) });
    router.refresh();
  });
  const pause = useSubmit(async () => { await api(`/workspaces/${wsId}/campaigns/${c.id}/pause`, { method: "POST", body: "{}" }); router.refresh(); });
  if (c.status === "completed") return <Alert kind="ok">Kampagnen er afsluttet: alle kontakter er ringet op.</Alert>;
  if (c.status === "running") return (
    <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-wrap items-center gap-space-sm">
      <p className="font-body-md text-body-md grow">Kampagnen kører. Der ringes til én kontakt ad gangen i det valgte tidsrum.</p>
      <Button type="button" variant="tonal" icon="pause" onClick={() => pause.run()} disabled={pause.pending}>Sæt på pause</Button>
      <ErrorBox error={pause.error} />
    </div>
  );
  const pending = c.counts.by_status.pending ?? 0;
  return (
    <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
      <h2 className="font-headline-sm text-headline-sm text-primary">{c.status === "paused" ? "Genoptag kampagnen" : "Start kampagnen"}</h2>
      {c.outbound_problem && <Alert kind="warn">{c.outbound_problem}</Alert>}
      <p className="font-body-md text-body-md">{pending} kontakter venter. Højst {kr(c.max_cost.net_minor)} + moms ({kr(c.max_cost.gross_minor)} inkl. moms) – {kr(c.package.net_minor)} pr. kontakt, som først bruges, når kontakten ringes op første gang. Betaling starter aldrig opkald.</p>
      <fieldset className="flex flex-col gap-space-xs">
        <legend className="font-label-md text-label-md font-semibold mb-1">Bekræft reglerne for opkald</legend>
        {checklist.map((t, i) => (
          <label key={i} className="flex items-start gap-space-xs font-body-md text-body-md">
            <input type="checkbox" className="mt-1 w-4 h-4 accent-primary" checked={checked[i]} onChange={(e) => setChecked(checked.map((v, j) => (j === i ? e.target.checked : v)))} />{t}
          </label>
        ))}
      </fieldset>
      <ErrorBox error={start.error} />
      <div><Button type="button" icon="call" onClick={() => start.run()} disabled={start.pending || !checked.every(Boolean) || pending === 0 || !!c.outbound_problem}>{start.pending ? "Starter…" : c.status === "paused" ? "Genoptag" : "Start kampagne"}</Button></div>
    </div>
  );
}

export function RemoveContact({ wsId, campaignId, id }: { wsId: string; campaignId: string; id: string }) {
  const router = useRouter();
  const r = useSubmit(async () => { await api(`/workspaces/${wsId}/campaigns/${campaignId}/contacts/${id}`, { method: "DELETE" }); router.refresh(); });
  return <button type="button" onClick={() => r.run()} disabled={r.pending} className="font-label-md text-label-md text-error hover:underline disabled:opacity-50">Fjern</button>;
}

export function DoNotCallList({ wsId, items, canManage }: { wsId: string; items: Dnc[]; canManage: boolean }) {
  const router = useRouter();
  const [f, setF] = useState({ phone: "", reason: "" });
  const add = useSubmit(async () => { await api(`/workspaces/${wsId}/do-not-call`, { method: "POST", body: JSON.stringify(f) }); setF({ phone: "", reason: "" }); router.refresh(); });
  const del = useSubmit(async (id: string) => { await api(`/workspaces/${wsId}/do-not-call/${id}`, { method: "DELETE" }); router.refresh(); });
  return (
    <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
      <h2 className="font-headline-sm text-headline-sm text-primary">Spærreliste</h2>
      <p className="font-body-sm text-body-sm text-on-surface-variant">Numre her bliver aldrig ringet op i en kampagne. Siger nogen i et opkald, at de ikke vil ringes op igen, kommer de automatisk på listen.</p>
      {items.length > 0 && <ul className="flex flex-col gap-space-xs">{items.map((d) => (
        <li key={d.id} className="flex flex-wrap items-center gap-space-sm p-space-sm rounded-lg bg-surface-container-low font-body-md text-body-md">
          <span className="font-label-lg text-label-lg">{d.phone}</span>
          <span className="text-on-surface-variant">{d.reason || (d.source === "call" ? "Frabad sig opkald" : "")}</span>
          {canManage && d.source !== "call" && <button type="button" className="ml-auto font-label-md text-label-md text-error hover:underline" onClick={() => del.run(d.id)}>Fjern</button>}
        </li>
      ))}</ul>}
      <form className="grid grid-cols-1 md:grid-cols-[1fr_2fr_auto] gap-space-sm items-end" onSubmit={(e) => { e.preventDefault(); add.run(); }}>
        <Field label="Telefonnummer" error={fieldError(add.error, "phone")}><Input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label="Årsag (valgfri)"><Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
        <Button type="submit" variant="tonal" icon="block" disabled={add.pending || !f.phone.trim()}>Spær nummer</Button>
      </form>
      <ErrorBox error={del.error} />
    </div>
  );
}
