/** Public contact facts for the marketing site (header, footer, CTAs, the Prøv-den chat). */
export const PHONE_DISPLAY = "93 70 34 33";
export const PHONE_INTL = "+45 93 70 34 33";
export const PHONE_TEL = "tel:+4593703433";
export const EMAIL = "info@dialogbot.dk";
/** Dialogbot's own opening hours (support, the contact page) – not when Peter rings: demo calls asked for on the site
 *  are rung at once, day and night (Fürster 12/11). */
export const HOURS = "Man–fre 08–17";

/** Erhverv self-service sign-up: open day and night, no call needed first (S0 «Erhverv døgnåbent»). Every Erhverv
 *  CTA and the chat lead here; the backend's GET /demo-call returns the same path. */
export const SIGNUP_ERHVERV = "/signup?intent=reception";
