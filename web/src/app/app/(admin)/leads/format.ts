export type Lead = {
  id: string; version: number; source: string; conversation_id: string | null; contact_name: string; contact_email: string | null;
  contact_phone: string | null; need_summary: string; qualification_status: string; qualification_reason: string | null;
  pipeline_status: string; billing_status: string; billing_reason: string | null; billing_decided_at: string | null;
  fee_snapshot: { net_minor: number; tax_minor: number; gross_minor: number; agreement_version: number; model: string } | null;
  created_at: string; tasks?: TaskItem[];
};
export type TaskItem = { id: string; lead_id: string | null; title: string; status: string; due_at: string | null; assignee_user_id: string | null; created_at: string; completed_at: string | null };

export const QUAL: Record<string, [string, string]> = {
  unqualified: ["Ikke vurderet", "bg-surface-container-high text-on-surface-variant"],
  qualified: ["Kvalificeret", "bg-secondary-container text-on-secondary-container"],
  disqualified: ["Ikke relevant", "bg-error-container text-on-error-container"],
};
export const PIPE: Record<string, string> = { new: "Ny", contacted: "Kontaktet", won: "Vundet", lost: "Tabt" };
export const BILL: Record<string, [string, string]> = {
  pending: ["Afventer godkendelse", "bg-tertiary-fixed text-on-tertiary-fixed"],
  approved: ["Godkendt", "bg-secondary-container text-on-secondary-container"],
  rejected: ["Afvist", "bg-surface-container-high text-on-surface-variant"],
};
export const SOURCE: Record<string, string> = { webchat: "Webchat", phone: "Telefon", manual: "Manuel" };

/** Whole øre → "149,00 kr." */
export const kr = (minor: number) => `${(minor / 100).toLocaleString("da-DK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kr.`;
export const when = (iso: string) => new Date(iso).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" });
