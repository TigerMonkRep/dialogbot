"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError, type ApiError } from "@/lib/client";
import { ErrorBox, Icon, inputCls, useSubmit } from "@/components/ui";
import type { Item, Version } from "./page";
import { DAYS, KIND_LABEL, UNIT_LABEL, kr, summarize } from "./format";

type Content = Record<string, unknown>;
const DAY_DA: Record<string, string> = { mon: "Man", tue: "Tir", wed: "Ons", thu: "Tor", fri: "Fre", sat: "Lør", sun: "Søn" };

export const EMPTY: Record<string, Content> = {
  service: { description: "", unit: "m2", price_net_minor: null, currency: "DKK" },
  opening_hours: { weekly: [{ days: ["mon", "tue", "wed", "thu", "fri"], open: "08:00", close: "16:00" }], closed_note: "" },
  coverage_area: { zones: [] },
  fact: { text: "" }, known_answer: { question: "", answer: "" }, unknown_answer: { rule: "" },
  offer: { discount_percent: 10, condition: { area_operator: "gte", area_threshold_m2: 40 }, starts_on: "", ends_on_inclusive: "" },
};

function Label({ children, htmlFor }: { children: React.ReactNode; htmlFor?: string }) {
  return <label htmlFor={htmlFor} className="block font-label-md text-label-md text-on-surface font-semibold mb-1">{children}</label>;
}

