import type { Metadata } from "next";
import Link from "@/i18n/link";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { SeoPage, type SeoFaq } from "@/components/seo-page";
import { alternatesFor, openGraphFor } from "@/lib/site";

const PATH = "/priser";

export async function generateMetadata(): Promise<Metadata> {
  const [t, locale] = await Promise.all([getT("landing.pricing.meta"), getLocale()]);
  return { title: t("title"), description: t("description"), alternates: alternatesFor(PATH, locale),
    openGraph: openGraphFor(PATH, locale, t("ogTitle")) };
}

export default async function Page() {
  const [t, raw] = await Promise.all([getT("landing.pricing"), getRaw()]);
  const s = (key: string) => t(`sections.${key}`);
  return (
    <SeoPage path={PATH} kicker={t("kicker")}
      title={t("title")}
      lead={t("lead")}
      points={raw<string[]>("landing.pricing.points")}
      sections={[
        { title: s("subscription.title"), body: <>
          <p><strong>{s("subscription.p1Price")}</strong>{s("subscription.p1a")}<strong>{s("subscription.p1Minutes")}</strong>{s("subscription.p1b")}</p>
          <p>{s("subscription.p2")}</p>
          <p>{s("subscription.p3a")}<Link href="/proev">{s("subscription.p3Link")}</Link>{s("subscription.p3b")}</p>
        </> },
        { title: s("whyMore.title"), body: <>
          <p>{s("whyMore.p1")}</p>
          <p>{s("whyMore.p2a")}<strong>{s("whyMore.p2Strong")}</strong>{s("whyMore.p2b")}<Link href="/viden/dialogbot-vs-vocalis">{s("whyMore.p2Vocalis")}</Link>{s("whyMore.p2c")}<Link href="/viden/dialogbot-vs-almindelig-chatbot">{s("whyMore.p2Chatbot")}</Link>{s("whyMore.p2d")}</p>
        </> },
        { title: s("included.title"), body: <ul>
          {raw<string[]>("landing.pricing.sections.included.items").map((x) => <li key={x}>{x}</li>)}
        </ul> },
        { title: s("specialists.title"), body: <>
          <p>{s("specialists.p1a")}<strong>{s("specialists.p1Price")}</strong>{s("specialists.p1b")}</p>
          <p>{s("specialists.p2")}</p>
        </> },
        { title: s("outbound.title"), body: <>
          <p>{s("outbound.p1a")}<strong>{s("outbound.p1Call")}</strong>{s("outbound.p1b")}<strong>{s("outbound.p1Minute")}</strong>{s("outbound.p1c")}</p>
          <p>{s("outbound.p2")}</p>
        </> },
        { title: s("start.title"), body: <p>{s("start.a")}<Link href="/proev">{s("start.tryLink")}</Link>{s("start.b")}<Link href="/signup">{s("start.signupLink")}</Link>{s("start.c")}<Link href="/ai-receptionist">{s("start.receptionistLink")}</Link>{s("start.d")}</p> },
      ]}
      faq={raw<SeoFaq[]>("landing.pricing.faq")} />
  );
}
