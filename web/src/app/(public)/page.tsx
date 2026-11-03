import Link from "@/i18n/link";
import { cookies } from "next/headers";
import type { Metadata } from "next";
import { COMPANY } from "@/components/legal-page";
import { SiteChrome } from "@/components/site-chrome";
import { ExplainerVideo } from "@/components/explainer-video";
import { videoStructuredData } from "@/lib/video";
import { ArrowIcon, CalendarIcon, ChatIcon, CheckIcon, PhoneIcon, PlayIcon, SendIcon, SmsIcon } from "@/components/site-icons";
import { API_BASE_URL, KNOWN_ACCOUNT_COOKIE, REFERRAL_COOKIE, SESSION_COOKIE } from "@/lib/config";
import { ApprovalScreenshot } from "@/components/approval-screenshot";
import { ProofSection } from "@/components/proof-section";
import { SITE_NAME, SITE_URL } from "@/lib/site";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { HTML_LANG, type Locale } from "@/i18n/config";
import type { T } from "@/i18n/translate";

/** The front page: one story, read top to bottom. What Dialogbot is (one sentence + the 70-second video), how it
 *  works (3 steps), what it does (4 tiles), a real call to listen to, the price, and at the end the two ways in:
 *  try it (/proev) or build it yourself (/byggevejledning). No "Vej A / Vej B" jargon: visitors did not understand it.
 *  No claims beyond the list prices; the ambassador banner is kept. */
type Recommender = { first_name: string; headline: string; code: string; customer_discount_bp: number };

/** The ambassador who sent this visitor (cookie set by /a/{slug}); null when none or no longer active, and
 *  never for someone who already has an account (logged in now, or has logged in from this browser before). */
async function recommender(): Promise<Recommender | null> {
  const store = await cookies();
  if (store.get(SESSION_COOKIE)?.value || store.get(KNOWN_ACCOUNT_COOKIE)?.value) return null;
  const ref = store.get(REFERRAL_COOKIE)?.value;
  if (!ref) return null;
  try {
    const r = await fetch(`${API_BASE_URL}/api/v1/public/ambassadors/${encodeURIComponent(ref)}`, { cache: "no-store" });
    return r.ok ? ((await r.json()) as Recommender) : null;
  } catch { return null; }
}

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("site");
  return {
    title: { absolute: t("home.meta.title") },
    description: t("home.meta.description"),
    alternates: { canonical: "/" },
    openGraph: { url: "/", title: t("home.meta.ogTitle"), images: ["/opengraph-image.png"] },
  };
}

const container = "max-w-[1180px] mx-auto px-4 sm:px-6";
const eyebrow = "eyebrow text-[13px] tracking-[1.5px]";
const h2 = "m-0 font-display font-extrabold text-[clamp(30px,3.4vw,44px)] leading-[1.05] tracking-[-1px]";
const btnPrimary = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-accent hover:bg-accent-deep text-white no-underline font-semibold text-[17px]";
const btnOutline = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-white border-2 border-ink text-ink no-underline font-semibold text-[17px] hover:bg-panel";
const stepNo = "inline-flex w-14 h-14 rounded-[14px] bg-highlight items-center justify-center font-display font-extrabold text-[30px] shrink-0";
const tile = "inline-flex w-12 h-12 rounded-xl bg-accent items-center justify-center shrink-0";

function Bubble({ who, initial, children }: { who: "D" | "K"; initial: string; children: React.ReactNode }) {
  const bot = who === "D";
  return (
    <div className={`flex gap-2.5 items-end ${bot ? "" : "justify-end"}`}>
      {bot && <span className="flex-none w-8 h-8 rounded-full bg-accent inline-flex items-center justify-center font-display font-extrabold text-[13px] text-white">{initial}</span>}
      <p className={`m-0 px-4 py-3 text-[15px] leading-normal max-w-[420px] ${bot ? "rounded-[16px_16px_16px_4px] bg-white border-2 border-ink" : "rounded-[16px_16px_4px_16px] bg-ink text-white"}`}>{children}</p>
      {!bot && <span className="flex-none w-8 h-8 rounded-full bg-highlight inline-flex items-center justify-center font-display font-extrabold text-[13px]">{initial}</span>}
    </div>
  );
}