/** Structured editor per knowledge kind (no raw JSON). Prices are entered in kr and stored in øre. */
export function ContentFields({ kind, value, onChange, idPrefix, error }: { kind: string; value: Content; onChange: (c: Content) => void; idPrefix: string; error?: ApiError | null }) {
  const set = (k: string, v: unknown) => onChange({ ...value, [k]: v });
  const id = (k: string) => `${idPrefix}-${k}`;
  switch (kind) {
    case "service": {
      const minor = value.price_net_minor as number | null;
      return (
        <div className="space-y-space-md">
          <div><Label htmlFor={id("desc")}>Beskrivelse til assistenten (hvad må den fortælle?)</Label><textarea id={id("desc")} rows={3} className={`${inputCls} resize-y`} value={String(value.description ?? "")} onChange={(e) => set("description", e.target.value)} /></div>
          <div className="grid grid-cols-2 gap-space-md">
            <div>
              <Label htmlFor={id("price")}>Basispris (ekskl. moms)</Label>
              <div className="flex items-center rounded-lg bg-surface shadow-inner focus-within:ring-2 focus-within:ring-primary">
                <input id={id("price")} inputMode="decimal" className="w-full bg-transparent px-3 py-2 font-body-md text-body-md focus:outline-none" value={minor == null ? "" : String(minor / 100).replace(".", ",")}
                  onChange={(e) => { const t = e.target.value.replace(/\./g, "").replace(",", "."); const n = Number(t); set("price_net_minor", t.trim() === "" ? null : Number.isFinite(n) ? Math.round(n * 100) : minor); }} />
                <span className="px-2 font-label-sm text-label-sm text-on-surface-variant whitespace-nowrap">kr</span>
              </div>
            </div>
            <div>
              <Label htmlFor={id("unit")}>Enhed</Label>
              <select id={id("unit")} className={inputCls} value={String(value.unit ?? "m2")} onChange={(e) => set("unit", e.target.value)}>
                {Object.entries(UNIT_LABEL).map(([k, l]) => <option key={k} value={k}>pr. {l}</option>)}
              </select>
            </div>
          </div>
        </div>
      );
    }
    case "opening_hours": {
      const weekly = (value.weekly as { days: string[]; open: string; close: string }[]) ?? [];
      const setRow = (i: number, row: Partial<(typeof weekly)[number]>) => set("weekly", weekly.map((w, j) => (j === i ? { ...w, ...row } : w)));
      return (
        <div className="space-y-space-md">
          {weekly.map((w, i) => (
            <fieldset key={i} className="p-space-sm rounded-lg bg-surface-container-low space-y-2">
              <legend className="sr-only">Tidsrum {i + 1}</legend>
              <div className="flex flex-wrap gap-1">
                {DAYS.map((d) => {
                  const on = w.days.includes(d);
                  return <button type="button" key={d} aria-pressed={on} onClick={() => setRow(i, { days: on ? w.days.filter((x) => x !== d) : [...w.days, d] })} className={`px-2 py-1 rounded font-label-sm text-label-sm font-semibold ${on ? "bg-primary text-on-primary" : "bg-surface-container text-on-surface-variant"}`}>{DAY_DA[d]}</button>;
                })}
              </div>
              <div className="flex items-center gap-2">
                <input aria-label="Åbner" type="time" className={`${inputCls} w-32`} value={w.open} onChange={(e) => setRow(i, { open: e.target.value })} />
                <span aria-hidden>–</span>
                <input aria-label="Lukker" type="time" className={`${inputCls} w-32`} value={w.close} onChange={(e) => setRow(i, { close: e.target.value })} />
                {weekly.length > 1 && <button type="button" aria-label="Fjern tidsrum" onClick={() => set("weekly", weekly.filter((_, j) => j !== i))} className="ml-auto text-on-surface-variant hover:text-error"><Icon name="delete" size={18} /></button>}
              </div>
            </fieldset>
          ))}
          <button type="button" onClick={() => set("weekly", [...weekly, { days: ["sat"], open: "10:00", close: "14:00" }])} className="font-label-sm text-label-sm text-secondary font-semibold flex items-center gap-1"><Icon name="add" size={16} />Tilføj tidsrum</button>
          <div><Label htmlFor={id("note")}>Uden for åbningstid</Label><input id={id("note")} className={inputCls} value={String(value.closed_note ?? "")} onChange={(e) => set("closed_note", e.target.value)} placeholder="Fx Weekend og helligdage: tager kun imod besked" /></div>
        </div>
      );
    }
    case "coverage_area":
      return <div><Label htmlFor={id("zones")}>Zoner (adskilt af komma)</Label><input id={id("zones")} className={inputCls} value={((value.zones as string[]) ?? []).join(", ")} onChange={(e) => set("zones", e.target.value.split(",").map((z) => z.trim()).filter(Boolean))} /></div>;
    case "fact":
      return <div><Label htmlFor={id("text")}>Faktum</Label><textarea id={id("text")} rows={2} className={inputCls} value={String(value.text ?? "")} onChange={(e) => set("text", e.target.value)} /></div>;
    case "known_answer":
      return (
        <div className="space-y-space-md">
          <div><Label htmlFor={id("q")}>Spørgsmål</Label><input id={id("q")} className={inputCls} value={String(value.question ?? "")} onChange={(e) => set("question", e.target.value)} /></div>
          <div><Label htmlFor={id("a")}>Godkendt svar</Label><textarea id={id("a")} rows={3} className={inputCls} value={String(value.answer ?? "")} onChange={(e) => set("answer", e.target.value)} /></div>
        </div>
      );
    case "unknown_answer":
      return <div><Label htmlFor={id("rule")}>Emne assistenten ikke må besvare</Label><textarea id={id("rule")} rows={2} className={inputCls} value={String(value.rule ?? "")} onChange={(e) => set("rule", e.target.value)} /></div>;
    case "offer": {
      const cond = (value.condition as { area_operator: string; area_threshold_m2: number | null }) ?? { area_operator: "gte", area_threshold_m2: null };
      return (
        <div className="grid grid-cols-2 gap-space-md">
          <div><Label htmlFor={id("pct")}>Rabat (%)</Label><input id={id("pct")} type="number" min={1} max={100} className={inputCls} value={Number(value.discount_percent ?? 0)} onChange={(e) => set("discount_percent", Number(e.target.value))} /></div>
          <div>
            <Label htmlFor={id("thr")}>Mindste areal (m²)</Label>
            <input id={id("thr")} type="number" min={0} className={inputCls} value={cond.area_threshold_m2 ?? ""} onChange={(e) => set("condition", { area_operator: "gte", area_threshold_m2: e.target.value === "" ? null : Number(e.target.value) })} />
            <span className="font-body-sm text-body-sm text-on-surface-variant">Gælder ved mindst (≥) dette areal.</span>
          </div>
          <div><Label htmlFor={id("from")}>Gælder fra</Label><input id={id("from")} type="date" className={inputCls} value={String(value.starts_on ?? "")} onChange={(e) => set("starts_on", e.target.value)} /></div>
          <div>
            <Label htmlFor={id("to")}>Gælder til og med</Label><input id={id("to")} type="date" className={inputCls} value={String(value.ends_on_inclusive ?? "")} onChange={(e) => set("ends_on_inclusive", e.target.value)} />
            {fieldError(error ?? null, "content.ends_on_inclusive") && <span role="alert" className="font-label-md text-label-md text-error">{fieldError(error ?? null, "content.ends_on_inclusive")}</span>}
          </div>
        </div>
      );
    }
    default: return null;
  }
}

function useVersionAction(wsId: string) {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  const act = async (v: Version, path: "submit" | "approve" | "reject", body?: unknown) => {
    setPending(path);
    try { await api(`/workspaces/${wsId}/knowledge/versions/${v.id}/${path}`, { method: "POST", body: body ? JSON.stringify(body) : undefined, headers: path === "approve" ? { "idempotency-key": `approve-${v.id}` } : undefined }); router.refresh(); }
    catch (e) { alert((e as ApiError).message); } finally { setPending(null); }
  };
  return { act, pending };
}

