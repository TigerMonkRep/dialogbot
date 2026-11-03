import type { Metadata } from "next";
import Link from "@/i18n/link";
import { notFound } from "next/navigation";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { SeoPage, type SeoFaq } from "@/components/seo-page";
import { INDUSTRIES, industryBySlug, industryKey, type IndustryCopy } from "@/lib/industries";
import { alternatesFor, openGraphFor } from "@/lib/site";

export const dynamicParams = false;

export function generateStaticParams() {
  return INDUSTRIES.map((i) => ({ branche: i.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ branche: string }> }): Promise<Metadata> {
  const i = industryBySlug((await params).branche);
  if (!i) return {};
  const [raw, locale] = await Promise.all([getRaw(), getLocale()]);
  const c = raw<IndustryCopy>(industryKey(i.slug));
  const path = `/ai-receptionist/${i.slug}`;
  return { title: c.title, description: c.description, alternates: alternatesFor(path, locale),
    openGraph: openGraphFor(path, locale, `${c.title} | Dialogbot`) };
}

export default async function Page({ params }: { params: Promise<{ branche: string }> }) {
  const i = industryBySlug((await params).branche);
  if (!i) notFound();
  const [t, tl, raw] = await Promise.all([getT("landing.industry"), getT("landing"), getRaw()]);
  const c = raw<IndustryCopy>(industryKey(i.slug));
  const others = INDUSTRIES.filter((x) => x.slug !== i.slug).map((x) => ({ slug: x.slug, name: raw<IndustryCopy>(industryKey(x.slug)).name }));
  return (
    <SeoPage path={`/ai-receptionist/${i.slug}`} kicker={t("kicker", { name: c.name })} title={c.title.split(" – ")[0]}
      lead={c.description} points={[...c.benefits, t("setupPoint")]}
      sections={[
        { title: t("problemTitle", { name: c.name }), body: <p>{c.pain}{t("problemText", { examples: c.examples })}</p> },
        { title: t("scenarioTitle"), body: <div className="flex flex-col gap-2.5 not-prose">
          {c.scenario.map(([who, line], n) => (
            <p key={n} className={`m-0 px-4 py-3 text-[15px] leading-normal max-w-[460px] border-2 border-ink ${who === "Dialogbot" ? "self-start rounded-[16px_16px_16px_4px] bg-white text-ink" : "self-end rounded-[16px_16px_4px_16px] bg-ink text-white"}`}>
              <span className="block text-xs font-semibold tracking-[1px] uppercase opacity-70 mb-0.5">{who}</span>{line}</p>
          ))}
          <p className="text-sm text-muted">{t("scenarioNote")}<Link href="/proev">{t("scenarioLink")}</Link>{t("scenarioEnd")}</p>
        </div> },
        { title: `“${c.objection[0]}”`, body: <p>{c.objection[1]}</p> },
        { title: t("priceTitle"), body: <p>{t("priceA")}<strong>{t("price")}</strong>{t("priceB")}<Link href="/priser">{t("priceLink")}</Link>{t("priceC")}</p> },
        { title: t("othersTitle"), body: <ul>{others.map((o) => <li key={o.slug}><Link href={`/ai-receptionist/${o.slug}`}>{tl("industryLink", { name: o.name })}</Link></li>)}</ul> },
      ]}
      faq={[...c.faq, ...raw<SeoFaq[]>("landing.industry.faq")]} />
  );
}
