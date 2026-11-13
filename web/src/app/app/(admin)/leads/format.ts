export type Lead = {
  id: string; version: number; source: string; conversation_id: string | null; contact_name: string; contact_email: string | null;
  contact_phone: string | null; need_summary: string; callback_from: string | null; callback_to: string | null; phone_verified_at?: string | null; callback_cancelled_at?: string | null; qualification_status: string; qualification_reason: string | null;
  pipeline_status: string; billing_status: string; billing_reason: string | null; billing_decided_at: string | null;
  fee_snapshot: { net_minor: number; tax_minor: number; gross_minor: number; agreement_version: number; model: string } | null;
  created_at: string; tasks?: TaskItem[];
};
export type TaskItem = { id: string; lead_id: string | null; title: string; status: string; due_at: string | null; assignee_user_id: string | null; created_at: string; completed_at: string | null };

import type { T } from "@/i18n/translate";
import { currencyOr, formatMoney } from "@/lib/markets";

/** Status → pill class; labels are `app.leads.qual.<k>`, `app.leads.pipe.<k>`, `app.leads.bill.<k>`, `app.leads.source.<k>`. */
export const QUAL: Record<string, string> = {
  unqualified: "bg-line text-ink-soft",
  qualified: "bg-success-soft text-success",
  disqualified: "bg-danger-soft text-danger",
};
export const PIPE = ["new", "contacted", "won", "lost"];
export const BILL: Record<string, string> = {
  pending: "bg-accent-soft text-accent-deep",
  approved: "bg-success-soft text-success",
  rejected: "bg-line text-ink-soft",
};
const SOURCES = ["webchat", "phone", "manual", "campaign"];
export const sourceLabel = (t: T, s: string) => (SOURCES.includes(s) ? t(`leads.source.${s}`) : s);

/** Minor units → "4,00 kr." (da/DKK) · "€0.55" (en/EUR): the viewer's language, the agreement's currency (DKK when the
 *  backend does not say). `lang` is a BCP-47 tag (HTML_LANG). */
export const kr = (minor: number, lang = "da", currency?: string | null) => formatMoney(minor, currencyOr(currency), lang);
export const when = (iso: string, lang = "da") => new Date(iso).toLocaleString(lang, { dateStyle: "short", timeStyle: "short" });

/** "tirsdag 29.9. kl. 08.00–12.00" in the viewer's locale time zone. */
export const callbackWindow = (t: T, lang: string, from: string, to: string) => {
  const f = new Date(from), e = new Date(to);
  return t("leads.callbackWindow", { day: f.toLocaleDateString(lang, { weekday: "long", day: "numeric", month: "numeric" }),
    from: f.toLocaleTimeString(lang, { timeStyle: "short" }), to: e.toLocaleTimeString(lang, { timeStyle: "short" }) });
};
