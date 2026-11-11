"use client";
/** Knowledge from a file or pasted text (besides the website): upload with drag-and-drop, a large text field, the
 *  import summary («Fandt 34 ting: 12 ydelser, 9 FAQ … · 3 overlapper eksisterende · 1 modstrid») and the grouped
 *  review of the suggestions («Godkend alle i kategorien», «Godkend alle»). Used on /app/viden and in setup step 1.
 *  Nothing reaches the assistant before approval; the file itself is never stored by the server. */
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { ErrorBox, Icon, inputCls, useSubmit } from "@/components/ui";
import { useT } from "@/i18n/client";

export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_TEXT_CHARS = 200_000;
const ACCEPT = ".pdf,.docx,.xlsx,.csv,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,text/plain,text/markdown";
const EXT = /\.(pdf|docx|xlsx|csv|txt|md)$/i;
const BTN_PRIMARY = "inline-flex items-center justify-center gap-1.5 min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-50";
const BTN = "inline-flex items-center justify-center gap-1.5 min-h-[44px] px-4 rounded-xl border-[1.5px] border-ink bg-paper text-[14px] font-semibold text-ink hover:bg-panel disabled:opacity-50";

export type ImportSummary = {
  found?: number; by_category?: Record<string, number>; new?: number; updates?: number; duplicates?: number;
  conflicts?: number; pending?: number; unverified?: number;
};
export type Import = {
  id: string; status: "running" | "done" | "failed"; error: string | null; source_type?: "website" | "file" | "text";
  source_name?: string | null; summary?: ImportSummary; created_items: { kind: string; title: string }[];
  pages: { url: string; title: string }[];
};
export type ReviewNote = { relation?: "new" | "update"; category?: string; source?: string; conflict?: string | null; conflicts?: { source: string; text: string }[]; source_type?: string };

/** Poll imports/latest every 3 s while `imp` runs; `onDone` once it has finished. */
export function useImport(wsId: string, initial: Import | null, onDone?: (imp: Import) => void) {
  const [imp, setImp] = useState<Import | null>(initial);
  const done = useRef(onDone);
  done.current = onDone;
  const running = imp?.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(async () => {
      const r = await api<{ import: Import | null }>(`/workspaces/${wsId}/knowledge/imports/latest`).catch(() => null);
      if (r?.import && r.import.status !== "running") { setImp(r.import); done.current?.(r.import); }
    }, 3000);
    return () => clearInterval(t);
  }, [running, wsId]);
  return [imp, setImp] as const;
}

/** «Upload fil»: a drop zone with a real file input (keyboard and screen readers use the button). */
export function FileDrop({ wsId, disabled, onStarted, id = "kn-file" }: { wsId: string; disabled?: boolean; onStarted: (imp: Import) => void; id?: string }) {
  const t = useT("app");
  const [over, setOver] = useState(false);
  const [name, setName] = useState<string | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const send = async (f: File | undefined) => {
    if (!f) return;
    setErr(null);
    if (f.size > MAX_FILE_BYTES) { setErr({ status: 422, code: "too_big", message: t("knowledge.sources.tooBig") }); return; }
    if (!EXT.test(f.name)) { setErr({ status: 422, code: "wrong_type", message: t("knowledge.sources.wrongType") }); return; }
    setBusy(true); setName(f.name);
    try {
      const imp = await api<Import>(`/workspaces/${wsId}/knowledge/import/file?name=${encodeURIComponent(f.name)}`, { method: "POST", body: await f.arrayBuffer(), headers: { "content-type": "application/octet-stream" } });
      onStarted(imp);
    } catch (e) { setErr(e as ApiError); } finally { setBusy(false); if (input.current) input.current.value = ""; }
  };
  return (
    <div className="flex flex-col gap-2">
      <div onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled && !busy) void send(e.dataTransfer.files?.[0]); }}
        data-testid="file-drop"
        className={`flex flex-col items-center justify-center gap-2 text-center rounded-xl border-2 border-dashed px-4 py-5 min-h-[132px] ${over ? "border-accent bg-accent-soft" : "border-ink bg-paper"}`}>
        <Icon name="upload_file" size={26} />
        <span className="text-[14px] text-ink-soft">{busy && name ? t("knowledge.sources.uploading", { name }) : t("knowledge.sources.drop")}</span>
        <input ref={input} id={id} type="file" accept={ACCEPT} className="sr-only" disabled={disabled || busy} onChange={(e) => void send(e.target.files?.[0])} />
        <label htmlFor={id} className={`${BTN} cursor-pointer ${disabled || busy ? "opacity-50 pointer-events-none" : ""}`}>{t("knowledge.sources.choose")}</label>
      </div>
      <p className="text-[13px] text-muted">{t("knowledge.sources.fileIntro")}</p>
      <ErrorBox error={err} />
    </div>
  );
}

