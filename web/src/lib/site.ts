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
  { href: "/priser", label: "Priser" },
  { href: "/viden", label: "Viden" },
];

/** Guides under /viden (also in the sitemap and on the /viden index). */
export const ARTICLES: { slug: string; title: string; teaser: string; published: string }[] = [
  { slug: "hvad-er-en-ai-receptionist", title: "Hvad er en AI-receptionist – og hvordan virker den?", published: "2026-10-07",
    teaser: "Sådan tager en AI-receptionist telefonen for en dansk virksomhed, hvad den kan, og hvad den ikke skal kunne." },
  { slug: "ai-telefonsvarer-eller-telefonpasning", title: "AI-telefonsvarer eller telefonpasning – hvad passer til jer?", published: "2026-10-07",
    teaser: "Telefonsvarer, telefonpasningsservice eller AI: fordele og ulemper, så I kan vælge rigtigt." },
  { slug: "viderestil-telefonen", title: "Sådan viderestiller du telefonen, når du er optaget", published: "2026-10-07",
    teaser: "De koder, du taster på mobilen for at viderestille ved optaget, ingen svar eller altid – og hvordan du slår det fra igen." },
];
