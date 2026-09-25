"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Badge, Button, ErrorBox, Field, Input, Textarea, useSubmit } from "@/components/ui";
import type { Item, Version } from "./page";

const KINDS: [string, string][] = [["service", "Ydelse"], ["opening_hours", "Åbningstider"], ["coverage_area", "Dækningsområde"], ["fact", "Faktum"], ["known_answer", "Kendt svar"], ["unknown_answer", "Må ikke besvares"], ["offer", "Tilbud"]];
const kindLabel = (k: string) => KINDS.find(([c]) => c === k)?.[1] ?? k;

const TEMPLATES: Record<string, string> = {
  service: '{"description": "", "unit": "m2", "price_net_minor": 14500, "currency": "DKK"}',
  opening_hours: '{"weekly": [{"days": ["mon","tue","wed","thu","fri"], "open": "08:00", "close": "16:00"}], "closed_note": ""}',
  coverage_area: '{"zones": ["Hovedstadsområdet"]}',
  fact: '{"text": ""}', known_answer: '{"question": "", "answer": ""}', unknown_answer: '{"rule": ""}',
  offer: '{"discount_percent": 15, "condition": {"area_operator": "gte", "area_threshold_m2": 40}, "starts_on": "2026-10-01", "ends_on_inclusive": "2026-11-30"}',
};

function parse(text: string): Record<string, unknown> {
  try { const v = JSON.parse(text); if (v && typeof v === "object" && !Array.isArray(v)) return v; } catch { /* fallthrough */ }
  throw { code: "validation_failed", message: "Indholdet skal være gyldig JSON (et objekt)", status: 422 };
}

