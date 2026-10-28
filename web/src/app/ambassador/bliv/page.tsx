import Link from "next/link";
import { redirect } from "next/navigation";
import { Icon } from "@/components/ui";
import { StepNumber } from "@/components/lego";
import { backend, isLoggedIn } from "@/lib/api.server";
import { kr, pct, type Program } from "../shared";
import { ApplyForm } from "./form";

const btnPrimary = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-accent hover:bg-accent-deep text-white no-underline font-semibold text-[17px]";
const btnOutline = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-white border-2 border-ink text-ink no-underline font-semibold text-[17px] hover:bg-panel";

/** The programme page as a byggevejledning: what an ambassador earns, the three steps, the rules, and the sign-up
 *  form (after login). Design: design-reference/byggevejledning/Main.dc.html. */
export default async function JoinPage() {
  const program = await backend<Program>("/public/ambassadors/program");
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
  const example = 149_500;
  const firstMonth = Math.round(example / 2 * t.rate_bp / 10000);
  const restMonths = (t.months - 1) * Math.round(example * t.rate_bp / 10000);
  const steps: [string, string, string, string[]][] = [
    ["1", "Anbefal", "Svar på fire hurtige spørgsmål om reglerne, og del dit personlige link eller din kode med virksomheder, du kender. Er du under 18, godkender en forælder via e-mail.", ["Gratis konto", "Dit link og din kode"]],
    ["2", "De bliver kunde", `Virksomheden opretter sig via dit link og får ${pct(t.customer_discount_bp ?? 5000)} rabat på første måned. Du ser firmanavn og status – aldrig deres samtaler.`, ["Virksomhed der misser opkald"]],
    ["3", "Du får udbetalt", `${kr(t.bonus_minor)} når kunden har betalt første faktura, plus ${pct(t.rate_bp)} af det de betaler i ${t.months} måneder. Udbetales til din bankkonto.`, ["Bankkonto", "CPR eller CVR"]],
  ];
  const rules = [
    `Du tjener kun, når kunden har betalt. Beløbet står som "optjent" i ${t.hold_days ?? 30} dage og bliver derefter klar til udbetaling.`,
    `Vi udbetaler til din bankkonto, når du har mindst ${kr(t.min_payout_minor ?? 50000)} klar.`,
    "Uden CVR er bonussen B-indkomst: vi indberetter den til Skattestyrelsen med dit CPR-nummer, og du betaler selv skatten via forskudsopgørelsen. Vi trækker ikke skat.",
    "Har du CVR, får du et afregningsbilag i stedet (med moms, hvis du er momsregistreret).",
    `Du skal være mindst ${t.min_age ?? 15} år. Er du under 18, skal en forælder godkende aftalen, før vi udbetaler – du kan godt skaffe kunder imens.`,
    "Du ser dine kunders firmanavn, status og din bonus – aldrig deres samtaler eller kundedata.",
  ];
  const faq: [string, string][] = [
    ["Hvornår får jeg penge?", `Når din kunde har betalt sin første faktura, får du ${kr(t.bonus_minor)}. Beløbet står som optjent i ${t.hold_days ?? 30} dage og udbetales, når du har mindst ${kr(t.min_payout_minor ?? 50000)} klar.`],
    ["Skal jeg betale skat?", "Ja. Uden CVR er det B-indkomst, som vi indberetter til Skattestyrelsen – du betaler selv skatten via forskudsopgørelsen. Med CVR får du et afregningsbilag."],
    ["Må jeg være under 18?", `Ja, fra ${t.min_age ?? 15} år. En forælder skal godkende aftalen via e-mail, før vi udbetaler. Du kan godt dele dit link imens.`],
    ["Hvad må jeg ikke?", "Du skal altid skrive, at det er reklame, og at du får bonus. Ingen masse-mails eller -sms'er til folk, du ikke kender, og brug aldrig AI til at ringe folk op."],
  ];
  return (
    <div className="flex flex-col gap-10 md:gap-14">
      {/* Hero: ink card with yellow eyebrow and the earnings example as a parts box */}
      <section className="rounded-[20px] bg-ink text-white p-6 md:p-10 grid md:grid-cols-5 gap-8 items-center shadow-block">
        <div className="md:col-span-3 flex flex-col gap-4">
          <span className="text-[13px] font-semibold uppercase tracking-[1.5px] text-highlight">Dialogbot Ambassadør</span>
          <h1 className="m-0 font-display font-extrabold text-[clamp(32px,4.4vw,52px)] leading-[1.02] tracking-[-1px] text-white">Anbefal Dialogbot – og tjen penge på hver kunde</h1>
          <p className="m-0 text-[17px] leading-normal text-white/85 max-w-xl">Kender du en håndværker, en frisør eller en klinik, der misser opkald? Vis dem Dialogbot. Bliver de kunde, får du en startbonus og en løbende andel – og de får {pct(t.customer_discount_bp ?? 5000)} rabat på første måned.</p>
          <a href="#tilmeld" className="inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-highlight hover:bg-highlight-deep text-ink no-underline font-semibold text-[17px] self-start">Bliv ambassadør<Icon name="arrow_downward" size={20} /></a>
        </div>
        <div className="md:col-span-2 rounded-xl border-[1.5px] border-white/70 px-4 py-3.5 flex flex-col gap-2.5">
          <span className="text-[12px] font-semibold uppercase tracking-[0.12em] text-highlight">Sådan tjener du · én kunde på abonnement</span>
          <dl className="m-0 grid grid-cols-[1fr_auto] gap-y-1.5 gap-x-3 text-[15px] tabular-nums">
            <dt className="flex gap-2.5"><b className="font-display font-extrabold min-w-7">1×</b>Startbonus</dt><dd className="m-0 text-right">{kr(t.bonus_minor)}</dd>
            <dt className="flex gap-2.5"><b className="font-display font-extrabold min-w-7">1×</b>Første måned ({pct(t.rate_bp)} af {kr(example / 2)})</dt><dd className="m-0 text-right">{kr(firstMonth)}</dd>
            <dt className="flex gap-2.5"><b className="font-display font-extrabold min-w-7">{t.months - 1}×</b>Måneder à {pct(t.rate_bp)} af {kr(example)}</dt><dd className="m-0 text-right">{kr(restMonths)}</dd>
            <dt className="font-display font-extrabold text-[17px] pt-2 border-t border-white/30">I alt det første år</dt><dd className="m-0 text-right font-display font-extrabold text-[17px] pt-2 border-t border-white/30">{kr(t.bonus_minor + firstMonth + restMonths)}</dd>
          </dl>
          <p className="m-0 text-[13px] text-white/75">Med 10 kunder er det over 20.000 kr. Beløbene er før skat.</p>
        </div>
      </section>

      {/* The three steps */}
      <section aria-labelledby="trin" className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <span className="eyebrow text-[13px] tracking-[1.5px]">Sådan gør du</span>
          <h2 id="trin" className="m-0 font-display font-extrabold text-[clamp(28px,3.4vw,40px)] leading-[1.05] tracking-[-1px]">Tre trin – så er du i gang</h2>
        </div>
        <ol className="m-0 p-0 list-none grid md:grid-cols-3 gap-5">
          {steps.map(([n, title, text, parts]) => (
            <li key={n} className="rounded-[20px] border-2 border-ink bg-white p-6 flex flex-col gap-4">
              <div className="flex items-center gap-3.5"><StepNumber value={n} /><h3 className="m-0 font-display font-bold text-[22px] leading-[1.15]">{title}</h3></div>
              <div className="rounded-xl border-[1.5px] border-ink px-3.5 py-3 flex flex-col gap-2">
                <span className="eyebrow">Du skal bruge</span>
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
            <span className="eyebrow">Reglerne</span>
            <h2 id="regler" className="m-0 font-display font-extrabold text-[26px] leading-[1.1] tracking-[-0.5px]">Sådan fungerer det</h2>
          </div>
          <ul className="m-0 p-0 list-none flex flex-col gap-2.5 text-[15px] leading-normal text-ink">
            {rules.map((x) => <li key={x} className="flex gap-2.5"><Icon name="check" size={20} className="text-accent flex-shrink-0 mt-0.5" />{x}</li>)}
          </ul>
          <div className="rounded-xl border-[1.5px] border-ink bg-white p-4 flex flex-col gap-1.5">
            <p className="m-0 text-[13px] font-semibold text-ink flex items-center gap-1.5"><Icon name="gavel" size={18} className="text-accent" />Reglerne du siger ja til</p>
            <p className="m-0 text-[15px] leading-normal text-ink-soft">{program.rules_text}</p>
          </div>
        </section>

        <section aria-labelledby="bliv" className="lg:col-span-3 rounded-[20px] bg-white border-2 border-ink p-6 md:p-8 flex flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <span className="eyebrow">Tilmelding</span>
            <h2 id="bliv" className="m-0 font-display font-extrabold text-[26px] leading-[1.1] tracking-[-0.5px]">Bliv ambassadør</h2>
          </div>
          {!loggedIn || !me ? (
            <div className="flex flex-col gap-4">
              <p className="m-0 text-[17px] leading-normal text-ink-soft">Opret først en gratis konto (eller log ind). Så kommer du direkte tilbage hertil.</p>
              <div className="flex flex-wrap gap-3">
                <Link href="/signup?next=/ambassador/bliv" className={btnPrimary}><Icon name="person_add" size={20} />Opret konto</Link>
                <Link href="/login?next=/ambassador/bliv" className={btnOutline}>Log ind</Link>
              </div>
            </div>
          ) : !me.email_verified ? (
            <p className="m-0 text-[17px] leading-normal text-ink-soft">Bekræft din e-mail først – vi har sendt et link til {me.email}. <Link href="/verify-email" className="text-accent font-semibold underline underline-offset-4">Send nyt link</Link></p>
          ) : (
            <ApplyForm program={program} defaultName={me.display_name} />
          )}
        </section>
      </div>

      {/* FAQ */}
      <section aria-labelledby="faq" className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <span className="eyebrow text-[13px] tracking-[1.5px]">Spørgsmål</span>
          <h2 id="faq" className="m-0 font-display font-extrabold text-[clamp(28px,3.4vw,40px)] leading-[1.05] tracking-[-1px]">Det spørger ambassadører om</h2>
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
