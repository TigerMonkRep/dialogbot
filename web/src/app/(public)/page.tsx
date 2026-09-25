import Link from "next/link";
import { Icon } from "@/components/ui";

/** P01 — public front page in the Stitch P04–P08 public style. Honest: only claims the product can back today;
 *  pricing, demo and help pages (P02–P09) are not linked until they exist. Product intent is carried into signup (A01). */
export default function Home() {
  const intents: [string, string, string, string][] = [
    ["reception", "support_agent", "Reception", "Telefon, webchat og bestilt callback besvaret af en assistent, der kun bruger jeres godkendte viden."],
    ["campaigns", "campaign", "Kampagner", "Udgående opfølgning i forudbetalte kontaktpakker. Betaling starter aldrig opkald."],
    ["both", "hub", "Begge dele", "Reception og kampagner i samme arbejdsrum med én fælles vidensbase."],
  ];
  const steps: [string, string, string, string, string[]][] = [
    ["01", "A06 · O01–O02", "Virksomhed & viden", "Opret arbejdsrummet, beskriv virksomheden og læg ydelser, priser og åbningstider ind. Det virker også uden hjemmeside.", ["Flere branchekategorier – også jeres egen", "Priser gemmes i hele øre, ekskl. moms", "Alt er kladder, indtil en ejer godkender"]],
    ["02", "O03 · O04", "Mål & sprog", "Vælg reception, kampagner eller begge. Planen tilpasser sig valget, og sprog styres på fire separate niveauer.", ["Callback hører under reception", "Booking kun hvis I vælger det", "Brugerflade, samtale, tilladte sprog og rapporter hver for sig"]],
    ["03", "G01 · G05", "Personlig plan", "Én næste handling ad gangen, ærlig fremdrift og servertjek, der bliver forældede, når konfigurationen ændres.", ["Gem og genoptag på enhver enhed", "Uafsluttede integrationer vises som ikke tilgængelige", "Aktivering er et særskilt, bevidst skridt"]],
  ];
  return (
    <div className="min-h-dvh bg-surface flex flex-col">
      <header className="sticky top-0 z-50 bg-surface/85 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.03)]">
        <div className="max-w-[1184px] mx-auto h-16 md:h-20 px-margin flex items-center justify-between gap-space-md">
          <Link href="/" className="flex items-center gap-space-sm">
            <span className="w-9 h-9 md:w-10 md:h-10 rounded-xl bg-primary-container flex items-center justify-center"><Icon name="support_agent" size={22} className="text-secondary-fixed" /></span>
            <span className="flex flex-col leading-tight"><span className="font-headline-sm text-headline-sm text-primary font-bold tracking-tight">Dialogbot</span><span className="hidden sm:block font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">Dansk AI-reception</span></span>
          </Link>
          <nav className="flex items-center gap-space-sm md:gap-space-lg" aria-label="Konto">
            <Link href="/login" className="px-space-sm py-2 font-label-lg text-label-lg text-primary hover:underline">Log ind</Link>
            <Link href="/signup" className="px-space-md md:px-space-lg py-2.5 rounded-lg bg-primary-container text-on-primary font-label-lg text-label-lg shadow-sm hover:bg-primary transition-colors">Start opsætning</Link>
          </nav>
        </div>
      </header>

      <main id="main" className="flex-1">
        {/* Hero */}
        <section className="max-w-[1184px] mx-auto px-margin pt-space-xl md:pt-margin-lg pb-margin-lg grid grid-cols-1 lg:grid-cols-12 gap-margin-lg items-center">
          <div className="lg:col-span-7 flex flex-col gap-space-lg">
            <span className="self-start inline-flex items-center gap-space-xs px-3 py-1 rounded-full bg-surface-container-high text-primary font-label-sm text-label-sm font-bold uppercase tracking-wider"><span className="w-1.5 h-1.5 rounded-full bg-secondary" />AI-reception for danske virksomheder</span>
            <h1 className="font-display-lg-mobile text-display-lg-mobile md:font-display-lg md:text-display-lg text-primary">Besvar henvendelser med den viden, I selv har godkendt</h1>
            <p className="font-body-lg text-body-lg text-on-surface-variant max-w-xl">Dialogbot bygges op omkring jeres ydelser, priser og åbningstider. Assistenten bruger kun godkendt viden – kladder og ændringer kræver altid en ejer eller administrator.</p>
            <div className="flex flex-col sm:flex-row gap-space-md">
              <Link href="/signup" className="px-space-xl py-3.5 rounded-xl bg-primary-container text-on-primary font-label-lg text-label-lg shadow-md hover:bg-primary transition-colors flex items-center justify-center gap-space-sm"><Icon name="bolt" size={20} />Start opsætning</Link>
              <a href="#trin" className="px-space-xl py-3.5 rounded-xl bg-surface-container-lowest text-primary font-label-lg text-label-lg shadow-sm hover:bg-surface-container-low transition-colors flex items-center justify-center gap-space-sm"><Icon name="format_list_numbered" size={20} />Se hvordan det virker</a>
            </div>
            <div className="flex flex-wrap gap-space-lg pt-space-md">
              <Trust icon="verified_user" title="Kun godkendt viden" text="Kladder bruges aldrig" />
              <Trust icon="public_off" title="Uden hjemmeside" text="Manuel opsætning er fuldgyldig" />
            </div>
          </div>
          <div className="lg:col-span-5">
            <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-xl flex flex-col gap-space-md">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5" aria-hidden><span className="w-3 h-3 rounded-full bg-error" /><span className="w-3 h-3 rounded-full bg-secondary-container" /><span className="w-3 h-3 rounded-full bg-secondary" /></span>
                <span className="px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm font-bold">Eksempel på opsætningen</span>
              </div>
              <Preview icon="menu_book" title="Viden godkendt" text="Ydelser, åbningstider og faste svar" badge="K05" />
              <Preview icon="route" title="Personlig plan" text="Én næste handling ad gangen" badge="G01" />
              <Preview icon="fact_check" title="Klarhedstjek" text="Beviser at profil, sprog og viden hænger sammen" badge="G05" />
              <p className="font-body-sm text-body-sm text-on-surface-variant">Telefoni, kalender og betaling tilkobles i senere milepæle og vises som ikke tilgængelige, indtil de virker.</p>
            </div>
          </div>
        </section>

        {/* Intent */}
        <section className="bg-surface-container-low">
          <div className="max-w-[1184px] mx-auto px-margin py-margin-lg flex flex-col gap-space-xl">
            <div className="text-center flex flex-col items-center gap-space-sm">
              <span className="px-3 py-1 rounded-full bg-surface-container-highest text-primary font-label-sm text-label-sm font-bold uppercase tracking-wider">Vælg udgangspunkt</span>
              <h2 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary">Hvad vil I starte med?</h2>
              <p className="font-body-md text-body-md text-on-surface-variant max-w-xl">Valget følger med gennem oprettelsen og kan ændres i opsætningen.</p>
            </div>
            <div className="grid gap-space-md md:grid-cols-3">
              {intents.map(([intent, icon, title, text]) => (
                <Link key={intent} href={`/signup?intent=${intent}`} className="group rounded-xl bg-surface-container-lowest p-space-xl shadow-sm hover:shadow-md transition-all flex flex-col gap-space-md">
                  <span className="w-11 h-11 rounded-xl bg-primary-container text-secondary-fixed flex items-center justify-center"><Icon name={icon} size={22} /></span>
                  <h3 className="font-headline-sm text-headline-sm text-primary font-bold">{title}</h3>
                  <p className="font-body-sm text-body-sm text-on-surface-variant flex-1">{text}</p>
                  <span className="font-label-lg text-label-lg text-secondary flex items-center gap-1">Kom i gang <Icon name="arrow_forward" size={18} className="group-hover:translate-x-0.5 transition-transform" /></span>
                </Link>
              ))}
            </div>
          </div>
        </section>

        {/* Steps */}
        <section id="trin" className="max-w-[1184px] mx-auto px-margin py-margin-lg flex flex-col gap-space-xl scroll-mt-24">
          <div className="text-center flex flex-col items-center gap-space-sm">
            <span className="px-3 py-1 rounded-full bg-surface-container-high text-primary font-label-sm text-label-sm font-bold uppercase tracking-wider">3 trin</span>
            <h2 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary">Fra virksomhedsviden til personlig plan</h2>
          </div>
          <ol className="grid gap-space-lg lg:grid-cols-3">
            {steps.map(([no, mod, title, text, points]) => (
              <li key={no} className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm flex flex-col gap-space-md">
                <div className="flex items-center gap-space-sm"><span className="px-2 py-0.5 rounded bg-primary-container text-on-primary font-mono text-label-sm font-bold">TRIN {no}</span><span className="font-mono text-label-sm text-on-surface-variant">{mod}</span></div>
                <h3 className="font-headline-md text-headline-md text-primary">{title}</h3>
                <p className="font-body-md text-body-md text-on-surface-variant">{text}</p>
                <ul className="flex flex-col gap-space-sm">{points.map((pt) => <li key={pt} className="flex items-start gap-space-sm font-body-sm text-body-sm text-on-surface"><Icon name="check_circle" size={20} className="text-secondary flex-shrink-0" />{pt}</li>)}</ul>
              </li>
            ))}
          </ol>
          <div className="self-center"><Link href="/signup" className="px-space-xl py-3.5 rounded-xl bg-primary-container text-on-primary font-label-lg text-label-lg shadow-md hover:bg-primary transition-colors flex items-center gap-space-sm"><Icon name="bolt" size={20} />Start opsætning</Link></div>
        </section>
      </main>

      <footer className="bg-surface-container-low">
        <div className="max-w-[1184px] mx-auto px-margin py-space-xl flex flex-col md:flex-row items-center justify-between gap-space-md font-body-sm text-body-sm text-on-surface-variant">
          <span className="flex items-center gap-space-sm"><span className="font-label-sm text-label-sm font-semibold uppercase tracking-wider text-primary">Dialogbot</span>•<span>AI-reception, callback og kampagner</span></span>
          <span>Priser, demo, hjælpecenter og vilkår udgives, når de er godkendt.</span>
        </div>
      </footer>
    </div>
  );
}

function Trust({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <div className="flex items-center gap-space-sm">
      <span className="w-9 h-9 rounded-lg bg-surface-container-high text-primary flex items-center justify-center"><Icon name={icon} size={20} /></span>
      <span className="flex flex-col"><span className="font-label-md text-label-md text-primary font-bold">{title}</span><span className="font-body-sm text-body-sm text-on-surface-variant">{text}</span></span>
    </div>
  );
}

function Preview({ icon, title, text, badge }: { icon: string; title: string; text: string; badge: string }) {
  return (
    <div className="p-space-md rounded-xl bg-surface-container-low flex items-center gap-space-md">
      <span className="w-10 h-10 rounded-lg bg-primary-container text-secondary-fixed flex items-center justify-center flex-shrink-0"><Icon name={icon} size={20} /></span>
      <span className="flex-1 min-w-0"><span className="block font-label-lg text-label-lg text-primary">{title}</span><span className="block font-body-sm text-body-sm text-on-surface-variant">{text}</span></span>
      <span className="font-mono text-label-sm text-on-surface-variant">{badge}</span>
    </div>
  );
}
