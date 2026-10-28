"use client";
import Link from "next/link";
import { useState } from "react";

export type Row = { label: string; value: string; status: "ready" | "soon" | "off"; ark?: string; href?: string; say?: string; tech?: boolean };
export type Chapter = { n: number; title: string; sub: string; rows: Row[] };

const STATUS: Record<Row["status"], [string, string]> = {
  ready: ["Klar", "bg-success-soft text-success"],
  soon: ["På vej", "bg-highlight text-ink"],
  off: ["Ikke sat op", "bg-paper text-muted border-[1.5px] border-line"],
};

/** Ask the assistant (in the dock) about one setting: simple values go through «før → efter → Godkend». */
function askAssistant(text: string) { window.dispatchEvent(new CustomEvent("dialogbot:assistant", { detail: { say: text } })); }

/** The chapters as tiles: search, status legend, «Vis teknik». «Ændr» opens the assistant or a sheet with the existing form. */
export function SettingsTiles({ chapters, canChange }: { chapters: Chapter[]; canChange: boolean }) {
  const [q, setQ] = useState("");
  const [tech, setTech] = useState(false);
  const needle = q.trim().toLowerCase();
  const shown = chapters.map((c) => ({ ...c, rows: c.rows.filter((r) => (tech || !r.tech) && (!needle || `${c.title} ${r.label} ${r.value}`.toLowerCase().includes(needle))) })).filter((c) => c.rows.length > 0 && (tech || c.title !== "Teknik" || c.rows.length > 0));
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex-[1_1_280px]">
          <label htmlFor="ind-q" className="block text-[13px] font-semibold text-ink mb-1">Find en indstilling</label>
          <input id="ind-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Fx åbningstider, kalender, stemme" className="w-full min-h-[46px] px-4 rounded-xl bg-paper border-2 border-ink text-[15px] text-ink placeholder:text-muted focus:outline-none focus:ring-[3px] focus:ring-accent focus:ring-offset-2" />
        </div>
        <label className="inline-flex items-center gap-2 min-h-[46px] text-[14px] font-semibold text-ink"><input type="checkbox" className="w-5 h-5 accent-[#2456F6]" checked={tech} onChange={(e) => setTech(e.target.checked)} />Vis teknik (API, webhooks, log)</label>
      </div>
      <ul className="flex flex-wrap gap-x-5 gap-y-1.5 text-[13px] text-ink-soft" aria-label="Forklaring af status">
        {(["ready", "soon", "off"] as const).map((s) => <li key={s} className="inline-flex items-center gap-2"><span className={`inline-flex px-2.5 py-0.5 rounded-full text-[12px] font-semibold ${STATUS[s][1]}`}>{STATUS[s][0]}</span>{s === "ready" ? "virker nu" : s === "soon" ? "vi kobler det på med dig" : "bruges ikke endnu"}</li>)}
      </ul>
      {shown.length === 0 && <p className="rounded-xl border-[1.5px] border-dashed border-ink px-4 py-4 text-[14px] text-ink-soft">Ingen indstillinger passer til «{q}».</p>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {shown.map((c) => (
          <section key={c.title} className="flex flex-col gap-3 rounded-2xl border-2 border-ink bg-paper px-5 py-5" aria-labelledby={`ch-${c.n}`}>
            <div className="flex items-center gap-3">
              <span className="inline-flex w-10 h-10 shrink-0 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-[20px] text-ink" aria-hidden>{c.n}</span>
              <div><h2 id={`ch-${c.n}`} className="font-display font-extrabold text-[20px] leading-tight text-ink">{c.title}</h2><p className="text-[13px] text-muted">{c.sub}</p></div>
            </div>
            <ul className="flex flex-col">
              {c.rows.map((r) => (
                <li key={r.label} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-3 border-t-[1.5px] border-line">
                  <span className="flex-[1_1_120px] text-[15px] font-semibold text-ink">{r.label}</span>
                  <span className="flex-[2_1_160px] min-w-0 text-[14px] text-ink-soft break-words">{r.value}</span>
                  <span className={`inline-flex px-2.5 py-0.5 rounded-full text-[12px] font-semibold ${STATUS[r.status][1]}`}>{STATUS[r.status][0]}</span>
                  {r.ark ? <Link href={`/app/indstillinger?ark=${r.ark}`} aria-label={`Ændr ${r.label}`} className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-lg border-[1.5px] border-ink text-[13px] font-semibold text-ink hover:bg-panel">Ændr</Link>
                    : r.href ? <Link href={r.href} aria-label={`Åbn ${r.label}`} className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-lg border-[1.5px] border-ink text-[13px] font-semibold text-ink hover:bg-panel">Åbn</Link>
                    : r.say && canChange ? <button type="button" aria-label={`Ændr ${r.label}`} className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-lg border-[1.5px] border-ink text-[13px] font-semibold text-ink hover:bg-panel" onClick={() => askAssistant(r.say!)}>Ændr</button> : null}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
