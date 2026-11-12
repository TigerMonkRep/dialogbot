import Link from "@/i18n/link";
import type { Metadata } from "next";
import { COMPANY } from "@/components/legal-page";
import { SiteChrome } from "@/components/site-chrome";
import { ExplainerVideo } from "@/components/explainer-video";
import { videoStructuredData } from "@/lib/video";
import { ArrowIcon, CalendarIcon, ChatIcon, CheckIcon, PhoneIcon, PlayIcon, SendIcon, SmsIcon } from "@/components/site-icons";
import { ApprovalScreenshot } from "@/components/approval-screenshot";
import { ProofSection } from "@/components/proof-section";
import { ReferralBanner } from "@/components/referral-banner";
import { AudienceMemory } from "@/components/audience-memory";
import { Mark, ShortArrow, Tilted } from "@/components/mark";
import { SITE_NAME, SITE_URL, alternatesFor, openGraphFor } from "@/lib/site";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { HTML_LANG, type Locale } from "@/i18n/config";
import type { T } from "@/i18n/translate";
import { market, schemaPrice } from "@/lib/markets";
import { SIGNUP_ERHVERV } from "@/lib/contact";

/** The Erhverv landing (/erhverv – the entry page at "/" sends business visitors here): one story, read top to
 *  bottom. What Dialogbot is (one sentence + the 70-second video), how it works (3 steps), what it does (4 tiles),
 *  a real call to listen to, the price, and at the end the two ways in: try it (/proev) or build it yourself
 *  (/byggevejledning). No "Vej A / Vej B" jargon: visitors did not understand it. No claims beyond the list prices;
 *  the ambassador banner is kept. The accent layer (Mark/Tilted/ShortArrow) follows docs/brand.md: one marker per
 *  viewport, thin ink lines under the h2 keyword, nothing on body text, buttons or the footer. */
const PATH = "/erhverv";

export async function generateMetadata(): Promise<Metadata> {
  const [t, locale] = await Promise.all([getT("site"), getLocale()]);
  return {
    title: { absolute: t("home.meta.title") },
    description: t("home.meta.description"),
    alternates: alternatesFor(PATH, locale),
    openGraph: openGraphFor(PATH, locale, t("home.meta.ogTitle")),
  };
}

const container = "max-w-[1180px] mx-auto px-4 sm:px-6";
const eyebrow = "eyebrow text-[13px] tracking-[1.5px]";
const h2 = "m-0 font-display font-extrabold text-[clamp(30px,3.4vw,44px)] leading-[1.05] tracking-[-1px]";
const btnPrimary = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-accent hover:bg-accent-deep text-white no-underline font-semibold text-[17px]";
const btnOutline = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-white border-2 border-ink text-ink no-underline font-semibold text-[17px] hover:bg-panel";
const stepNo = "inline-flex w-14 h-14 rounded-[14px] bg-highlight items-center justify-center font-display font-extrabold text-[30px] shrink-0";
const tile = "inline-flex w-12 h-12 rounded-xl bg-accent items-center justify-center shrink-0";

/** Three check points under a dashed rule – the same on all three price cards. */
function Points({ items }: { items: string[] }) {
  return (
    <ul className="m-0 p-0 list-none flex flex-col gap-2 pt-1 border-t-2 border-dashed border-ink/30">
      {items.map((x) => (
        <li key={x} className="flex items-start gap-2.5 text-[15px] pt-2"><span className="mt-0.5 inline-flex w-5 h-5 shrink-0 rounded-full bg-success text-white items-center justify-center"><CheckIcon size={12} /></span><span>{x}</span></li>
      ))}
    </ul>
  );
}

/** The two add-on price cards (campaign calls, specialist setup): icon tile + «Tilvalg» stamp, the price, three
 *  check points and an outline door – so they carry as much as the subscription card instead of a bare number. */
