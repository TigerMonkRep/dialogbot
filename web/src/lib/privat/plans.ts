/** Dialogbot Privat plan catalogue per market (prices INCL. VAT, minor units, from lib/prices.json via lib/markets.ts).
 *  Shared by the public landing (/privat) and the app (Konto, Butikken paywall). Mirrors the backend's Plan objects
 *  (GET /privat/subscription → plans[]); the API stays the source of truth once a user is logged in – this file is for
 *  the public page and as a fallback. Dependency-free apart from markets.ts. */
import { PRIVAT_TRIAL_DAYS, privatPrices, type Currency } from "@/lib/markets";

export type PlanKey = "basis" | "plus" | "familie";
export type PlanInterval = "month" | "year";

export type Plan = {
  key: PlanKey;
  name: string;
  currency: Currency;
  /** Minor units per month when paid monthly. */
  monthlyMinor: number;
  /** Minor units per month when paid yearly. */
  yearlyMonthlyMinor: number;
  /** Minor units per year (what is actually charged on the yearly plan). */
  yearlyTotalMinor: number;
  /** Calls included per calendar month. */
  calls: number;
  /** People on the account. */
  people: number;
  /** All apps in Butikken included. */
  appsIncluded: boolean;
  recommended: boolean;
  /** i18n keys under privat.json → plans.features.<key>. */
  features: string[];
};

type Spec = Omit<Plan, "currency" | "monthlyMinor" | "yearlyMonthlyMinor" | "yearlyTotalMinor">;
const SPECS: readonly Spec[] = [
  { key: "basis", name: "Basis", calls: 3, people: 1, appsIncluded: false, recommended: false, features: ["listsUnlimited", "calls", "people"] },
  { key: "plus", name: "Plus", calls: 10, people: 1, appsIncluded: true, recommended: true, features: ["allInBasis", "calls", "sharedLists", "allApps"] },
  { key: "familie", name: "Familie", calls: 25, people: 5, appsIncluded: true, recommended: false, features: ["allInPlus", "calls", "people", "sharedCalendar"] },
];

/** The three plans with the prices of `currency`. */
export function plansFor(currency: Currency): Plan[] {
  const prices = privatPrices(currency);
  return SPECS.map((s) => ({ ...s, currency, monthlyMinor: prices[s.key].monthly, yearlyMonthlyMinor: prices[s.key].yearly_monthly,
    yearlyTotalMinor: prices[s.key].yearly_total }));
}

/** The Danish catalogue (DKK). */
export const PLANS: readonly Plan[] = plansFor("DKK");

export const TRIAL_DAYS = PRIVAT_TRIAL_DAYS;

export function planByKey(key: string | null | undefined, currency: Currency = "DKK"): Plan | undefined {
  return plansFor(currency).find((p) => p.key === key);
}

/** The API's shape of a plan (GET /privat/subscription → plans[]). */
export function apiPlans(currency: Currency) {
  return plansFor(currency).map((p) => ({ key: p.key, name: p.name, monthly_minor: p.monthlyMinor, yearly_monthly_minor: p.yearlyMonthlyMinor,
    yearly_total_minor: p.yearlyTotalMinor, calls: p.calls, people: p.people, apps_included: p.appsIncluded, recommended: p.recommended, features: p.features }));
}

/** Where the app takes over (login + Stripe Checkout): /privat/konto?plan=plus&interval=year */
export function planCheckoutHref(plan: PlanKey, interval: PlanInterval): string {
  return `/privat/konto?plan=${plan}&interval=${interval}`;
}
