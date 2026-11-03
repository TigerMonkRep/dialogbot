import type { Metadata } from "next";
import { HTML_LANG, LOCALES, OG_LOCALE, type Locale } from "@/i18n/config";

/** Public site facts used for SEO: canonical origin, the keyword landing pages and shared copy.
 *  Texts live in messages/<locale>/landing.json (landing.meta, landing.nav.*, landing.articles.<slug>.*). */
export const SITE_URL = "https://dialogbot.app";
export const SITE_NAME = "Dialogbot";
/** @deprecated Danish only – use t("landing.meta.title"). Kept for callers not yet translated. */
export const SITE_TITLE = "Dialogbot – AI-receptionist, AI-telefonsvarer og chatbot til danske virksomheder";
/** @deprecated Danish only – use t("landing.meta.description"). Kept for callers not yet translated. */
export const SITE_DESCRIPTION =
  "Dialogbot er en dansk AI-receptionist, der tager telefonen og chatten for din virksomhed døgnet rundt – svarer ud fra jeres egen viden, booker tider og samler henvendelser. Vi guider jer gennem hele opsætningen.";

/** Keyword landing pages (also in the sitemap and the footer). Label: t(`landing.nav.${key}`);
 *  `label` is the Danish text, kept for callers not yet translated. */
export const LANDING_PAGES: { href: string; key: string; label: string }[] = [
  { href: "/ai-receptionist", key: "aiReceptionist", label: "AI-receptionist" },
  { href: "/ai-telefonsvarer", key: "aiPhone", label: "AI-telefonsvarer" },
  { href: "/chatbot", key: "chatbot", label: "Chatbot til hjemmesiden" },
  { href: "/priser", key: "pricing", label: "Priser" },
  { href: "/viden", key: "knowledge", label: "Viden" },
];

/** Guides under /viden (also in the sitemap and on the /viden index). Title and teaser:
 *  t(`landing.articles.${slug}.title`) / `.teaser`. */
export const ARTICLES: { slug: string; published: string }[] = [
  { slug: "hvad-er-en-ai-receptionist", published: "2026-10-07" },
  { slug: "ai-telefonsvarer-eller-telefonpasning", published: "2026-10-07" },
  { slug: "viderestil-telefonen", published: "2026-10-07" },
  { slug: "dialogbot-vs-vocalis", published: "2026-11-03" },
  { slug: "dialogbot-vs-almindelig-chatbot", published: "2026-11-03" },
];

/** Absolute URL of a marketing page in one language: localeUrl("en", "/priser") → "https://dialogbot.app/en/priser";
 *  "/" or "" is the front page ("https://dialogbot.app/en"). */
export function localeUrl(locale: Locale, path: string): string {
  return `${SITE_URL}/${locale}${path === "/" ? "" : path}`;
}

/** hreflang map for a marketing page: every language (keyed by HTML_LANG, e.g. "nb" for Norwegian) plus
 *  x-default → the English version. Used by the sitemap and by alternatesFor. */
export function languageAlternates(path: string): Record<string, string> {
  const languages: Record<string, string> = {};
  for (const l of LOCALES) languages[HTML_LANG[l]] = localeUrl(l, path);
  languages["x-default"] = localeUrl("en", path);
  return languages;
}

/** `alternates` for generateMetadata on a marketing page: canonical = this language's URL, plus hreflang for all
 *  languages. `alternates: alternatesFor("/priser", locale)`. */
export function alternatesFor(path: string, locale: Locale): NonNullable<Metadata["alternates"]> {
  return { canonical: localeUrl(locale, path), languages: languageAlternates(path) };
}

/** `openGraph` for a marketing page in one language (url, og:locale, the shared image). */
export function openGraphFor(path: string, locale: Locale, title: string): NonNullable<Metadata["openGraph"]> {
  return { url: localeUrl(locale, path), title, locale: OG_LOCALE[locale], images: ["/opengraph-image.png"] };
}
