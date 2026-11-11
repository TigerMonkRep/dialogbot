/** Markets: which currency a language sells in, the list prices of that market and how a price is written.
 *  The numbers come from prices.json, generated from app/modules/billing/markets.py (never edit the JSON by hand).
 *  Erhverv prices are excl. VAT, Privat prices incl. VAT; all amounts are minor units (øre, öre, cent).
 *  Dependency-free so it works in server components, client components and the fake Privat backend. */
import PRICES from "./prices.json";
import { HTML_LANG, type Locale } from "@/i18n/config";

export type Currency = "DKK" | "SEK" | "NOK" | "EUR";
/** extra_minute = inbound minute above the package, outbound_extra_minute = outbound (campaign) minute above it.
 *  No price per call (decision 2026-11-10). */
export type ErhvervItem = "monthly" | "extra_minute" | "outbound_extra_minute" | "call_answered" | "call_voicemail" | "call_no_answer" | "setup";
export type PrivatPlanKey = "basis" | "plus" | "familie";
export type PrivatPrice = { monthly: number; yearly_monthly: number; yearly_total: number };
/** Dialogbot Privat's extra call (beyond the plan's calls), incl. VAT: by outcome + per started minute, at most `max`. */
export type ExtraCallPrices = { answered: number; voicemail: number; no_answer: number; minute: number; max: number };
/** The Opkaldssaldo's bonuses and the extra task, incl. VAT. */
export type BalanceAmounts = { welcome: number; referral: number; extra_task: number };

type PriceTable = {
  currencies: Currency[];
  localeCurrency: Record<string, Currency>;
  includedMinutes: number;
  privatTrialDays: number;
  erhverv: Record<Currency, Record<ErhvervItem, number>>;
  privat: Record<Currency, Record<PrivatPlanKey, PrivatPrice>>;
  privatExtraCall: Record<Currency, ExtraCallPrices>;
  privatTopups: Record<Currency, number[]>;
  privatBalance: Record<Currency, BalanceAmounts>;
};
const P = PRICES as unknown as PriceTable;

export const CURRENCIES: readonly Currency[] = P.currencies;
/** The package: minutes a month that inbound and outbound calls share. */
export const INCLUDED_MINUTES = P.includedMinutes;
export const PRIVAT_TRIAL_DAYS = P.privatTrialDays;
/** Danish VAT, included in every Privat price (prices.py TAX_BASIS_POINTS). */
export const PRIVAT_VAT_BP = 2500;

/** EU member states (ISO 3166-1 alpha-2), as in markets.py EU_VAT_BP. An Erhverv customer in one of these other than
 *  DK is invoiced without VAT (reverse charge) and must give a VAT number. */
export const EU_COUNTRIES: readonly string[] = ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU", "IE",
  "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"];

export function isCurrency(v: unknown): v is Currency {
  return typeof v === "string" && (CURRENCIES as readonly string[]).includes(v);
}

/** The currency the website shows for a language: da → DKK, sv → SEK, no → NOK, everything else → EUR. */
export function currencyFor(locale: Locale | string | null | undefined): Currency {
  return P.localeCurrency[(locale ?? "da").toLowerCase()] ?? "DKK";
}

/** A currency from an API response (any case, may be missing) – DKK when unknown. */
export function currencyOr(v: unknown, fallback: Currency = "DKK"): Currency {
  const c = typeof v === "string" ? v.toUpperCase() : "";
  return isCurrency(c) ? c : fallback;
}

const cache = new Map<string, Intl.NumberFormat>();
function nf(lang: string, currency: Currency | null, decimals: boolean): Intl.NumberFormat {
  const key = `${lang}|${currency}|${decimals}`;
  let f = cache.get(key);
  if (!f) {
    const digits = decimals ? 2 : 0;
    f = new Intl.NumberFormat(lang, currency
      ? { style: "currency", currency, currencyDisplay: "symbol", minimumFractionDigits: digits, maximumFractionDigits: digits }
      : { minimumFractionDigits: digits, maximumFractionDigits: digits });
    cache.set(key, f);
  }
  return f;
}

