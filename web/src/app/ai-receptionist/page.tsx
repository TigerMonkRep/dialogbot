import type { Metadata } from "next";
import Link from "@/i18n/link";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { SeoPage, type SeoFaq } from "@/components/seo-page";
import { alternatesFor, openGraphFor } from "@/lib/site";

const PATH = "/ai-receptionist";

export async function generateMetadata(): Promise<Metadata> {
  const [t, locale] = await Promise.all([getT("landing.receptionist.meta"), getLocale()]);
  return { title: t("title"), description: t("description"), alternates: alternatesFor(PATH, locale),
    openGraph: openGraphFor(PATH, locale, t("ogTitle")) };
}

export default async function Page() {
  const [t, raw] = await Promise.all([getT("landing.receptionist"), getRaw()]);
  const s = (key: string) => t(`sections.${key}`);
  return (
    <SeoPage path={PATH} kicker={t("kicker")}
      title={t("title")}
      lead={t("lead")}
      points={raw<string[]>("landing.receptionist.points")}
      sections={[
        { title: s("what.title"), body: <>
          <p>{s("what.p1")}</p>
          <p>{s("what.p2")}</p>
        </> },
        { title: s("canDo.title"), body: <ul>
          {raw<[string, string][]>("landing.receptionist.sections.canDo.items").map(([b, rest]) => <li key={b}><strong>{b}</strong>{rest}</li>)}
        </ul> },
        { title: s("industries.title"), body: <>
          <p>{s("industries.p1")}</p>
          <p>{s("industries.p2")}</p>
        </> },
        { title: s("price.title"), body: <>
          <p>{s("price.p1a")}<strong>{s("price.p1Price")}</strong>{s("price.p1b")}</p>
          <p>{s("price.p2a")}<Link href="/ai-telefonsvarer">{s("price.p2Phone")}</Link>{s("price.p2b")}<Link href="/chatbot">{s("price.p2Chatbot")}</Link>{s("price.p2c")}</p>
        </> },
      ]}
      faq={raw<SeoFaq[]>("landing.receptionist.faq")} />
  );
}
