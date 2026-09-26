"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { Icon } from "@/components/ui";
import type { Task } from "./page";
import { whyText } from "./why";

export function ModeToggle({ wsId, mode, goals, canEdit }: { wsId: string; mode: string; goals: Record<string, unknown>; canEdit: boolean }) {
  const router = useRouter();
  const set = async (m: string) => { if (!canEdit || m === mode) return; await api(`/workspaces/${wsId}/goals`, { method: "PUT", body: JSON.stringify({ ...goals, guidance_mode: m, expected_version: goals.version }) }); router.refresh(); };
  const btn = (m: string, icon: string, label: string) => (
    <button onClick={() => set(m)} aria-pressed={mode === m} disabled={!canEdit}
      className={`flex items-center gap-space-xs px-3.5 py-1.5 rounded-lg font-label-md text-label-md transition-all ${mode === m ? "bg-primary text-on-primary font-semibold" : "text-on-surface-variant hover:text-on-surface font-medium"}`}>
      <Icon name={icon} size={16} /><span>{label}</span>
    </button>
  );
  return <div className="inline-flex p-1 rounded-xl bg-surface-container-lowest shadow-sm" role="group" aria-label="Vejledningstilstand">{btn("guided", "navigation", "Guid mig trin for trin")}{btn("self_managed", "tune", "Jeg vil selv sætte op")}</div>;
}

export function WhyBlock({ task }: { task: Task }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="p-space-md rounded-lg bg-surface-container-lowest/10 backdrop-blur-sm text-on-primary space-y-2">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex items-center justify-between w-full font-label-md text-label-md text-secondary-fixed hover:text-white transition-colors">
        <span className="flex items-center gap-1.5"><Icon name="lightbulb" size={18} />Hvorfor dette trin er forudsætning?</span>
        <Icon name="expand_more" size={18} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="text-primary-fixed font-body-sm text-body-sm leading-normal pt-1">{whyText(task)}</div>}
    </div>
  );
}

export function GoalArchitecture({ wsId, goals, canEdit }: { wsId: string; goals: Record<string, unknown>; canEdit: boolean }) {
  const router = useRouter();
  const [g, setG] = useState(goals);
  const reception = g.product_intent !== "campaigns";
  const save = async (patch: Record<string, unknown>) => {
    const next = { ...g, ...patch };
    setG(next);
    try { await api(`/workspaces/${wsId}/goals`, { method: "PUT", body: JSON.stringify({ ...next, expected_version: goals.version }) }); router.refresh(); } catch (e) { alert((e as { message: string }).message); setG(goals); }
  };
  const tag = (text: string, tone: "secondary" | "neutral" | "tertiary") => (
    <span className={`px-1.5 rounded font-label-sm text-label-sm ${tone === "secondary" ? "bg-secondary-fixed text-on-secondary-fixed font-semibold" : tone === "tertiary" ? "bg-tertiary-fixed text-on-tertiary-fixed font-semibold" : "bg-surface-container-highest text-on-surface"}`}>{text}</span>
  );
  const item = (key: string, label: string, t: React.ReactNode, text: string) => (
    <label className={`flex items-start gap-space-md p-space-md rounded-xl bg-surface-container-low transition-all hover:bg-surface-container ${canEdit ? "cursor-pointer" : ""}`}>
      <input type="checkbox" className="mt-1 w-4 h-4 rounded accent-primary" checked={Boolean(g[key])} disabled={!canEdit} onChange={(e) => save({ [key]: e.target.checked })} />
      <div className="space-y-0.5">
        <div className="flex items-center gap-space-xs"><span className="font-label-lg text-label-lg font-bold text-on-surface">{label}</span>{t}</div>
        <p className="font-body-sm text-body-sm text-on-surface-variant">{text}</p>
      </div>
    </label>
  );
  const campaignsOn = g.product_intent === "campaigns" || g.product_intent === "both";
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
      {reception && item("inbound_phone", "Indgående telefoni", tag("Tale AI", "secondary"), "Besvarer hovednummeret i og uden for åbningstid. Kræver telefoniudbyder.")}
      {reception && item("webchat", "Hjemmeside-webchat", tag("Widget", "neutral"), "Samme godkendte viden i en web-widget på jeres hjemmeside.")}
      {reception && item("callback", "Bestilt callback", tag("SMS / Tale", "neutral"), "Kunder anmoder om opringning. Hører under reception – ikke en separat prisplan.")}
      {reception && item("booking", "Aftalebooking", tag("Kalender API", "tertiary"), "Direkte booking i jeres kalender. Kræver kalenderadapter.")}
      <label className={`flex items-start gap-space-md p-space-md rounded-xl transition-all md:col-span-2 ${campaignsOn ? "bg-surface-container-low hover:bg-surface-container" : "bg-surface-container/50 opacity-75 hover:opacity-100"} ${canEdit ? "cursor-pointer" : ""}`}>
        <input type="checkbox" className="mt-1 w-4 h-4 rounded accent-primary" checked={campaignsOn} disabled={!canEdit} onChange={(e) => save({ product_intent: e.target.checked ? (reception ? "both" : "campaigns") : "reception" })} />
        <div className="space-y-0.5">
          <div className="flex items-center gap-space-xs">
            <span className="font-label-lg text-label-lg font-bold text-on-surface">Udgående kampagner</span>
            <span className="px-2 py-0.5 rounded-full bg-surface-container-highest text-on-surface-variant font-label-sm text-label-sm">{campaignsOn ? "Aktiveret" : "Valgfri / deaktiveret"}</span>
          </div>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Forudbetalte kontaktpakker (9 kr., højst 2 forsøg). Betaling starter aldrig opkald.</p>
        </div>
      </label>
    </div>
  );
}

