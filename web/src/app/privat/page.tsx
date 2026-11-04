import type { Metadata } from "next";
import Link from "next/link";
import SiteLink from "@/i18n/link";
import { LogoMark } from "@/components/ui";
import { AudienceSwitch } from "@/components/audience-switch";
import { Ico } from "@/components/privat/icons";
import { PublicPlans } from "@/components/privat/plans-public";
import { getRaw, getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("privat");
  return { title: t("landing.metaTitle"), description: t("landing.metaDescription") };
}

const H2 = "m-0 text-[clamp(28px,3.2vw,40px)] leading-[1.05] tracking-[-0.02em]";
const WRAP = "w-full max-w-[1200px] mx-auto px-5 sm:px-8";
const PILL_CTA = "inline-flex items-center justify-center min-h-[54px] px-7 rounded-full border-2 border-ink bg-accent text-on-accent text-[16px] font-semibold no-underline shadow-[6px_6px_0_var(--color-ink)] hover:bg-accent-deep";
const CHIP = "inline-flex items-center min-h-9 px-3 rounded-full border-2 border-ink bg-white text-[13px] font-semibold";

/** Public landing for Dialogbot Privat (design canvas "Dialogbot – Erhverv vs. Privat", artboard "Privat – landingside").
 *  Orange theme via data-theme="privat"; the language follows the cookie like the app (no /<locale>/ prefix). The hero
 *  demo card is static. Texts: privat.json → landing.*. */