function PriceAddon({ k, price, icon, href, points, t }: { k: "campaign" | "setup"; price: string; icon: React.ReactNode; href: string; points: string[]; t: T }) {
  return (
    <article className="flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink">
      <span className="flex items-center gap-3">
        <span className={tile}>{icon}</span>
        <span className="ml-auto inline-flex items-center min-h-6 px-2.5 rounded-full border-[1.5px] border-ink bg-panel text-ink text-[11px] font-semibold uppercase tracking-[0.12em]">{t(`home.price.${k}.badge`)}</span>
      </span>
      <span className="font-display font-bold text-xl">{t(`home.price.${k}.name`)}</span>
      <div className="flex items-baseline gap-2 flex-wrap"><span className="font-display font-extrabold text-[48px] tracking-[-1.5px] leading-none">{price}</span><span className="text-lg font-semibold text-ink-soft">{t(`home.price.${k}.unit`)}</span></div>
      <span className="text-[15px] text-ink-soft">{t(`home.price.${k}.text`)}</span>
      <Points items={points} />
      <Link href={href} className={`${btnOutline} mt-auto`}>{t(`home.price.${k}.cta`)}<ArrowIcon size={18} /></Link>
    </article>
  );
}

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
      <AudienceMemory audience="erhverv" />
      <ReferralBanner />

      {/* 1. HERO: what it is, in one sentence – and the video that explains it */}
      <section className="bg-white">
        <div className={`${container} pt-10 sm:pt-16 pb-12 sm:pb-16 flex flex-wrap gap-10 lg:gap-14 items-center`}>
          <div className="flex-[1_1_380px] min-w-0 flex flex-col gap-5">
            <span className={eyebrow}>{t("home.hero.eyebrow")}</span>
            <h1 className="m-0 font-display font-extrabold text-[clamp(38px,5vw,64px)] leading-[1.02] tracking-[-1.6px]">{t("home.hero.title.before")}<Mark kind="marker">{t("home.hero.title.mark")}</Mark>{t("home.hero.title.after")}</h1>
            <p className="m-0 text-[18px] sm:text-[19px] leading-[1.55] text-ink-soft max-w-[540px]">{t("home.hero.lead")}</p>
            <div className="flex flex-wrap gap-3">
              <Link href={SIGNUP_ERHVERV} className={btnPrimary} data-signup-cta>{t("home.hero.signupCta")}<ArrowIcon size={18} /></Link>
              <Link href="/proev" className={btnOutline}>{t("home.hero.cta")}</Link>
              <Link href="/start" className={btnOutline} data-funnel-entry>{t("funnel.entry")}</Link>
              <div className="hidden sm:block"><ExplainerVideo variant="button" /></div>
              <ShortArrow className="hidden lg:inline-flex ml-auto mr-2 self-center" />
            </div>
            <p className="m-0 text-sm text-muted">{t("home.hero.signupNote")}</p>
          </div>
          <div className="flex-[1_1_420px] min-w-0 max-w-[640px]"><ExplainerVideo variant="poster" /></div>
        </div>
      </section>

      {/* 2. HOW IT WORKS: three steps */}
      <section className="bg-panel border-y-2 border-ink">
        <div className={`${container} py-14 sm:py-20 flex flex-col gap-9`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>{t("home.how.eyebrow")}</span>
            <h2 className={h2}>{t("home.how.title.before")}<Mark kind="underline">{t("home.how.title.mark")}</Mark>{t("home.how.title.after")}</h2>
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
                  {n === "1" ? <Tilted deg={5}><span className={stepNo}>{n as string}</span></Tilted> : <span className={stepNo}>{n as string}</span>}
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
            <h2 className={h2}>{t("home.features.title.before")}<Mark kind="underline">{t("home.features.title.mark")}</Mark>{t("home.features.title.after")}</h2>
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
            <div className="flex flex-wrap gap-3">
              <Link href={SIGNUP_ERHVERV} className={`${btnPrimary} min-h-14 px-6`}>{t("home.hero.signupCta")}<ArrowIcon size={20} /></Link>
              <Link href="/proev" className={`${btnOutline} min-h-14 px-6`}><PlayIcon size={20} />{t("home.demo.cta")}</Link>
            </div>
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
            <h2 className={h2}>{t("home.price.title.before")}<Mark kind="marker" long>{t("home.price.title.mark")}</Mark>{t("home.price.title.after")}</h2>
            <p className="m-0 text-[17px] leading-[1.55] text-ink-soft">{t("home.price.lead")}</p>
          </div>
          <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr))]">
            <article className="flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink shadow-block">
              <span className="flex items-center gap-3"><span className={tile}><PhoneIcon size={22} /></span><span className="ml-auto inline-flex items-center min-h-6 px-2.5 rounded-full bg-highlight text-ink text-[11px] font-semibold uppercase tracking-[0.12em]">{t("home.price.subscription.badge")}</span></span>
              <span className="font-display font-bold text-xl">{t("home.price.subscription.name")}</span>
              <div className="flex items-baseline gap-2 flex-wrap"><span className="font-display font-extrabold text-[48px] tracking-[-1.5px] leading-none"><Mark kind="ring">{t("prices.monthly")}</Mark></span><span className="text-lg font-semibold text-ink-soft">{t("home.price.subscription.unit")}</span></div>
              <span className="text-[15px] text-ink-soft">{t("home.price.subscription.text")}</span>
              <Points items={raw<string[]>("site.home.price.subscription.points")} />
              <span className="text-[15px] text-ink-soft">{t("home.price.subscription.compare")}</span>
              <Link href={SIGNUP_ERHVERV} className={`${btnPrimary} mt-auto`}>{t("home.price.subscription.signupCta")}<ArrowIcon size={18} /></Link>
              <Link href="/proev" className="self-start text-[15px] font-semibold text-ink underline underline-offset-4 inline-flex items-center min-h-11">{t("home.price.subscription.cta")}</Link>
            </article>
            <PriceAddon k="campaign" price={t("prices.perCall")} icon={<SendIcon size={22} />} href="/kontakt" points={raw<string[]>("site.home.price.campaign.points")} t={t} />
            <PriceAddon k="setup" price={t("prices.setup")} icon={<CalendarIcon size={22} />} href="/kontakt" points={raw<string[]>("site.home.price.setup.points")} t={t} />
          </div>
          <div className="flex flex-col gap-2 max-w-[720px]">
            <h3 className="m-0 font-display font-bold text-[22px] leading-tight">{t("home.price.whyTitle")}</h3>
            <p className="m-0 text-[16px] leading-[1.55] text-ink-soft">{t("home.price.whyText")}</p>
          </div>
          {/* CTA row: the price should end in a door, not a paragraph. */}
          <div className="rounded-[20px] bg-ink text-white p-6 sm:p-8 flex flex-col md:flex-row md:items-center gap-5 md:gap-8">
            <div className="flex-1 flex flex-col gap-1.5">
              <span className="font-display font-extrabold text-[24px] leading-tight">{t("home.price.bottom.title")}</span>
              <span className="text-[16px] text-white/80">{t("home.price.bottom.text")}</span>
            </div>
            <div className="flex flex-col sm:flex-row gap-3 shrink-0">
              <Link href={SIGNUP_ERHVERV} className={btnPrimary}>{t("home.hero.signupCta")}<ArrowIcon size={18} /></Link>
              <Link href="/proev" className="inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] border-2 border-white text-white no-underline font-semibold text-[17px] hover:bg-white/10"><PhoneIcon size={18} />{t("home.price.bottom.primary")}</Link>
              <Link href="/byggevejledning" className="inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-white text-ink no-underline font-semibold text-[17px] hover:bg-panel">{t("home.price.bottom.secondary")}<ArrowIcon size={18} /></Link>
            </div>
          </div>
          <Link href="/priser" className="self-start text-[15px] font-semibold text-ink underline underline-offset-4 inline-flex items-center min-h-11">{t("home.price.allDetails")}</Link>
        </div>
      </section>

      {/* 6. GET STARTED: the two ways in, in plain words */}
      <section className="bg-panel border-t-2 border-ink">
        <div className={`${container} py-14 sm:py-20 flex flex-col gap-8`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>{t("home.start.eyebrow")}</span>
            <h2 className={h2}>{t("home.start.title.before")}<Mark kind="underline">{t("home.start.title.mark")}</Mark>{t("home.start.title.after")}</h2>
          </div>
          <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr))]">
            <Link href={SIGNUP_ERHVERV} className="group flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink shadow-block text-ink no-underline">
              <span className="inline-flex self-start items-center gap-2 px-3 py-1.5 rounded-full bg-highlight text-[13px] font-semibold tracking-[1px] uppercase">{t("home.start.signup.badge")}</span>
              <span className="font-display font-extrabold text-[28px] leading-[1.05] tracking-[-0.5px]">{t("home.start.signup.title")}</span>
              <span className="text-[16px] leading-[1.5] text-ink-soft">{t("home.start.signup.text")}</span>
              <span className={`${btnPrimary} mt-auto group-hover:bg-accent-deep`}>{t("home.start.signup.cta")}<ArrowIcon size={18} /></span>
            </Link>
            <Link href="/proev" className="group flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink text-ink no-underline">
              <span className="inline-flex self-start items-center gap-2 px-3 py-1.5 rounded-full bg-highlight text-[13px] font-semibold tracking-[1px] uppercase">{t("home.start.try.badge")}</span>
              <span className="font-display font-extrabold text-[28px] leading-[1.05] tracking-[-0.5px]">{t("home.start.try.title")}</span>
              <span className="text-[16px] leading-[1.5] text-ink-soft">{t("home.start.try.text")}</span>
              <span className={`${btnOutline} mt-auto`}>{t("home.start.try.cta")}<ArrowIcon size={18} /></span>
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
  const m = market(locale);
  const offer = (k: "subscription" | "campaign" | "setup", minor: number) => ({ "@type": "Offer", name: t(`home.ld.${k}.name`),
    price: schemaPrice(minor), priceCurrency: m.currency, description: t(`home.ld.${k}.description`),
    priceSpecification: { "@type": "PriceSpecification", price: schemaPrice(minor), priceCurrency: m.currency, valueAddedTaxIncluded: false } });
  const org = { "@type": "Organization", "@id": `${SITE_URL}/#organization`, name: SITE_NAME, url: SITE_URL,
    logo: `${SITE_URL}/icon.png`, email: COMPANY.email, telephone: "+4593703433", vatID: `DK${COMPANY.cvr}`,
    address: { "@type": "PostalAddress", streetAddress: "Abildgade 18", postalCode: "8200", addressLocality: "Aarhus", addressCountry: "DK" } };
  return [
    { "@context": "https://schema.org", ...org },
    { "@context": "https://schema.org", "@type": "WebSite", "@id": `${SITE_URL}/#website`, url: SITE_URL, name: SITE_NAME,
      inLanguage: lang, publisher: { "@id": `${SITE_URL}/#organization` } },
    { "@context": "https://schema.org", "@type": "SoftwareApplication", name: "Dialogbot", applicationCategory: "BusinessApplication",
      operatingSystem: "Web", description: t("home.ld.appDescription"), inLanguage: lang, url: `${SITE_URL}${PATH}`,
      publisher: { "@id": `${SITE_URL}/#organization` },
      offers: [
        offer("subscription", m.erhverv.monthly),
        offer("campaign", m.erhverv.call_answered),
        offer("setup", m.erhverv.setup),
      ] },
    { "@context": "https://schema.org", ...videoStructuredData(SITE_URL, t, locale, lang) },
  ];
}
