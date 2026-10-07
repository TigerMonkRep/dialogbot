/** Public site facts used for SEO: canonical origin, the keyword landing pages and shared copy. */
export const SITE_URL = "https://www.dialogbot.dk";
export const SITE_NAME = "Dialogbot";
export const SITE_TITLE = "Dialogbot – AI-receptionist, AI-telefonsvarer og chatbot til danske virksomheder";
export const SITE_DESCRIPTION =
  "Dialogbot er en dansk AI-receptionist, der tager telefonen og chatten for din virksomhed døgnet rundt – svarer ud fra jeres egen viden, booker tider og samler henvendelser. Vi guider jer gennem hele opsætningen.";

/** Keyword landing pages (also in the sitemap and the footer). */
export const LANDING_PAGES: { href: string; label: string }[] = [
  { href: "/ai-receptionist", label: "AI-receptionist" },
  { href: "/ai-telefonsvarer", label: "AI-telefonsvarer" },
  { href: "/chatbot", label: "Chatbot til hjemmesiden" },
];
