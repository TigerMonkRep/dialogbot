"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Button, Icon, Tag } from "@/components/ui";
import type { Task } from "./page";

export function ModeToggle({ wsId, mode, goals, canEdit }: { wsId: string; mode: string; goals: Record<string, unknown>; canEdit: boolean }) {
  const router = useRouter();
  const set = async (m: string) => { if (!canEdit || m === mode) return; await api(`/workspaces/${wsId}/goals`, { method: "PUT", body: JSON.stringify({ ...goals, guidance_mode: m, expected_version: goals.version }) }); router.refresh(); };
  const btn = (m: string, icon: string, label: string) => (
    <button onClick={() => set(m)} className={`flex items-center gap-space-xs px-3.5 py-1.5 rounded-lg text-label-md transition-all ${mode === m ? "bg-primary text-on-primary font-semibold shadow-sm" : "text-on-surface-variant hover:text-on-surface"}`} aria-pressed={mode === m}><Icon name={icon} size={16} />{label}</button>
  );
  return <div className="flex items-center gap-1 p-1 rounded-xl bg-surface-container-low">{btn("guided", "navigation", "Guid mig trin for trin")}{btn("self_managed", "tune", "Jeg vil selv sætte op")}</div>;
}

export function WhyBlock({ task }: { task: Task }) {
  const [open, setOpen] = useState(true);
  const why: Record<string, string> = {
    "knowledge.services": "Assistenten må kun love det, som virksomheden har godkendt. Uden mindst én godkendt ydelse findes der intet, den kan svare korrekt på.",
    "knowledge.review": "Kun ejere og administratorer kan gøre viden aktiv. Det sikrer, at ingen medarbejder ved en fejl publicerer priser eller løfter.",
    "checks.server": "Tjekkene beviser, at profil, sprog og godkendt viden hænger sammen. De bliver forældede, når du ændrer noget, så et gammelt bestået tjek ikke dækker en ny konfiguration.",
  };
  return (
    <div className="p-space-md rounded-lg bg-surface-container-lowest/10 backdrop-blur-sm space-y-2">
      <button onClick={() => setOpen(!open)} className="flex items-center justify-between w-full text-label-md text-secondary-fixed hover:text-white" aria-expanded={open}><span className="flex items-center gap-1.5"><Icon name="lightbulb" size={18} />Hvorfor dette trin er forudsætning?</span><Icon name="expand_more" size={18} className={open ? "rotate-180 transition-transform" : "transition-transform"} /></button>
      {open && <div className="text-primary-fixed text-body-sm leading-normal pt-1">{why[task.key] ?? `Trinnet er ${task.required ? "nødvendigt" : "valgfrit"} for de mål, du har valgt. ${task.blocked_by[0]?.message ?? ""}`}</div>}
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
  const item = (key: string, label: string, tag: React.ReactNode, text: string, disabled = false) => (
    <label className={`flex items-start gap-space-md p-space-md rounded-xl transition-all ${disabled ? "bg-surface-container/50 opacity-75" : "bg-surface-container-low hover:bg-surface-container"} ${canEdit && !disabled ? "cursor-pointer" : ""}`}>
      <input type="checkbox" className="mt-1 w-4 h-4 rounded accent-primary" checked={Boolean(g[key])} disabled={!canEdit || disabled} onChange={(e) => save({ [key]: e.target.checked })} />
      <div className="space-y-0.5"><div className="flex items-center gap-space-xs"><span className="text-label-lg font-bold text-on-surface">{label}</span>{tag}</div><p className="text-body-sm text-on-surface-variant">{text}</p></div>
    </label>
  );
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
      {reception && item("inbound_phone", "Indgående telefoni", <Tag tone="secondary">Tale AI</Tag>, "Besvarer hovednummer i og uden for åbningstid. Kræver telefoniudbyder (milepæl B).")}
      {reception && item("webchat", "Hjemmeside-webchat", <Tag>Widget</Tag>, "Synkroniseret vidensbase med web-widget på jeres hjemmeside.")}
      {reception && item("callback", "Bestilt callback", <Tag>SMS / Tale</Tag>, "Kunder anmoder om opringning. Hører under reception – ikke en separat prisplan.")}
      {reception && item("booking", "Aftalebooking", <Tag tone="tertiary">Kalender API</Tag>, "Direkte besigtigelsesbooking i jeres kalender. Kræver kalenderadapter (milepæl C).")}
      <label className={`flex items-start gap-space-md p-space-md rounded-xl bg-surface-container/50 ${reception ? "md:col-span-2" : ""}`}>
        <input type="checkbox" className="mt-1 w-4 h-4 rounded accent-primary" checked={g.product_intent === "campaigns" || g.product_intent === "both"} disabled={!canEdit} onChange={(e) => save({ product_intent: e.target.checked ? (reception ? "both" : "campaigns") : "reception" })} />
        <div className="space-y-0.5"><div className="flex items-center gap-space-xs"><span className="text-label-lg font-bold text-on-surface">Udgående kampagner</span><span className="px-2 py-0.5 rounded-full bg-surface-container-highest text-on-surface-variant text-label-sm">{g.product_intent === "reception" ? "Valgfri / deaktiveret" : "Aktiveret"}</span></div><p className="text-body-sm text-on-surface-variant">Forudbetalte kontaktpakker (9 kr., højst 2 forsøg). Betaling starter aldrig opkald. Milepæl D.</p></div>
      </label>
    </div>
  );
}

export function RunChecks({ wsId }: { wsId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="secondary" icon="play_arrow" disabled={pending} onClick={async () => {
        setPending(true);
        try { const r = await api<{ results: { status: string }[]; skipped: unknown[] }>(`/workspaces/${wsId}/setup/checks/run-all`, { method: "POST" }); setMsg(`${r.results.filter((x) => x.status === "passed").length}/${r.results.length} bestået · ${r.skipped.length} kræver integration`); router.refresh(); }
        catch (e) { setMsg((e as { message: string }).message); } finally { setPending(false); }
      }}>{pending ? "Kører…" : "Kør alle tjek"}</Button>
      {msg && <span className="text-label-sm text-on-surface-variant">{msg}</span>}
    </div>
  );
}

export function SkipButton({ wsId, taskKey, unskip }: { wsId: string; taskKey: string; unskip?: boolean }) {
  const router = useRouter();
  return <Button variant="ghost" className="border border-outline-variant/60 px-space-md py-2 text-label-md" onClick={async () => { try { await api(`/workspaces/${wsId}/setup/tasks/${taskKey}/${unskip ? "unskip" : "skip"}`, { method: "POST" }); router.refresh(); } catch (e) { alert((e as { message: string }).message); } }}>{unskip ? "Fortryd spring" : "Spring over"}</Button>;
}
