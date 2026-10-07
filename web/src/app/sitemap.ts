import type { MetadataRoute } from "next";
import { ARTICLES, LANDING_PAGES, SITE_URL } from "@/lib/site";
import { INDUSTRIES } from "@/lib/industries";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const page = (path: string, priority: number, changeFrequency: "weekly" | "monthly" | "yearly") =>
    ({ url: `${SITE_URL}${path}`, lastModified: now, changeFrequency, priority });
  return [
    page("", 1, "weekly"),
    ...LANDING_PAGES.map((p) => page(p.href, 0.9, "monthly")),
    ...INDUSTRIES.map((i) => page(`/ai-receptionist/${i.slug}`, 0.8, "monthly")),
    ...ARTICLES.map((a) => page(`/viden/${a.slug}`, 0.7, "monthly")),
    page("/ambassador/bliv", 0.6, "monthly"),
    page("/signup", 0.5, "yearly"),
    page("/kontakt", 0.4, "yearly"),
    page("/vilkaar", 0.2, "yearly"),
    page("/privatliv", 0.2, "yearly"),
  ];
}
