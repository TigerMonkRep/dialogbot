"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { ErrorBox, Icon, inputCls, useSubmit } from "@/components/ui";
import type { Item, Profile, SourceImport, Version } from "./types";
import { DAYS, KIND_LABEL, UNIT_LABEL, parsePrice, summarize } from "./format";

type Content = Record<string, unknown>;
const DAY_DA: Record<string, string> = { mon: "Man", tue: "Tir", wed: "Ons", thu: "Tor", fri: "Fre", sat: "Lør", sun: "Søn" };
const BTN = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-[1.5px] border-ink bg-paper text-[14px] font-semibold text-ink hover:bg-panel disabled:opacity-50";
const BTN_PRIMARY = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-50";
const SMALL = "inline-flex items-center justify-center min-h-[44px] px-3.5 rounded-lg border-[1.5px] border-ink bg-paper text-[13px] font-semibold text-ink hover:bg-panel disabled:opacity-50";
const LABEL = "block text-[13px] font-semibold text-ink mb-1";

export const EMPTY: Record<string, Content> = {
  service: { description: "", unit: "job", price_net_minor: null, currency: "DKK", promote: true },
  opening_hours: { weekly: [{ days: ["mon", "tue", "wed", "thu", "fri"], open: "08:00", close: "16:00" }], closed_note: "" },
  coverage_area: { zones: [] },
  fact: { text: "" }, known_answer: { question: "", answer: "" }, unknown_answer: { rule: "" },
  offer: { discount_percent: 10, condition: { area_operator: "gte", area_threshold_m2: 40 }, starts_on: "", ends_on_inclusive: "" },
};

/** Draft → (approve | submit). Owners and admins publish at once; others send the change for review. */
async function save(wsId: string, canApprove: boolean, p: { item?: Item; kind: string; title: string; content: Content }): Promise<"live" | "pending"> {
  let v: Version;
  const draft = p.item?.open_draft;
  if (draft) v = await api<Version>(`/workspaces/${wsId}/knowledge/versions/${draft.id}`, { method: "PUT", body: JSON.stringify({ expected_edit_version: draft.edit_version, title: p.title, content: p.content }) });
  else if (p.item) v = await api<Version>(`/workspaces/${wsId}/knowledge/items/${p.item.id}/drafts`, { method: "POST", body: JSON.stringify({ title: p.title, content: p.content }) });
  else v = (await api<Item>(`/workspaces/${wsId}/knowledge/items`, { method: "POST", body: JSON.stringify({ kind: p.kind, title: p.title, content: p.content }) })).open_draft!;
  if (canApprove) { await api(`/workspaces/${wsId}/knowledge/versions/${v.id}/approve`, { method: "POST", headers: { "idempotency-key": `approve-${v.id}` } }); return "live"; }
  if (v.status === "draft") await api(`/workspaces/${wsId}/knowledge/versions/${v.id}/submit`, { method: "POST" });
  return "pending";
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return <div><label htmlFor={id} className={LABEL}>{label}</label>{children}</div>;
}