export default async function PrivatLanding() {
  const t = await getT("privat");
  const tc = await getT("common");
  const raw = await getRaw();
  const three = raw<{ title: string; text: string }[]>("privat.landing.three.items");
  const steps = raw<string[]>("privat.landing.control.steps");
  const apps = raw<Record<string, string>>("privat.landing.store.apps");
  const tryHref = "/privat/dag";
  const appTiles: { key: string; bg: string; fg: string }[] = [
    { key: "sharedLists", bg: "bg-accent", fg: "text-on-accent" },
    { key: "wishlist", bg: "bg-success-soft", fg: "text-ink" },
    { key: "birthdays", bg: "bg-highlight", fg: "text-ink" },
    { key: "calendar", bg: "bg-[#2456F6]", fg: "text-white" },
    { key: "meals", bg: "bg-panel", fg: "text-ink" },
    { key: "car", bg: "bg-accent", fg: "text-on-accent" },
    { key: "doctor", bg: "bg-success-soft", fg: "text-ink" },
    { key: "more", bg: "bg-white", fg: "text-muted" },
  ];
  const initials = (name: string) => name.split(/\s+/).filter((w) => /^[\p{L}\p{N}]/u.test(w)).slice(0, 2).map((w) => w[0].toUpperCase()).join("");

  return (
    <div data-theme="privat" className="min-h-dvh flex flex-col bg-paper text-ink">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-full focus:bg-ink focus:text-white">{tc("chrome.skip")}</a>
      <AudienceSwitch current="privat" />

      <header className="border-b-2 border-ink bg-paper">
        <div className={`${WRAP} min-h-[72px] py-3 flex flex-wrap items-center gap-3`}>
          <Link href="/privat" className="inline-flex items-center gap-2.5 min-h-11 text-ink no-underline" aria-label="Dialogbot Privat">
            <LogoMark size={36} />
            <span className="font-display font-extrabold text-[22px] tracking-[-0.3px]">Dialogbot</span>
            <span className="inline-flex items-center rounded-full bg-accent text-on-accent text-[12px] font-semibold uppercase tracking-[0.04em] px-2.5 py-[3px]">{t("brand.privat")}</span>
          </Link>
          <span className="flex-1" />
          <Link href={`/login?next=${encodeURIComponent(tryHref)}`} className="inline-flex items-center min-h-11 px-[18px] rounded-full border-2 border-ink bg-paper text-[15px] font-semibold text-ink no-underline hover:bg-panel">{t("landing.login")}</Link>
        </div>
      </header>

      <main id="main" className="flex-1 flex flex-col">
        {/* Hero */}
        <section className={`${WRAP} py-12 lg:py-14 flex flex-wrap items-center gap-10`}>
          <div className="flex-[1_1_320px] lg:flex-[1_1_420px] flex flex-col gap-[18px]">
            <p className="m-0 text-[12px] font-semibold uppercase tracking-[0.1em] text-accent">{t("landing.eyebrow")}</p>
            <h1 className="m-0 text-[clamp(40px,5.5vw,68px)] leading-[1.02] tracking-[-0.025em]">{t("landing.title")}</h1>
            <p className="m-0 text-[18px] leading-normal text-ink-soft max-w-[520px]">{t("landing.lead")}</p>
            <div className="flex flex-wrap items-center gap-3 mt-1.5">
              <Link href={tryHref} className={PILL_CTA}>{t("landing.cta")}</Link>
              <Link href="/privat/start" className="inline-flex items-center justify-center min-h-[48px] px-5 rounded-full border-2 border-ink bg-white text-[15px] font-semibold text-ink no-underline hover:bg-panel" data-funnel-entry>{t("funnel.entry")}</Link>
              <span className="text-[14px] text-muted">{t("landing.note")}</span>
            </div>
          </div>

          {/* Static demo card */}
          <div className="flex-[1_1_300px] lg:flex-[1_1_380px] w-full max-w-[520px] flex flex-col gap-3 rounded-[28px] border-2 border-ink bg-white p-5 sm:p-[22px] shadow-block" aria-label={t("landing.demo.badge")}>
            <div className="flex flex-wrap items-center gap-2.5 text-[13px] text-muted">
              <LogoMark size={32} />
              <span><strong className="text-ink">Peter</strong> · {t("landing.demo.role")}</span>
              <span className="ml-auto inline-flex items-center rounded-full border-2 border-ink bg-success-soft text-ink text-[11px] font-bold uppercase tracking-[0.08em] px-2.5 py-[3px]">{t("landing.demo.badge")}</span>
            </div>
            <div className="self-end max-w-[85%] bg-ink text-white rounded-[20px_20px_6px_20px] px-4 py-3 text-[15px] leading-[1.45]">{t("landing.demo.ask")}</div>
            <div className="self-start max-w-[90%] bg-panel border-2 border-ink rounded-[20px_20px_20px_6px] px-4 py-3 text-[15px] leading-[1.45]">
              {t("landing.demo.replyBefore")}<strong>{t("landing.demo.replyName")}</strong>{t("landing.demo.replyAfter")}
            </div>
            <div className="flex flex-wrap gap-2" aria-hidden="true">
              <span className="inline-flex items-center min-h-10 px-[18px] rounded-full border-2 border-ink bg-accent text-on-accent text-[14px] font-semibold">{t("landing.demo.yes")}</span>
              <span className="inline-flex items-center min-h-10 px-[18px] rounded-full border-2 border-ink bg-white text-[14px] font-semibold">{t("landing.demo.wait")}</span>
            </div>
            <div className="flex flex-wrap gap-1.5 pt-1" aria-hidden="true">
              <span className={CHIP}>{t("landing.demo.quickRemind")}</span>
              <span className={CHIP}>{t("landing.demo.quickList")}</span>
              <span className={CHIP}>{t("landing.demo.quickCall")}</span>
            </div>
            <div className="flex items-center gap-1.5 rounded-full border-2 border-ink bg-white p-[5px] pl-4">
              <label htmlFor="privat-demo" className="sr-only">{t("landing.demo.inputLabel")}</label>
              <input id="privat-demo" type="text" readOnly placeholder={t("landing.demo.placeholder")} className="flex-1 min-w-0 bg-transparent border-0 outline-0 text-[14px] text-ink placeholder:text-muted" />
              <span className="inline-flex items-center justify-center w-[38px] h-[38px] rounded-full border-2 border-ink bg-white text-ink shrink-0" aria-hidden="true"><Ico name="mic" size={18} /></span>
              <Link href={tryHref} className="inline-flex items-center gap-1 min-h-[38px] px-4 rounded-full border-2 border-ink bg-accent text-on-accent text-[14px] font-semibold no-underline hover:bg-accent-deep">{t("landing.demo.send")} <Ico name="arrow" size={16} stroke={2.6} /></Link>
            </div>
            <div className="flex items-center gap-2.5 rounded-[20px] border-2 border-ink bg-success-soft px-4 py-3 text-[15px] font-semibold">
              <Ico name="check" size={20} stroke={3} />
              <span>{t("landing.demo.done")}</span>
            </div>
          </div>
        </section>

        {/* Tre ting */}
        <section className="bg-panel border-y-2 border-ink py-14">
          <div className={`${WRAP} flex flex-col gap-7`}>
            <h2 className={H2}>{t("landing.three.title")}</h2>
            <div className="grid gap-5 md:grid-cols-3">
              {three.map((item, i) => (
                <article key={item.title} className="flex flex-col gap-2.5 rounded-[24px] border-2 border-ink bg-paper p-[22px]">
                  <span className={`inline-flex items-center justify-center w-11 h-11 rounded-full border-2 border-ink ${i === 2 ? "bg-accent text-on-accent" : "bg-white text-ink"}`} aria-hidden="true">
                    <Ico name={i === 0 ? "list" : i === 1 ? "bell" : "phone"} size={22} stroke={2.4} />
                  </span>
                  <h3 className="m-0 text-[20px] font-bold">{item.title}</h3>
                  <p className="m-0 text-[15px] leading-normal text-ink-soft">{item.text}</p>
                  <span className={`text-[13px] font-semibold ${i === 2 ? "text-accent" : "text-success"}`}>{i === 2 ? t("landing.three.includedTrial") : t("landing.three.included")}</span>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* Du bestemmer */}
        <section className={`${WRAP} py-14 flex flex-wrap items-center gap-10`}>
          <div className="flex-[1_1_300px] lg:flex-[1_1_360px] flex flex-col gap-3.5">
            <h2 className={H2}>{t("landing.control.title")}</h2>
            <p className="m-0 text-[17px] leading-normal text-ink-soft">{t("landing.control.text")}</p>
          </div>
          <ol className="flex-[1_1_300px] lg:flex-[1_1_380px] m-0 p-0 list-none flex flex-col gap-3">
            {steps.map((s, i) => (
              <li key={s} className="flex items-center gap-3.5 rounded-full border-2 border-ink bg-white py-2.5 pl-2.5 pr-[18px]">
                <span className={`inline-grid place-items-center w-9 h-9 shrink-0 rounded-full border-2 border-ink font-display font-extrabold ${i === 2 ? "bg-success-soft text-ink" : "bg-accent text-on-accent"}`}>{i + 1}</span>
                <span className="text-[16px] font-semibold">{s}</span>
              </li>
            ))}
          </ol>
        </section>

        {/* Butikken */}
        <section className="border-t-2 border-ink bg-white py-14">
          <div className={`${WRAP} flex flex-wrap items-center gap-9`}>
            <div className="flex-[1_1_300px] lg:flex-[1_1_340px] flex flex-col gap-3">
              <p className="m-0 text-[12px] font-semibold uppercase tracking-[0.1em] text-accent">{t("landing.store.eyebrow")}</p>
              <h2 className={H2}>{t("landing.store.title")}</h2>
              <p className="m-0 text-[17px] leading-normal text-ink-soft">{t("landing.store.text")}</p>
              <Link href="/privat/butik" className="self-start inline-flex items-center gap-1.5 min-h-12 px-[22px] rounded-full border-2 border-ink bg-white text-[15px] font-semibold text-ink no-underline hover:bg-panel">{t("landing.store.cta")} <Ico name="arrow" size={16} stroke={2.6} /></Link>
            </div>
            <ul className="flex-[1_1_300px] lg:flex-[1_1_440px] m-0 p-0 list-none grid grid-cols-[repeat(auto-fill,minmax(84px,1fr))] gap-x-2.5 gap-y-[18px] justify-items-center">
              {appTiles.map((a) => {
                const name = apps[a.key] ?? a.key;
                return (
                  <li key={a.key} className="min-w-[84px]">
                    <Link href="/privat/butik" className="flex flex-col items-center gap-2 text-ink no-underline">
                      <span className={`inline-grid place-items-center w-[68px] h-[68px] rounded-[20px] border-2 border-ink font-display font-extrabold text-[24px] shadow-[5px_5px_0_var(--color-ink)] ${a.bg} ${a.fg}`} aria-hidden="true">
                        {a.key === "more" ? "+" : initials(name)}
                      </span>
                      <span className="text-[13px] font-semibold text-center">{name}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        </section>

        {/* Priser */}
        <section id="priser" className="bg-ink text-white py-14">
          <div className={WRAP}><PublicPlans /></div>
        </section>

        {/* CTA */}
        <section className={`${WRAP} py-14 flex flex-col items-center gap-4 text-center`}>
          <h2 className={H2}>{t("landing.final.title")}</h2>
          <p className="m-0 text-[16px] text-ink-soft">{t("landing.final.text")}</p>
          <Link href={tryHref} className={PILL_CTA}>{t("landing.final.cta")}</Link>
        </section>
      </main>

      <footer className="border-t-2 border-ink py-5">
        <div className={`${WRAP} flex flex-wrap justify-center gap-x-7 gap-y-3 text-[13px] text-muted`}>
          <span className="inline-flex items-center min-h-8">{t("landing.footer.brand")}</span>
          <SiteLink href="/" className="inline-flex items-center gap-1 min-h-8 font-semibold text-ink no-underline hover:text-accent">{t("landing.footer.business")} <Ico name="arrow" size={14} stroke={2.6} /></SiteLink>
          <SiteLink href="/privatliv" className="inline-flex items-center min-h-8 text-ink no-underline hover:text-accent">{t("landing.footer.privacy")}</SiteLink>
          <SiteLink href="/vilkaar" className="inline-flex items-center min-h-8 text-ink no-underline hover:text-accent">{t("landing.footer.terms")}</SiteLink>
        </div>
      </footer>
    </div>
  );
}
