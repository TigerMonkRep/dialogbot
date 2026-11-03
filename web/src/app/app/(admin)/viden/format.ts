/** Shared (server + client) helpers for rendering knowledge content. Money is stored in øre (minor units). */

import type { T } from "@/i18n/translate";

const KINDS = ["service", "opening_hours", "coverage_area", "fact", "known_answer", "unknown_answer", "offer"];
/** Kind → label (`app.knowledge.kind.<kind>`); unknown kinds are shown as they are. */
export const kindLabel = (t: T, kind: string) => (KINDS.includes(kind) ? t(`knowledge.kind.${kind}`) : kind);
/** Price units; labels are `app.knowledge.unit.<unit>`. */
export const UNITS = ["m2", "hour", "item", "job"];
export const unitLabel = (t: T, u: string) => (UNITS.includes(u) ? t(`knowledge.unit.${u}`) : u);
export const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

/** `lang` is a BCP-47 tag (HTML_LANG[locale]). */
export function kr(minor: unknown, lang = "da"): string | null {
  if (typeof minor !== "number") return null;
  return `${(minor / 100).toLocaleString(lang, { minimumFractionDigits: minor % 100 ? 2 : 0, maximumFractionDigits: 2 })},-`;
}

/** `dayNames` are the lower-case short weekday names Monday→Sunday (`app.time.weekdaysShortLower`). */
export function daysLabel(days: string[], dayNames: string[]): string {
  const idx = days.map((d) => DAYS.indexOf(d as (typeof DAYS)[number])).filter((i) => i >= 0).sort((a, b) => a - b);
  const contiguous = idx.every((v, i) => i === 0 || v === idx[i - 1] + 1);
  return contiguous && idx.length > 2 ? `${dayNames[idx[0]]}–${dayNames[idx[idx.length - 1]]}` : idx.map((i) => dayNames[i]).join(", ");
}

export const dateDa = (iso: unknown, lang = "da") => typeof iso === "string" ? new Date(iso + "T00:00:00").toLocaleDateString(lang, { day: "numeric", month: "short", year: "numeric" }) : "";

/** What `summarize` needs to speak the viewer's language. */
export type Fmt = { t: T; lang: string; days: string[] };

/** One-line headline + detail for any knowledge kind (used in K03/K05 cards). */
export function summarize(f: Fmt, kind: string, c: Record<string, unknown>): { headline: string; detail: string } {
  const { t, lang } = f;
  switch (kind) {
    case "service": {
      const price = kr(c.price_net_minor, lang);
      return { headline: price ? `${price} kr${c.unit ? ` / ${unitLabel(t, String(c.unit))}` : ""}` : t("knowledge.sum.noPrice"), detail: String(c.description ?? "") };
    }
    case "opening_hours": {
      const weekly = (c.weekly as { days: string[]; open: string; close: string }[] | undefined) ?? [];
      return { headline: weekly.map((w) => `${daysLabel(w.days, f.days)} ${w.open}–${w.close}`).join(" · ") || t("knowledge.sum.noTimes"), detail: String(c.closed_note ?? "") };
    }
    case "coverage_area": return { headline: ((c.zones as string[] | undefined) ?? []).join(" · ") || t("knowledge.sum.noZones"), detail: "" };
    case "fact": return { headline: String(c.text ?? ""), detail: "" };
    case "known_answer": return { headline: String(c.question ?? ""), detail: String(c.answer ?? "") };
    case "unknown_answer": return { headline: String(c.rule ?? ""), detail: t("knowledge.sum.human") };
    case "offer": {
      const cond = (c.condition as { area_operator?: string; area_threshold_m2?: number } | undefined) ?? {};
      const thr = cond.area_threshold_m2 != null ? `${cond.area_operator === "gt" ? ">" : "≥"} ${cond.area_threshold_m2} m²` : t("knowledge.sum.allAreas");
      return { headline: t("knowledge.sum.discount", { pct: String(c.discount_percent ?? 0), thr }), detail: t("knowledge.sum.period", { from: dateDa(c.starts_on, lang), to: dateDa(c.ends_on_inclusive, lang) }) };
    }
    default: return { headline: JSON.stringify(c), detail: "" };
  }
}

/** «fra 1.200 kr. pr. m²» → øre + unit. Null when no number can be read. Danish formats: «1.200,50», «1200», «850,-». */
export function parsePrice(text: string): { minor: number; unit: string } | null {
  const m = text.match(/(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?/);
  if (!m) return null;
  const kr = Number(m[1].replace(/\./g, "")), ore = m[2] ? Number(m[2].padEnd(2, "0")) : 0;
  const low = text.toLowerCase();
  const unit = /m²|m2|kvm|kvadrat/.test(low) ? "m2" : /time|\/t\b/.test(low) ? "hour" : /stk|styk/.test(low) ? "item" : "job";
  return { minor: kr * 100 + ore, unit };
}
