/** The «Opkaldssaldo» on screen (F-PDEC-01): the balance in kroner and what an extra call costs, in the account's own
 *  currency (from /privat/me), formatted for the page's language. Falls back to the page's market (prices.json) while
 *  the account has not loaded. It never shows a count of anything but kroner. */
import { balanceAmounts, currencyFor, currencyOr, extraCallPrices, formatPrice, topupAmounts, type Currency } from "@/lib/markets";
import type { Balance } from "./api";

export type Saldo = {
  currency: Currency;
  /** øre on the balance now (open reservations already taken off) and held by open reservations */
  balance: number; held: number;
  /** the most one extra call costs (what is reserved before it is dialled) */
  maxMinor: number;
  extraTaskMinor: number;
  topups: number[];
  fmt: (minor: number) => string;
  /** the extra-call prices as text for the i18n tokens {pXAnswered} … {pXMax} */
  vars: { pXAnswered: string; pXVoicemail: string; pXNoAnswer: string; pXMinute: string; pXMax: string; pExtraTask: string };
};

export function saldo(balance: Balance | null | undefined, locale: string): Saldo {
  const currency = balance?.currency ? currencyOr(balance.currency) : currencyFor(locale);
  const x = balance?.extra_call ?? extraCallPrices(currency);
  const fmt = (minor: number) => formatPrice(minor, currency, locale);
  const extraTaskMinor = balance?.extra_task_minor ?? balanceAmounts(currency).extra_task;
  return {
    currency, balance: balance?.balance_minor ?? 0, held: balance?.held_minor ?? 0, maxMinor: x.max, extraTaskMinor,
    topups: balance?.topups_minor ?? topupAmounts(currency), fmt,
    vars: { pXAnswered: fmt(x.answered), pXVoicemail: fmt(x.voicemail), pXNoAnswer: fmt(x.no_answer), pXMinute: fmt(x.minute),
      pXMax: fmt(x.max), pExtraTask: fmt(extraTaskMinor) },
  };
}

/** A ledger amount: «+50 kr.», «−17,50 kr.», «0 kr.» */
export function signed(minor: number, currency: string, locale: string): string {
  const s = formatPrice(Math.abs(minor), currencyOr(currency), locale);
  return minor > 0 ? `+${s}` : minor < 0 ? `−${s}` : s;
}
