import type { MetadataRoute } from "next";
import { LOCALES } from "@/i18n/config";
import { ARTICLES, LANDING_PAGES, SITE_URL, languageAlternates, localeUrl } from "@/lib/site";
import { INDUSTRIES } from "@/lib/industries";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  type Freq = "weekly" | "monthly" | "yearly";
  /** A marketing page: one entry per language, each with hreflang alternates (incl. x-default → /en). */
  const page = (path: string, priority: number, changeFrequency: Freq): MetadataRoute.Sitemap => {
    const languages = languageAlternates(path);
    return LOCALES.map((l) => ({ url: localeUrl(l, path), lastModified: now, changeFrequency, priority, alternates: { languages } }));
  };
  /** An unprefixed page (app/auth – its language is the user's choice). */
  const plain = (path: string, priority: number, changeFrequency: Freq): MetadataRoute.Sitemap =>
    [{ url: `${SITE_URL}${path}`, lastModified: now, changeFrequency, priority }];
  return [
    ...page("/", 1, "weekly"),
    ...page("/erhverv", 0.95, "weekly"),
    ...page("/proev", 0.9, "monthly"),
    ...page("/byggevejledning", 0.9, "monthly"),
    ...LANDING_PAGES.flatMap((p) => page(p.href, 0.9, "monthly")),
    ...INDUSTRIES.flatMap((i) => page(`/ai-receptionist/${i.slug}`, 0.8, "monthly")),
    ...ARTICLES.flatMap((a) => page(`/viden/${a.slug}`, 0.7, "monthly")),
    ...page("/ambassador/bliv", 0.6, "monthly"),
    ...plain("/signup", 0.5, "yearly"),
    ...plain("/privat", 0.8, "monthly"),
    // The quiz-funnels (language = cookie, like /privat); their numbered steps are noindex.
    ...plain("/start", 0.8, "monthly"),
    ...plain("/privat/start", 0.7, "monthly"),
    ...plain("/privat/vilkaar", 0.2, "yearly"),
    ...page("/om", 0.5, "monthly"),
    ...page("/gdpr", 0.6, "monthly"),
    ...page("/kontakt", 0.4, "yearly"),
    ...page("/vilkaar", 0.2, "yearly"),
    ...page("/privatliv", 0.2, "yearly"),
  ];
}
