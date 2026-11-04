/** Dialogbot Privat plans (prices in DKK incl. 25 % VAT). The app prefers the catalogue the API sends
 *  (Subscription.plans); this is the fallback for the landing page and the in-browser simulation. */
export type PlanKey = "basis" | "plus" | "familie";
export type PlanSpec = {
  key: PlanKey; name: string;
  /** kr. per month, billed monthly */
  monthly: number;
  /** kr. per month when billed yearly */
  yearlyMonthly: number;
  /** kr. per year, billed yearly */
  yearlyTotal: number;
  calls: number; people: number; appsIncluded: boolean; recommended: boolean;
  features: string[];
};

export const PLANS: PlanSpec[] = [
  { key: "basis", name: "Basis", monthly: 49, yearlyMonthly: 39, yearlyTotal: 468, calls: 3, people: 1, appsIncluded: false, recommended: false,
    features: ["3 opkald om måneden", "Ubegrænsede lister og påmindelser", "1 person", "Gratis apps i Butikken"] },
  { key: "plus", name: "Plus", monthly: 99, yearlyMonthly: 79, yearlyTotal: 948, calls: 10, people: 1, appsIncluded: true, recommended: true,
    features: ["10 opkald om måneden", "Ubegrænsede lister og påmindelser", "1 person", "Alle apps i Butikken"] },
  { key: "familie", name: "Familie", monthly: 169, yearlyMonthly: 135, yearlyTotal: 1620, calls: 25, people: 5, appsIncluded: true, recommended: false,
    features: ["25 opkald om måneden", "Ubegrænsede lister og påmindelser", "Op til 5 personer", "Alle apps i Butikken"] },
];

export const TRIAL_DAYS = 14;
