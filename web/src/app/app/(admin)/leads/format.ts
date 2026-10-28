export type Lead = {
  id: string; version: number; source: string; conversation_id: string | null; contact_name: string; contact_email: string | null;
  contact_phone: string | null; need_summary: string; callback_from: string | null; callback_to: string | null; qualification_status: string; qualification_reason: string | null;
  pipeline_status: string; billing_status: string; billing_reason: string | null; billing_decided_at: string | null;
  fee_snapshot: { net_minor: number; tax_minor: number; gross_minor: number; agreement_version: number; model: string } | null;
  created_at: string; tasks?: TaskItem[];
};
export type TaskItem = { id: string; lead_id: string | null; title: string; status: string; due_at: string | null; assignee_user_id: string | null; created_at: string; completed_at: string | null };

export const QUAL: Record<string, [string, string]> = {
  unqualified: ["Ikke vurderet", "bg-line text-ink-soft"],
  qualified: ["Kvalificeret", "bg-success-soft text-success"],
  disqualified: ["Ikke relevant", "bg-danger-soft text-danger"],
};
export const PIPE: Record<string, string> = { new: "Ny", contacted: "Kontaktet", won: "Vundet", lost: "Tabt" };
export const BILL: Record<string, [string, string]> = {
  pending: ["Afventer godkendelse", "bg-accent-soft text-accent-deep"],
  approved: ["Godkendt", "bg-success-soft text-success"],
  rejected: ["Afvist", "bg-line text-ink-soft"],
};
export const SOURCE: Record<string, string> = { webchat: "Webchat", phone: "Telefon", manual: "Manuel", campaign: "Kampagne" };

/** Whole øre → "4,00 kr." */
export const kr = (minor: number) => `${(minor / 100).toLocaleString("da-DK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kr.`;
export const when = (iso: string) => new Date(iso).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" });

/** "tirsdag 29.9. kl. 08.00–12.00" in the viewer's locale time zone. */
export const callbackWindow = (from: string, to: string) => {
  const f = new Date(from), t = new Date(to);
  return `${f.toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "numeric" })} kl. ${f.toLocaleTimeString("da-DK", { timeStyle: "short" })}–${t.toLocaleTimeString("da-DK", { timeStyle: "short" })}`;
};
