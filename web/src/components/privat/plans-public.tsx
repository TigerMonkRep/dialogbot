"use client";
import { useState } from "react";
import Link from "next/link";
import { useLocale, useT } from "@/i18n/client";
import { currencyFor, formatAmount, formatPrice } from "@/lib/markets";
import { plansFor, planCheckoutHref, type Plan, type PlanInterval } from "@/lib/privat/plans";
import { Mark } from "@/components/mark";

const Check = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden className="shrink-0 mt-px text-success"><path d="M5 12l5 5L20 7" /></svg>
);

/** Monthly/yearly toggle and the three plan cards on the public /privat page (section "14 dage gratis. Så vælger du
 *  selv."). Reads the catalogue of the language's market from lib/privat/plans.ts (DKK, SEK, NOK or EUR); every CTA goes to /privat/konto?plan=…&interval=…, where the
 *  app handles login and Stripe Checkout. Texts: privat.json → landing.pricing.*. */
export function PublicPlans() {
  const t = useT("privat");
  const locale = useLocale();
  const [interval, setInterval] = useState<PlanInterval>("month");
  const yearly = interval === "year";
  const plans = plansFor(currencyFor(locale));
  const fmt = (minor: number) => formatPrice(minor, plans[0].currency, locale);
  const num = (minor: number) => formatAmount(minor, locale);
  const seg = (v: PlanInterval, label: string) => {
    const active = interval === v;
    return (
      <button type="button" role="radio" aria-checked={active} onClick={() => setInterval(v)}
        className={`min-h-10 px-4 sm:px-[18px] rounded-full text-[14px] font-semibold whitespace-nowrap transition-colors ${active ? "bg-white text-ink" : "text-white hover:bg-white/10"}`}>
        {label}
      </button>
    );
  };
  return (
    <div className="flex flex-col gap-7">
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div className="flex flex-col gap-2.5 max-w-[620px]">
          <h2 className="m-0 text-[clamp(28px,3.2vw,40px)] leading-[1.05] tracking-[-0.02em]">{t("landing.pricing.title.before")}<Mark kind="ring" tone="yellow">{t("landing.pricing.title.mark")}</Mark>{t("landing.pricing.title.after")}</h2>
          <p className="m-0 text-[16px] leading-normal opacity-85">{t("landing.pricing.text")}</p>
        </div>
        <div role="radiogroup" aria-label={t("landing.pricing.intervalLabel")} className="inline-flex gap-1 p-1 rounded-full border-2 border-white bg-white/5">
          {seg("month", t("landing.pricing.monthly"))}
          {seg("year", t("landing.pricing.yearly"))}
        </div>
      </div>
      <div className="grid gap-6 pt-3 md:grid-cols-3 text-ink">
        {plans.map((p) => <PlanCard key={p.key} plan={p} yearly={yearly} t={t} fmt={fmt} num={num} />)}
      </div>
      <p className="m-0 text-[13px] opacity-70">{t("landing.pricing.note")}</p>
    </div>
  );
}

function PlanCard({ plan, yearly, t, fmt, num }: { plan: Plan; yearly: boolean; t: ReturnType<typeof useT>; fmt: (m: number) => string; num: (m: number) => string }) {
  const price = yearly ? plan.yearlyMonthlyMinor : plan.monthlyMinor;
  const rec = plan.recommended;
  const feature = (key: string) => {
    if (key === "calls") return t("landing.pricing.features.calls", { n: plan.calls });
    if (key === "people") return t("landing.pricing.features.people", { n: plan.people });
    return t(`landing.pricing.features.${key}`);
  };
  return (
    <article className={`relative flex flex-col gap-3 rounded-[24px] border-2 p-6 ${rec ? "border-accent bg-panel shadow-[8px_8px_0_var(--color-accent)]" : "border-ink bg-white shadow-block"}`}>
      {rec && (
        <span className="absolute -top-3.5 left-6 inline-flex items-center rounded-full border-2 border-ink bg-accent text-on-accent text-[12px] font-bold uppercase tracking-[0.06em] px-3 py-1">
          {t("landing.pricing.recommended")}
        </span>
      )}
      <h3 className="m-0 text-[22px] leading-tight">{plan.name}</h3>
      <p className="m-0 text-[14px] text-ink-soft min-h-[42px]">{t(`landing.pricing.tagline.${plan.key}`)}</p>
      <div className="flex items-baseline gap-1">
        <span className="font-display font-extrabold text-[40px] leading-none tracking-[-0.02em]">{t("landing.pricing.price", { num: num(price), price: fmt(price) })}</span>
        <span className="text-[14px] text-muted">{t("landing.pricing.perMonth")}</span>
      </div>
      <span className="text-[12px] text-muted min-h-4">
        {yearly ? t("landing.pricing.billedYearly", { amount: fmt(plan.yearlyTotalMinor) }) : t("landing.pricing.billedMonthly")}
      </span>
      <ul className="m-0 p-0 list-none flex flex-col gap-2 text-[14px]">
        {plan.features.map((f) => <li key={f} className="flex gap-2 items-start"><Check /><span>{feature(f)}</span></li>)}
      </ul>
      <Link href={planCheckoutHref(plan.key, yearly ? "year" : "month")}
        className={`mt-auto inline-flex items-center justify-center min-h-[50px] rounded-full border-2 border-ink text-[15px] font-semibold no-underline ${rec ? "bg-accent text-on-accent hover:bg-accent-deep" : "bg-white text-ink hover:bg-panel"}`}>
        {t("landing.pricing.cta")}
      </Link>
    </article>
  );
}
