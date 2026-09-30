import Link from "next/link";
import { redirect } from "next/navigation";
import { Icon } from "@/components/ui";
import { backend, isLoggedIn } from "@/lib/api.server";
import { kr, pct, type Program } from "../shared";
import { ApplyForm } from "./form";

/** The programme page: what an ambassador earns, the rules, and the sign-up form (after login). */
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
  const steps: [string, string, string][] = [
    ["person_add", "Tilmeld dig", "Svar på fire hurtige spørgsmål om reglerne. Er du under 18, godkender en forælder via e-mail."],
    ["link", "Del dit link", "Du får et personligt link og en kode. Vis Dialogbot til virksomheder, du kender."],
    ["payments", "Få bonus", `${kr(t.bonus_minor)} når kunden har betalt første faktura, plus ${pct(t.rate_bp)} af det de betaler i ${t.months} måneder.`],
  ];
  return (
    <div className="space-y-space-xl">
      <section className="rounded-2xl bg-primary text-on-primary p-space-lg md:p-space-xl grid md:grid-cols-5 gap-space-lg items-center">
        <div className="md:col-span-3 space-y-space-sm">
          <span className="font-label-sm text-label-sm font-bold uppercase tracking-wider text-secondary-fixed">Dialogbot Ambassadør</span>
          <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg tracking-tight">Anbefal Dialogbot – og tjen penge på hver kunde</h1>
          <p className="font-body-md text-body-md opacity-90 max-w-xl">Kender du en håndværker, en frisør eller en klinik, der misser opkald? Vis dem Dialogbot. Bliver de kunde, får du en startbonus og en løbende andel – og de får {pct(t.customer_discount_bp ?? 5000)} rabat på første måned.</p>
        </div>
        <div className="md:col-span-2 rounded-xl bg-primary-container p-space-md space-y-space-xs">
          <p className="font-label-sm text-label-sm uppercase tracking-wider text-secondary-fixed font-bold">Eksempel: én kunde på abonnement</p>
          <dl className="grid grid-cols-2 gap-y-1 font-body-sm text-body-sm tabular-nums">
            <dt>Startbonus</dt><dd className="text-right">{kr(t.bonus_minor)}</dd>
            <dt>Første måned ({pct(t.rate_bp)} af {kr(example / 2)})</dt><dd className="text-right">{kr(Math.round(example / 2 * t.rate_bp / 10000))}</dd>
            <dt>{t.months - 1} måneder à {pct(t.rate_bp)} af {kr(example)}</dt><dd className="text-right">{kr((t.months - 1) * Math.round(example * t.rate_bp / 10000))}</dd>
            <dt className="font-bold pt-1">I alt det første år</dt><dd className="text-right font-bold pt-1">{kr(t.bonus_minor + Math.round(example / 2 * t.rate_bp / 10000) + (t.months - 1) * Math.round(example * t.rate_bp / 10000))}</dd>
          </dl>
          <p className="font-label-sm text-label-sm opacity-80">Med 10 kunder er det over 20.000 kr. Beløbene er før skat.</p>
        </div>
      </section>

      <ol className="grid md:grid-cols-3 gap-space-md">
        {steps.map(([icon, title, text], i) => (
          <li key={title} className="rounded-xl bg-surface-container-lowest p-space-lg shadow-sm space-y-space-xs">
            <div className="flex items-center gap-space-sm"><span className="w-9 h-9 rounded-full bg-secondary-container text-on-secondary-container flex items-center justify-center"><Icon name={icon} size={20} /></span><span className="font-label-sm text-label-sm text-on-surface-variant">Trin {i + 1}</span></div>
            <h2 className="font-headline-sm text-headline-sm text-primary font-bold">{title}</h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant">{text}</p>
          </li>
        ))}
      </ol>

      <div className="grid lg:grid-cols-5 gap-space-lg items-start">
        <section className="lg:col-span-2 rounded-xl bg-surface-container-low p-space-lg space-y-space-md">
          <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Sådan fungerer det</h2>
          <ul className="space-y-space-sm font-body-sm text-body-sm text-on-surface">
            {[
              `Du tjener kun, når kunden har betalt. Beløbet står som "optjent" i ${t.hold_days ?? 30} dage og bliver derefter klar til udbetaling.`,
              `Vi udbetaler til din bankkonto, når du har mindst ${kr(t.min_payout_minor ?? 50000)} klar.`,
              "Uden CVR er bonussen B-indkomst: vi indberetter den til Skattestyrelsen med dit CPR-nummer, og du betaler selv skatten via forskudsopgørelsen. Vi trækker ikke skat.",
              "Har du CVR, får du et afregningsbilag i stedet (med moms, hvis du er momsregistreret).",
              `Du skal være mindst ${t.min_age ?? 15} år. Er du under 18, skal en forælder godkende aftalen, før vi udbetaler – du kan godt skaffe kunder imens.`,
              "Du ser dine kunders firmanavn, status og din bonus – aldrig deres samtaler eller kundedata.",
            ].map((x) => <li key={x} className="flex gap-space-xs"><Icon name="check_circle" size={18} className="text-secondary flex-shrink-0 mt-0.5" />{x}</li>)}
          </ul>
          <div className="rounded-lg bg-surface-container-lowest p-space-md space-y-space-xs">
            <p className="font-label-md text-label-md font-bold text-primary flex items-center gap-1"><Icon name="gavel" size={18} />Reglerne</p>
            <p className="font-body-sm text-body-sm text-on-surface-variant">{program.rules_text}</p>
          </div>
        </section>

        <section className="lg:col-span-3 rounded-xl bg-surface-container-lowest p-space-lg shadow-sm space-y-space-md">
          <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Bliv ambassadør</h2>
          {!loggedIn || !me ? (
            <div className="space-y-space-md">
              <p className="font-body-md text-body-md text-on-surface-variant">Opret først en gratis konto (eller log ind). Så kommer du direkte tilbage hertil.</p>
              <div className="flex flex-wrap gap-space-sm">
                <Link href="/signup?next=/ambassador/bliv" className="inline-flex items-center gap-space-xs bg-primary text-on-primary font-label-lg text-label-lg px-gutter-lg py-space-sm rounded-lg"><Icon name="person_add" size={18} />Opret konto</Link>
                <Link href="/login?next=/ambassador/bliv" className="inline-flex items-center gap-space-xs bg-surface-container-low text-primary font-label-lg text-label-lg px-gutter-lg py-space-sm rounded-lg">Log ind</Link>
              </div>
            </div>
          ) : !me.email_verified ? (
            <p className="font-body-md text-body-md text-on-surface-variant">Bekræft din e-mail først – vi har sendt et link til {me.email}. <Link href="/verify-email" className="underline text-primary">Send nyt link</Link></p>
          ) : (
            <ApplyForm program={program} defaultName={me.display_name} />
          )}
        </section>
      </div>
    </div>
  );
}