export function NewItemForm({ wsId }: { wsId: string }) {
  const router = useRouter();
  const [kind, setKind] = useState("service");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState(TEMPLATES.service);
  const { run, pending, error } = useSubmit(async () => {
    await api(`/workspaces/${wsId}/knowledge/items`, { method: "POST", body: JSON.stringify({ kind, title, content: parse(content) }) });
    setTitle(""); router.refresh();
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-3">
      <ErrorBox error={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Art"><select className="w-full rounded-xl border border-line bg-white px-3.5 py-2.5 text-sm" value={kind} onChange={(e) => { setKind(e.target.value); setContent(TEMPLATES[e.target.value]); }}>{KINDS.map(([c, l]) => <option key={c} value={c}>{l}</option>)}</select></Field>
        <Field label="Titel"><Input required value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
      </div>
      <Field label="Indhold (JSON)" hint={kind === "offer" ? "Tilbud gælder ved mindst (gte) tærsklen og inden for datoerne, slutdato inklusive." : undefined}><Textarea value={content} onChange={(e) => setContent(e.target.value)} className="font-mono" /></Field>
      <Button type="submit" disabled={pending || !title}>Gem som kladde</Button>
    </form>
  );
}

function VersionActions({ wsId, v, canApprove }: { wsId: string; v: Version; canApprove: boolean }) {
  const router = useRouter();
  const { run, pending, error } = useSubmit(async () => undefined);
  const act = (path: string, body?: unknown) => run().then(async () => {
    try { await api(`/workspaces/${wsId}/knowledge/versions/${v.id}/${path}`, { method: "POST", body: body ? JSON.stringify(body) : undefined, headers: path === "approve" ? { "idempotency-key": `approve-${v.id}` } : undefined }); router.refresh(); }
    catch (e) { alert((e as { message: string }).message); }
  });
  return (
    <span className="flex flex-wrap gap-2">
      <ErrorBox error={error} />
      {v.status === "draft" && <Button variant="secondary" disabled={pending} onClick={() => act("submit")}>Send til gennemgang</Button>}
      {(v.status === "in_review" || v.status === "draft") && canApprove && <Button disabled={pending} onClick={() => act("approve")}>Godkend</Button>}
      {v.status === "in_review" && canApprove && <Button variant="danger" disabled={pending} onClick={() => { const reason = prompt("Begrundelse for afvisning"); if (reason) act("reject", { reason }); }}>Afvis</Button>}
      {!canApprove && v.status === "in_review" && <span className="text-xs text-muted">Afventer godkendelse af administrator</span>}
    </span>
  );
}

export function ReviewQueue({ wsId, queue, canApprove }: { wsId: string; queue: Version[]; canApprove: boolean }) {
  return (
    <ul className="divide-y divide-line text-sm">
      {queue.map((v) => (
        <li key={v.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
          <span><strong>{v.title}</strong> <span className="text-muted">v{v.version_no}</span> <Badge status={v.status} /></span>
          <VersionActions wsId={wsId} v={v} canApprove={canApprove} />
        </li>
      ))}
    </ul>
  );
}

export function KnowledgeList({ wsId, items, canDraft, canApprove }: { wsId: string; items: Item[]; canDraft: boolean; canApprove: boolean }) {
  const router = useRouter();
  const [editing, setEditing] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const { run, pending, error } = useSubmit(async () => {
    const item = items.find((i) => i.id === editing)!;
    if (item.open_draft) await api(`/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}`, { method: "PUT", body: JSON.stringify({ expected_edit_version: item.open_draft.edit_version, title, content: parse(text) }) });
    else await api(`/workspaces/${wsId}/knowledge/items/${item.id}/drafts`, { method: "POST", body: JSON.stringify({ title, content: parse(text) }) });
    setEditing(null); router.refresh();
  });
  if (items.length === 0) return <p className="text-sm text-muted">Ingen vidensemner endnu. Opret det første nedenfor – mindst én ydelse og åbningstider er nødvendige.</p>;
  return (
    <ul className="divide-y divide-line text-sm">
      {items.map((i) => {
        const v = i.approved_version ?? i.open_draft;
        return (
          <li key={i.id} className="space-y-2 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span><span className="mr-2 rounded bg-white px-2 py-0.5 text-xs text-muted">{kindLabel(i.kind)}</span><strong>{v?.title}</strong>
                {i.approved_version && <> <Badge status="approved" /> <span className="text-xs text-muted">v{i.approved_version.version_no}</span></>}
                {i.open_draft && <> <Badge status={i.open_draft.status} /> <span className="text-xs text-muted">v{i.open_draft.version_no}</span></>}
              </span>
              <span className="flex flex-wrap gap-2">
                {i.open_draft && <VersionActions wsId={wsId} v={i.open_draft} canApprove={canApprove} />}
                {canDraft && editing !== i.id && <Button variant="ghost" className="border border-line" onClick={() => { const src = i.open_draft ?? i.approved_version!; setEditing(i.id); setTitle(src.title); setText(JSON.stringify(src.content, null, 2)); }}>{i.open_draft ? "Redigér kladde" : "Ny kladde"}</Button>}
              </span>
            </div>
            {editing === i.id ? (
              <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-2 rounded-xl border border-line bg-white p-3">
                <ErrorBox error={error} />
                {error?.code === "version_conflict" && <Alert kind="info">Kladden er ændret af en anden. <button className="underline" type="button" onClick={() => router.refresh()}>Genindlæs</button></Alert>}
                <Field label="Titel"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
                <Field label="Indhold (JSON)"><Textarea className="font-mono" value={text} onChange={(e) => setText(e.target.value)} /></Field>
                <p className="text-xs text-muted">{i.approved_version ? "Den godkendte version forbliver aktiv, indtil kladden godkendes." : ""}</p>
                <span className="flex gap-2"><Button type="submit" disabled={pending}>Gem kladde</Button><Button type="button" variant="ghost" onClick={() => setEditing(null)}>Annullér</Button></span>
              </form>
            ) : <pre className="overflow-x-auto rounded-lg bg-white p-2 text-xs text-muted">{JSON.stringify(v?.content)}</pre>}
          </li>
        );
      })}
    </ul>
  );
}