/** "Udvid alle" for the <details> phase list. */
export function ExpandAll({ target }: { target: string }) {
  const [all, setAll] = useState(false);
  return (
    <button className="font-label-md text-label-md text-secondary hover:underline font-semibold" aria-controls={target}
      onClick={() => { const next = !all; document.querySelectorAll<HTMLDetailsElement>(`#${target} > details`).forEach((d) => { d.open = next; }); setAll(next); }}>
      {all ? "Fold alle sammen" : "Udvid alle"}
    </button>
  );
}

export function RunChecks({ wsId, compact = false }: { wsId: string; compact?: boolean }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <div className="flex flex-col items-end gap-1 flex-shrink-0">
      <button disabled={pending} className={`rounded-lg bg-secondary-fixed text-on-secondary-fixed font-label-md text-label-md font-bold hover:brightness-105 transition-all shadow-sm flex items-center gap-1 disabled:opacity-60 ${compact ? "px-3 h-9" : "px-3 py-1.5"}`}
        onClick={async () => {
          setPending(true);
          try { const r = await api<{ results: { status: string }[]; skipped: unknown[] }>(`/workspaces/${wsId}/setup/checks/run-all`, { method: "POST" }); setMsg(`${r.results.filter((x) => x.status === "passed").length}/${r.results.length} bestået`); router.refresh(); }
          catch (e) { setMsg((e as { message: string }).message); } finally { setPending(false); }
        }}>
        <Icon name="play_arrow" size={18} />{pending ? "Kører…" : "Kør alle"}
      </button>
      {msg && <span role="status" className="font-label-sm text-label-sm text-on-surface-variant">{msg}</span>}
    </div>
  );
}

export function SkipButton({ wsId, taskKey, unskip }: { wsId: string; taskKey: string; unskip?: boolean }) {
  const router = useRouter();
  return (
    <button className="px-2.5 py-1 rounded font-label-sm text-label-sm text-on-surface-variant hover:bg-surface-container"
      onClick={async () => { try { await api(`/workspaces/${wsId}/setup/tasks/${taskKey}/${unskip ? "unskip" : "skip"}`, { method: "POST" }); router.refresh(); } catch (e) { alert((e as { message: string }).message); } }}>
      {unskip ? "Fortryd spring" : "Spring over"}
    </button>
  );
}

/** G04 mobile slide-up sheet. Only real destinations; unbuilt support goes to the honest placeholder. */
export function HelpSheet({ next }: { next: { label: string; why: string; href: string } | null }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey); return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  const shortcut = (href: string, icon: string, title: string, sub: string) => (
    <Link href={href} onClick={() => setOpen(false)} className="w-full p-3 rounded-lg bg-surface-container flex items-center justify-between text-left hover:bg-surface-container-high transition-colors">
      <span className="flex items-center gap-space-xs"><Icon name={icon} size={20} className="text-primary" /><span className="flex flex-col"><span className="font-label-md text-label-md text-primary font-semibold">{title}</span><span className="font-body-sm text-[12px] text-on-surface-variant">{sub}</span></span></span>
      <Icon name="arrow_forward" size={18} className="text-outline" />
    </Link>
  );
  return (
    <>
      <button onClick={() => setOpen(true)} aria-haspopup="dialog" className="w-full h-10 rounded-lg bg-secondary-container text-on-secondary-container font-label-lg text-label-lg font-bold flex items-center justify-center gap-2 shadow-sm active:scale-[0.98] transition-transform">
        <Icon name="lightbulb" size={18} /><span>Åbn Hjælp mig videre</span>
      </button>
      {open && (
        <div className="fixed inset-0 z-[60] bg-inverse-surface/40 backdrop-blur-sm flex flex-col justify-end" onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
          <div role="dialog" aria-modal="true" aria-labelledby="g04-title" className="w-full bg-surface-container-lowest rounded-t-2xl p-margin pb-safe flex flex-col gap-space-md shadow-2xl text-on-surface">
            <div className="w-12 h-1 bg-outline-variant rounded-full mx-auto" />
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-md bg-secondary-container text-on-secondary-fixed flex items-center justify-center"><Icon name="explore" size={18} /></div>
                <span id="g04-title" className="font-headline-sm text-headline-sm text-primary">Hjælp mig videre</span>
              </div>
              <button autoFocus onClick={() => setOpen(false)} aria-label="Luk" className="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-on-surface-variant"><Icon name="close" size={18} /></button>
            </div>
            {next && <p className="font-body-sm text-body-sm text-on-surface-variant"><strong className="text-primary">{next.label}:</strong> {next.why}</p>}
            <div className="flex flex-col gap-2 pb-space-md">
              {next && shortcut(next.href, "bolt", `Gå til: ${next.label}`, "Det anbefalede næste trin")}
              {shortcut("/app/knowledge?tab=k05", "fact_check", "Gennemgå og godkend viden", "Kun godkendt viden bruges af assistenten")}
              {shortcut("/app/not-yet?area=Kundesupport", "support_agent", "Kundesupport", "Ikke bygget endnu")}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