export default async function Home() {
  const rec = await recommender();
  const t = await getT("site");
  const raw = await getRaw();
  const locale = await getLocale();
  const howSteps = raw<{ title: string; text: string }[]>("site.home.how.steps");
  const features = raw<{ title: string; text: string }[]>("site.home.features.items");
  const lines = raw<string[]>("site.demoCall.lines");
  const D = t("demoCall.botInitial");
  const K = t("demoCall.customerInitial");
  return (
    <SiteChrome compactFooter={false}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData(t, HTML_LANG[locale], locale)) }} />
      {rec && (
        <section aria-label={t("home.referral.label")} className="bg-highlight border-b-2 border-ink">
          <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-3 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-6">
            <span className="w-10 h-10 rounded-full bg-ink text-highlight flex items-center justify-center font-display font-extrabold text-lg shrink-0" aria-hidden>{rec.first_name.slice(0, 1)}</span>
            <div className="flex-1 min-w-0 text-ink">
              <p className="font-semibold text-[15px]">{t("home.referral.offer", { name: rec.first_name, pct: rec.customer_discount_bp / 100 })}</p>
              {rec.headline && <p className="text-sm">&ldquo;{rec.headline}&rdquo;</p>}
              <p className="text-xs text-ink-soft">{t("home.referral.bonus", { name: rec.first_name })}</p>
            </div>
            <Link href="/signup" className="inline-flex items-center justify-center gap-2 min-h-11 bg-ink text-white font-semibold text-[15px] px-5 rounded-xl no-underline">{t("home.referral.cta")}<ArrowIcon size={16} /></Link>
          </div>
        </section>
      )}

      {/* 1. HERO: what it is, in one sentence – and the video that explains it */}
      <section className="bg-white">
        <div className={`${container} pt-10 sm:pt-16 pb-12 sm:pb-16 flex flex-wrap gap-10 lg:gap-14 items-center`}>
          <div className="flex-[1_1_380px] min-w-0 flex flex-col gap-5">
            <span className={eyebrow}>{t("home.hero.eyebrow")}</span>
            <h1 className="m-0 font-display font-extrabold text-[clamp(38px,5vw,64px)] leading-[1.02] tracking-[-1.6px]">{t("home.hero.title")}</h1>
            <p className="m-0 text-[18px] sm:text-[19px] leading-[1.55] text-ink-soft max-w-[540px]">{t("home.hero.lead")}</p>
            <div className="flex flex-wrap gap-3">
              <Link href="/proev" className={btnPrimary}>{t("home.hero.cta")}<ArrowIcon size={18} /></Link>
              <div className="hidden sm:block"><ExplainerVideo variant="button" /></div>
            </div>
            <p className="m-0 text-sm text-muted">{t("home.hero.note")}</p>
          </div>
          <div className="flex-[1_1_420px] min-w-0 max-w-[640px]"><ExplainerVideo variant="poster" /></div>
        </div>
      </section>

      {/* 2. HOW IT WORKS: three steps */}
      <section className="bg-panel border-y-2 border-ink">
        <div className={`${container} py-14 sm:py-20 flex flex-col gap-9`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>{t("home.how.eyebrow")}</span>
            <h2 className={h2}>{t("home.how.title")}</h2>
            <p className="m-0 text-[17px] leading-[1.55] text-ink-soft">{t("home.how.lead")}</p>
          </div>
          <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr))]">
            {[
              ["1", howSteps[0].title, howSteps[0].text, <PhoneIcon key="p" size={30} stroke="#FFFFFF" />],
              ["2", howSteps[1].title, howSteps[1].text, <CalendarIcon key="c" size={30} stroke="#FFFFFF" />],
              ["3", howSteps[2].title, howSteps[2].text, <SmsIcon key="s" size={30} stroke="#FFFFFF" />],
            ].map(([n, title, text, icon]) => (
              <article key={n as string} className="flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink">
                <div className="flex items-center gap-4">
                  <span className={stepNo}>{n as string}</span>
                  <span className={tile}>{icon}</span>
                </div>
                <h3 className="m-0 font-display font-extrabold text-[24px] leading-[1.1] tracking-[-0.4px]">{title as string}</h3>
                <p className="m-0 text-[16px] leading-[1.55] text-ink-soft">{text as string}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* 3. WHAT IT DOES: four tiles */}
      <section className="bg-white">
        <div className={`${container} py-14 sm:py-20 flex flex-col gap-9`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>{t("home.features.eyebrow")}</span>
            <h2 className={h2}>{t("home.features.title")}</h2>
          </div>
          <div className="grid gap-5 [grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr))]">
            {[
              [features[0].title, features[0].text, <PhoneIcon key="1" size={24} stroke="#FFFFFF" />],
              [features[1].title, features[1].text, <CalendarIcon key="2" size={24} stroke="#FFFFFF" />],
              [features[2].title, features[2].text, <ChatIcon key="3" size={24} stroke="#FFFFFF" />],
              [features[3].title, features[3].text, <SendIcon key="4" size={24} stroke="#FFFFFF" />],
            ].map(([title, text, icon]) => (
              <div key={title as string} className="flex flex-col gap-3 p-5 rounded-2xl bg-panel border-[1.5px] border-ink">
                <span className={tile}>{icon}</span>
                <span className="font-display font-bold text-[20px] leading-tight">{title as string}</span>
                <span className="text-[15px] leading-[1.5] text-ink-soft">{text as string}</span>
              </div>
            ))}
          </div>
          <p className="m-0 text-[15px] text-ink-soft">{t("home.features.note")}</p>
        </div>
      </section>

      {/* 4. HEAR A CALL */}
      <section id="demo" className="bg-panel border-y-2 border-ink scroll-mt-6">
        <div className={`${container} py-14 sm:py-20 flex flex-wrap gap-12 items-center`}>
          <div className="flex-[1_1_380px] min-w-0 flex flex-col gap-4">
            <span className={eyebrow}>{t("home.demo.eyebrow")}</span>
            <h2 className={h2}>{t("home.demo.title")}</h2>
            <p className="m-0 text-[17px] leading-[1.55] text-ink-soft">{t("home.demo.lead")}</p>
            <Link href="/proev" className={`${btnPrimary} self-start min-h-14 px-6`}><PlayIcon size={20} />{t("home.demo.cta")}</Link>
          </div>
          <div className="flex-[1_1_380px] min-w-0 flex flex-col gap-3 p-5 sm:p-6 rounded-[20px] bg-white border-2 border-ink">
            <div className="flex items-center justify-between gap-3 text-[13px] font-semibold text-muted tracking-[1px] uppercase"><span>{t("demoCall.label")}</span><span>0:48</span></div>
            <Bubble who="D" initial={D}>{lines[0]}</Bubble>
            <Bubble who="K" initial={K}>{lines[1]}</Bubble>
            <Bubble who="D" initial={D}>{lines[2]}</Bubble>
            <Bubble who="K" initial={K}>{lines[3]}</Bubble>
            <div className="flex items-center gap-2 mt-1.5 px-3 py-2.5 rounded-[10px] bg-panel border-[1.5px] border-ink text-[13px] font-semibold"><CheckIcon size={16} stroke="#2456F6" />{t("demoCall.booked")}</div>
          </div>
          <ApprovalScreenshot />
        </div>
      </section>

      {/* 4b. PROOF (D3.1/D3.2/D3.5): renders nothing until real, consented customer data is filled in in
          src/lib/proof.ts. No invented names, quotes or counts. */}
      <ProofSection />

      {/* 5. PRICE */}
      <section id="pris" className="bg-white scroll-mt-6">
        <div className={`${container} py-14 sm:py-20 flex flex-col gap-9`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>{t("home.price.eyebrow")}</span>
            <h2 className={h2}>{t("home.price.title")}</h2>
            <p className="m-0 text-[17px] leading-[1.55] text-ink-soft">{t("home.price.lead")}</p>
          </div>
          <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr))]">
            <article className="flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink shadow-block">
              <span className="flex items-center gap-3 flex-wrap"><span className="font-display font-bold text-xl">{t("home.price.subscription.name")}</span><span className="inline-flex items-center min-h-6 px-2.5 rounded-full bg-highlight text-ink text-[11px] font-semibold uppercase tracking-[0.12em]">{t("home.price.subscription.badge")}</span></span>
              <div className="flex items-baseline gap-2 flex-wrap"><span className="font-display font-extrabold text-[48px] tracking-[-1.5px] leading-none">{t("prices.monthly")}</span><span className="text-lg font-semibold text-ink-soft">{t("home.price.subscription.unit")}</span></div>
              <span className="text-[15px] text-ink-soft">{t("home.price.subscription.text")}</span>
              <span className="text-[15px] text-ink-soft">{t("home.price.subscription.compare")}</span>
              <Link href="/proev" className={`${btnPrimary} mt-auto`}>{t("home.price.subscription.cta")}<ArrowIcon size={18} /></Link>
            </article>
            <article className="flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink">
              <span className="font-display font-bold text-xl">{t("home.price.campaign.name")}</span>
              <div className="flex items-baseline gap-2 flex-wrap"><span className="font-display font-extrabold text-[48px] tracking-[-1.5px] leading-none">{t("prices.perCall")}</span><span className="text-lg font-semibold text-ink-soft">{t("home.price.campaign.unit")}</span></div>
              <span className="text-[15px] text-ink-soft">{t("home.price.campaign.text")}</span>
            </article>
            <article className="flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink">
              <span className="font-display font-bold text-xl">{t("home.price.setup.name")}</span>
              <div className="flex items-baseline gap-2 flex-wrap"><span className="font-display font-extrabold text-[48px] tracking-[-1.5px] leading-none">{t("prices.setup")}</span><span className="text-lg font-semibold text-ink-soft">{t("home.price.setup.unit")}</span></div>
              <span className="text-[15px] text-ink-soft">{t("home.price.setup.text")}</span>
            </article>
          </div>
          <div className="flex flex-col gap-2 max-w-[720px]">
            <h3 className="m-0 font-display font-bold text-[22px] leading-tight">{t("home.price.whyTitle")}</h3>
            <p className="m-0 text-[16px] leading-[1.55] text-ink-soft">{t("home.price.whyText")}</p>
          </div>
          <Link href="/priser" className="self-start text-[15px] font-semibold text-ink underline underline-offset-4 inline-flex items-center min-h-11">{t("home.price.allDetails")}</Link>
        </div>
      </section>

      {/* 6. GET STARTED: the two ways in, in plain words */}
      <section className="bg-panel border-t-2 border-ink">
        <div className={`${container} py-14 sm:py-20 flex flex-col gap-8`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>{t("home.start.eyebrow")}</span>
            <h2 className={h2}>{t("home.start.title")}</h2>
          </div>
          <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr))]">
            <Link href="/proev" className="group flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink shadow-block text-ink no-underline">
              <span className="inline-flex self-start items-center gap-2 px-3 py-1.5 rounded-full bg-highlight text-[13px] font-semibold tracking-[1px] uppercase">{t("home.start.try.badge")}</span>
              <span className="font-display font-extrabold text-[28px] leading-[1.05] tracking-[-0.5px]">{t("home.start.try.title")}</span>
              <span className="text-[16px] leading-[1.5] text-ink-soft">{t("home.start.try.text")}</span>
              <span className={`${btnPrimary} mt-auto group-hover:bg-accent-deep`}>{t("home.start.try.cta")}<ArrowIcon size={18} /></span>
            </Link>
            <Link href="/byggevejledning" className="group flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink text-ink no-underline">
              <span className="inline-flex self-start items-center gap-2 px-3 py-1.5 rounded-full bg-panel border-[1.5px] border-ink text-[13px] font-semibold tracking-[1px] uppercase">{t("home.start.build.badge")}</span>
              <span className="font-display font-extrabold text-[28px] leading-[1.05] tracking-[-0.5px]">{t("home.start.build.title")}</span>
              <span className="text-[16px] leading-[1.5] text-ink-soft">{t("home.start.build.text")}</span>
              <span className={`${btnOutline} mt-auto`}>{t("home.start.build.cta")}<ArrowIcon size={18} /></span>
            </Link>
          </div>
          <p className="m-0 text-[15px] text-ink-soft">{t("home.start.specialists")}</p>
        </div>
      </section>
    </SiteChrome>
  );
}