/** «Indsæt tekst»: up to 200 000 characters. */
export function PasteText({ wsId, disabled, onStarted, id = "kn-text" }: { wsId: string; disabled?: boolean; onStarted: (imp: Import) => void; id?: string }) {
  const t = useT("app");
  const [text, setText] = useState("");
  const s = useSubmit(async () => {
    onStarted(await api<Import>(`/workspaces/${wsId}/knowledge/import/text`, { method: "POST", body: JSON.stringify({ text }) }));
    setText(""); return true;
  });
  return (
    <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); s.run(); }}>
      <label htmlFor={id} className="text-[13px] font-semibold text-ink">{t("knowledge.sources.textLabel")}</label>
      <textarea id={id} rows={6} maxLength={MAX_TEXT_CHARS} className={`${inputCls} resize-y min-h-[132px]`} value={text} disabled={disabled}
        placeholder={t("knowledge.sources.textPlaceholder")} onChange={(e) => setText(e.target.value)} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[13px] text-muted">{t("knowledge.sources.chars", { n: text.length.toLocaleString(), max: MAX_TEXT_CHARS.toLocaleString() })}</span>
        <button type="submit" className={BTN_PRIMARY} disabled={disabled || s.pending || text.trim().length < 20}>{t("knowledge.sources.analyse")}</button>
      </div>
      <p className="text-[13px] text-muted">{t("knowledge.sources.textIntro")}</p>
      <ErrorBox error={s.error} />
    </form>
  );
}

const CAT_ORDER = ["service", "opening_hours", "faq", "policy", "contact", "fact", "offer", "coverage_area", "rule"];
const KIND_CAT: Record<string, string> = { service: "service", opening_hours: "opening_hours", known_answer: "faq", unknown_answer: "rule", offer: "offer", coverage_area: "coverage_area", fact: "fact" };

/** «Fandt 34 ting: 12 ydelser, 9 FAQ … · 3 overlapper eksisterende · 1 modstrid». */
export function ImportStatus({ imp }: { imp: Import | null }) {
  const t = useT("app");
  if (!imp) return null;
  const what = imp.source_type === "file" ? t("knowledge.sources.readingFile", { name: imp.source_name ?? "" }) : imp.source_type === "text" ? t("knowledge.sources.readingText") : t("knowledge.import.running");
  if (imp.status === "running") return <p role="status" className="text-[14px] text-ink-soft">{what} {imp.source_type !== "website" && t("knowledge.sources.running")}</p>;
  if (imp.status === "failed") return <p role="alert" className="text-[14px] text-danger">{imp.error ?? t("knowledge.sources.failed")}</p>;
  if (imp.source_type === "website" || !imp.summary) return <p role="status" className="text-[14px] text-ink">{imp.created_items.length === 0 ? t("knowledge.import.noNew") : t("knowledge.import.created", { n: imp.created_items.length })} · {t("knowledge.import.pages", { n: imp.pages.length })}</p>;
  const s = imp.summary;
  const cats = CAT_ORDER.filter((c) => s.by_category?.[c]).map((c) => t(`knowledge.sources.cat.${c}`, { n: s.by_category![c] }));
  const overlap = (s.updates ?? 0) + (s.duplicates ?? 0) + (s.pending ?? 0);
  return (
    <p role="status" className="text-[14px] text-ink" data-testid="import-summary">
      <b>{t("knowledge.sources.found", { n: s.found ?? 0 })}</b>{cats.length ? `: ${cats.join(", ")}` : ""}
      {overlap > 0 && ` · ${t("knowledge.sources.overlap", { n: overlap })}`}
      {(s.conflicts ?? 0) > 0 && <> · <b className="text-danger">{t("knowledge.sources.conflicts", { n: s.conflicts! })}</b></>}
      {(s.unverified ?? 0) > 0 && ` · ${t("knowledge.sources.unverified", { n: s.unverified! })}`}
      {imp.created_items.length === 0 && <span className="block">{t("knowledge.sources.nothing")}</span>}
    </p>
  );
}

type Draft = { id: string; status: string; title: string; source_ref?: string | null; review_note?: ReviewNote | null };
type ReviewItem = { id: string; kind: string; open_draft: Draft | null };