/** Draft workflow buttons: submit for review, approve (owner/admin), reject with reason. */
export function VersionActions({ wsId, v, canApprove, compact = false }: { wsId: string; v: Version; canApprove: boolean; compact?: boolean }) {
  const { act, pending } = useVersionAction(wsId);
  const btn = "px-3 py-1.5 rounded-lg font-label-md text-label-md font-semibold transition-colors disabled:opacity-60";
  return (
    <span className="flex flex-wrap items-center gap-2">
      {v.status === "draft" && !canApprove && <button disabled={!!pending} className={`${btn} bg-surface-container text-primary hover:bg-surface-container-high`} onClick={() => act(v, "submit")}>Send til gennemgang</button>}
      {(v.status === "in_review" || v.status === "draft") && canApprove && <button disabled={!!pending} className={`${btn} bg-secondary-fixed text-on-secondary-fixed hover:brightness-95`} onClick={() => act(v, "approve")}>{pending === "approve" ? "Godkender…" : compact ? "Godkend" : "Godkend version"}</button>}
      {v.status === "in_review" && canApprove && <button disabled={!!pending} className={`${btn} bg-surface-container-lowest text-error hover:bg-error-container`} onClick={() => { const reason = prompt("Begrundelse for afvisning"); if (reason) act(v, "reject", { reason }); }}>Afvis</button>}
      {!canApprove && v.status === "in_review" && <span className="font-label-sm text-label-sm text-on-surface-variant">Afventer godkendelse af ejer/administrator</span>}
    </span>
  );
}

/** K05: keep the approved version (reject the proposal; only possible once it is in review). */
export function KeepButton({ wsId, v, label }: { wsId: string; v: Version; label: string }) {
  const { act, pending } = useVersionAction(wsId);
  const canReject = v.status === "in_review";
  return (
    <button disabled={!!pending || !canReject} title={canReject ? undefined : "En kladde kan først afvises, når den er sendt til gennemgang"}
      onClick={() => { const reason = prompt("Begrundelse (gemmes i revisionsloggen)", "Behold eksisterende version"); if (reason) act(v, "reject", { reason }); }}
      className="w-full py-2 rounded-lg bg-primary text-on-primary font-label-md text-label-md font-semibold hover:bg-primary-container transition-colors disabled:opacity-60">{pending === "reject" ? "Afviser…" : label}</button>
  );
}

/** K05: approve the proposed version; it replaces the active one and stales knowledge-dependent checks. */
export function ApproveNewButton({ wsId, v, label }: { wsId: string; v: Version; label: string }) {
  const { act, pending } = useVersionAction(wsId);
  return <button disabled={!!pending} onClick={() => act(v, "approve")} className="w-full py-2 rounded-lg bg-secondary-fixed text-on-secondary-fixed font-label-md text-label-md font-semibold hover:brightness-95 transition-all disabled:opacity-60">{pending === "approve" ? "Godkender…" : label}</button>;
}

