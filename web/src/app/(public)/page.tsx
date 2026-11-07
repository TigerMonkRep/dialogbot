import Link from "@/i18n/link";
import type { Metadata } from "next";
import { COMPANY } from "@/components/legal-page";
import { ExplainerVideo } from "@/components/explainer-video";
import { LanguageSwitcher } from "@/components/language-switcher";
import { Mark, ShortArrow, Tilted } from "@/components/mark";
import { ReferralBanner } from "@/components/referral-banner";
import { SiteFooter } from "@/components/site-chrome";
import { ArrowIcon, CalendarIcon, ChatIcon, CheckIcon, CloseIcon, MenuIcon, PhoneIcon, PlusIcon, SendIcon, SmsIcon } from "@/components/site-icons";
import { LogoMark } from "@/components/ui";
import { CUSTOMER_QUOTES } from "@/lib/proof";
import { PLANS, TRIAL_DAYS } from "@/lib/privat/plans";
import { SITE_NAME, SITE_URL, alternatesFor, openGraphFor } from "@/lib/site";
import { HTML_LANG } from "@/i18n/config";
import { getLocale, getRaw, getT } from "@/i18n/server";
import s from "./entry.module.css";

/** The entry page ("/"): one assistant, two doors. Hear it first (hero with the looping call transcript), then
 *  Trin 2 – choose Erhverv (/erhverv) or Privat (/privat). Opening a door sets the `db_aud` cookie (src/proxy.ts),
 *  after which "/" sends the visitor straight to that door; "/?aud=reset" shows the entry again.
 *  Design: out/canvas/preview.html. Texts: messages/<locale>/entry.json; prices from site.json / lib/privat/plans.ts.
 *  Accent layer: one marker (h1), thin ink lines under the h2 keywords, the ring around 2.495 – nothing on body
 *  text, buttons or the footer. */
const PATH = "/";

export async function generateMetadata(): Promise<Metadata> {
  const [t, locale] = await Promise.all([getT("entry"), getLocale()]);
  return {
    title: { absolute: t("meta.title") },
    description: t("meta.description"),
    alternates: alternatesFor(PATH, locale),
    openGraph: openGraphFor(PATH, locale, t("meta.ogTitle")),
  };
}

const wrap = "max-w-[1200px] mx-auto px-5 sm:px-6";
const h2 = "m-0 font-display font-extrabold text-[clamp(32px,3.4vw,46px)] leading-[1.06] tracking-[-0.022em]";
const h3 = "m-0 font-display font-bold text-[21px] leading-[1.15] tracking-[-0.01em]";
const lead = "m-0 text-[19px] leading-[1.55] text-ink-soft max-w-[34em]";
const para = "m-0 text-[16px] leading-[1.55] text-ink-soft";
const small = "text-[13px] leading-[1.5] text-muted font-medium";
const sec = "py-16 lg:py-28";
const secHead = "flex flex-col gap-4 max-w-[38em] mb-9 lg:mb-14";
const btn = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-6 rounded-[14px] border-2 font-semibold text-[16px] leading-none whitespace-nowrap no-underline";
const btnPri = `${btn} bg-accent border-accent text-white hover:bg-accent-deep hover:border-accent-deep hover:text-white`;
const btnOra = `${btn} bg-[#E0521A] border-[#E0521A] text-white hover:bg-[#B8400F] hover:border-[#B8400F] hover:text-white`;
const btnYel = `${btn} bg-highlight border-highlight text-ink hover:bg-highlight-deep hover:border-highlight-deep`;
const btnInv = `${btn} bg-transparent border-white text-white hover:bg-white/10 hover:text-white`;
const step = "inline-flex items-center justify-center shrink-0 w-14 h-14 rounded-[14px] bg-highlight text-ink font-display font-extrabold text-[30px] tracking-[-0.02em]";
const stepSm = "inline-flex items-center justify-center shrink-0 w-10 h-10 rounded-[10px] bg-highlight text-ink font-display font-extrabold text-[20px] tracking-[-0.02em]";
const icoTile = "inline-flex items-center justify-center shrink-0 w-11 h-11 rounded-xl bg-accent text-white";
const checkBox = "inline-flex items-center justify-center shrink-0 w-5 h-5 rounded-md mt-px bg-ink text-white";