function langOf(locale: Locale | string): string {
  return (HTML_LANG as Record<string, string>)[locale] ?? locale;
}

/** Danish keeps the house style the site has always used ("2.495 kr.", plain spaces); others follow Intl. */
function house(s: string, lang: string): string {
  return lang === "da" ? s.replace(/[  ]/g, " ") : s;
}

/** 249500 DKK da → "2.495 kr." · 369500 SEK sv → "3 695 kr" · 32900 EUR en → "€329", de → "329 €" · 150 DKK → "1,50 kr."
 *  Decimals only when the amount has them. `locale` is a site locale ("no") or a BCP-47 tag ("nb"). */
export function formatPrice(minor: number, currency: Currency, locale: Locale | string = "da"): string {
  const lang = langOf(locale);
  return house(nf(lang, currency, minor % 100 !== 0).format(minor / 100), lang);
}

/** Statements and invoices: always two decimals – "4,00 kr." (da/DKK) · "€0.55" (en/EUR) · "3 695,00 kr" (sv/SEK). */
export function formatMoney(minor: number, currency: Currency, locale: Locale | string = "da"): string {
  const lang = langOf(locale);
  return house(nf(lang, currency, true).format(minor / 100), lang);
}

/** The amount without the currency: 249500 → "2.495" (da) · "2,495" (en). For big price figures with the unit beside. */
export function formatAmount(minor: number, locale: Locale | string = "da"): string {
  const lang = langOf(locale);
  return house(nf(lang, null, minor % 100 !== 0).format(minor / 100), lang);
}

/** The currency sign as the language writes it: "kr." (da/DKK), "kr" (sv/SEK, nb/NOK), "€" (EUR). */
export function currencySymbol(currency: Currency, locale: Locale | string = "da"): string {
  return nf(langOf(locale), currency, false).formatToParts(1).find((p) => p.type === "currency")?.value ?? currency;
}

/** Schema.org wants a plain decimal: 249500 → "2495", 150 → "1.50". */
export function schemaPrice(minor: number): string {
  return minor % 100 ? (minor / 100).toFixed(2) : String(minor / 100);
}

// ------------------------------------------------------------------ the list prices of a market

export function erhvervPrices(currency: Currency): Record<ErhvervItem, number> {
  return P.erhverv[currency] ?? P.erhverv.DKK;
}

export function privatPrices(currency: Currency): Record<PrivatPlanKey, PrivatPrice> {
  return P.privat[currency] ?? P.privat.DKK;
}

/** What an extra call costs in a currency (markets.privat_extra_call: Erhverv's net price by outcome + 25 % moms). */
export function extraCallPrices(currency: Currency): ExtraCallPrices {
  return P.privatExtraCall[currency] ?? P.privatExtraCall.DKK;
}

/** The three top-ups of the Opkaldssaldo (50, 100, 200 kr. incl. moms, or the currency's amounts). */
export function topupAmounts(currency: Currency): number[] {
  return P.privatTopups[currency] ?? P.privatTopups.DKK;
}

export function balanceAmounts(currency: Currency): BalanceAmounts {
  return P.privatBalance[currency] ?? P.privatBalance.DKK;
}

/** The VAT inside a gross Privat price (25 % Danish VAT → a fifth of the gross): 5000 → 1000. */
export function includedVat(grossMinor: number, bp = PRIVAT_VAT_BP): number {
  return Math.round(grossMinor - grossMinor * 10000 / (10000 + bp));
}

/** Everything a page needs for one language. */
export function market(locale: Locale | string) {
  const currency = currencyFor(locale);
  return {
    currency,
    erhverv: erhvervPrices(currency),
    privat: privatPrices(currency),
    extraCall: extraCallPrices(currency),
    topups: topupAmounts(currency),
    fmt: (minor: number) => formatPrice(minor, currency, locale),
  };
}

// ------------------------------------------------------------------ i18n price tokens

/** Every {p…} token the translator fills in (see i18n/translate.ts). Copy writes these instead of amounts, so a price
 *  lives in one place: «Fra {pMonthly}/md.» → «Fra 2.495 kr./md.» (da) · «From €329/month» (en).
 *  …Num = the amount without currency (for big figures with the unit beside); pCur = the currency sign. */
