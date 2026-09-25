/** Shared (server + client) helpers for rendering knowledge content. Money is stored in øre (minor units). */

export const KIND_LABEL: Record<string, string> = {
  service: "Ydelse", opening_hours: "Åbningstider", coverage_area: "Dækningsområde", fact: "Faktum",
  known_answer: "Kendt svar", unknown_answer: "Må ikke besvares", offer: "Tilbud",
};
export const UNIT_LABEL: Record<string, string> = { m2: "m²", hour: "time", item: "stk.", job: "opgave" };
const DAY: Record<string, string> = { mon: "man", tue: "tir", wed: "ons", thu: "tor", fri: "fre", sat: "lør", sun: "søn" };
export const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

export function kr(minor: unknown): string | null {
  if (typeof minor !== "number") return null;
  return `${(minor / 100).toLocaleString("da-DK", { minimumFractionDigits: minor % 100 ? 2 : 0, maximumFractionDigits: 2 })},-`;
}

export function daysLabel(days: string[]): string {
  const idx = days.map((d) => DAYS.indexOf(d as (typeof DAYS)[number])).filter((i) => i >= 0).sort((a, b) => a - b);
  const contiguous = idx.every((v, i) => i === 0 || v === idx[i - 1] + 1);
  return contiguous && idx.length > 2 ? `${DAY[DAYS[idx[0]]]}–${DAY[DAYS[idx[idx.length - 1]]]}` : idx.map((i) => DAY[DAYS[i]]).join(", ");
}

export const dateDa = (iso?: unknown) => typeof iso === "string" ? new Date(iso + "T00:00:00").toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" }) : "";

/** One-line headline + detail for any knowledge kind (used in K03/K05 cards). */
export function summarize(kind: string, c: Record<string, unknown>): { headline: string; detail: string } {
  switch (kind) {
    case "service": {
      const price = kr(c.price_net_minor);
      return { headline: price ? `${price} kr${c.unit ? ` / ${UNIT_LABEL[String(c.unit)] ?? c.unit}` : ""}` : "Ingen pris", detail: String(c.description ?? "") };
    }
    case "opening_hours": {
      const weekly = (c.weekly as { days: string[]; open: string; close: string }[] | undefined) ?? [];
      return { headline: weekly.map((w) => `${daysLabel(w.days)} ${w.open}–${w.close}`).join(" · ") || "Ingen tider", detail: String(c.closed_note ?? "") };
    }
    case "coverage_area": return { headline: ((c.zones as string[] | undefined) ?? []).join(" · ") || "Ingen zoner", detail: "" };
    case "fact": return { headline: String(c.text ?? ""), detail: "" };
    case "known_answer": return { headline: String(c.question ?? ""), detail: String(c.answer ?? "") };
    case "unknown_answer": return { headline: String(c.rule ?? ""), detail: "Assistenten henviser til et menneske." };
    case "offer": {
      const cond = (c.condition as { area_operator?: string; area_threshold_m2?: number } | undefined) ?? {};
      const thr = cond.area_threshold_m2 != null ? `${cond.area_operator === "gt" ? ">" : "≥"} ${cond.area_threshold_m2} m²` : "alle arealer";
      return { headline: `-${c.discount_percent ?? 0}% ved ${thr}`, detail: `${dateDa(c.starts_on)} – ${dateDa(c.ends_on_inclusive)} (begge dage inkl.)` };
    }
    default: return { headline: JSON.stringify(c), detail: "" };
  }
}
