"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/client";
import { ErrorBox, useSubmit } from "@/components/ui";

/** M03 operator actions on the operations screen: one controlled retry of a failed job or calendar write, and
 *  suspend/resume of a tenant. Each click carries an Idempotency-Key (one per intent), so a double click or a retry
 *  of the request replays the first answer instead of acting twice. Nothing here runs by itself. */
const BTN = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper text-[14px] font-semibold text-ink hover:bg-panel disabled:opacity-50";
const BTN_DANGER = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-2 border-danger bg-paper text-[14px] font-semibold text-danger hover:bg-danger-soft disabled:opacity-50";
const RESULT: Record<string, string> = {
  queued: "Sat i kø til ét nyt forsøg.", already_queued: "Står allerede i kø – intet ekstra forsøg.",
  synced: "Skrevet i kalenderen.", already_synced: "Står allerede i kalenderen – intet skrevet.",
  failed: "Kalenderen fejlede igen – se fejlen.", nothing_to_do: "Intet at gøre.",
};

function useKey() {
  const key = useRef<string>("");
  return { get: () => (key.current ||= crypto.randomUUID()), reset: () => { key.current = ""; } };
}

export function RetryJob({ id, disabled, label }: { id: string; disabled?: boolean; label: string }) {
  const router = useRouter();
  const key = useKey();
  const [done, setDone] = useState<string | null>(null);
  const run = useSubmit(async () => {
    const r = await api<{ result: string }>(`/operator/admin/operations/jobs/${id}/retry`, {
      method: "POST", body: "{}", headers: { "Idempotency-Key": key.get() } });
    setDone(RESULT[r.result] ?? r.result);
    key.reset();
    router.refresh();
  });
  return (
    <span className="flex flex-col gap-1">
      <button type="button" className={BTN} disabled={disabled || run.pending} onClick={() => run.run()} aria-label={`${label}: genkør én gang`}>
        {run.pending ? "Genkører…" : "Genkør én gang"}</button>
      {done && <span role="status" className="text-[13px] text-ink">{done}</span>}
      <ErrorBox error={run.error} />
    </span>
  );
}

export function RetryCalendar({ id, outcome, disabled, label }: { id: string; outcome: string | null; disabled?: boolean; label: string }) {
  const router = useRouter();
  const key = useKey();
  const [checked, setChecked] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const unknown = outcome === "unknown";
  const run = useSubmit(async () => {
    const r = await api<{ result: string }>(`/operator/admin/operations/bookings/${id}/calendar-retry`, {
      method: "POST", body: JSON.stringify({ confirm_not_created: unknown && checked }), headers: { "Idempotency-Key": key.get() } });
    setDone(RESULT[r.result] ?? r.result);
    key.reset();
    router.refresh();
  });
  return (
    <span className="flex flex-col gap-1.5">
      {unknown && (
        <label className="flex items-start gap-2 text-[13px] text-ink max-w-[360px]">
          <input type="checkbox" className="mt-1 w-4 h-4" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
          <span>Jeg har set efter i kundens kalender: aftalen står der ikke.</span>
        </label>
      )}
      <button type="button" className={BTN} disabled={disabled || run.pending || (unknown && !checked)} onClick={() => run.run()} aria-label={`${label}: prøv kalenderen igen`}>
        {run.pending ? "Skriver…" : "Prøv kalenderen igen"}</button>
      {done && <span role="status" className="text-[13px] text-ink">{done}</span>}
      <ErrorBox error={run.error} />
    </span>
  );
}

export function Suspend({ workspaceId, name, suspended }: { workspaceId: string; name: string; suspended: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const run = useSubmit(async (action: "suspend" | "resume") => {
    await api(`/operator/admin/operations/workspaces/${workspaceId}/${action}`, {
      method: "POST", body: JSON.stringify(action === "suspend" ? { reason } : {}) });
    setOpen(false);
    setReason("");
    router.refresh();
  });
  if (suspended) {
    return (
      <span className="flex flex-col gap-1">
        <button type="button" className={BTN} disabled={run.pending} onClick={() => run.run("resume")} aria-label={`Genoptag ${name}`}>{run.pending ? "Genoptager…" : "Genoptag"}</button>
        <ErrorBox error={run.error} />
      </span>
    );
  }
  if (!open) return <button type="button" className={BTN_DANGER} onClick={() => setOpen(true)} aria-label={`Sæt ${name} på pause`}>Sæt kunden på pause</button>;
  return (
    <form className="flex flex-col gap-2 max-w-[420px]" onSubmit={(e) => { e.preventDefault(); run.run("suspend"); }}>
      <label className="text-[13px] font-semibold text-ink" htmlFor={`susp-${workspaceId}`}>Hvorfor sættes {name} på pause?</label>
      <input id={`susp-${workspaceId}`} required minLength={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)}
        className="min-h-[44px] rounded-xl border-[1.5px] border-ink px-3 text-[14px]" placeholder="Fx Google-kalenderen svarer 401" />
      <p className="text-[12px] text-muted">Køen, kampagneopkald og handlinger i kundens systemer venter, til I genoptager. Indgående opkald og chat besvares stadig.</p>
      <span className="flex flex-wrap gap-2">
        <button type="submit" className={BTN_DANGER} disabled={run.pending || reason.trim().length < 3}>{run.pending ? "Sætter på pause…" : "Sæt på pause"}</button>
        <button type="button" className={BTN} onClick={() => setOpen(false)}>Fortryd</button>
      </span>
      <ErrorBox error={run.error} />
    </form>
  );
}
