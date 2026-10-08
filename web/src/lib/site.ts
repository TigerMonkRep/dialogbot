import type { Metadata } from "next";

/** Public site facts used for SEO: canonical origin, the keyword landing pages and shared copy. */
export const SITE_URL = "https://www.dialogbot.dk";
export const SITE_NAME = "Dialogbot";
/** Front-page title (≤ 65 characters, keyword first). Other pages use their own title + " | Dialogbot". */
export const SITE_TITLE = "AI-receptionist, AI-telefonsvarer og chatbot | Dialogbot";
/** Front-page description (120–160 characters). */
export const SITE_DESCRIPTION =
  "Dansk AI-receptionist, der tager telefonen og chatten for din virksomhed døgnet rundt – svarer ud fra jeres egen viden, booker tider og samler henvendelser.";

/** Pages that must stay out of Google (sign-in flows, the app, onboarding). They are also kept out of the sitemap. */
export const NOINDEX: NonNullable<Metadata["robots"]> = { index: false, follow: false };

/** Keyword landing pages (also in the sitemap and the footer). `updated` is the sitemap lastmod: bump it when the page changes. */
export const LANDING_PAGES: { href: string; label: string; updated: string }[] = [
  { href: "/ai-receptionist", label: "AI-receptionist", updated: "2026-10-08" },
  { href: "/ai-telefonsvarer", label: "AI-telefonsvarer", updated: "2026-10-08" },
  { href: "/chatbot", label: "Chatbot til hjemmesiden", updated: "2026-10-08" },
  { href: "/priser", label: "Priser", updated: "2026-10-07" },
  { href: "/viden", label: "Viden", updated: "2026-10-07" },
];

/** Other indexable pages with their last content change (sitemap lastmod). */
export const PAGE_UPDATED = {
  home: "2026-10-08",
  ambassadorJoin: "2026-10-08",
  contact: "2026-10-06",
  terms: "2026-10-06",
  privacy: "2026-10-06",
} as const;

/** Guides under /viden (also in the sitemap and on the /viden index). `updated` defaults to `published`. */
export const ARTICLES: { slug: string; title: string; teaser: string; published: string; updated?: string }[] = [
  { slug: "hvad-er-en-ai-receptionist", title: "Hvad er en AI-receptionist – og hvordan virker den?", published: "2026-10-07",
    teaser: "Sådan tager en AI-receptionist telefonen for en dansk virksomhed, hvad den kan, og hvad den ikke skal kunne." },
  { slug: "ai-telefonsvarer-eller-telefonpasning", title: "AI-telefonsvarer eller telefonpasning – hvad passer til jer?", published: "2026-10-07", updated: "2026-10-08",
    teaser: "Telefonsvarer, telefonpasningsservice eller AI: fordele og ulemper, så I kan vælge rigtigt." },
  { slug: "viderestil-telefonen", title: "Sådan viderestiller du telefonen, når du er optaget", published: "2026-10-07",
    teaser: "De koder, du taster på mobilen for at viderestille ved optaget, ingen svar eller altid – og hvordan du slår det fra igen." },
];