export const categoryOf = (i: ReviewItem) => i.open_draft?.review_note?.category ?? KIND_CAT[i.kind] ?? "fact";
export const hasConflict = (i: ReviewItem) => !!(i.open_draft?.review_note?.conflict || i.open_draft?.review_note?.conflicts?.length);

/** The grouped review: one block per category with «Godkend alle i kategorien», and «Godkend alle» on top. Suggestions
 *  with a conflict are left out of the bulk approval: the owner decides those one by one. `card` renders one draft
 *  (with inline editing). */
export function ReviewGroups<I extends ReviewItem>({ wsId, items, canApprove, card, onApproved }: { wsId: string; items: I[]; canApprove: boolean; card: (i: I) => React.ReactNode; onApproved?: () => void }) {
  const t = useT("app");
  const router = useRouter();
  const [ok, setOk] = useState<number | null>(null);
  const groups = CAT_ORDER.map((c) => [c, items.filter((i) => categoryOf(i) === c)] as const).filter(([, l]) => l.length);
  const approve = useSubmit(async (ids: string[]) => {
    const r = await api<{ approved: number }>(`/workspaces/${wsId}/knowledge/versions/approve-batch`, { method: "POST", body: JSON.stringify({ version_ids: ids }) });
    setOk(r.approved); router.refresh(); onApproved?.(); return true;
  });
  const bulk = (l: I[]) => l.filter((i) => !hasConflict(i) && i.open_draft).map((i) => i.open_draft!.id);
  const all = bulk(items);
  const conflicts = items.filter(hasConflict).length;
  if (!items.length) return ok != null ? <p role="status" className="text-[14px] font-semibold text-success">{t("knowledge.review.done", { n: ok })}</p> : null;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        {canApprove && all.length > 0 && <button type="button" className={BTN_PRIMARY} disabled={approve.pending} onClick={() => approve.run(all)}>{approve.pending ? t("knowledge.review.approving") : t("knowledge.review.approveAll", { n: all.length })}</button>}
        {ok != null && <span role="status" className="text-[14px] font-semibold text-success">{t("knowledge.review.done", { n: ok })}</span>}
        {canApprove && conflicts > 0 && <span className="text-[13px] text-ink-soft">{t("knowledge.review.conflictsSkipped")}</span>}
      </div>
      <ErrorBox error={approve.error} />
      {groups.map(([c, l]) => {
        const ids = bulk(l);
        return (
          <section key={c} aria-labelledby={`rv-${c}`} className="flex flex-col gap-3 rounded-xl border-[1.5px] border-ink p-3 sm:p-4" data-testid={`review-${c}`}>
            <div className="flex flex-wrap items-center gap-2 justify-between">
              <h3 id={`rv-${c}`} className="font-display font-bold text-[17px] text-ink">{t(`knowledge.review.group.${c}`)} <span className="text-muted font-sans text-[14px] font-semibold">({l.length})</span></h3>
              {canApprove && ids.length > 0 && <button type="button" className={BTN} disabled={approve.pending} onClick={() => approve.run(ids)} aria-label={`${t("knowledge.review.approveCategory")}: ${t(`knowledge.review.group.${c}`)}`}>{t("knowledge.review.approveCategory")}</button>}
            </div>
            {l.map((i) => <div key={i.id}>{card(i)}</div>)}
          </section>
        );
      })}
    </div>
  );
}

/** Source, «Opdaterer eksisterende» and conflicts for one draft (shown on its card). */
export function NoteLine({ note, sourceRef }: { note?: ReviewNote | null; sourceRef?: string | null }) {
  const t = useT("app");
  const src = note?.source ?? sourceRef;
  const conflicts = [...(note?.conflict ? [{ source: note.source ?? "", text: note.conflict }] : []), ...(note?.conflicts ?? [])];
  if (!src && !note) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        {note?.relation === "update" && <span className="inline-flex px-2.5 py-1 rounded-full bg-accent-soft border-[1.5px] border-ink text-[12px] font-semibold text-ink">{t("knowledge.review.update")}</span>}
        {src && <span className="text-[13px] text-muted break-all">{t("knowledge.review.source", { ref: src })}</span>}
      </div>
      {conflicts.map((c, i) => <p key={i} role="note" className="rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger"><b>{t("knowledge.review.conflict")}:</b> {c.text}{c.source && c.source !== src ? ` (${c.source})` : ""}</p>)}
    </div>
  );
}
