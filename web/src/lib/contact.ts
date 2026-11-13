/** Public contact facts for the marketing site (header, footer, CTAs, the Prøv-den chat). */
export const PHONE_DISPLAY = "93 70 34 33";
export const PHONE_INTL = "+45 93 70 34 33";
export const PHONE_TEL = "tel:+4593703433";
export const EMAIL = "info@dialogbot.app";

/** The US demo line (set in Vercel as NEXT_PUBLIC_US_PHONE, E.164, e.g. +16283773337): a US number that Dialogbot's
 *  own assistant answers in English. Unset = the US edition shows the Danish number like every other edition. */
const US_E164 = (process.env.NEXT_PUBLIC_US_PHONE ?? "").replace(/[^+\d]/g, "");
const US = /^\+1\d{10}$/.test(US_E164)
  ? { display: `(${US_E164.slice(2, 5)}) ${US_E164.slice(5, 8)}-${US_E164.slice(8)}`,
      intl: `+1 ${US_E164.slice(2, 5)} ${US_E164.slice(5, 8)} ${US_E164.slice(8)}`, tel: `tel:${US_E164}`, local: true }
  : null;

export type Phone = { display: string; intl: string; tel: string; local: boolean };
/** The number an edition shows: the US demo line on /us (when set), otherwise Dialogbot's Danish number. `local`:
 *  the reader can ring it as a domestic call and is answered in their own language. */
export function phoneFor(locale: string): Phone {
  if (locale === "us" && US) return US;
  return { display: PHONE_DISPLAY, intl: PHONE_INTL, tel: PHONE_TEL, local: locale === "da" };
}
/** Dialogbot's own opening hours (support, the contact page) – not when Peter rings: demo calls asked for on the site
 *  are rung at once, day and night (Fürster 12/11). */
export const HOURS = "Man–fre 08–17";

/** Erhverv self-service sign-up: open day and night, no call needed first (S0 «Erhverv døgnåbent»). Every Erhverv
 *  CTA and the chat lead here; the backend's GET /demo-call returns the same path. */
export const SIGNUP_ERHVERV = "/signup?intent=reception";