/** schema.org data for Google: the company, the site and the product with its two list prices. `t` is the "site"
 *  translator, `lang` the page's BCP-47 language. */
function structuredData(t: T, lang: string, locale: Locale) {
  const org = { "@type": "Organization", "@id": `${SITE_URL}/#organization`, name: SITE_NAME, url: SITE_URL,
    logo: `${SITE_URL}/icon.png`, email: COMPANY.email, telephone: "+4593703433", vatID: `DK${COMPANY.cvr}`,
    address: { "@type": "PostalAddress", streetAddress: "Abildgade 18", postalCode: "8200", addressLocality: "Aarhus", addressCountry: "DK" } };
  return [
    { "@context": "https://schema.org", ...org },
    { "@context": "https://schema.org", "@type": "WebSite", "@id": `${SITE_URL}/#website`, url: SITE_URL, name: SITE_NAME,
      inLanguage: lang, publisher: { "@id": `${SITE_URL}/#organization` } },
    { "@context": "https://schema.org", "@type": "SoftwareApplication", name: "Dialogbot", applicationCategory: "BusinessApplication",
      operatingSystem: "Web", description: t("home.ld.appDescription"), inLanguage: lang, url: SITE_URL,
      publisher: { "@id": `${SITE_URL}/#organization` },
      offers: [
        { "@type": "Offer", name: t("home.ld.subscription.name"), price: "2495", priceCurrency: "DKK", description: t("home.ld.subscription.description") },
        { "@type": "Offer", name: t("home.ld.campaign.name"), price: "4", priceCurrency: "DKK", description: t("home.ld.campaign.description") },
        { "@type": "Offer", name: t("home.ld.setup.name"), price: "5000", priceCurrency: "DKK", description: t("home.ld.setup.description") },
      ] },
    { "@context": "https://schema.org", ...videoStructuredData(SITE_URL, t, locale, lang) },
  ];
}
