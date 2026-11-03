import type { Metadata } from "next";
import Link from "@/i18n/link";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { SeoPage, type SeoFaq } from "@/components/seo-page";
import { ARTICLES, alternatesFor, openGraphFor } from "@/lib/site";
import { INDUSTRIES, industryKey, type IndustryCopy } from "@/lib/industries";

const PATH = "/viden";

export async function generateMetadata(): Promise<Metadata> {
  const [t, locale] = await Promise.all([getT("landing.knowledge.meta"), getLocale()]);
  return { title: t("title"), description: t("description"), alternates: alternatesFor(PATH, locale),
    openGraph: openGraphFor(PATH, locale, t("ogTitle")) };
}

export default async function Page() {
  const [t, tl, raw] = await Promise.all([getT("landing.knowledge"), getT("landing"), getRaw()]);
  const articles = ARTICLES.map((a) => ({ slug: a.slug, title: tl(`articles.${a.slug}.title`), teaser: tl(`articles.${a.slug}.teaser`) }));
  const industries = INDUSTRIES.map((i) => ({ slug: i.slug, ...raw<IndustryCopy>(industryKey(i.slug)) }));
  return (
    <SeoPage path={PATH} kicker={t("kicker")}
      title={t("title")}
      lead={t("lead")}
      points={articles.map((a) => a.title)}
      sections={[
        { title: t("guidesTitle"), body: <ul>{articles.map((a) => <li key={a.slug}><Link href={`/viden/${a.slug}`}><strong>{a.title}</strong></Link> – {a.teaser}</li>)}</ul> },
        { title: t("industriesTitle"), body: <ul>{industries.map((i) => <li key={i.slug}><Link href={`/ai-receptionist/${i.slug}`}>{tl("industryLink", { name: i.name })}</Link> – {i.examples}</li>)}</ul> },
      ]}
      faq={raw<SeoFaq[]>("landing.knowledge.faq")} />
  );
}