/** Fields per kind. Prices are typed in kr and stored in øre. */
function Fields({ kind, value, onChange, id }: { kind: string; value: Content; onChange: (c: Content) => void; id: string }) {
  const set = (k: string, v: unknown) => onChange({ ...value, [k]: v });
  switch (kind) {
    case "service": {
      const minor = value.price_net_minor as number | null;
      return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Field label="Pris (ekskl. moms)" id={`${id}-price`}>
            <div className="flex items-center gap-2"><input id={`${id}-price`} inputMode="decimal" className={inputCls} value={minor == null ? "" : String(minor / 100).replace(".", ",")}
              onChange={(e) => { const t = e.target.value.replace(/\./g, "").replace(",", "."); const n = Number(t); set("price_net_minor", t.trim() === "" ? null : Number.isFinite(n) ? Math.round(n * 100) : minor); }} /><span className="text-[14px] text-ink-soft">kr</span></div>
          </Field>
          <Field label="Enhed" id={`${id}-unit`}>
            <select id={`${id}-unit`} className={inputCls} value={String(value.unit ?? "job")} onChange={(e) => set("unit", e.target.value)}>{Object.entries(UNIT_LABEL).map(([k, l]) => <option key={k} value={k}>pr. {l}</option>)}</select>
          </Field>
          <Field label="Sælger den selv?" id={`${id}-promote`}>
            <select id={`${id}-promote`} className={inputCls} value={value.promote === false ? "no" : "yes"} onChange={(e) => set("promote", e.target.value === "yes")}><option value="yes">Sælger</option><option value="no">Kun hvis spurgt</option></select>
          </Field>
          <div className="md:col-span-3"><Field label="Hvad skal den sige bagefter?" id={`${id}-desc`}><textarea id={`${id}-desc`} rows={2} className={`${inputCls} resize-y`} value={String(value.description ?? "")} onChange={(e) => set("description", e.target.value)} /></Field></div>
        </div>
      );
    }
    case "opening_hours": {
      const weekly = (value.weekly as { days: string[]; open: string; close: string }[]) ?? [];
      const setRow = (i: number, row: Partial<(typeof weekly)[number]>) => set("weekly", weekly.map((w, j) => (j === i ? { ...w, ...row } : w)));
      return (
        <div className="flex flex-col gap-3">
          {weekly.map((w, i) => (
            <fieldset key={i} className="rounded-xl border-[1.5px] border-line p-3 flex flex-col gap-2">
              <legend className="sr-only">Tidsrum {i + 1}</legend>
              <div className="flex flex-wrap gap-1.5">{DAYS.map((d) => { const on = w.days.includes(d); return <button type="button" key={d} aria-pressed={on} onClick={() => setRow(i, { days: on ? w.days.filter((x) => x !== d) : [...w.days, d] })} className={`min-h-[44px] min-w-[44px] px-2.5 rounded-lg border-[1.5px] border-ink text-[13px] font-semibold ${on ? "bg-ink text-paper" : "text-ink"}`}>{DAY_DA[d]}</button>; })}</div>
              <div className="flex items-center gap-2">
                <input aria-label="Åbner" type="time" className={`${inputCls} w-32`} value={w.open} onChange={(e) => setRow(i, { open: e.target.value })} /><span aria-hidden>–</span>
                <input aria-label="Lukker" type="time" className={`${inputCls} w-32`} value={w.close} onChange={(e) => setRow(i, { close: e.target.value })} />
                {weekly.length > 1 && <button type="button" aria-label="Fjern tidsrum" className={`${SMALL} ml-auto`} onClick={() => set("weekly", weekly.filter((_, j) => j !== i))}><Icon name="delete" size={18} /></button>}
              </div>
            </fieldset>
          ))}
          <button type="button" className={`${SMALL} self-start`} onClick={() => set("weekly", [...weekly, { days: ["sat"], open: "10:00", close: "14:00" }])}>+ Tilføj tidsrum</button>
          <Field label="Uden for åbningstid" id={`${id}-note`}><input id={`${id}-note`} className={inputCls} value={String(value.closed_note ?? "")} onChange={(e) => set("closed_note", e.target.value)} placeholder="Fx weekend og helligdage: tager kun imod besked" /></Field>
        </div>
      );
    }
    case "coverage_area":
      return <Field label="Hvor kører I? (adskil med komma)" id={`${id}-zones`}><input id={`${id}-zones`} className={inputCls} value={((value.zones as string[]) ?? []).join(", ")} onChange={(e) => set("zones", e.target.value.split(",").map((z) => z.trim()).filter(Boolean))} /></Field>;
    case "fact":
      return <Field label="Det, den må vide" id={`${id}-text`}><textarea id={`${id}-text`} rows={2} className={inputCls} value={String(value.text ?? "")} onChange={(e) => set("text", e.target.value)} /></Field>;
    case "known_answer":
      return (
        <div className="flex flex-col gap-3">
          <Field label="Spørgsmålet" id={`${id}-q`}><input id={`${id}-q`} className={inputCls} value={String(value.question ?? "")} onChange={(e) => set("question", e.target.value)} /></Field>
          <Field label="Svaret" id={`${id}-a`}><textarea id={`${id}-a`} rows={3} className={inputCls} value={String(value.answer ?? "")} onChange={(e) => set("answer", e.target.value)} /></Field>
        </div>
      );
    case "unknown_answer":
      return <Field label="Emne, den ikke må udtale sig om" id={`${id}-rule`}><input id={`${id}-rule`} className={inputCls} value={String(value.rule ?? "")} onChange={(e) => set("rule", e.target.value)} /></Field>;
    case "offer": {
      const cond = (value.condition as { area_threshold_m2: number | null }) ?? { area_threshold_m2: null };
      return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Rabat (%)" id={`${id}-pct`}><input id={`${id}-pct`} type="number" min={1} max={100} className={inputCls} value={Number(value.discount_percent ?? 0)} onChange={(e) => set("discount_percent", Number(e.target.value))} /></Field>
          <Field label="Gælder ved mindst (m²)" id={`${id}-thr`}><input id={`${id}-thr`} type="number" min={0} className={inputCls} value={cond.area_threshold_m2 ?? ""} onChange={(e) => set("condition", { area_operator: "gte", area_threshold_m2: e.target.value === "" ? null : Number(e.target.value) })} /></Field>
          <Field label="Fra" id={`${id}-from`}><input id={`${id}-from`} type="date" className={inputCls} value={String(value.starts_on ?? "")} onChange={(e) => set("starts_on", e.target.value)} /></Field>
          <Field label="Til og med" id={`${id}-to`}><input id={`${id}-to`} type="date" className={inputCls} value={String(value.ends_on_inclusive ?? "")} onChange={(e) => set("ends_on_inclusive", e.target.value)} /></Field>
        </div>
      );
    }
    default: return null;
  }
}

