/** Campaign types and status labels (plain module: usable from server and client components). */
import type { T } from "@/i18n/translate";
export type Counts = { total: number; open: number; calls: number; by_status: Record<string, number>; by_outcome: Record<string, number> };
export type Campaign = {
  id: string; name: string; status: "draft" | "running" | "paused" | "completed"; version: number; purpose: string; opening: string;
  questions: string[]; success: string; phone_number_id: string | null; call_days: string[]; call_from: string; call_to: string;
  pricing: { call_net_minor: number; minute_net_minor: number; max_attempts: number; max_connected_seconds: number; currency?: string }; counts: Counts;
  max_cost: { net_minor: number; tax_minor: number; gross_minor: number }; outbound_problem: string | null;
  legal_confirmation: { at: string; accepted_max_net_minor: number } | null; started_at: string | null; completed_at: string | null;
};
export type Contact = {
  id: string; name: string; company: string; phone: string; email: string | null; kind: string; consent_source: string; status: string;
  attempts: number; connected_seconds: number; outcome: string | null; summary: string; error: string | null; lead_id: string | null; charged: boolean;
};
export type Dnc = { id: string; phone: string; reason: string; source: string; created_at: string };
export type PhoneNumber = { id: string; e164: string; label: string; active: boolean };

/** Status → pill class; the label is `app.campaigns.status.<status>`. */
export const STATUS: Record<Campaign["status"], string> = {
  draft: "bg-line text-ink-soft",
  running: "bg-success-soft text-success",
  paused: "bg-accent-soft text-accent-deep",
  completed: "bg-panel text-ink",
};
const CONTACT_STATUS = ["pending", "calling", "done", "no_answer", "failed", "opted_out", "skipped"];
const OUTCOME = ["interested", "callback", "not_interested", "opt_out", "no_answer"];
/** A contact's outcome if it has one, else its status (unknown values are shown as they are). */
export const contactLabel = (t: T, x: { outcome: string | null; status: string }) =>
  x.outcome ? (OUTCOME.includes(x.outcome) ? t(`campaigns.outcome.${x.outcome}`) : x.outcome)
    : CONTACT_STATUS.includes(x.status) ? t(`campaigns.contactStatus.${x.status}`) : x.status;
