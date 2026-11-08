/** Wishes: money in minor units, typed amounts, image links. Amounts are always computed by the backend; these only
 *  format and parse what the user sees and types. */
import { HTML_LANG, type Locale } from "@/i18n/config";

const MINOR: Record<string, number> = { JPY: 0, KRW: 0, ISK: 0, CLP: 0, BHD: 3, KWD: 3, OMR: 3, JOD: 3, TND: 3 };
export const minorDigits = (currency: string) => MINOR[currency] ?? 2;

/** 125000 DKK (da) → «1.250 kr.»; decimals only when there are øre. */
export function money(minor: number, currency: string, locale: Locale): string {
  const d = minorDigits(currency);
  const v = minor / 10 ** d;
  const frac = minor % 10 ** d !== 0;
  const tag = HTML_LANG[locale] ?? "da-DK";
  try {
    const s = new Intl.NumberFormat(tag, { style: "currency", currency, minimumFractionDigits: frac ? d : 0, maximumFractionDigits: d }).format(v);
    // Danish house style: «1.250 kr.» (Intl writes «1.250 kr.» already in da-DK; keep a single space)
    return s.replace(/ /g, " ");
  } catch {
    return `${v.toLocaleString(tag)} ${currency}`;
  }
}

/** «1.250», «1250,50», «1 250 kr.» → minor units; null when it is not a plain positive amount. */
export function parseAmount(raw: string, currency: string): number | null {
  let s = raw.replace(/[^\d.,]/g, "").replace(/^[.,]+|[.,]+$/g, "");  // «1.250 kr.» → «1.250»
  if (!s || !/\d/.test(s)) return null;
  if (s.includes(",") && s.includes(".")) s = s.lastIndexOf(",") > s.lastIndexOf(".") ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  else if (s.includes(",")) s = /,\d{1,2}$/.test(s) ? s.replace(/\.(?=.*,)/g, "").replace(",", ".") : s.replace(/,/g, "");
  else if ((s.match(/\./g) ?? []).length > 1 || /\.\d{3}$/.test(s)) s = s.replace(/\./g, "");
  const v = Number(s);
  if (!Number.isFinite(v) || v < 0) return null;
  return Math.round(v * 10 ** minorDigits(currency));
}

/** The amount for an input field: 125000 → «1250» (or «1250,50»). */
export function amountInput(minor: number | null | undefined, currency: string, locale: Locale): string {
  if (minor == null) return "";
  const d = minorDigits(currency);
  const v = minor / 10 ** d;
  return minor % 10 ** d === 0 ? String(v) : v.toFixed(d).replace(".", locale === "en" ? "." : ",");
}

/** Dev/test backends sign `local://privat-files/<key>?exp&sig`: the browser loads those through the BFF. */
export function imgSrc(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  const m = url.match(/^local:\/\/privat-files\/([^?]+)\?(.*)$/);
  if (m) return `/api/backend/privat/dev-files?key=${encodeURIComponent(m[1])}&${m[2]}`;
  return url;
}

export const CURRENCIES = ["DKK", "SEK", "NOK", "EUR", "GBP", "USD"] as const;
