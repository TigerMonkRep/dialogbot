import { SITE_NAME, SITE_URL } from "@/lib/site";

/** Renders structured data. Keep every claim in it something the repo can back. Server component. */
export function JsonLd({ data }: { data: object | object[] }) {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }} />;
}

/** BreadcrumbList for a sub-page: [["Viden", "/viden"], ["Guide", "/viden/guide"]] – the front page is added first. */
export function breadcrumbList(trail: [name: string, path: string][]) {
  return {
    "@context": "https://schema.org", "@type": "BreadcrumbList",
    itemListElement: [[SITE_NAME, ""] as [string, string], ...trail].map(([name, path], n) => ({
      "@type": "ListItem", position: n + 1, name, item: `${SITE_URL}${path}`,
    })),
  };
}