const PhoneGlyph = ({ size = 24 }: { size?: number }) => <PhoneIcon size={size} stroke="#FFFFFF" />;

export default async function Entry() {
  const [t, raw, locale, ts, tc] = await Promise.all([getT("entry"), getRaw(), getLocale(), getT("site"), getT("common")]);
  const lang = HTML_LANG[locale];
  const lines = raw<string[]>("entry.phone.lines");
  const facts = raw<{ title: string; text: string }[]>("entry.proof.facts");
  const kpis = raw<{ n: string; label: string }[]>("entry.choose.business.kpis");
  const rows = raw<{ time: string; name: string; status: string; tone: "ok" | "plain" | "yellow" }[]>("entry.choose.business.rows");
  const bricks = raw<string[]>("entry.how.bricks");
  const howSteps = raw<{ title: string; text: string }[]>("entry.how.steps");
  const tiles = raw<{ title: string; text: string }[]>("entry.can.tiles");
  const bizPoints = raw<string[]>("entry.pricing.business.points");
  const priPoints = raw<string[]>("entry.pricing.private.points");
  const faq = raw<{ q: string; a: string }[]>("entry.faq.items");
  const monthly = ts("prices.monthly");
  const setup = ts("prices.setup");
  const privateFrom = String(Math.min(...PLANS.map((p) => p.monthly)));
  const quote = CUSTOMER_QUOTES[0];
  const nav: [string, string][] = [["#saadan", t("nav.how")], ["#erhverv", t("nav.business")], ["#privat", t("nav.private")], ["#priser", t("nav.pricing")]];
  const tileIcons = [<PhoneGlyph key="p" size={22} />, <CalendarIcon key="c" size={22} stroke="#FFFFFF" />, <ChatIcon key="w" size={22} stroke="#FFFFFF" />,
    <SmsIcon key="s" size={22} stroke="#FFFFFF" />, <SendIcon key="o" size={22} stroke="#FFFFFF" />, <PersonIcon key="u" size={22} />];

  return (
    <div className="min-h-dvh flex flex-col bg-white text-ink">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-white">{tc("chrome.skip")}</a>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData(lang)) }} />

      {/* NAV: sticky; on a phone it collapses to logo + Prøv den + menu */}
      <header className={s.nav}>
        <div className={`${wrap} relative flex items-center gap-3 lg:gap-8 h-16 lg:h-[72px]`}>
          <Link href="/" aria-label={tc("chrome.home")} className="inline-flex items-center gap-2.5 min-h-11 text-ink no-underline">
            <LogoMark size={36} /><span className="font-display font-extrabold text-[22px] tracking-[-0.3px]">Dialogbot</span>
          </Link>
          <nav aria-label={t("nav.pages")} className="hidden lg:flex gap-7 ml-3 text-[15px] font-medium">
            {nav.map(([h, l]) => <a key={h} href={h} className="inline-flex items-center min-h-11 text-ink no-underline hover:text-accent-deep">{l}</a>)}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden lg:inline-flex"><LanguageSwitcher compact /></span>
            <Link href="/login" className="hidden lg:inline-flex items-center min-h-11 px-3.5 text-[15px] font-semibold text-ink no-underline hover:text-accent-deep">{t("nav.login")}</Link>
            <Link href="/proev" className={`${btnPri} min-h-11 px-[18px] text-[15px] rounded-xl`}>{t("nav.try")}</Link>
            <details className={`${s.menu} lg:hidden`}>
              <summary className="inline-flex items-center justify-center w-11 h-11 rounded-xl border-2 border-ink bg-white text-ink cursor-pointer" aria-label={t("nav.menu")}>
                <span className={`${s.open} inline-flex`}><MenuIcon size={22} /></span><span className={s.close}><CloseIcon size={20} /></span>
              </summary>
              <div className={`${s.menuPanel} z-30`}>
                <nav aria-label={t("nav.pages")} className={`${wrap} py-3 flex flex-col`}>
                  {nav.map(([h, l]) => <a key={h} href={h} className="inline-flex items-center min-h-12 text-[17px] font-semibold text-ink no-underline border-b border-line last:border-0">{l}</a>)}
                  <Link href="/login" className="inline-flex items-center min-h-12 text-[17px] font-semibold text-ink no-underline">{t("nav.login")}</Link>
                  <div className="py-3"><LanguageSwitcher /></div>
                </nav>
              </div>
            </details>
          </div>
        </div>
      </header>

      <main id="main" className="flex-1 flex flex-col">
        <ReferralBanner />

        {/* HERO: "Hør den først" – copy left, the phone right */}
        <section className="pt-14 pb-16 lg:pt-[88px] lg:pb-[104px]">
          <div className={`${wrap} grid gap-14 lg:gap-16 items-center lg:grid-cols-[minmax(0,1fr)_440px]`}>
            <div className="flex flex-col gap-7">
              <div className="flex items-center gap-3.5"><span className={stepSm}>1</span><span className="text-[14px] font-semibold text-ink">{t("hero.step")}</span></div>
              <h1 className="m-0 font-display font-extrabold text-[clamp(40px,4.45vw,64px)] leading-[1.02] tracking-[-0.025em] max-w-[11em]">
                {t("hero.title.before")}<Mark kind="marker">{t("hero.title.mark")}</Mark>{t("hero.title.after")}
              </h1>
              <p className={lead}>{t("hero.lead")}</p>
              <div className="flex flex-wrap items-center gap-3">
                <Link href="/proev" className={`${btnPri} max-sm:w-full`}>{t("hero.cta")}</Link>
                <ExplainerVideo variant="button" ghost label={t("hero.watch")} />
              </div>
              <div className="flex items-center gap-3">
                <p className={`m-0 ${small}`}>{t("hero.note")}</p>
                <span className={`hidden lg:inline-flex items-center gap-2.5 ml-auto pr-2 ${small} text-ink font-semibold`}>{t("hero.listen")}<ShortArrow /></span>
              </div>
            </div>
            <div className="flex justify-center">
              <Phone t={t} lines={lines} />
            </div>
          </div>
        </section>

        {/* PROOF STRIP: four facts, and the first real customer quote once one exists (src/lib/proof.ts) */}
        <section className="border-y-2 border-ink bg-white" aria-label={t("proof.label")}>
          <div className={`${wrap} py-10 grid gap-8 lg:gap-14 items-center ${quote ? "lg:grid-cols-[1.35fr_1fr]" : ""}`}>
            <dl className="m-0 grid grid-cols-2 lg:grid-cols-4 gap-4">
              {facts.map((f) => (
                <div key={f.title} className="flex flex-col gap-1.5">
                  <dt className="font-display font-extrabold text-[18px] tracking-[-0.01em] whitespace-nowrap">{f.title}</dt>
                  <dd className={`m-0 ${small}`}>{f.text}</dd>
                </div>
              ))}
            </dl>
            {quote && (
              <figure className="m-0 flex gap-4 items-start border-l-2 border-line pl-6">
                <div>
                  <blockquote className="m-0 font-display font-bold text-[20px] leading-[1.3] tracking-[-0.01em]">«{ts(`proof.data.quotes.${quote.id}.quote`)}»</blockquote>
                  <figcaption className="mt-2 text-[14px] text-muted font-medium">{quote.name}, {ts(`proof.data.quotes.${quote.id}.business`)}</figcaption>
                </div>
              </figure>
            )}
          </div>
        </section>

        {/* TRIN 2: the two doors */}
        <section id="trin2" className={`${sec} scroll-mt-20`}>
          <div className={wrap}>
            <div className={secHead}>
              <div className="flex items-center gap-4"><Tilted deg={-5}><span className={step}>2</span></Tilted><span className="text-[14px] font-semibold text-ink">{t("choose.step")}</span></div>
              <h2 className={h2}>{t("choose.title.before")}<Mark kind="underline">{t("choose.title.mark")}</Mark>{t("choose.title.after")}</h2>
              <p className={lead}>{t("choose.lead")}</p>
            </div>
            <div className="grid gap-8 lg:grid-cols-2">
              {/* Erhverv */}
              <article id="erhverv" className="relative flex flex-col gap-6 p-7 lg:p-10 lg:min-h-[620px] rounded-2xl border-2 border-ink bg-white scroll-mt-20">
                <p className="m-0 text-[14px] font-semibold text-muted"><span className="inline-block mr-2.5 px-2.5 py-[5px] rounded-lg bg-accent text-white font-bold text-[13px]">{t("choose.business.kick")}</span>{t("choose.business.kickText")}</p>
                <h3 className="m-0 font-display font-extrabold text-[28px] lg:text-[34px] leading-[1.05] tracking-[-0.02em]">{t("choose.business.title")}</h3>
                <p className={`${para} max-w-[30em]`}>{t("choose.business.text")}</p>
                <div className="mt-auto flex flex-col gap-3.5 p-[18px] rounded-xl border-2 border-ink bg-white" role="img" aria-label={t("choose.business.uiLabel")}>
                  <div className="flex items-center justify-between text-[13px] font-semibold text-muted"><span>{t("choose.business.today")}</span><span>{t("choose.business.company")}</span></div>
                  <div className="grid grid-cols-1 min-[560px]:grid-cols-3 gap-1.5 min-[560px]:gap-2.5">
                    {kpis.map((k) => (
                      <div key={k.label} className="flex flex-row min-[560px]:flex-col items-baseline min-[560px]:items-start gap-2 min-[560px]:gap-0.5 px-3 py-2 min-[560px]:p-3 rounded-[10px] border-[1.5px] border-ink bg-white">
                        <b className="font-display font-extrabold text-[24px] min-[560px]:text-[28px] leading-none tracking-[-0.02em]">{k.n}</b><span className="text-[12px] font-semibold text-muted">{k.label}</span>
                      </div>
                    ))}
                  </div>
                  <div className="rounded-[10px] border-[1.5px] border-ink bg-white overflow-hidden">
                    {rows.map((r, i) => (
                      <div key={r.time} className={`flex items-center gap-2 min-[560px]:gap-3 px-2.5 py-2.5 min-[560px]:px-3 text-[13.5px] ${i ? "border-t-[1.5px] border-line" : ""}`}>
                        <span className="w-10 text-[12.5px] font-semibold text-muted tabular-nums">{r.time}</span>
                        <span className="flex-1 min-w-0 font-semibold truncate">{r.name}</span>
                        <span className={`text-[12px] font-semibold px-2 py-[3px] rounded-full border-[1.5px] ${r.tone === "ok" ? "bg-success-soft text-success border-success-soft" : r.tone === "yellow" ? "bg-highlight border-highlight" : "border-ink"}`}>{r.status}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Link href="/erhverv" className={btnPri}>{t("choose.business.cta")}<ArrowIcon size={18} /></Link>
                  <span className={small}>{t("choose.business.price", { price: monthly })}</span>
                </div>
              </article>
              {/* Privat */}
              <article id="privat" className="relative flex flex-col gap-6 p-7 lg:p-10 lg:min-h-[620px] rounded-[32px] border-2 border-ink bg-[#FFFBF5] scroll-mt-20">
                <p className="m-0 text-[14px] font-semibold text-muted"><span className="inline-block mr-2.5 px-2.5 py-[5px] rounded-full bg-[#E0521A] text-white font-bold text-[13px]">{t("choose.private.kick")}</span>{t("choose.private.kickText")}</p>
                <h3 className="m-0 font-display font-extrabold text-[28px] lg:text-[34px] leading-[1.05] tracking-[-0.02em]">{t("choose.private.title")}</h3>
                <p className={`${para} max-w-[30em]`}>{t("choose.private.text")}</p>
                <div className="mt-auto flex flex-col gap-2.5 p-[18px] rounded-3xl border-2 border-ink bg-white" role="img" aria-label={t("choose.private.uiLabel")}>
                  <div className="flex items-center gap-2 text-[12px] font-semibold text-muted"><span className="inline-flex items-center justify-center w-[22px] h-[22px] rounded-full bg-[#E0521A] text-white"><PersonIcon size={13} /></span>{t("choose.private.who")}</div>
                  <div className="self-start max-w-[88%] px-3.5 py-[11px] rounded-[20px] rounded-bl-md border-[1.5px] border-ink bg-[#FFF4E6] text-[14.5px] leading-[1.42]">{t("choose.private.ask")}</div>
                  <div className="self-end max-w-[88%] px-3.5 py-[11px] rounded-[20px] rounded-br-md bg-[#E0521A] text-white text-[14.5px] leading-[1.42]">{t("choose.private.yes")}</div>
                  <div className="self-start max-w-[88%] flex items-center gap-2 px-3.5 py-[11px] rounded-[20px] rounded-bl-md border-[1.5px] border-ink bg-white text-[14.5px] leading-[1.42]">
                    <span className="inline-flex items-center justify-center shrink-0 w-[22px] h-[22px] rounded-full bg-success text-white"><CheckIcon size={12} /></span>{t("choose.private.done")}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Link href="/privat" className={btnOra}>{t("choose.private.cta")}<ArrowIcon size={18} /></Link>
                  <span className={small}>{t("choose.private.trial", { days: TRIAL_DAYS })}</span>
                </div>
              </article>
            </div>
          </div>
        </section>

        {/* SÅDAN VIRKER DET */}
        <section id="saadan" className={`${sec} bg-panel scroll-mt-20`}>
          <div className={wrap}>
            <div className={secHead}>
              <h2 className={h2}>{t("how.title.before")}<Mark kind="underline">{t("how.title.mark")}</Mark>{t("how.title.after")}</h2>
              <p className={lead}>{t("how.lead")}</p>
            </div>
            <div className="grid grid-cols-3 gap-3.5 sm:gap-5 lg:gap-10 mb-10 items-center" aria-hidden="true">
              {[
                ["bg-accent text-white", <PhoneGlyph key="p" size={28} />],
                ["bg-highlight text-ink", <CalendarIcon key="c" size={28} />],
                ["bg-ink text-white", <SmsIcon key="s" size={28} stroke="#FFFFFF" />],
              ].map(([cls, icon], i) => (
                <div key={i} className="relative flex items-center">
                  <div className={`flex flex-col items-center justify-center gap-1.5 sm:gap-2 w-full max-w-[200px] lg:w-[180px] h-[84px] sm:h-[100px] lg:h-[120px] rounded-[18px] lg:rounded-3xl border-2 border-ink text-[12px] sm:text-[13px] font-semibold ${cls}`}>{icon}<span>{bricks[i]}</span></div>
                  {i < 2 && <BrickArrow className="hidden sm:block absolute -right-[18px] lg:-right-[22px] top-1/2 -translate-y-1/2 w-8 lg:w-11" />}
                </div>
              ))}
            </div>
            <div className="grid gap-9 lg:grid-cols-3 lg:gap-10">
              {howSteps.map((st, i) => (
                <div key={st.title} className="flex flex-col gap-[18px]">
                  {i === 1 ? <Tilted deg={5}><span className={step}>{i + 1}</span></Tilted> : <span className={step}>{i + 1}</span>}
                  <h3 className="m-0 font-display font-extrabold text-[24px] leading-[1.15] tracking-[-0.02em]">{st.title}</h3>
                  <p className={para}>{st.text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* DET KAN DEN: six tiles */}
        <section id="kan" className={`${sec} scroll-mt-20`}>
          <div className={wrap}>
            <div className={secHead}>
              <h2 className={h2}>{t("can.title.before")}<Mark kind="underline">{t("can.title.mark")}</Mark>{t("can.title.after")}</h2>
              <p className={lead}>{t("can.lead")}</p>
            </div>
            <ul className="m-0 p-0 list-none grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {tiles.map((tile, i) => (
                <li key={tile.title} className={`${s.tile} flex flex-row sm:flex-col items-start gap-4 p-5 sm:p-[26px] rounded-2xl border-2 border-ink bg-white`}>
                  <span className={`${icoTile} ${i === 5 ? "bg-[#E0521A]" : ""}`}>{tileIcons[i]}</span>
                  <div className="flex flex-col gap-1.5 sm:gap-2.5">
                    <h3 className={`${h3} text-[19px]`}>{tile.title}</h3>
                    <p className={`${para} text-[15px]`}>{tile.text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* PRISER: the two doors' entry prices */}
        <section id="priser" className={`${sec} bg-panel scroll-mt-20`}>
          <div className={wrap}>
            <div className={secHead}>
              <h2 className={h2}>{t("pricing.title")}</h2>
              <p className={lead}>{t("pricing.lead")}</p>
            </div>
            <div className="grid gap-6 lg:grid-cols-2 max-w-[960px]">
              <article className="flex flex-col gap-[18px] p-7 sm:p-9 rounded-2xl border-2 border-ink bg-white shadow-block">
                <h3 className="m-0 font-display font-extrabold text-[24px] tracking-[-0.02em]">{t("pricing.business.name")}</h3>
                <p className="m-0 flex items-baseline gap-2.5 font-display font-extrabold tracking-[-0.03em] leading-none flex-wrap">
                  <span className="text-[18px] font-bold text-muted">{t("pricing.from")}</span>
                  <span className="text-[52px] sm:text-[60px] mx-[0.3em]"><Mark kind="ring">{monthly}</Mark></span>
                  <span className="text-[18px] font-bold text-muted">{t("pricing.business.unit")}</span>
                </p>
                <ul className="m-0 p-0 list-none flex flex-col gap-2.5 text-[15px] text-ink-soft">
                  {bizPoints.map((p) => <li key={p} className="flex items-start gap-2.5"><span className={checkBox}><CheckIcon size={12} /></span><span>{p}</span></li>)}
                </ul>
                <Link href="/proev" className={`${btnPri} self-start mt-2`}>{t("pricing.business.cta")}</Link>
              </article>
              <article className="flex flex-col gap-[18px] p-7 sm:p-9 rounded-[28px] border-2 border-ink bg-[#FFFBF5]">
                <h3 className="m-0 font-display font-extrabold text-[24px] tracking-[-0.02em]">{t("pricing.private.name")}</h3>
                <p className="m-0 flex items-baseline gap-2.5 font-display font-extrabold tracking-[-0.03em] leading-none flex-wrap">
                  <span className="text-[18px] font-bold text-muted">{t("pricing.from")}</span>
                  <span className="text-[52px] sm:text-[60px]">{privateFrom}</span>
                  <span className="text-[18px] font-bold text-muted">{t("pricing.private.unit", { days: TRIAL_DAYS })}</span>
                </p>
                <ul className="m-0 p-0 list-none flex flex-col gap-2.5 text-[15px] text-ink-soft">
                  {priPoints.map((p) => <li key={p} className="flex items-start gap-2.5"><span className={`${checkBox} bg-[#E0521A]`}><CheckIcon size={12} /></span><span>{p}</span></li>)}
                </ul>
                <Link href="/privat/start" className={`${btnOra} self-start mt-2`}>{t("pricing.private.cta", { days: TRIAL_DAYS })}</Link>
              </article>
            </div>
            <p className="m-0 mt-7"><Link href="/priser" className="inline-flex items-center min-h-11 font-semibold text-accent underline underline-offset-4 hover:text-accent-deep">{t("pricing.all")}</Link></p>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className={`${sec} scroll-mt-20`}>
          <div className={wrap}>
            <div className={`${secHead} mb-10`}><h2 className={h2}>{t("faq.title")}</h2></div>
            <div className="max-w-[760px] flex flex-col border-t-2 border-ink">
              {faq.map((f, i) => (
                <details key={f.q} className={`${s.faq} border-b-2 border-ink`} open={i === 0}>
                  <summary className="flex items-center justify-between gap-6 py-[22px] cursor-pointer font-display font-bold text-[18px] sm:text-[21px] tracking-[-0.01em]">
                    {f.q}<span className={`${s.plus} inline-flex items-center justify-center shrink-0 w-8 h-8 rounded-[10px] border-2 border-ink`} aria-hidden="true"><PlusIcon size={16} /></span>
                  </summary>
                  <p className={`${para} pb-6 sm:pr-14 max-w-[36em]`}>{t(`faq.items.${i}.a`, { setup })}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* CTA BAND */}
        <section className="bg-ink text-white py-[72px] lg:py-28">
          <div className={`${wrap} flex flex-col items-start gap-7`}>
            <h2 className={`${h2} text-white max-w-[14em]`}>{t("band.title")}</h2>
            <p className="m-0 text-[18px] leading-[1.55] text-[#C9D3E3] max-w-[32em]">{t("band.text")}</p>
            <div className="flex flex-wrap gap-3">
              <Link href="/proev" className={btnYel}>{t("band.primary")}</Link>
              <Link href="/start" className={btnInv}>{t("band.secondary")}</Link>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter audience={null} />
    </div>
  );
}

/** The phone with the looping call: incoming card → "Dialogbot svarer" → five bubbles → booked chip. Decorative;
 *  the whole story is in the aria-label, the bubbles are hidden from assistive tech. */
function Phone({ t, lines }: { t: (k: string) => string; lines: string[] }) {
  return (
    <div className={s.phone} role="img" aria-label={t("phone.alt")}>
      <span className="absolute left-1/2 top-3 w-24 h-[26px] -ml-12 rounded-full bg-ink" aria-hidden="true" />
      <div className="flex items-center justify-between px-[26px] pt-[18px] text-[13px] font-semibold" aria-hidden="true">
        <span>{t("phone.time")}</span>
        <span className="inline-flex items-center gap-1.5"><i className={`${s.liveDot} w-2 h-2 rounded-full bg-success`} />{t("phone.live")}</span>
      </div>
      <div className="relative flex-1 flex flex-col gap-3 px-[18px] pt-[22px] pb-[18px]" aria-hidden="true">
        <div className={`${s.callcard} absolute left-[18px] right-[18px] top-11 flex flex-col gap-3 p-[18px] rounded-[20px] border-2 border-ink bg-white`}>
          <div className="flex items-center gap-3.5">
            <span className="relative flex items-center justify-center w-[52px] h-[52px] rounded-2xl bg-accent"><em className={s.ringPulse} /><PhoneGlyph /></span>
            <div><div className="font-display font-extrabold text-[20px] tracking-[-0.01em]">{t("phone.caller")}</div><div className={small}>{t("phone.callerSub")}</div></div>
          </div>
          <div className="flex gap-2">
            <span className="flex-1 flex items-center justify-center h-10 rounded-xl border-2 border-ink text-[13px] font-semibold">{t("phone.decline")}</span>
            <span className="flex-1 flex items-center justify-center h-10 rounded-xl border-2 border-accent bg-accent text-white text-[13px] font-semibold">{t("phone.answer")}</span>
          </div>
        </div>
        <div className={`${s.livebar} flex items-center gap-2.5 px-3 py-2.5 rounded-[14px] border-[1.5px] border-ink bg-white text-[13px] font-semibold`}>
          <span className="flex items-center justify-center shrink-0 w-[30px] h-[30px] rounded-[9px] bg-accent"><PhoneGlyph size={16} /></span>
          <span>{t("phone.answer")}</span><span className="ml-auto text-muted tabular-nums">{t("phone.timer")}</span>
        </div>
        {lines.map((l, i) => (
          <div key={i} className={`${s.tb} ${s[`b${i + 1}`]} max-w-[86%] px-3.5 py-[11px] rounded-[18px] text-[14.5px] leading-[1.42] ${i % 2 === 0 ? "self-start bg-white border-[1.5px] border-ink rounded-bl-md" : "self-end bg-accent text-white rounded-br-md"}`}>{l}</div>
        ))}
        <div className={`${s.chip} self-center mt-auto inline-flex items-center gap-2 px-3.5 py-2.5 rounded-full bg-highlight border-2 border-ink shadow-block-sm font-display font-extrabold text-[15px] tracking-[-0.01em]`}>
          <b className="inline-flex items-center justify-center w-[22px] h-[22px] rounded-[7px] bg-ink"><CheckIcon size={12} stroke="#FFCF3F" /></b>{t("phone.chip")}
        </div>
      </div>
    </div>
  );
}

const PersonIcon = ({ size = 22 }: { size?: number }) => (
  <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>
);
const BrickArrow = ({ className = "" }: { className?: string }) => (
  <svg viewBox="0 0 40 26" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={`text-ink ${className}`}><path d="M4 13h32M28 5l8 8-8 8" /></svg>
);

/** schema.org for the entry: the company and the site (the product with its offers lives on /erhverv). */
function structuredData(lang: string) {
  return [
    { "@context": "https://schema.org", "@type": "Organization", "@id": `${SITE_URL}/#organization`, name: SITE_NAME, url: SITE_URL,
      logo: `${SITE_URL}/icon.png`, email: COMPANY.email, telephone: "+4593703433", vatID: `DK${COMPANY.cvr}`,
      address: { "@type": "PostalAddress", streetAddress: "Abildgade 18", postalCode: "8200", addressLocality: "Aarhus", addressCountry: "DK" } },
    { "@context": "https://schema.org", "@type": "WebSite", "@id": `${SITE_URL}/#website`, url: SITE_URL, name: SITE_NAME, inLanguage: lang,
      publisher: { "@id": `${SITE_URL}/#organization` } },
  ];
}
