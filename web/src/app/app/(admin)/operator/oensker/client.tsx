"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { Select, Textarea } from "@/components/ui";

const dt = (iso: string) => new Date(iso).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Copenhagen" });

export type Wish = {
  id: string; workspace_id: string; workspace_name: string; text: string; page: string | null; summary: string; category: string;
  status: "new" | "planned" | "done" | "declined"; admin_note: string; times_asked: number; created_at: string; updated_at: string | null;
  user?: { email: string; name: string } | null;
};
export type WishList = {
  items: Wish[]; total: number; categories: Record<string, string>;
  counts: { status: Record<Wish["status"], number>; category_open: Record<string, number> };
};

/** [tab label, badge label, badge colours] */
const STATUS: Record<Wish["status"], [string, string, string]> = {
  new: ["Nye", "Ny", "bg-highlight text-ink"], planned: ["Planlagt", "Planlagt", "bg-accent text-white"],
  done: ["Lavet", "Lavet", "bg-success-soft text-success"], declined: ["Afvist", "Afvist", "bg-paper text-muted border-[1.5px] border-line"],
};

/** Counts per status (tabs) and per category for the open wishes (new + planned), then one card per wish. */
export function Wishes({ data, status, category, q }: { data: WishList; status: string; category: string; q: string }) {
  const router = useRouter();
  const href = (p: { status?: string; category?: string; q?: string }) => {
    const sp = new URLSearchParams();
    const s = p.status ?? status, c = p.category ?? category, qq = p.q ?? q;
    if (s && s !== "new") sp.set("status", s);
    if (c) sp.set("category", c);
    if (qq) sp.set("q", qq);
    const str = sp.toString();
    return `/app/operator/oensker${str ? `?${str}` : ""}`;
  };
  const allCount = Object.values(data.counts.status).reduce((a, b) => a + b, 0);
  const pill = (active: boolean) => `inline-flex items-center gap-2 px-4 py-2 rounded-full border-2 border-ink text-[14px] font-semibold ${active ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-panel"}`;
  return (
    <div className="flex flex-col gap-space-md">
      <nav aria-label="Status" className="flex flex-wrap gap-2">
        {(Object.keys(STATUS) as Wish["status"][]).map((s) => (
          <Link key={s} href={href({ status: s })} aria-current={status === s ? "page" : undefined} className={pill(status === s)}>
            {STATUS[s][0]} <span className="tabular-nums">{data.counts.status[s] ?? 0}</span>
          </Link>
        ))}
        <Link href={href({ status: "all" })} aria-current={status === "all" ? "page" : undefined} className={pill(status === "all")}>Alle <span className="tabular-nums">{allCount}</span></Link>
      </nav>

      <section aria-label="Åbne ønsker pr. kategori" className="rounded-2xl bg-paper border-2 border-ink p-space-md flex flex-col gap-2">
        <h2 className="eyebrow">Åbne ønsker (nye + planlagte) pr. kategori</h2>
        <div className="flex flex-wrap gap-2">
          <Link href={href({ category: "" })} className={pill(!category)}>Alle kategorier</Link>
          {Object.entries(data.categories).map(([k, label]) => (
            <Link key={k} href={href({ category: k })} aria-current={category === k ? "page" : undefined} className={pill(category === k)}>
              {label} <span className="tabular-nums">{data.counts.category_open[k] ?? 0}</span>
            </Link>
          ))}
        </div>
      </section>

      <form action="/app/operator/oensker" className="flex flex-wrap gap-2 items-end">
        {status !== "new" && <input type="hidden" name="status" value={status} />}
        {category && <input type="hidden" name="category" value={category} />}
        <label className="flex-[1_1_240px] flex flex-col gap-1 text-[13px] font-semibold text-ink">Søg i ønsker og noter
          <input name="q" defaultValue={q} maxLength={100} className="min-h-[46px] px-3.5 rounded-xl border-2 border-ink bg-paper text-[15px] text-ink" />
        </label>
        <button type="submit" className="min-h-[46px] px-5 rounded-xl bg-ink text-paper text-[14px] font-semibold">Søg</button>
      </form>

      <p className="text-[14px] text-muted">{data.total === 0 ? "Ingen ønsker her." : `${data.total} ønske${data.total === 1 ? "" : "r"}${data.total > data.items.length ? ` – viser de ${data.items.length} nyeste` : ""}.`}</p>
      <ul className="flex flex-col gap-space-md">
        {data.items.map((w) => <WishCard key={w.id} w={w} categories={data.categories} onSaved={() => router.refresh()} />)}
      </ul>
    </div>
  );
}

function WishCard({ w, categories, onSaved }: { w: Wish; categories: Record<string, string>; onSaved: () => void }) {
  const [status, setStatus] = useState(w.status);
  const [note, setNote] = useState(w.admin_note);
  const [cat, setCat] = useState(w.category);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const dirty = status !== w.status || note !== w.admin_note || cat !== w.category;
  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await api(`/operator/assistant/requests/${w.id}`, { method: "PATCH", body: JSON.stringify({ status, admin_note: note, category: cat }) });
      setMsg({ ok: true, text: "Gemt." }); onSaved();
    } catch (e) { setMsg({ ok: false, text: (e as ApiError).message ?? "Kunne ikke gemme." }); }
    setBusy(false);
  };
  return (
    <li className="rounded-2xl bg-paper border-2 border-ink p-space-md flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-[1_1_320px]">
          <p className="font-display font-bold text-[17px] text-ink break-words">{w.summary}</p>
          <p className="text-[13px] text-muted">
            <Link href={`/app/operator/admin/kunder/${w.workspace_id}`} className="underline font-semibold text-ink">{w.workspace_name}</Link>
            {w.user && <> · {w.user.name || w.user.email}</>} · {dt(w.created_at)}{w.page && <> · på {w.page}</>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {w.times_asked > 1 && <span className="inline-flex px-2.5 py-0.5 rounded-full text-[12px] font-semibold bg-danger-soft text-danger">Spurgt {w.times_asked} gange</span>}
          <span className="inline-flex px-2.5 py-0.5 rounded-full text-[12px] font-semibold bg-panel border-[1.5px] border-ink text-ink">{categories[w.category] ?? w.category}</span>
          <span className={`inline-flex px-2.5 py-0.5 rounded-full text-[12px] font-semibold ${STATUS[w.status][2]}`}>{STATUS[w.status][1]}</span>
        </div>
      </div>
      <blockquote className="m-0 px-3.5 py-2.5 rounded-xl bg-panel border-l-4 border-ink text-[15px] text-ink break-words">«{w.text}»</blockquote>
      <div className="grid grid-cols-1 md:grid-cols-[180px_200px_1fr_auto] gap-2 items-start">
        <label className="flex flex-col gap-1 text-[13px] font-semibold text-ink">Status
          <Select value={status} onChange={(e) => setStatus(e.target.value as Wish["status"])}>
            {(Object.keys(STATUS) as Wish["status"][]).map((k) => <option key={k} value={k}>{STATUS[k][1]}</option>)}
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-[13px] font-semibold text-ink">Kategori
          <Select value={cat} onChange={(e) => setCat(e.target.value)}>
            {Object.entries(categories).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-[13px] font-semibold text-ink">Note (kun for Dialogbot)
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} className="min-h-[46px]" />
        </label>
        <button type="button" onClick={save} disabled={!dirty || busy} className="md:mt-6 min-h-[46px] px-5 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-50">{busy ? "Gemmer …" : "Gem"}</button>
      </div>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`m-0 text-[14px] ${msg.ok ? "text-success" : "text-danger"}`}>{msg.text}</p>}
    </li>
  );
}