const titleOf = (kind: string, c: Content, fallback: string) =>
  kind === "known_answer" ? String(c.question ?? "").slice(0, 120) || fallback : kind === "unknown_answer" ? String(c.rule ?? "").slice(0, 120) || fallback : kind === "fact" ? String(c.text ?? "").slice(0, 80) || fallback : fallback;

/** Inline editor for one knowledge item (or a new one). Saving publishes for owners/admins, otherwise it goes to review. */
export function ItemEditor({ wsId, canApprove, kind, item, title: t0, onDone, askTitle = false }: { wsId: string; canApprove: boolean; kind: string; item?: Item; title?: string; onDone?: () => void; askTitle?: boolean }) {
  const router = useRouter();
  const src = item?.open_draft ?? item?.approved_version;
  const [title, setTitle] = useState(src?.title ?? t0 ?? "");
  const [content, setContent] = useState<Content>(src?.content ?? EMPTY[kind]);
  const [done, setDone] = useState<"live" | "pending" | null>(null);
  const s = useSubmit(async () => {
    const r = await save(wsId, canApprove, { item, kind, title: askTitle || kind === "service" || kind === "offer" ? title.trim() : titleOf(kind, content, title || KIND_LABEL[kind]), content });
    setDone(r); router.refresh(); onDone?.(); return true;
  });
  const id = item?.id ?? `new-${kind}`;
  return (
    <form className="flex flex-col gap-3 rounded-xl border-[1.5px] border-dashed border-ink p-4" onSubmit={(e) => { e.preventDefault(); s.run(); }}>
      {(askTitle || kind === "service" || kind === "offer") && <Field label={kind === "offer" ? "Hvad hedder tilbuddet?" : "Hvad hedder den?"} id={`${id}-title`}><input id={`${id}-title`} required className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>}
      <Fields kind={kind} value={content} onChange={(c) => { setContent(c); setDone(null); }} id={id} />
      <ErrorBox error={s.error} />
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={s.pending} className={BTN_PRIMARY}>{s.pending ? "Gemmer…" : canApprove ? "Gem" : "Send til godkendelse"}</button>
        {done === "live" && <span role="status" className="text-[14px] font-semibold text-success">Gemt – Dialogbot bruger det nu</span>}
        {done === "pending" && <span role="status" className="text-[14px] font-semibold text-ink">Sendt til godkendelse hos en ejer eller administrator</span>}
      </div>
    </form>
  );
}

