/** H01 support: types and small pieces shared by the list (/app/support) and the ticket page (/app/support/[ticket]). */
export type Attachment = { id: string; filename: string; content_type: string; size_bytes: number };
export type Message = { id: string; author_kind: "customer" | "operator"; author_name: string; body: string; created_at: string; attachments: Attachment[] };
export type Status = "open" | "in_progress" | "waiting_customer" | "resolved";
export type Summary = { number: number; subject: string; category: string; status: Status; created_at: string; updated_at: string; resolved_at: string | null };
export type Ticket = Summary & { created_by: string | null; messages: Message[] };
export type List = { items: Summary[]; open: number; categories: string[]; max_files: number; max_bytes: number };

/** Status → pill colours (brand tokens): waiting for the customer is the one that asks for action (Trin-gul). */
const PILL: Record<Status, string> = {
  open: "bg-accent-soft text-accent-deep border-accent-soft",
  in_progress: "bg-accent-soft text-accent-deep border-accent-soft",
  waiting_customer: "bg-highlight text-ink border-highlight",
  resolved: "bg-success-soft text-success border-success-soft",
};

export function StatusPill({ status, label }: { status: Status; label: string }) {
  return <span data-status={status} className={`inline-flex items-center rounded-full border-[1.5px] px-2.5 py-0.5 text-[12px] font-semibold uppercase tracking-[0.06em] whitespace-nowrap ${PILL[status] ?? PILL.open}`}>{label}</span>;
}

export const when = (lang: string, iso: string) =>
  new Date(iso).toLocaleString(lang, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Copenhagen" });

export const size = (lang: string, n: number) =>
  n >= 1024 * 1024 ? `${(n / 1024 / 1024).toLocaleString(lang, { maximumFractionDigits: 1 })} MB` : `${Math.max(1, Math.round(n / 1024)).toLocaleString(lang)} KB`;
