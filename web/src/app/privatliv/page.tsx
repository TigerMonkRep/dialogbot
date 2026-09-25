import type { Metadata } from "next";
import Link from "next/link";
import { Icon } from "@/components/ui";

export const metadata: Metadata = { title: "Privatliv – venteliste | Dialogbot", description: "Sådan behandler Dialogbot oplysninger fra ventelisten." };

const CONTROLLER_ADDRESS = "Abildgade 18, 8200 Aarhus, Danmark";

/** Privacy notice for the P00 waitlist. Deliberately limited to what the waitlist actually does. */
export default function PrivacyPage() {
  const sections: [string, React.ReactNode][] = [
    ["Hvem er ansvarlig?", <>Dialogbot, {CONTROLLER_ADDRESS}. Henvendelser om dine oplysninger sendes til denne adresse.</>],
    ["Hvad gemmer vi?", <>Din e-mailadresse, den branche og de interesser, du eventuelt vælger, hvilken side du tilmeldte dig fra, samt tidspunktet for tilmelding og samtykke. Vi opretter ingen konto og gemmer ikke andet om dig fra ventelisten.</>],
    ["Hvorfor?", <>Kun for at give dig besked, når Dialogbot åbner for nye virksomheder, og for at prioritere, hvilke funktioner vi bygger først. Vi sender ikke nyhedsbreve eller reklame, og vi sælger eller deler ikke listen.</>],
    ["Retsgrundlag", <>Dit samtykke (databeskyttelsesforordningens art. 6, stk. 1, litra a), som du giver ved at sætte flueben i formularen. Du kan til enhver tid trække det tilbage.</>],
    ["Hvor længe?", <>Indtil vi har givet besked om åbningen, eller indtil du beder os slette dig – dog højst 24 måneder efter tilmelding.</>],
    ["Hvem behandler data for os?", <>Oplysningerne ligger i vores database hos Supabase og behandles af vores server hos Render (Frankfurt, EU). Websiden leveres via Vercel. De fungerer som databehandlere.</>],
    ["Dine rettigheder", <>Du har ret til indsigt, berigtigelse og sletning, til at trække dit samtykke tilbage og til dataportabilitet. Skriv til {CONTROLLER_ADDRESS}. Du kan klage til Datatilsynet (<a className="underline" href="https://www.datatilsynet.dk" rel="noreferrer">datatilsynet.dk</a>).</>],
  ];
  return (
    <div className="min-h-dvh bg-surface">
      <header className="bg-surface/85 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.03)]">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link href="/preview" className="flex items-center gap-2.5"><span className="w-9 h-9 rounded-lg bg-primary flex items-center justify-center text-secondary-fixed"><Icon name="support_agent" size={22} /></span><span className="font-headline-sm text-headline-sm text-primary font-bold">Dialogbot</span></Link>
          <Link href="/preview#venteliste" className="font-label-md text-label-md text-primary font-semibold flex items-center gap-1"><Icon name="arrow_back" size={18} />Til ventelisten</Link>
        </div>
      </header>
      <main id="main" className="max-w-3xl mx-auto px-4 sm:px-6 py-space-xl flex flex-col gap-space-lg">
        <div>
          <span className="font-label-sm text-label-sm uppercase tracking-wider text-secondary font-bold">Privatliv</span>
          <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary">Sådan behandler vi oplysninger fra ventelisten</h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant mt-space-xs">Gælder tilmelding til tidlig adgang. Opdateret 25. september 2026.</p>
        </div>
        {sections.map(([h, body]) => (
          <section key={h} className="bg-surface-container-lowest rounded-xl p-space-md sm:p-space-lg shadow-sm">
            <h2 className="font-headline-sm text-headline-sm text-primary mb-space-xs">{h}</h2>
            <p className="font-body-md text-body-md text-on-surface-variant">{body}</p>
          </section>
        ))}
      </main>
    </div>
  );
}
