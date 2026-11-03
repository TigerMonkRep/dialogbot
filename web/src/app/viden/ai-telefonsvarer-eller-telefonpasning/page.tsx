import type { Metadata } from "next";
import { Blocks, type RichSection } from "@/components/legal-page";
import { SeoPage, type SeoFaq } from "@/components/seo-page";
import { getLocale, getRaw, getT, localePath } from "@/i18n/server";

const slug = "ai-telefonsvarer-eller-telefonpasning";
const path = `/viden/${slug}`;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT(`articles.${slug}`);
  const url = localePath(await getLocale(), path);
  return {
    title: t("meta.title"), description: t("meta.description"), alternates: { canonical: url },
    openGraph: { url, type: "article", title: t("meta.ogTitle"), images: ["/opengraph-image.png"] },
  };
}

export default async function Page() {
  const t = await getT(`articles.${slug}`);
  const raw = await getRaw();
  const sections = raw<RichSection[]>(`articles.${slug}.sections`);
  return (
    <SeoPage path={path} kicker={t("kicker")} article={{ published: "2026-10-07" }}
      title={t("title")} lead={t("lead")} points={raw<string[]>(`articles.${slug}.points`)}
      sections={sections.map((s) => ({ title: s.title, body: <Blocks blocks={s.body} /> }))}
      faq={raw<SeoFaq[]>(`articles.${slug}.faq`)} />
  );
}
