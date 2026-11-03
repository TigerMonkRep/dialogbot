/** Real, consented customer proof for the public site. Fill these in with REAL data only – every component that
 *  reads them renders nothing while they are empty, so the site never shows invented customers, quotes or counts.
 *  (Audit D3.1, D3.2, D3.3, D3.5, D1.5.)
 *
 *  Names, numbers, photos and links live here. The human texts (business, quote, labels, the founder's role and
 *  "why", the screenshot's alt text) live per language in messages/<locale>/site.json under "proof.data":
 *  quotes are keyed by the quote's `id` (proof.data.quotes.<id>.business / .quote). */

export type CustomerQuote = {
  /** Key of the texts in proof.data.quotes.<id> ({ "business": "Tømrer, Aarhus", "quote": "…" }). The quote is one
   *  concrete outcome, in the customer's own words – written permission required. */
  id: string;
  /** First name and surname as the customer has agreed to show them. */
  name: string;
  /** Optional path under /public, e.g. "/proof/peter.jpg". */
  photo?: string;
};

/** Five named customers, one line each. Empty until the first customers have said yes. */
export const CUSTOMER_QUOTES: CustomerQuote[] = [];

/** A true usage figure, e.g. { value: "1.240" } with proof.data.usageLabel "opkald besvaret". */
export const USAGE_COUNT: { value: string } | null = null;

/** Trustpilot (or similar) once reviews exist: { rating: "4,8", reviews: 12, url: "https://dk.trustpilot.com/review/..." }. */
export const REVIEW_SCORE: { rating: string; reviews: number; url: string } | null = null;

/** The person behind Dialogbot. Name, photo and profile link here; role and the two-line "why I built this" in the
 *  site's own voice in proof.data.founderRole / proof.data.founderWhy. */
export const FOUNDER: { name: string; photo?: string; profileUrl?: string } | null = null;

/** Screenshot of the knowledge-approval diff ("før → efter, «Godkend?»") or the daily enquiry report; alt text in
 *  proof.data.screenshotAlt. */
export const PRODUCT_SCREENSHOT: { src: string; width: number; height: number } | null = null;
