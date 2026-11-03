import type { Metadata } from "next";
import { Blocks, type RichSection } from "@/components/legal-page";
import { SeoPage, type SeoFaq } from "@/components/seo-page";
import { getLocale, getRaw, getT, localePath } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("legal.gdpr");
  const url = localePath(await getLocale(), "/gdpr");
  return {
    title: t("meta.title"), description: t("meta.description"), alternates: { canonical: url },
    openGraph: { url, title: t("meta.ogTitle"), images: ["/opengraph-image.png"] },
  };
}

/** Plain-language data-handling statement (audit D3.4). Every sentence mirrors /privatliv and /vilkaar – change those
 *  first if the facts change (texts: messages/<locale>/legal.json → gdpr). */
export default async function Page() {
  const t = await getT("legal");
  const raw = await getRaw();
  const notice = t("notice");
  const sections = raw<RichSection[]>("legal.gdpr.sections").map((s, i) => ({
    title: s.title,
    body: <>
      {i === 0 && notice && <p className="text-[15px] text-ink"><em>{notice}</em></p>}
      <Blocks blocks={s.body} />
    </>,
  }));
  return (
    <SeoPage path="/gdpr" kicker={t("gdpr.kicker")} title={t("gdpr.title")} lead={t("gdpr.lead")}
      points={raw<string[]>("legal.gdpr.points")} sections={sections} faq={raw<SeoFaq[]>("legal.gdpr.faq")} />
  );
}