/** K03 card: shows the active (approved) version; editing creates or updates a draft that needs approval. */
export function ItemCard({ wsId, item, canDraft, canApprove }: { wsId: string; item: Item; canDraft: boolean; canApprove: boolean }) {
  const router = useRouter();
  const src = item.open_draft ?? item.approved_version!;
  const [title, setTitle] = useState(src.title);
  const [content, setContent] = useState<Content>(src.content);
  const dirty = title !== src.title || JSON.stringify(content) !== JSON.stringify(src.content);
  const { run, pending, error } = useSubmit(async () => {
    if (item.open_draft) await api(`/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}`, { method: "PUT", body: JSON.stringify({ expected_edit_version: item.open_draft.edit_version, title, content }) });
    else await api(`/workspaces/${wsId}/knowledge/items/${item.id}/drafts`, { method: "POST", body: JSON.stringify({ title, content }) });
    router.refresh(); return true;
  });
  const approved = item.approved_version;
  const sum = approved ? summarize(item.kind, approved.content) : null;
  const isService = item.kind === "service";
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
      <div className="flex items-start justify-between gap-space-sm">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-space-sm">
            <span className="px-2 py-0.5 rounded bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm">{KIND_LABEL[item.kind] ?? item.kind}</span>
            {approved && !item.open_draft && <span className="px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-bold">Aktiv &amp; godkendt</span>}
            {item.open_draft && <span className="px-2 py-0.5 rounded-full bg-tertiary-fixed text-on-tertiary-fixed font-label-sm text-label-sm font-bold">{item.open_draft.status === "in_review" ? "Til gennemgang" : "Kladde"}{approved ? " – aktiv version uændret" : ""}</span>}
          </div>
          <h3 className="font-headline-sm text-headline-sm text-primary break-words">{approved?.title ?? title}</h3>
        </div>
        {isService && sum && <div className="text-right flex-shrink-0"><span className="font-headline-md text-headline-md text-primary font-bold">{kr(approved!.content.price_net_minor)}</span><span className="font-label-sm text-label-sm text-on-surface-variant"> kr / {UNIT_LABEL[String(approved!.content.unit)] ?? ""}</span></div>}
      </div>
      {canDraft && <div><Label htmlFor={`${item.id}-title`}>Titel</Label><input id={`${item.id}-title`} className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} /></div>}
      {canDraft ? <ContentFields kind={item.kind} value={content} onChange={setContent} idPrefix={item.id} error={error} /> : <p className="font-body-md text-body-md text-on-surface">{summarize(item.kind, content).headline}</p>}
      <ErrorBox error={error} />
      {error?.code === "version_conflict" && <p className="font-label-md text-label-md">Kladden er ændret af en anden. <button type="button" className="underline" onClick={() => router.refresh()}>Genindlæs</button></p>}
      {approved && (
        <div className="p-space-sm rounded-lg bg-surface-container-low flex items-center justify-between gap-space-sm">
          <span className="flex items-center gap-space-xs font-label-md text-label-md text-primary font-semibold"><Icon name="verified" size={18} className="text-secondary" />Aktiv version v{approved.version_no}</span>
          <span className="font-label-sm text-label-sm text-on-surface-variant truncate">{sum?.headline}</span>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-space-sm pt-space-xs">
        {item.open_draft ? <VersionActions wsId={wsId} v={item.open_draft} canApprove={canApprove} /> : <span className="font-label-sm text-label-sm text-on-surface-variant">{approved?.submitted_at ? `Godkendt version sendt ${new Date(approved.submitted_at).toLocaleDateString("da-DK")}` : "Manuelt indtastet"}</span>}
        {canDraft && <button type="submit" disabled={!dirty || pending} className="px-3 py-1.5 rounded-lg bg-surface-container text-primary font-label-md text-label-md font-semibold hover:bg-surface-container-high disabled:opacity-50">{pending ? "Gemmer…" : item.open_draft ? "Gem kladde" : "Gem som ny kladde"}</button>}
      </div>
    </form>
  );
}

/** New knowledge item (K03/K04) with structured fields; saved as a draft. */
export function NewItemForm({ wsId, kinds, onDone }: { wsId: string; kinds: string[]; onDone?: () => void }) {
  const router = useRouter();
  const [kind, setKind] = useState(kinds[0]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState<Content>(EMPTY[kinds[0]]);
  const { run, pending, error } = useSubmit(async () => {
    await api(`/workspaces/${wsId}/knowledge/items`, { method: "POST", body: JSON.stringify({ kind, title, content }) });
    setTitle(""); setContent(EMPTY[kind]); router.refresh(); onDone?.(); return true;
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-space-md">
      <ErrorBox error={error} />
      {kinds.length > 1 && (
        <div><Label htmlFor="new-kind">Art</Label>
          <select id="new-kind" className={inputCls} value={kind} onChange={(e) => { setKind(e.target.value); setContent(EMPTY[e.target.value]); }}>{kinds.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}</select>
        </div>
      )}
      <div><Label htmlFor="new-title">Titel</Label><input id="new-title" required className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} placeholder={kind === "offer" ? "Fx 15% arealrabat ved store projekter" : "Fx Standard gulvafslibning"} /></div>
      <ContentFields kind={kind} value={content} onChange={setContent} idPrefix="new" error={error} />
      <button type="submit" disabled={pending || !title} className="w-full py-2.5 rounded-lg bg-primary text-on-primary font-label-lg text-label-lg hover:bg-primary-container transition-colors disabled:opacity-50 flex items-center justify-center gap-space-xs"><Icon name="add" size={18} />{pending ? "Gemmer…" : "Gem som kladde"}</button>
      <p className="font-body-sm text-body-sm text-on-surface-variant">Kladden bruges først af assistenten, når en ejer eller administrator har godkendt den.</p>
    </form>
  );
}

/** Toggleable "new item" panel used by the K03/K04 headers. */
export function AddPanel({ wsId, kinds, label }: { wsId: string; kinds: string[]; label: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-space-md">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex items-center gap-space-sm bg-primary hover:bg-primary-container text-on-primary px-space-lg py-space-sm rounded-xl font-label-lg text-label-lg shadow-sm transition-all"><Icon name={open ? "close" : "add"} size={20} />{open ? "Luk" : label}</button>
      {open && <div className="bg-surface-container-lowest rounded-xl p-space-lg shadow-md max-w-xl"><NewItemForm wsId={wsId} kinds={kinds} onDone={() => setOpen(false)} /></div>}
    </div>
  );
}

