/** Dialogbot Privat plan catalogue (prices in DKK incl. 25 % VAT). Shared by the public landing (/privat) and the app
 *  (Konto, Butikken paywall). Mirrors the backend's Plan objects (GET /privat/subscription → plans[]); the API stays the
 *  source of truth once a user is logged in – this file is for the public page and as a fallback. Dependency-free. */
export type PlanKey = "basis" | "plus" | "familie";
export type PlanInterval = "month" | "year";

export type Plan = {
  key: PlanKey;
  name: string;
  /** kr. per month when paid monthly. */
  monthly: number;
  /** kr. per month when paid yearly. */
  yearlyMonthly: number;
  /** kr. per year (what is actually charged on the yearly plan). */
  yearlyTotal: number;
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

export const PLANS: readonly Plan[] = [
  { key: "basis", name: "Basis", monthly: 49, yearlyMonthly: 39, yearlyTotal: 468, calls: 3, people: 1, appsIncluded: false, recommended: false,
    features: ["listsUnlimited", "calls", "people"] },
  { key: "plus", name: "Plus", monthly: 99, yearlyMonthly: 79, yearlyTotal: 948, calls: 10, people: 1, appsIncluded: true, recommended: true,
    features: ["allInBasis", "calls", "sharedLists", "allApps"] },
  { key: "familie", name: "Familie", monthly: 169, yearlyMonthly: 135, yearlyTotal: 1620, calls: 25, people: 5, appsIncluded: true, recommended: false,
    features: ["allInPlus", "calls", "people", "sharedCalendar"] },
] as const;

export const TRIAL_DAYS = 14;

export function planByKey(key: string | null | undefined): Plan | undefined {
  return PLANS.find((p) => p.key === key);
}

/** Where the app takes over (login + Stripe Checkout): /privat/konto?plan=plus&interval=year */
export function planCheckoutHref(plan: PlanKey, interval: PlanInterval): string {
  return `/privat/konto?plan=${plan}&interval=${interval}`;
}
