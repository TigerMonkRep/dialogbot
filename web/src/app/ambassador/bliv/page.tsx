import type { Metadata } from "next";
import Link from "@/i18n/link";
import { redirect } from "next/navigation";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { alternatesFor } from "@/lib/site";
import { Icon } from "@/components/ui";
import { StepNumber } from "@/components/lego";
import { backend, isLoggedIn } from "@/lib/api.server";
import { kr, pct, type Program } from "../shared";
import { ApplyForm } from "./form";

const btnPrimary = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-accent hover:bg-accent-deep text-white no-underline font-semibold text-[17px]";
const btnOutline = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-white border-2 border-ink text-ink no-underline font-semibold text-[17px] hover:bg-panel";

export async function generateMetadata(): Promise<Metadata> {
  return { alternates: alternatesFor("/ambassador/bliv", await getLocale()) };
}

/** The programme page as a byggevejledning: what an ambassador earns, the three steps, the rules, and the sign-up
 *  form (after login). Design: design-reference/byggevejledning/Main.dc.html. */
export default async function JoinPage() {
  const program = await backend<Program>("/public/ambassadors/program");
  const [tr, raw] = await Promise.all([getT("landing.ambassador"), getRaw()]);
  const loggedIn = await isLoggedIn();
  let me: { email: string; display_name: string; email_verified: boolean } | null = null;
  if (loggedIn) {
    try {
      me = await backend("/auth/me");
      const amb = await backend<{ enrolled: boolean }>("/ambassador/me");
      if (amb.enrolled) redirect("/ambassador");
    } catch (e) {
      if ((e as { digest?: string }).digest?.startsWith("NEXT_REDIRECT")) throw e;
      me = null;
    }
  }
  const t = program.terms;
  const example = 249_500; // the subscription, 2.495 kr./md.
  const firstMonth = Math.round(example / 2 * t.rate_bp / 10000);  // the customer pays half the first month (welcome discount)
  const perMonth = Math.round(example * t.rate_bp / 10000);
  const restMonths = (t.months - 1) * perMonth;
  const firstYear = t.bonus_minor + firstMonth + restMonths;
  const steps: [string, string, string, string[]][] = [
    ["1", tr("steps.recommendTitle"), tr("steps.recommendText"), raw<string[]>("landing.ambassador.steps.recommendParts")],
    ["2", tr("steps.customerTitle"), tr("steps.customerText", { discount: pct(t.customer_discount_bp ?? 5000) }), raw<string[]>("landing.ambassador.steps.customerParts")],
    ["3", tr("steps.payoutTitle"), tr("steps.payoutText", { bonus: kr(t.bonus_minor), rate: pct(t.rate_bp), months: t.months }), raw<string[]>("landing.ambassador.steps.payoutParts")],
  ];
  const rules = [
    tr("rules.earned", { days: t.hold_days ?? 30 }),
    tr("rules.payoutMin", { amount: kr(t.min_payout_minor ?? 50000) }),
    tr("rules.tax"),
    tr("rules.cvr"),
    tr("rules.age", { age: t.min_age ?? 15 }),
    tr("rules.privacy"),
  ];
  const faq: [string, string][] = [
    [tr("faq.whenQ"), tr("faq.whenA", { bonus: kr(t.bonus_minor), days: t.hold_days ?? 30, amount: kr(t.min_payout_minor ?? 50000) })],
    [tr("faq.taxQ"), tr("faq.taxA")],
    [tr("faq.ageQ"), tr("faq.ageA", { age: t.min_age ?? 15 })],
    [tr("faq.rulesQ"), tr("faq.rulesA")],
  ];
  return (
    <div className="flex flex-col gap-10 md:gap-14">
      {/* Hero: ink card with yellow eyebrow and the earnings example as a parts box */}
      <section className="rounded-[20px] bg-ink text-white p-6 md:p-10 grid md:grid-cols-5 gap-8 items-center shadow-block overflow-hidden">
        <div className="md:col-span-3 min-w-0 flex flex-col gap-4">
          <span className="text-[13px] font-semibold uppercase tracking-[1.5px] text-highlight">{tr("join.eyebrow")}</span>
          <h1 className="m-0 font-display font-extrabold text-[clamp(32px,4.4vw,52px)] leading-[1.02] tracking-[-1px] text-white">{tr("join.title")}</h1>
          <p className="m-0 text-[17px] leading-normal text-white/85 max-w-xl">{tr("join.intro", { discount: pct(t.customer_discount_bp ?? 5000) })}</p>
          <a href="#tilmeld" className="inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-highlight hover:bg-highlight-deep text-ink no-underline font-semibold text-[17px] self-start">{tr("join.cta")}<Icon name="arrow_forward" size={20} /></a>
        </div>
        <div className="md:col-span-2 min-w-0 rounded-xl border-[1.5px] border-white/70 px-4 py-3.5 flex flex-col gap-2.5">
          <span className="text-[12px] font-semibold uppercase tracking-[0.12em] text-highlight">{tr("join.earnTitle")}</span>
          <dl className="m-0 grid grid-cols-[1fr_auto] gap-y-1.5 gap-x-3 text-[15px] tabular-nums">
            <dt className="flex gap-2.5"><b className="font-display font-extrabold min-w-7">1×</b>{tr("join.startBonus")}</dt><dd className="m-0 text-right">{kr(t.bonus_minor)}</dd>
            <dt className="flex gap-2.5"><b className="font-display font-extrabold min-w-7">1×</b>{tr("join.firstMonth", { rate: pct(t.rate_bp), amount: kr(example / 2) })}</dt><dd className="m-0 text-right">{kr(firstMonth)}</dd>
            <dt className="flex gap-2.5"><b className="font-display font-extrabold min-w-7">{t.months - 1}×</b>{tr("join.months", { perMonth: kr(perMonth), rate: pct(t.rate_bp), amount: kr(example) })}</dt><dd className="m-0 text-right">{kr(restMonths)}</dd>
            <dt className="font-display font-extrabold text-[17px] pt-2 border-t border-white/30">{tr("join.total")}</dt><dd className="m-0 text-right font-display font-extrabold text-[17px] pt-2 border-t border-white/30">{kr(firstYear)}</dd>
          </dl>
          <p className="m-0 text-[13px] text-white/75">{tr("join.tenCustomers", { amount: kr(firstYear * 10) })}</p>
        </div>
      </section>

      {/* The three steps */}
      <section aria-labelledby="trin" className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <span className="eyebrow text-[13px] tracking-[1.5px]">{tr("steps.eyebrow")}</span>
          <h2 id="trin" className="m-0 font-display font-extrabold text-[clamp(28px,3.4vw,40px)] leading-[1.05] tracking-[-1px]">{tr("steps.title")}</h2>
        </div>
        <ol className="m-0 p-0 list-none grid md:grid-cols-3 gap-5">
          {steps.map(([n, title, text, parts]) => (
            <li key={n} className="rounded-[20px] border-2 border-ink bg-white p-6 flex flex-col gap-4">
              <div className="flex items-center gap-3.5"><StepNumber value={n} /><h3 className="m-0 font-display font-bold text-[22px] leading-[1.15]">{title}</h3></div>
              <div className="rounded-xl border-[1.5px] border-ink px-3.5 py-3 flex flex-col gap-2">
                <span className="eyebrow">{tr("steps.needs")}</span>
                <ul className="m-0 p-0 list-none flex flex-col gap-1.5 text-[15px]">{parts.map((p) => <li key={p} className="flex gap-2.5"><b className="font-display font-extrabold min-w-7">1×</b>{p}</li>)}</ul>
              </div>
              <p className="m-0 text-[15px] leading-normal text-ink-soft">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* Rules + form */}
      <div id="tilmeld" className="grid lg:grid-cols-5 gap-6 lg:gap-8 items-start scroll-mt-6">
        <section aria-labelledby="regler" className="lg:col-span-2 rounded-[20px] bg-panel border-2 border-ink p-6 flex flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <span className="eyebrow">{tr("rules.eyebrow")}</span>
            <h2 id="regler" className="m-0 font-display font-extrabold text-[26px] leading-[1.1] tracking-[-0.5px]">{tr("rules.title")}</h2>
          </div>
          <ul className="m-0 p-0 list-none flex flex-col gap-2.5 text-[15px] leading-normal text-ink">
            {rules.map((x) => <li key={x} className="flex gap-2.5"><Icon name="check" size={20} className="text-accent flex-shrink-0 mt-0.5" />{x}</li>)}
          </ul>
          <div className="rounded-xl border-[1.5px] border-ink bg-white p-4 flex flex-col gap-1.5">
            <p className="m-0 text-[13px] font-semibold text-ink flex items-center gap-1.5"><Icon name="gavel" size={18} className="text-accent" />{tr("rules.agreeTitle")}</p>
            <p className="m-0 text-[15px] leading-normal text-ink-soft">{program.rules_text}</p>
          </div>
        </section>

        <section aria-labelledby="bliv" className="lg:col-span-3 rounded-[20px] bg-white border-2 border-ink p-6 md:p-8 flex flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <span className="eyebrow">{tr("signup.eyebrow")}</span>
            <h2 id="bliv" className="m-0 font-display font-extrabold text-[26px] leading-[1.1] tracking-[-0.5px]">{tr("signup.title")}</h2>
          </div>
          {!loggedIn || !me ? (
            <div className="flex flex-col gap-4">
              <p className="m-0 text-[17px] leading-normal text-ink-soft">{tr("signup.loginFirst")}</p>
              <div className="flex flex-wrap gap-3">
                <Link href="/signup?next=/ambassador/bliv" className={btnPrimary}><Icon name="person_add" size={20} />{tr("signup.createAccount")}</Link>
                <Link href="/login?next=/ambassador/bliv" className={btnOutline}>{tr("signup.login")}</Link>
              </div>
            </div>
          ) : !me.email_verified ? (
            <p className="m-0 text-[17px] leading-normal text-ink-soft">{tr("signup.verifyFirst", { email: me.email })}<Link href="/verify-email" className="text-accent font-semibold underline underline-offset-4">{tr("signup.resend")}</Link></p>
          ) : (
            <ApplyForm program={program} defaultName={me.display_name} />
          )}
        </section>
      </div>

      {/* FAQ */}
      <section aria-labelledby="faq" className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <span className="eyebrow text-[13px] tracking-[1.5px]">{tr("faq.eyebrow")}</span>
          <h2 id="faq" className="m-0 font-display font-extrabold text-[clamp(28px,3.4vw,40px)] leading-[1.05] tracking-[-1px]">{tr("faq.title")}</h2>
        </div>
        <div className="flex flex-col gap-3 max-w-3xl">
          {faq.map(([q, a]) => (
            <details key={q} className="group rounded-2xl border-2 border-ink bg-white open:bg-panel">
              <summary className="list-none cursor-pointer flex items-center justify-between gap-4 min-h-14 px-5 py-3 font-display font-bold text-[18px] [&::-webkit-details-marker]:hidden">{q}<Icon name="expand_more" size={24} className="flex-shrink-0 transition-transform group-open:rotate-180" /></summary>
              <p className="m-0 px-5 pb-5 text-[15px] leading-normal text-ink-soft">{a}</p>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
