import Link from "next/link";
import { Icon } from "@/components/ui";
import { IndustrySwitcher } from "./industries";

/** P01 — front page (Stitch "p01_dialogbot_forside", desktop + mobile).
 *  Honesty: a preview banner says what is not built yet; conversations are labelled as examples; no invented
 *  company facts, metrics or links to pages that do not exist. Product intent is carried into signup. */
export default function Home() {
  const transcript: [boolean, string][] = [
    [true, "Jeg vil gerne have et tilbud på gulvafslibning."],
    [false, "Selvfølgelig. Hvor stort er arealet?"],
    [true, "Cirka 65 m². Kan I komme forbi på onsdag?"],
    [false, "Der er en tid onsdag kl. 10.30. Skal jeg booke den til dig?"],
    [true, "Ja tak."],
  ];
  const faq: [string, string][] = [
    ["Kan jeg beholde mit eksisterende telefonnummer?", "Det er planen: I viderestiller jeres nuværende nummer til Dialogbot, når I er optaget eller har lukket, og beholder jeres teleudbyder. Telefoni er under udvikling og kan ikke tilkobles endnu."],
    ["Kan Dialogbot bruge min kalender?", "Kalenderforbindelse til Google og Microsoft er planlagt. Indtil den findes, vises den som ikke tilgængelig i opsætningen, og der bookes intet automatisk."],
    ["Kan jeg godkende svar og manuskript først?", "Ja. Al viden starter som kladde og bliver først brugt, når en ejer eller administrator har godkendt den. Det virker allerede i dag i videnscentret."],
    ["Hvad sker der, hvis assistenten ikke kender svaret?", "Den gætter ikke. Assistenten svarer kun ud fra godkendt viden og siger ærligt, når noget ikke fremgår, så en medarbejder kan følge op."],
    ["Kan den følge op på mine eksisterende tilbud?", "Kundeopfølgning i forudbetalte kontaktpakker er planlagt. Betaling starter aldrig opkald – I godkender altid listen og manuskriptet først."],
    ["Hvordan kommer jeg i gang?", "Opret en konto, beskriv virksomheden og læg ydelser, priser og åbningstider ind. En personlig plan viser én næste handling ad gangen – også uden hjemmeside."],
  ];
  const cta = (
    <>
      <Link href="/signup" className="inline-flex items-center justify-center gap-space-xs bg-secondary-fixed hover:bg-secondary-fixed-dim text-on-secondary-fixed font-label-lg text-label-lg px-gutter-lg py-space-md rounded-xl shadow-md transition-all"><Icon name="bolt" size={20} />Start opsætning</Link>
      <a href="#trin" className="inline-flex items-center justify-center gap-space-xs bg-surface-container-highest/20 hover:bg-surface-container-highest/30 text-on-primary font-label-lg text-label-lg px-gutter-lg py-space-md rounded-xl transition-all">Sådan fungerer det<Icon name="arrow_forward" size={18} /></a>
    </>
  );
  return (
    <div className="min-h-dvh bg-surface flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-space-md focus:py-2 focus:rounded-lg focus:bg-primary focus:text-on-primary">Spring til indhold</a>
      <header className="sticky top-0 z-50 bg-surface/90 backdrop-blur-xl shadow-[0_1px_8px_rgba(22,78,67,0.06)]">
        <div className="h-16 lg:h-20 max-w-7xl mx-auto px-4 sm:px-margin-md lg:px-margin-lg flex items-center justify-between gap-space-lg">
          <div className="flex items-center gap-space-lg">
            <Link href="/" className="flex items-center gap-space-sm">
              <span className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-on-primary shadow-sm"><Icon name="support_agent" size={20} /></span>
              <span className="font-headline-sm text-headline-sm text-primary tracking-tight font-bold">Dialogbot</span>
            </Link>
            <nav className="hidden lg:flex items-center gap-space-lg ml-space-md" aria-label="Sektioner">
              {[["#spor", "Løsninger"], ["#trin", "Sådan fungerer det"], ["#faq", "Spørgsmål"]].map(([h, l]) => <a key={h} href={h} className="font-label-lg text-label-lg text-on-surface-variant hover:text-on-surface transition-colors">{l}</a>)}
            </nav>
          </div>
          <div className="flex items-center gap-space-sm sm:gap-space-md">
            <Link href="/login" className="hidden sm:inline-flex font-label-lg text-label-lg text-on-surface-variant hover:text-on-surface px-space-md py-space-sm rounded-lg hover:bg-surface-container transition-colors">Log ind</Link>
            <Link href="/signup" className="hidden sm:inline-flex items-center justify-center bg-primary hover:bg-primary-container text-on-primary font-label-lg text-label-lg px-gutter-lg py-space-sm rounded-lg transition-all shadow-[0_2px_4px_rgba(22,78,67,0.12)]">Start opsætning</Link>
            <Link href="/login" aria-label="Log ind" className="sm:hidden w-9 h-9 rounded-full bg-primary flex items-center justify-center text-on-primary"><Icon name="person" size={20} /></Link>
          </div>
        </div>
        <p className="bg-secondary-fixed text-on-secondary-fixed font-label-sm text-label-sm text-center px-4 py-1.5">
          <strong>Privat preview.</strong> Telefoni, webchat, kalender og kampagner er under udvikling – eksemplerne viser, hvad Dialogbot bygges til.
        </p>
      </header>

      <main id="main" className="flex-1">
        {/* 1. Hero */}
        <section className="relative bg-primary text-on-primary overflow-hidden pt-8 pb-12 lg:pt-16 lg:pb-28">
          <div aria-hidden className="absolute inset-0 pointer-events-none opacity-25">
            <div className="absolute -top-32 -left-20 w-96 h-96 rounded-full bg-secondary blur-3xl" />
            <div className="absolute top-1/2 -right-32 w-[520px] h-[520px] rounded-full bg-primary-container blur-3xl" />
          </div>
          <div className="relative max-w-7xl mx-auto px-4 sm:px-margin-md lg:px-margin-lg grid grid-cols-1 lg:grid-cols-12 gap-space-xl lg:gap-gutter-lg items-center">
            <div className="lg:col-span-6 flex flex-col gap-space-lg">
              <span className="inline-flex items-center gap-space-xs self-start px-space-md py-space-xs rounded-full bg-secondary/20 text-secondary-fixed font-label-sm text-label-sm"><span className="w-2 h-2 rounded-full bg-secondary-fixed animate-pulse" />AI-reception og kundeopfølgning</span>
              <div className="flex flex-col gap-space-sm">
                <h1 className="font-display-lg-mobile text-display-lg-mobile md:font-display-lg md:text-display-lg font-bold text-on-primary tracking-tight">Du driver forretningen.<br /><span className="text-secondary-fixed">Dialogbot tager samtalen.</span></h1>
                <p className="font-body-md text-body-md md:font-body-lg md:text-body-lg text-on-primary-container max-w-xl">Besvar opkald og chat, hjælp kunder med at booke, og følg op på tilbud — med en AI-assistent, der bruger din virksomheds viden og følger dine regler.</p>
              </div>
              <div className="flex flex-col sm:flex-row sm:flex-wrap gap-space-md">{cta}</div>
              <span className="flex items-center gap-space-sm font-label-sm text-label-sm text-on-primary-container/80"><Icon name="verified" size={16} className="text-secondary-fixed" />Din viden • Din tone • Dine spilleregler</span>
            </div>
            <div className="lg:col-span-6">
              <div className="bg-surface-container-lowest text-on-surface rounded-xl p-space-md lg:p-space-lg shadow-xl flex flex-col gap-space-md">
                <div className="flex items-center gap-space-xs"><span className="w-2.5 h-2.5 rounded-full bg-secondary" /><span className="font-label-sm text-label-sm text-on-surface-variant font-semibold uppercase tracking-wider">Eksempel på en samtale • Fjord Gulvservice</span></div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
                  <div className="bg-surface-container-low rounded-lg p-space-md flex flex-col gap-space-sm">
                    <span className="font-label-sm text-label-sm text-primary font-semibold flex items-center gap-1"><Icon name="record_voice_over" size={15} />Transskription</span>
                    <ol className="flex flex-col gap-space-xs font-body-sm text-body-sm">
                      {transcript.map(([customer, t], i) => (
                        <li key={i} className={`flex flex-col gap-0.5 ${customer ? "items-end" : "items-start"}`}>
                          <span className="font-label-sm text-[10px] text-on-surface-variant">{customer ? "Kunde" : "Dialogbot"}</span>
                          <span className={`px-space-sm py-1.5 rounded-lg max-w-[90%] ${customer ? "bg-primary text-on-primary rounded-tr-none" : "bg-surface-container-lowest text-on-surface rounded-tl-none shadow-sm"}`}>{t}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                  <div className="bg-surface-container-highest/60 rounded-lg p-space-md flex flex-col justify-between gap-space-sm">
                    <div className="flex flex-col gap-space-sm">
                      <span className="self-start inline-flex items-center gap-1 px-space-sm py-0.5 rounded-full bg-secondary-fixed text-on-secondary-fixed font-label-sm text-label-sm"><Icon name="check_circle" size={15} filled />Besigtigelse foreslået</span>
                      <div className="bg-surface-container-lowest rounded-lg p-space-sm shadow-sm">
                        <span className="flex items-center gap-space-xs text-primary font-label-lg text-label-lg font-bold"><Icon name="calendar_month" size={18} />Onsdag kl. 10.30 – 11.15</span>
                      </div>
                      <dl className="flex flex-col gap-1.5 font-body-sm text-body-sm bg-surface-container-lowest/80 rounded-lg p-space-sm">
                        <div className="flex justify-between gap-2"><dt className="text-on-surface-variant">Opgave:</dt><dd className="font-semibold">65 m² gulv</dd></div>
                        <div className="flex justify-between gap-2"><dt className="text-on-surface-variant">Pris (godkendt viden):</dt><dd className="font-semibold">145 kr./m²</dd></div>
                      </dl>
                    </div>
                    <p className="font-body-sm text-[11px] leading-tight text-on-surface-variant bg-surface-container-lowest/50 p-2 rounded flex gap-1"><Icon name="info" size={13} />Illustration – ingen rigtige opkald eller bookinger.</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 2. Two tracks */}
        <section id="spor" className="py-14 lg:py-28 scroll-mt-28">
          <div className="max-w-7xl mx-auto px-4 sm:px-margin-md lg:px-margin-lg">
            <SectionHead tag="To spor • Én assistent" title="Tag imod nye kunder. Følg op på de eksisterende." text="To spor, der deler samme virksomhedsviden og regler." />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg lg:gap-gutter-lg items-stretch">
              <Track chip="Indgående henvendelser" chipCls="bg-surface-container text-primary" icon="call_received" title="Når kunden ringer, mens du er optaget." text="Dialogbot tager imod henvendelsen, stiller de relevante spørgsmål og hjælper kunden videre. Du får behov, kontaktoplysninger og næste handling samlet." href="/signup?intent=reception" link="Start med reception">
                <span className="font-label-sm text-label-sm text-on-surface-variant font-semibold uppercase tracking-wider">3 kanaler → én samlet indbakke</span>
                <div className="grid grid-cols-3 gap-space-xs">
                  {[["call", "Telefon"], ["chat", "Webchat"], ["ring_volume", "Callback"]].map(([i, l]) => <div key={l} className="bg-surface-container-lowest rounded-lg p-space-sm text-center flex flex-col items-center gap-1 shadow-sm"><Icon name={i} size={20} className="text-primary" /><span className="font-label-sm text-label-sm text-on-surface">{l}</span></div>)}
                </div>
              </Track>
              <Track chip="Udgående opfølgning" chipCls="bg-secondary-container text-on-secondary-fixed" icon="outbox" title="Tilbud sendt. Samtalen behøver ikke stoppe der." text="Vælg kontakter, tilpas samtalen og godkend forløbet. Dialogbot følger op og samler svarene, så du kan tage næste skridt." href="/signup?intent=campaigns" link="Start med kundeopfølgning">
                <span className="font-label-sm text-label-sm text-on-surface-variant font-semibold uppercase tracking-wider">Forløb</span>
                <ol className="grid grid-cols-2 md:grid-cols-4 gap-space-xs">
                  {["Udvalgte kontakter", "Godkendt manus", "Høflig samtale", "Klart resultat"].map((l, i) => <li key={l} className="bg-surface-container-lowest rounded-lg p-2 flex flex-col gap-1 shadow-sm"><span className="text-[10px] font-bold text-secondary">0{i + 1}</span><span className="font-label-sm text-label-sm font-semibold text-on-surface">{l}</span></li>)}
                </ol>
              </Track>
            </div>
          </div>
        </section>

        {/* 3. Industries */}
        <section className="py-14 lg:py-20 bg-surface-container-low">
          <div className="max-w-7xl mx-auto px-4 sm:px-margin-md lg:px-margin-lg">
            <SectionHead tag="Bred anvendelighed" title="Samme assistent. Forskellige arbejdsdage." text="Indhold og spørgsmål tilpasses din virksomheds fagsprog og regler." />
            <IndustrySwitcher />
          </div>
        </section>

        {/* 4. Steps + control */}
        <section id="trin" className="py-14 lg:py-28 scroll-mt-28">
          <div className="max-w-7xl mx-auto px-4 sm:px-margin-md lg:px-margin-lg">
            <SectionHead tag="Gennemskuelig proces" title="Fra din virksomheds viden til den første samtale." text="En personlig opsætningsguide hjælper dig videre trin for trin." />
            <ol className="grid grid-cols-1 md:grid-cols-3 gap-space-md md:gap-gutter-lg mb-10 lg:mb-12">
              {[["Fortæl om din virksomhed", "Læg ydelser, priser og åbningstider ind manuelt. Det virker også uden hjemmeside – ingen webcrawler, der gætter forkert.", "edit_note", "Manuel opsætning er fuldgyldig"],
                ["Gennemgå og godkend", "Al viden er kladde, indtil en ejer eller administrator godkender den. Kun godkendt viden bruges af assistenten.", "rule", "Fuld kontrol over tilladte svar"],
                ["Prøv den, før du slår til", "Stil assistenten spørgsmål i en intern test, før den taler med en eneste kunde.", "play_circle", "Intern test i videnscentret"]].map(([t, d, i, f], n) => (
                <li key={t} className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm flex flex-col gap-space-md">
                  <span className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-primary font-bold font-headline-sm">{n + 1}</span>
                  <h3 className="font-headline-sm text-headline-sm font-bold text-on-surface">{t}</h3>
                  <p className="font-body-md text-body-md text-on-surface-variant">{d}</p>
                  <span className="mt-auto flex items-center gap-space-xs text-[12px] font-medium text-secondary"><Icon name={i} size={16} />{f}</span>
                </li>
              ))}
            </ol>
            <div className="bg-primary text-on-primary rounded-xl p-space-lg lg:p-margin-lg shadow-md grid grid-cols-1 lg:grid-cols-12 gap-space-lg lg:gap-gutter-lg items-center">
              <div className="lg:col-span-5 flex flex-col gap-space-xs">
                <span className="text-secondary-fixed font-label-sm text-label-sm font-semibold uppercase tracking-wider">Tryghed</span>
                <h3 className="font-headline-md text-headline-md font-bold text-on-primary">Du bestemmer, hvad Dialogbot må sige og gøre.</h3>
                <p className="font-body-md text-body-md text-on-primary-container">Assistenten er afgrænset til den viden og de regler, virksomheden har godkendt.</p>
              </div>
              <ul className="lg:col-span-7 flex flex-col gap-space-sm">
                {[["Godkendt virksomhedsviden", "Assistenten svarer kun ud fra oplysninger, som en ejer eller administrator har godkendt."],
                  ["Aftalte regler", "Åbningstider, priser og tilbud gælder præcis som godkendt – kladder bruges aldrig."],
                  ["Ærlig om det ukendte", "Står svaret ikke i den godkendte viden, siger assistenten det og overlader sagen til jer."]].map(([t, d]) => (
                  <li key={t} className="flex items-start gap-space-sm bg-primary-container/40 p-space-md rounded-lg"><Icon name="check_circle" size={22} filled className="text-secondary-fixed mt-0.5" /><span className="flex flex-col gap-0.5"><span className="font-label-lg text-label-lg font-semibold text-on-primary">{t}</span><span className="font-body-sm text-body-sm text-on-primary-container">{d}</span></span></li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* 5. Outcome */}
        <section className="py-14 lg:py-28 bg-surface-container-low">
          <div className="max-w-7xl mx-auto px-4 sm:px-margin-md lg:px-margin-lg">
            <SectionHead tag="Overblik" title="Samtalen slutter. Dit overblik begynder." text="Se, hvem der henvendte sig, hvad de har brug for, og hvad næste skridt er — uden at lytte optagelser igennem." />
            <div className="max-w-3xl mx-auto bg-surface-container-lowest rounded-xl p-space-md sm:p-space-lg lg:p-margin-lg shadow-md flex flex-col gap-space-md">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm">
                <div className="flex items-center gap-space-sm">
                  <span className="w-10 h-10 rounded-full bg-surface-container flex items-center justify-center text-primary font-bold">HV</span>
                  <span><span className="font-label-lg text-label-lg font-bold text-on-surface block">Henrik (eksempel)</span><span className="font-body-sm text-body-sm text-on-surface-variant">Hellerup</span></span>
                </div>
                <span className="self-start sm:self-auto px-space-sm py-1 rounded bg-secondary-container text-on-secondary-fixed font-label-sm text-label-sm font-semibold">Klar til overdragelse</span>
              </div>
              <div className="bg-surface-container-low rounded-lg p-space-md flex flex-col gap-space-xs">
                <span className="font-label-sm text-label-sm font-semibold text-primary uppercase tracking-wider">Sammenfatning af behov</span>
                <p className="font-body-md text-body-md text-on-surface">Kunden ønsker afslibning af 65 m² fyrretræsgulv med hvidpigmenteret lak og kender den vejledende pris på 145 kr./m².</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
                <div className="bg-surface-container rounded-lg p-space-sm flex flex-col gap-1"><span className="font-label-sm text-label-sm font-semibold text-primary">Aftalt:</span><p className="font-body-sm text-body-sm text-on-surface">Besigtigelse onsdag kl. 10.30–11.15.</p></div>
                <div className="bg-surface-container rounded-lg p-space-sm flex flex-col gap-1"><span className="font-label-sm text-label-sm font-semibold text-primary">Næste opgave:</span><p className="font-body-sm text-body-sm text-on-surface">Tjek parkeringsforhold før ankomst.</p></div>
              </div>
              <p className="flex items-center gap-space-xs font-body-sm text-body-sm text-on-surface-variant"><Icon name="info" size={18} className="text-secondary" />Illustration af det overblik, vi bygger.</p>
            </div>
          </div>
        </section>

        {/* 6. FAQ */}
        <section id="faq" className="py-14 lg:py-28 scroll-mt-28">
          <div className="max-w-4xl mx-auto px-4 sm:px-margin-md lg:px-margin-lg">
            <SectionHead tag="Spørgsmål & svar" title="Ofte stillede spørgsmål" text="Hvad der virker i dag, og hvad der er på vej." />
            <div className="flex flex-col gap-space-sm">
              {faq.map(([q, a]) => (
                <details key={q} className="group bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
                  <summary className="cursor-pointer list-none p-space-md lg:p-space-lg flex items-center justify-between gap-space-md hover:bg-surface-container-low/50 transition-colors">
                    <span className="font-label-lg text-label-lg sm:font-headline-sm sm:text-headline-sm text-on-surface font-semibold">{q}</span>
                    <Icon name="expand_more" size={24} className="text-primary transition-transform group-open:rotate-180" />
                  </summary>
                  <p className="px-space-md pb-space-lg lg:px-space-lg font-body-md text-body-md text-on-surface-variant">{a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* 7. Final CTA */}
        <section className="pb-14 lg:pb-28">
          <div className="max-w-7xl mx-auto px-4 sm:px-margin-md lg:px-margin-lg">
            <div className="relative bg-primary text-on-primary rounded-2xl p-space-lg lg:p-20 shadow-xl overflow-hidden text-center flex flex-col items-center">
              <div aria-hidden className="absolute -top-24 -left-24 w-80 h-80 rounded-full bg-secondary opacity-10 blur-3xl pointer-events-none" />
              <div className="relative max-w-2xl flex flex-col items-center gap-space-md">
                <span className="px-space-sm py-1 rounded-full bg-secondary-fixed/20 text-secondary-fixed font-label-sm text-label-sm font-semibold">Klar til at komme i gang?</span>
                <h2 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg font-bold text-on-primary tracking-tight">Byg din assistent på din egen viden.</h2>
                <p className="font-body-md text-body-md md:font-body-lg md:text-body-lg text-on-primary-container">Opret arbejdsrummet, læg jeres viden ind, og test assistenten internt.</p>
                <div className="flex flex-col sm:flex-row gap-space-md pt-space-sm w-full sm:w-auto">{cta}</div>
                <p className="text-on-primary-container/80 font-label-sm text-label-sm">To prismodeller: fast abonnement på 1.495 kr./md. uden leadgebyr, eller 149 kr. pr. godkendt lead. Priser ekskl. moms.</p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="bg-surface-container-low shadow-[0_-1px_0_rgba(220,227,220,0.6)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-margin-md lg:px-margin-lg py-space-xl flex flex-col md:flex-row items-center justify-between gap-space-md font-body-sm text-body-sm text-on-surface-variant">
          <span className="flex items-center gap-space-sm"><span className="font-label-sm text-label-sm font-semibold uppercase tracking-wider text-primary">Dialogbot</span>•<span>AI-reception og kundeopfølgning</span></span>
          <nav className="flex items-center gap-space-md" aria-label="Konto"><Link href="/privatliv" className="hover:text-on-surface">Privatliv</Link><Link href="/login" className="hover:text-on-surface">Log ind</Link><Link href="/signup" className="hover:text-on-surface">Opret konto</Link></nav>
        </div>
      </footer>
    </div>
  );
}

function SectionHead({ tag, title, text }: { tag: string; title: string; text: string }) {
  return (
    <div className="flex flex-col sm:items-center sm:text-center max-w-2xl mx-auto mb-8 lg:mb-16">
      <span className="text-secondary font-label-sm text-label-sm uppercase tracking-wider mb-space-xs font-semibold">{tag}</span>
      <h2 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg font-bold text-primary tracking-tight">{title}</h2>
      <p className="font-body-md text-body-md md:font-body-lg md:text-body-lg text-on-surface-variant mt-space-xs">{text}</p>
    </div>
  );
}

function Track({ chip, chipCls, icon, title, text, href, link, children }: { chip: string; chipCls: string; icon: string; title: string; text: string; href: string; link: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface-container-lowest rounded-xl p-space-md sm:p-space-lg lg:p-margin-lg shadow-sm flex flex-col justify-between gap-space-lg">
      <div className="flex flex-col gap-space-md">
        <div className="flex items-center justify-between"><span className={`px-space-sm py-1 rounded-full font-label-sm text-label-sm font-semibold ${chipCls}`}>{chip}</span><Icon name={icon} size={24} className="text-primary" /></div>
        <h3 className="font-headline-md text-headline-md font-bold text-on-surface">{title}</h3>
        <p className="font-body-md text-body-md text-on-surface-variant">{text}</p>
        <div className="bg-surface-container-low rounded-xl p-space-md flex flex-col gap-space-sm">{children}</div>
      </div>
      <Link href={href} className="self-start inline-flex items-center gap-space-xs text-primary font-label-lg text-label-lg font-bold hover:text-primary-container group">{link}<Icon name="arrow_forward" size={18} className="group-hover:translate-x-1 transition-transform" /></Link>
    </div>
  );
}
