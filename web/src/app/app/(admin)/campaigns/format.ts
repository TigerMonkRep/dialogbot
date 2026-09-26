/** Campaign types and Danish labels (plain module: usable from server and client components). */
export type Counts = { total: number; open: number; packages_used: number; by_status: Record<string, number>; by_outcome: Record<string, number> };
export type Campaign = {
  id: string; name: string; status: "draft" | "running" | "paused" | "completed"; version: number; purpose: string; opening: string;
  questions: string[]; success: string; phone_number_id: string | null; call_days: string[]; call_from: string; call_to: string;
  package: { net_minor: number; max_attempts: number; max_connected_seconds: number }; counts: Counts;
  max_cost: { net_minor: number; tax_minor: number; gross_minor: number }; outbound_problem: string | null;
  legal_confirmation: { at: string; accepted_max_net_minor: number } | null; started_at: string | null; completed_at: string | null;
};
export type Contact = {
  id: string; name: string; company: string; phone: string; email: string | null; kind: string; consent_source: string; status: string;
  attempts: number; connected_seconds: number; outcome: string | null; summary: string; error: string | null; lead_id: string | null; charged: boolean;
};
export type Dnc = { id: string; phone: string; reason: string; source: string; created_at: string };
export type PhoneNumber = { id: string; e164: string; label: string; active: boolean };

export const STATUS: Record<Campaign["status"], [string, string]> = {
  draft: ["Kladde", "bg-surface-container-high text-on-surface-variant"],
  running: ["Kører", "bg-secondary-container text-on-secondary-container"],
  paused: ["På pause", "bg-tertiary-fixed text-on-tertiary-fixed"],
  completed: ["Afsluttet", "bg-primary-fixed text-on-primary-fixed"],
};
export const CONTACT_STATUS: Record<string, string> = {
  pending: "Venter", calling: "Ringer nu", done: "Talt med", no_answer: "Intet svar", failed: "Fejlede", opted_out: "Frabedt sig opkald", skipped: "Spærret",
};
export const OUTCOME: Record<string, string> = {
  interested: "Interesseret", callback: "Ring tilbage", not_interested: "Ikke interesseret", opt_out: "Vil ikke ringes op", no_answer: "Intet svar",
};
