import type { MetadataRoute } from "next";
import { ARTICLES, LANDING_PAGES, PAGE_UPDATED, SITE_URL } from "@/lib/site";
import { INDUSTRIES } from "@/lib/industries";

/** Only indexable pages. Sign-in flows, onboarding and the app are noindex and stay out. lastmod is the page's real
 *  last change (a fixed date per page), never `new Date()`, so Google can trust it. */
export default function sitemap(): MetadataRoute.Sitemap {
  const page = (path: string, updated: string, priority: number, changeFrequency: "weekly" | "monthly" | "yearly") =>
    ({ url: `${SITE_URL}${path}`, lastModified: new Date(updated), changeFrequency, priority });
  return [
    page("", PAGE_UPDATED.home, 1, "weekly"),
    ...LANDING_PAGES.map((p) => page(p.href, p.updated, 0.9, "monthly")),
    ...INDUSTRIES.map((i) => page(`/ai-receptionist/${i.slug}`, i.updated, 0.8, "monthly")),
    ...ARTICLES.map((a) => page(`/viden/${a.slug}`, a.updated ?? a.published, 0.7, "monthly")),
    page("/ambassador/bliv", PAGE_UPDATED.ambassadorJoin, 0.6, "monthly"),
    page("/kontakt", PAGE_UPDATED.contact, 0.4, "yearly"),
    page("/vilkaar", PAGE_UPDATED.terms, 0.2, "yearly"),
    page("/privatliv", PAGE_UPDATED.privacy, 0.2, "yearly"),
  ];
}
