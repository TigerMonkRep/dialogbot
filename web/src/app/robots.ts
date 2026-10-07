import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

/** Public marketing pages are crawlable; the app, sign-in flows and API are not. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/app", "/api", "/onboarding", "/preview", "/invite", "/password", "/verify-email", "/a/", "/ambassador/udbetalinger"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
