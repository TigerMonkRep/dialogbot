import type { Metadata } from "next";
import Link from "next/link";
import { SeoPage } from "@/components/seo-page";

const path = "/viden/hvad-er-en-ai-receptionist";
export const metadata: Metadata = {
  title: "Hvad er en AI-receptionist – og hvordan virker den?",
  description: "En AI-receptionist tager telefonen og chatten for din virksomhed, svarer ud fra jeres egen viden og booker tider. Sådan virker den, og det skal du kigge efter.",
  alternates: { canonical: path },
  openGraph: { url: path, type: "article", title: "Hvad er en AI-receptionist? | Dialogbot", images: ["/opengraph-image.png"] },
};

export default function Page() {
  return (
    <SeoPage path={path} kicker="Hvad er en AI-receptionist?" article={{ published: "2026-10-07" }}
      title="Hvad er en AI-receptionist – og hvordan virker den?"
      lead="En AI-receptionist er en digital assistent, der tager telefonen og chatten for din virksomhed. Her er, hvad den kan, hvordan den virker, og hvad du skal kigge efter, før du vælger en."
      points={["Tager telefonen og chatten døgnet rundt", "Svarer ud fra virksomhedens egen viden", "Afklarer behovet og samler kontaktoplysninger", "Kan booke tider og sende SMS", "Skal aldrig gætte eller love noget, I ikke har godkendt"]}
      sections={[
        { title: "Kort fortalt", body: <>
          <p>En AI-receptionist svarer, når du ikke selv kan: når du er optaget, hos en kunde eller har lukket. I stedet for en telefonsvarer, der beder kunden lægge en besked, taler den med kunden, finder ud af hvad de har brug for, og samler navn, nummer og behov, så du kan ringe tilbage til en varm kunde.</p>
          <p>Den bygger på tre dele: <strong>talegenkendelse</strong>, der forstår hvad kunden siger, en <strong>sprogmodel</strong>, der finder det rigtige svar i virksomhedens viden, og en <strong>stemme</strong>, der svarer naturligt på dansk.</p>
        </> },
        { title: "Hvad kan en AI-receptionist?", body: <ul>
          <li>Svare på de faste spørgsmål: åbningstider, priser, ydelser, adresse og parkering.</li>
          <li>Afklare behovet med de spørgsmål, virksomheden har bestemt.</li>
          <li>Finde ledige tider og booke, flytte eller aflyse aftaler.</li>
          <li>Sende kunden en bekræftelse på SMS.</li>
          <li>Give virksomheden en kort, skrevet opsummering af hver samtale.</li>
        </ul> },
        { title: "Hvad skal den ikke kunne?", body: <>
          <p>En god AI-receptionist <strong>gætter aldrig</strong>. Den skal kun svare ud fra viden, virksomheden har godkendt, og ærligt sige, når noget ikke fremgår. Den må ikke love rabatter, give faglige råd eller lade som om, den er et menneske.</p>
          <p>Hos Dialogbot starter al viden som en kladde og bliver først brugt, når en ejer eller administrator har godkendt den.</p>
        </> },
        { title: "Det skal du kigge efter", body: <ul>
          <li><strong>Dansk tale</strong> – lyder den naturlig, og forstår den navne og fagord?</li>
          <li><strong>Kontrol</strong> – kan du selv godkende, hvad den må sige?</li>
          <li><strong>Handlinger</strong> – kan den booke og sende SMS, eller tager den kun beskeder?</li>
          <li><strong>Opsætning</strong> – får du hjælp, eller skal du selv finde ud af det?</li>
          <li><strong>Pris</strong> – fast pris eller pr. henvendelse, og er der binding?</li>
        </ul> },
        { title: "Prøv det selv", body: <p>Den bedste test er at høre den. <Link href="/#demo">Bliv ringet op af Dialogbot</Link>, vælg din branche, og hør hvordan den ville tage telefonen for dig. Læs mere om <Link href="/ai-receptionist">Dialogbots AI-receptionist</Link> eller se <Link href="/priser">priserne</Link>.</p> },
      ]}
      faq={[
        ["Er en AI-receptionist det samme som en chatbot?", "Ikke helt. En chatbot skriver, en AI-receptionist taler i telefonen. Dialogbot gør begge dele med den samme viden."],
        ["Lyder en AI-receptionist som en robot?", "Moderne stemmer lyder naturlige. Dialogbot taler dansk og siger altid ærligt, at den er en digital assistent, hvis kunden spørger."],
        ["Hvad koster en AI-receptionist?", "Hos Dialogbot 1.495 kr. om måneden eller 149 kr. pr. godkendt henvendelse, ekskl. moms."],
      ]} />
  );
}