/** «Ret» button that opens/closes an editor under the row. */
export function Edit({ wsId, canApprove, kind, item, label = "Ret" }: { wsId: string; canApprove: boolean; kind: string; item?: Item; label?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col gap-3 w-full">
      <button type="button" className={`${SMALL} self-start`} aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Luk" : label}</button>
      {open && <ItemEditor wsId={wsId} canApprove={canApprove} kind={kind} item={item} askTitle={kind === "fact"} />}
    </div>
  );
}

/** Name + what you do: the business profile (not knowledge), saved directly. */
export function ProfileEdit({ wsId, profile }: { wsId: string; profile: Profile }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(profile.legal_name);
  const [desc, setDesc] = useState(profile.description);
  const [ok, setOk] = useState(false);
  const s = useSubmit(async () => {
    await api(`/workspaces/${wsId}/profile`, { method: "PUT", body: JSON.stringify({ ...profile, legal_name: name.trim(), description: desc.trim(), expected_version: profile.version }) });
    setOk(true); router.refresh(); return true;
  });
  return (
    <div className="flex flex-col gap-3">
      <button type="button" className={`${SMALL} self-start`} aria-expanded={open} onClick={() => { setOpen(!open); setOk(false); }}>{open ? "Luk" : "Ret"}</button>
      {open && (
        <form className="flex flex-col gap-3 rounded-xl border-[1.5px] border-dashed border-ink p-4" onSubmit={(e) => { e.preventDefault(); s.run(); }}>
          <Field label="Navn" id="p-name"><input id="p-name" required className={inputCls} value={name} onChange={(e) => { setName(e.target.value); setOk(false); }} /></Field>
          <Field label="Hvad I laver" id="p-desc"><textarea id="p-desc" rows={3} className={inputCls} value={desc} onChange={(e) => { setDesc(e.target.value); setOk(false); }} /></Field>
          <ErrorBox error={s.error} />
          <div className="flex items-center gap-3"><button type="submit" disabled={s.pending} className={BTN_PRIMARY}>Gem</button>{ok && <span role="status" className="text-[14px] font-semibold text-success">Gemt</span>}</div>
        </form>
      )}
    </div>
  );
}

/** «Hør»: asks Dialogbot the question a customer would ask and shows the answer right here. */
export function Hear({ wsId, question }: { wsId: string; question: string }) {
  const [reply, setReply] = useState<string | null>(null);
  const ask = useSubmit(async () => { setReply((await api<{ reply: string }>(`/workspaces/${wsId}/assistant/preview`, { method: "POST", body: JSON.stringify({ message: question }) })).reply); return true; });
  return (
    <div className="flex flex-col gap-2 items-end">
      <button type="button" className={SMALL} disabled={ask.pending} onClick={() => ask.run()}>{ask.pending ? "Lytter…" : "Hør"}</button>
      {reply && <p role="status" className="max-w-[420px] rounded-xl border-2 border-ink bg-accent-soft px-3.5 py-2.5 text-[14px] text-ink"><span className="eyebrow block mb-0.5">Sådan svarer den på «{question}»</span>{reply}</p>}
      <ErrorBox error={ask.error} />
    </div>
  );
}

