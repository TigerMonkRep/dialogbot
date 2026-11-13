/** M06: Danish labels and pills for the operators' support queue (operator pages stay Danish, see i18n/README). */
export type QueueItem = {
  id: string; number: number; subject: string; category: string; status: string; priority: string; created_at: string; updated_at: string;
  resolved_at: string | null; workspace: { id: string; name: string }; assigned_to: { id: string; name: string } | null;
  created_by: { name: string; email: string } | null; context_path: string;
};

export const STATUS: Record<string, string> = { open: "Hos Dialogbot", in_progress: "Under behandling", waiting_customer: "Afventer kunde", resolved: "Løst" };
export const PRIORITY: Record<string, string> = { critical: "Kritisk", high: "Høj", normal: "Normal", low: "Lav" };
export const CATEGORY: Record<string, string> = {
  reception: "Telefon, chat og reception", campaigns: "Kampagner og henvendelser", calendar: "Kalender og bookinger", billing: "Fakturering og forbrug", other: "Andet",
};

const STATUS_PILL: Record<string, string> = { open: "bg-accent-soft text-accent-deep", in_progress: "bg-accent-soft text-accent-deep", waiting_customer: "bg-highlight text-ink", resolved: "bg-success-soft text-success" };
const PRIO_PILL: Record<string, string> = { critical: "bg-danger text-white", high: "bg-danger-soft text-danger", normal: "bg-panel text-ink", low: "bg-paper text-muted" };
const pill = "inline-flex items-center rounded-full border-[1.5px] border-ink px-2.5 py-0.5 text-[12px] font-semibold whitespace-nowrap";

export const StatusPill = ({ s }: { s: string }) => <span data-status={s} className={`${pill} ${STATUS_PILL[s] ?? ""}`}>{STATUS[s] ?? s}</span>;
export const PriorityPill = ({ p }: { p: string }) => <span data-priority={p} className={`${pill} ${PRIO_PILL[p] ?? ""}`}>{PRIORITY[p] ?? p}</span>;
