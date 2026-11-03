import type { Metadata } from "next";
import { COMPANY } from "@/components/legal-page";
import { FounderBlock } from "@/components/founder-block";
import { SeoPage, type SeoFaq } from "@/components/seo-page";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { FOUNDER } from "@/lib/proof";
import { alternatesFor, openGraphFor } from "@/lib/site";

const PATH = "/om";

export async function generateMetadata(): Promise<Metadata> {
  const [t, locale] = await Promise.all([getT("landing.about.meta"), getLocale()]);
  return { title: t("title"), description: t("description"), alternates: alternatesFor(PATH, locale),
    openGraph: openGraphFor(PATH, locale, t("ogTitle")) };
}

/** Who is behind Dialogbot (audit D3.3). The founder block fills in from src/lib/proof.ts; until then the page
 *  shows only what is already public: company, address, phone. */
export default async function Page() {
  const [t, raw] = await Promise.all([getT("landing.about"), getRaw()]);
  return (
    <SeoPage path={PATH} kicker={t("kicker")}
      title={t("title")}
      lead={FOUNDER ? t("leadFounder", { name: FOUNDER.name }) : t("lead")}
      points={[t("points.company"), t("points.cvr", { cvr: COMPANY.cvr }), t("points.call"), t("points.noBinding")]}
      sections={[
        { title: t("sections.why.title"), body: <>
          <p>{t("sections.why.p")}</p>
          {FOUNDER && <FounderBlock />}
        </> },
        { title: t("sections.find.title"), body: <p>{COMPANY.name}, {t("sections.find.cvrNo")} {COMPANY.cvr}, {COMPANY.address}. {t("sections.find.a")}<a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>{t("sections.find.b")}<a href="tel:+4593703433">93 70 34 33</a>.</p> },
      ]}
      faq={raw<SeoFaq[]>("landing.about.faq")} />
  );
}
