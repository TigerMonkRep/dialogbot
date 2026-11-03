/** Real, consented customer proof for the public site. Fill these in with REAL data only – every component that
 *  reads them renders nothing while they are empty, so the site never shows invented customers, quotes or counts.
 *  (Audit D3.1, D3.2, D3.3, D3.5, D1.5.) */

export type CustomerQuote = {
  /** First name and surname as the customer has agreed to show them. */
  name: string;
  /** Their business, e.g. "Tømrer, Aarhus". */
  business: string;
  /** One concrete outcome, in their own words. Written permission required. */
  quote: string;
  /** Optional path under /public, e.g. "/proof/peter.jpg". */
  photo?: string;
};

/** Five named customers, one line each. Empty until the first customers have said yes. */
export const CUSTOMER_QUOTES: CustomerQuote[] = [];

/** A true usage figure, e.g. { value: "1.240", label: "opkald besvaret" } or "5 virksomheder bruger Dialogbot". */
export const USAGE_COUNT: { value: string; label: string } | null = null;

/** Trustpilot (or similar) once reviews exist: { rating: "4,8", reviews: 12, url: "https://dk.trustpilot.com/review/..." }. */
export const REVIEW_SCORE: { rating: string; reviews: number; url: string } | null = null;

/** The person behind Dialogbot. Name, photo and a two-line "why I built this" in the site's own voice. */
export const FOUNDER: { name: string; role: string; photo?: string; why: string; profileUrl?: string } | null = null;

/** Screenshot of the knowledge-approval diff ("før → efter, «Godkend?»") or the daily enquiry report. */
export const PRODUCT_SCREENSHOT: { src: string; width: number; height: number; alt: string } | null = null;