/** «Tilføj en ydelse»: three fields. Saved, then Dialogbot answers the obvious question so you hear how it says it. */
export function AddService({ wsId, canApprove, canAsk }: { wsId: string; canApprove: boolean; canAsk: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(""), [price, setPrice] = useState(""), [note, setNote] = useState("");
  const [heard, setHeard] = useState<{ q: string; a: string } | null>(null);
  const [pending, setPending] = useState(false);
  const s = useSubmit(async () => {
    const p = parsePrice(price);
    if (!p) throw { status: 422, code: "bad_price", message: "Skriv prisen med tal, fx «fra 1.200 kr.» eller «850 kr. pr. m²»." } satisfies Partial<ApiError>;
    const r = await save(wsId, canApprove, { kind: "service", title: name.trim(), content: { description: [price.trim() && `Pris: ${price.trim()}.`, note.trim()].filter(Boolean).join(" "), unit: p.unit, price_net_minor: p.minor, currency: "DKK", promote: true } });
    setPending(r === "pending");
    if (r === "live" && canAsk) { const q = `Hvad koster ${name.trim()}?`; setHeard({ q, a: (await api<{ reply: string }>(`/workspaces/${wsId}/assistant/preview`, { method: "POST", body: JSON.stringify({ message: q }) })).reply }); }
    setName(""); setPrice(""); setNote(""); router.refresh(); return true;
  });
  return (
    <div className="flex flex-col gap-3">
      <button type="button" aria-expanded={open} className={BTN_PRIMARY + " self-start"} onClick={() => setOpen(!open)}><Icon name={open ? "close" : "add"} size={18} />&nbsp;{open ? "Luk" : "Tilføj en ydelse"}</button>
      {open && (
        <form className="rounded-xl border-2 border-dashed border-ink p-4 flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); s.run(); }}>
          <span className="eyebrow">Ny ydelse · 3 felter</span>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Hvad hedder den?" id="ns-name"><input id="ns-name" required className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Pris (som kunden skal høre den)" id="ns-price"><input id="ns-price" required className={inputCls} value={price} onChange={(e) => setPrice(e.target.value)} placeholder="fra 1.200 kr." /></Field>
            <Field label="Hvad skal den sige bagefter?" id="ns-note"><input id="ns-note" className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Fx: Vi aftaler tid for besigtigelse" /></Field>
          </div>
          <ErrorBox error={s.error} />
          <div className="flex flex-wrap gap-3"><button type="submit" disabled={s.pending || !name.trim()} className={BTN_PRIMARY}>{s.pending ? "Gemmer…" : canApprove ? "Gem – og vis mig, hvordan den siger det" : "Send til godkendelse"}</button><button type="button" className={BTN} onClick={() => setOpen(false)}>Annuller</button></div>
          {pending && <p role="status" className="text-[14px] text-ink">Sendt til godkendelse hos en ejer eller administrator.</p>}
          {heard && <p role="status" className="rounded-xl border-2 border-ink bg-accent-soft px-3.5 py-2.5 text-[14px] text-ink"><span className="eyebrow block mb-0.5">Sådan svarer den på «{heard.q}»</span>{heard.a}</p>}
        </form>
      )}
    </div>
  );
}

/** «Tilføj et svar» / «Tilføj en regel» / «Tilføj tilbud»: a new item of one kind, opened from a button. */
export function AddItem({ wsId, canApprove, kind, label, initial, openByDefault = false, id }: { wsId: string; canApprove: boolean; kind: "known_answer" | "unknown_answer" | "offer" | "fact"; label: string; initial?: Content; openByDefault?: boolean; id?: string }) {
  const [open, setOpen] = useState(openByDefault);
  return (
    <div className="flex flex-col gap-3" id={id}>
      <button type="button" aria-expanded={open} className={`${BTN} self-start border-dashed`} onClick={() => setOpen(!open)}>{open ? "Luk" : `+ ${label}`}</button>
      {open && <NewWithInitial wsId={wsId} canApprove={canApprove} kind={kind} initial={initial} onDone={() => setOpen(false)} />}
    </div>
  );
}
function NewWithInitial({ wsId, canApprove, kind, initial, onDone }: { wsId: string; canApprove: boolean; kind: string; initial?: Content; onDone: () => void }) {
  const router = useRouter();
  const [content, setContent] = useState<Content>({ ...EMPTY[kind], ...initial });
  const [title, setTitle] = useState("");
  const [done, setDone] = useState<"live" | "pending" | null>(null);
  const s = useSubmit(async () => {
    const r = await save(wsId, canApprove, { kind, title: kind === "offer" ? title.trim() : titleOf(kind, content, KIND_LABEL[kind]), content });
    setDone(r); router.refresh(); if (r === "live") onDone(); return true;
  });
  return (
    <form className="flex flex-col gap-3 rounded-xl border-[1.5px] border-dashed border-ink p-4" onSubmit={(e) => { e.preventDefault(); s.run(); }}>
      {kind === "offer" && <Field label="Hvad hedder tilbuddet?" id="no-title"><input id="no-title" required className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>}
      <Fields kind={kind} value={content} onChange={setContent} id={`add-${kind}`} />
      <ErrorBox error={s.error} />
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={s.pending} className={BTN_PRIMARY}>{s.pending ? "Gemmer…" : canApprove ? "Gem" : "Send til godkendelse"}</button>
        {done === "pending" && <span role="status" className="text-[14px] font-semibold text-ink">Sendt til godkendelse</span>}
      </div>
    </form>
  );
}

/** Remove an approved item (approvers) or a draft. */
export function Remove({ wsId, item, canApprove, label }: { wsId: string; item: Item; canApprove: boolean; label: string }) {
  const router = useRouter();
  const del = useSubmit(async () => {
    if (!window.confirm(`Fjern «${label}»? Dialogbot holder straks op med at bruge det.`)) return false;
    await api(`/workspaces/${wsId}/knowledge/items/${item.id}`, { method: "DELETE" });
    router.refresh(); return true;
  });
  if (item.approved_version && !canApprove) return null;
  return <><button type="button" aria-label={`Fjern ${label}`} title="Fjern" className={SMALL} disabled={del.pending} onClick={() => del.run()}><Icon name="delete" size={18} /></button><ErrorBox error={del.error} /></>;
}

/** A proposed change (draft or in review): before → after, with «Godkend», «Ret» and «Afvis». */
export function DraftCard({ wsId, item, canApprove, canDraft, note }: { wsId: string; item: Item; canApprove: boolean; canDraft: boolean; note?: string }) {
  const router = useRouter();
  const v = item.open_draft!;
  const [editing, setEditing] = useState(false);
  const next = summarize(item.kind, v.content);
  const was = item.approved_version ? summarize(item.kind, item.approved_version.content) : null;
  const act = useSubmit(async () => {
    await api(`/workspaces/${wsId}/knowledge/versions/${v.id}/approve`, { method: "POST", headers: { "idempotency-key": `approve-${v.id}` } });
    router.refresh(); return true;
  });
  const reject = useSubmit(async () => {
    const reason = window.prompt("Hvorfor afviser du forslaget? (gemmes i loggen)", "Passer ikke");
    if (!reason) return false;
    if (v.status === "draft") await api(`/workspaces/${wsId}/knowledge/versions/${v.id}/submit`, { method: "POST" });
    await api(`/workspaces/${wsId}/knowledge/versions/${v.id}/reject`, { method: "POST", body: JSON.stringify({ reason }) });
    router.refresh(); return true;
  });
  const submit = useSubmit(async () => { await api(`/workspaces/${wsId}/knowledge/versions/${v.id}/submit`, { method: "POST" }); router.refresh(); return true; });
  return (
    <div className="flex flex-col gap-3 rounded-xl border-2 border-dashed border-ink p-4">
      <span className="eyebrow">{note ?? "Dialogbot foreslår"} · {KIND_LABEL[item.kind] ?? item.kind}</span>
      <p className="text-[16px] font-semibold text-ink">{item.kind === "known_answer" ? `«${next.headline}»` : v.title}</p>
      {was && <p className="text-[14px] text-ink-soft"><b className="text-ink">Nu:</b> {was.headline}{was.detail ? ` – ${was.detail}` : ""}</p>}
      <p className="text-[14px] text-ink-soft">{was && <b className="text-ink">Forslag: </b>}{item.kind === "known_answer" ? next.detail : `${next.headline}${next.detail ? ` – ${next.detail}` : ""}`}</p>
      <div className="flex flex-wrap items-center gap-2.5">
        {canApprove ? <button type="button" className={BTN_PRIMARY} disabled={act.pending} onClick={() => act.run()}>{act.pending ? "Godkender…" : item.kind === "known_answer" ? "Godkend svaret" : "Godkend"}</button>
          : v.status === "draft" && canDraft ? <button type="button" className={BTN_PRIMARY} disabled={submit.pending} onClick={() => submit.run()}>Send til godkendelse</button>
          : <span className="text-[14px] font-semibold text-ink">Afventer godkendelse hos en ejer eller administrator</span>}
        {canDraft && <button type="button" className={BTN} aria-expanded={editing} onClick={() => setEditing(!editing)}>{item.kind === "known_answer" ? "Ret svaret" : "Ret"}</button>}
        {canApprove && <button type="button" className={BTN} disabled={reject.pending} onClick={() => reject.run()}>Afvis</button>}
      </div>
      <ErrorBox error={act.error ?? reject.error ?? submit.error} />
      {editing && <ItemEditor wsId={wsId} canApprove={false} kind={item.kind} item={item} onDone={() => setEditing(false)} askTitle={item.kind === "fact"} />}
    </div>
  );
}

/** Show the first rows, reveal the rest. */
export function More({ children, count, label }: { children: React.ReactNode; count: number; label: string }) {
  const [open, setOpen] = useState(false);
  if (count <= 0) return null;
  return <>{open && children}<button type="button" aria-expanded={open} className="self-start min-h-[44px] text-[14px] font-semibold text-accent hover:underline" onClick={() => setOpen(!open)}>{open ? "Vis færre" : label}</button></>;
}

/** «Hent fra hjemmesiden»: the backend reads the site and creates drafts; they show up in the boxes as «Dialogbot foreslår». */
export function ImportFromSite({ wsId, defaultUrl, initial, aiReady, openByDefault }: { wsId: string; defaultUrl: string; initial: SourceImport | null; aiReady: boolean; openByDefault: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(openByDefault);
  const [url, setUrl] = useState(defaultUrl);
  const [imp, setImp] = useState<SourceImport | null>(initial);
  const running = imp?.status === "running";
  const start = useSubmit(async () => { setImp(await api<SourceImport>(`/workspaces/${wsId}/knowledge/import`, { method: "POST", body: JSON.stringify({ url }) })); return true; });
  useEffect(() => {
    if (!running) return;
    const t = setInterval(async () => {
      const r = await api<{ import: SourceImport | null }>(`/workspaces/${wsId}/knowledge/imports/latest`).catch(() => null);
      if (r?.import && r.import.status !== "running") { setImp(r.import); router.refresh(); }
    }, 3000);
    return () => clearInterval(t);
  }, [running, wsId, router]);
  return (
    <div className="flex flex-col gap-3">
      <button type="button" className={BTN} aria-expanded={open} onClick={() => setOpen(!open)}><Icon name="download" size={18} />&nbsp;Hent fra hjemmesiden</button>
      {open && (
        <div className="flex flex-col gap-3 rounded-2xl border-2 border-ink bg-paper p-4 max-w-[640px]">
          <p className="text-[14px] text-ink-soft">Vi læser jeres egne sider og foreslår ydelser, fakta og faste svar. Forslagene ligger som kladder, til du har godkendt dem. Priser gættes aldrig.</p>
          {!aiReady ? <p className="text-[14px] text-ink">Kræver, at AI er slået til på serveren.</p> : (
            <form className="flex flex-col sm:flex-row gap-3" onSubmit={(e) => { e.preventDefault(); start.run(); }}>
              <label htmlFor="imp-url" className="sr-only">Hjemmesidens adresse</label>
              <input id="imp-url" className={inputCls} placeholder="https://www.jeres-firma.dk" value={url} onChange={(e) => setUrl(e.target.value)} disabled={running} />
              <button type="submit" className={`${BTN_PRIMARY} shrink-0`} disabled={start.pending || running || !url.trim()}>{running ? "Læser hjemmesiden…" : "Hent forslag"}</button>
            </form>
          )}
          <ErrorBox error={start.error} />
          {running && <p role="status" className="text-[14px] text-ink-soft">Læser sider og skriver forslag. Det tager typisk under et minut.</p>}
          {imp?.status === "failed" && <p role="alert" className="text-[14px] text-danger">{imp.error ?? "Importen fejlede."}</p>}
          {imp?.status === "done" && <p role="status" className="text-[14px] text-ink">{imp.created_items.length === 0 ? "Ingen nye forslag" : `${imp.created_items.length} forslag lagt som kladder – godkend dem herunder`} · {imp.pages.length} sider læst.</p>}
        </div>
      )}
    </div>
  );
}
