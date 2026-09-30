/** Types and formatting shared by the ambassador portal and the operator pages. */
export type Terms = { bonus_minor: number; rate_bp: number; months: number; hold_days?: number; customer_discount_bp?: number; min_payout_minor?: number; min_age?: number };
export type Balances = { held_minor: number; payable_minor: number; in_payout_minor: number; paid_minor: number; min_payout_minor: number };
export type Profile = {
  enrolled: true; id: string; status: "pending" | "active" | "suspended" | "rejected"; kind: "private" | "company";
  full_name: string; email: string | null; phone: string; slug: string; code: string; link: string; headline: string;
  company_name: string | null; cvr: string | null; vat_registered: boolean; birth_date: string | null; minor: boolean;
  parent_name: string | null; parent_email: string | null; parent_consent_at: string | null;
  has_cpr: boolean; has_bank: boolean; bank_last4: string | null; terms: Terms; payout_blockers: string[]; decision_note: string;
  stats: { clicks_30d: number; customers: number; paying: number }; balances: Balances; version: number; created_at: string;
};
export type Customer = { workspace_id: string; company: string; status: string; signed_up: string; via: string; first_paid_month: string | null; share_until: string | null; earned_minor: number };
export type Entry = { id: string; kind: "bonus" | "share" | "reversal"; label: string; company: string; month: string; base_minor: number; amount_minor: number; status: string; status_label: string; hold_until: string; payout_id: string | null; created_at: string };
export type Payout = { id: string; number: number; status: "pending" | "paid" | "cancelled"; amount_minor: number; income_type: "b_income" | "invoice"; reference: string; paid_at: string | null; created_at: string };
export type Statement = Payout & { ambassador: { full_name: string; kind: string; company_name: string | null; cvr: string | null; vat_registered: boolean; bank_last4: string | null }; lines: Entry[]; tax_note: string };
export type Program = { rules_version: string; rules_text: string; quiz: { id: string; question: string; options: { id: string; label: string }[] }[]; terms: Terms };

export const kr = (minor: number) => `${(minor / 100).toLocaleString("da-DK", { minimumFractionDigits: minor % 100 ? 2 : 0, maximumFractionDigits: 2 })} kr.`;
export const pct = (bp: number) => `${(bp / 100).toLocaleString("da-DK")} %`;
export const date = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" }) : "–");
export const monthLabel = (ym: string | null) => {
  if (!ym) return "–";
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("da-DK", { month: "long", year: "numeric" });
};
export const STATUS: Record<Profile["status"], { label: string; tone: string }> = {
  pending: { label: "Afventer godkendelse", tone: "bg-tertiary-fixed text-on-tertiary-fixed" },
  active: { label: "Aktiv", tone: "bg-secondary-container text-on-secondary-container" },
  suspended: { label: "Sat på pause", tone: "bg-error-container text-on-error-container" },
  rejected: { label: "Ikke godkendt", tone: "bg-surface-container-high text-on-surface-variant" },
};
