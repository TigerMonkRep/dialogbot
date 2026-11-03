import type { Metadata } from "next";
import Link from "@/i18n/link";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { SeoPage, type SeoFaq } from "@/components/seo-page";
import { alternatesFor, openGraphFor } from "@/lib/site";

const PATH = "/chatbot";

export async function generateMetadata(): Promise<Metadata> {
  const [t, locale] = await Promise.all([getT("landing.chatbot.meta"), getLocale()]);
  return { title: t("title"), description: t("description"), alternates: alternatesFor(PATH, locale),
    openGraph: openGraphFor(PATH, locale, t("ogTitle")) };
}

export default async function Page() {
  const [t, raw] = await Promise.all([getT("landing.chatbot"), getRaw()]);
  const s = (key: string) => t(`sections.${key}`);
  return (
    <SeoPage path={PATH} kicker={t("kicker")}
      title={t("title")}
      lead={t("lead")}
      points={raw<string[]>("landing.chatbot.points")}
      sections={[
        { title: s("noGuessing.title"), body: <>
          <p>{s("noGuessing.p1")}</p>
          <p>{s("noGuessing.p2")}</p>
        </> },
        { title: s("canDo.title"), body: <ul>
          {raw<[string, string][]>("landing.chatbot.sections.canDo.items").map(([b, rest]) => <li key={b}><strong>{b}</strong>{rest}</li>)}
        </ul> },
        { title: s("sameKnowledge.title"), body: <p>{s("sameKnowledge.a")}<Link href="/ai-receptionist">{s("sameKnowledge.receptionistLink")}</Link>{s("sameKnowledge.b")}<Link href="/ai-telefonsvarer">{s("sameKnowledge.phoneLink")}</Link>{s("sameKnowledge.c")}</p> },
        { title: s("price.title"), body: <p>{s("price.a")}<strong>{s("price.price")}</strong>{s("price.b")}</p> },
      ]}
      faq={raw<SeoFaq[]>("landing.chatbot.faq")} />
  );
}
