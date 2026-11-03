import type { Metadata } from "next";
import Link from "@/i18n/link";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { SeoPage, type SeoFaq } from "@/components/seo-page";
import { alternatesFor, openGraphFor } from "@/lib/site";

const PATH = "/ai-telefonsvarer";

export async function generateMetadata(): Promise<Metadata> {
  const [t, locale] = await Promise.all([getT("landing.phone.meta"), getLocale()]);
  return { title: t("title"), description: t("description"), alternates: alternatesFor(PATH, locale),
    openGraph: openGraphFor(PATH, locale, t("ogTitle")) };
}

export default async function Page() {
  const [t, raw] = await Promise.all([getT("landing.phone"), getRaw()]);
  const s = (key: string) => t(`sections.${key}`);
  return (
    <SeoPage path={PATH} kicker={t("kicker")}
      title={t("title")}
      lead={t("lead")}
      points={raw<string[]>("landing.phone.points")}
      sections={[
        { title: s("conversation.title"), body: <>
          <p>{s("conversation.p1")}</p>
          <p>{s("conversation.p2")}</p>
        </> },
        { title: s("howItWorks.title"), body: <ul>
          {raw<[string, string][]>("landing.phone.sections.howItWorks.items").map(([b, rest]) => <li key={b}><strong>{b}</strong>{rest}</li>)}
        </ul> },
        { title: s("human.title"), body: <>
          <p>{s("human.p1")}</p>
          <p>{s("human.p2a")}<Link href="/proev">{s("human.p2Link")}</Link>{s("human.p2b")}</p>
        </> },
        { title: s("price.title"), body: <p>{s("price.a")}<strong>{s("price.price")}</strong>{s("price.b")}<Link href="/ai-receptionist">{s("price.receptionistLink")}</Link>{s("price.c")}<Link href="/chatbot">{s("price.chatbotLink")}</Link>{s("price.d")}</p> },
      ]}
      faq={raw<SeoFaq[]>("landing.phone.faq")} />
  );
}