export const PRICE_TOKENS = [
  "pMonthly", "pMinute", "pExtraMinute", "pSetup",
  "pMonthlyNum", "pMinuteNum", "pSetupNum", "pCallAnswered", "pCallVoicemail", "pCallNoAnswer", "pCallAnsweredNum", "pContactMax",
  "pIncluded", "pCur",
  "pBasis", "pPlus", "pFamilie", "pBasisYear", "pPlusYear", "pFamilieYear",
  "pBasisYearTotal", "pPlusYearTotal", "pFamilieYearTotal",
  "pBasisNum", "pPlusNum", "pFamilieNum", "pPrivatFrom", "pPrivatFromNum",
  // Privat's extra call and Opkaldssaldo (incl. VAT): by outcome, per started minute, the maximum; top-ups; bonuses
  "pXAnswered", "pXVoicemail", "pXNoAnswer", "pXMinute", "pXMax", "pTopup1", "pTopup2", "pTopup3",
  "pWelcome", "pReferral", "pExtraTask", "pTrialDays",
] as const;
export type PriceToken = (typeof PRICE_TOKENS)[number];

const tokenCache = new Map<string, Record<PriceToken, string | number>>();

/** The values of every {p…} token for a language (cached; the table is static). */
export function priceVars(locale: Locale | string): Record<PriceToken, string | number> {
  const hit = tokenCache.get(locale);
  if (hit) return hit;
  const c = currencyFor(locale);
  const e = erhvervPrices(c), pv = privatPrices(c), x = extraCallPrices(c), tu = topupAmounts(c), b = balanceAmounts(c);
  const f = (m: number) => formatPrice(m, c, locale);
  const n = (m: number) => formatAmount(m, locale);
  const from = Math.min(pv.basis.monthly, pv.plus.monthly, pv.familie.monthly);
  const v: Record<PriceToken, string | number> = {
    // pMinute = outbound minute above the package, pExtraMinute = inbound minute above it
    pMonthly: f(e.monthly), pMinute: f(e.outbound_extra_minute), pExtraMinute: f(e.extra_minute), pSetup: f(e.setup),
    pMonthlyNum: n(e.monthly), pMinuteNum: n(e.outbound_extra_minute), pSetupNum: n(e.setup),
    // outbound call after the package, by outcome; a contact at most (2 attempts answered + 3 minutes)
    pCallAnswered: f(e.call_answered), pCallVoicemail: f(e.call_voicemail), pCallNoAnswer: f(e.call_no_answer),
    pCallAnsweredNum: n(e.call_answered), pContactMax: f(2 * e.call_answered + 3 * e.outbound_extra_minute),
    pIncluded: INCLUDED_MINUTES, pCur: currencySymbol(c, locale),
    pBasis: f(pv.basis.monthly), pPlus: f(pv.plus.monthly), pFamilie: f(pv.familie.monthly),
    pBasisYear: f(pv.basis.yearly_monthly), pPlusYear: f(pv.plus.yearly_monthly), pFamilieYear: f(pv.familie.yearly_monthly),
    pBasisYearTotal: f(pv.basis.yearly_total), pPlusYearTotal: f(pv.plus.yearly_total), pFamilieYearTotal: f(pv.familie.yearly_total),
    pBasisNum: n(pv.basis.monthly), pPlusNum: n(pv.plus.monthly), pFamilieNum: n(pv.familie.monthly),
    pPrivatFrom: f(from), pPrivatFromNum: n(from),
    pXAnswered: f(x.answered), pXVoicemail: f(x.voicemail), pXNoAnswer: f(x.no_answer), pXMinute: f(x.minute),
    pXMax: f(x.max), pTopup1: f(tu[0]), pTopup2: f(tu[1]), pTopup3: f(tu[2]),
    pWelcome: f(b.welcome), pReferral: f(b.referral), pExtraTask: f(b.extra_task), pTrialDays: PRIVAT_TRIAL_DAYS,
  };
  tokenCache.set(locale, v);
  return v;
}
