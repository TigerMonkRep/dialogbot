import type { Metadata } from "next";
import Link from "next/link";
import { SeoPage } from "@/components/seo-page";

export const metadata: Metadata = {
  title: "AI-telefonsvarer og AI-telefon til virksomheder – på dansk",
  description: "En AI-telefonsvarer, der taler med kunden i stedet for at bede dem lægge en besked. Dialogbot tager telefonen på dansk, afklarer behovet, booker tider og sender jer henvendelsen.",
  alternates: { canonical: "/ai-telefonsvarer" },
  openGraph: { url: "/ai-telefonsvarer", title: "AI-telefonsvarer og AI-telefon på dansk | Dialogbot", images: ["/opengraph-image.png"] },
};

export default function Page() {
  return (
    <SeoPage path="/ai-telefonsvarer" kicker="AI-telefonsvarer"
      title="AI-telefonsvareren, der faktisk taler med kunden"
      lead="Ingen kunde gider lægge en besked. Dialogbot er en AI-telefon, der tager opkaldet på dansk, forstår hvad kunden vil, og sørger for, at I kan ringe tilbage med det samme – eller booker tiden direkte."
      points={["Tager telefonen på dansk – døgnet rundt", "Kender jeres egne fagord og navne", "Booker tider og sender SMS-bekræftelse", "Ingen talebeskeder at lytte igennem", "Behold jeres eget nummer"]}
      sections={[
        { title: "Fra telefonsvarer til samtale", body: <>
          <p>En almindelig telefonsvarer beder kunden lægge en besked – og mange lægger på og ringer til en konkurrent i stedet. En AI-telefonsvarer som Dialogbot svarer i stedet med en naturlig dansk stemme, stiller de rigtige spørgsmål og samler oplysningerne for jer.</p>
          <p>Bagefter får I en kort, skrevet opsummering af samtalen med navn, nummer og behov – og en opgave, hvis kunden skal ringes op. I skal aldrig lytte en talebesked igennem igen.</p>
        </> },
        { title: "Sådan virker AI-telefonen", body: <ul>
          <li><strong>Viderestilling:</strong> I viderestiller jeres nummer til Dialogbot, når I er optaget eller har lukket – eller bruger et nyt Dialogbot-nummer.</li>
          <li><strong>Jeres viden:</strong> Assistenten svarer ud fra jeres godkendte ydelser, priser, åbningstider og regler.</li>
          <li><strong>Handlinger:</strong> Den kan finde ledige tider, booke, flytte og aflyse aftaler og sende kunden en SMS – altid først efter kundens ja.</li>
          <li><strong>Overblik:</strong> Alle samtaler lander i jeres indbakke, og I får en daglig rapport.</li>
        </ul> },
        { title: "Lyder den som et menneske?", body: <>
          <p>Dialogbot taler naturligt dansk og lytter, til kunden er færdig med at tale. I vælger selv stemmen, og I kan høre den, før I bestemmer jer. Den siger altid ærligt, at den er en digital assistent – den lyver aldrig om at være et menneske.</p>
          <p>Den bedste måde at finde ud af det på er at prøve: <Link href="/#demo">bliv ringet op af Dialogbot</Link>, og hør selv, hvordan den ville tage telefonen for jer.</p>
        </> },
        { title: "Pris", body: <p>Fast abonnement på <strong>1.495 kr. om måneden</strong>, eller <strong>149 kr. pr. godkendt henvendelse</strong> uden fast pris – alle priser ekskl. moms. Vi guider jer gennem hele opsætningen. Se også <Link href="/ai-receptionist">AI-receptionist</Link> og <Link href="/chatbot">chatbot til hjemmesiden</Link>.</p> },
      ]}
      faq={[
        ["Hvad er forskellen på en AI-telefonsvarer og en almindelig telefonsvarer?", "En almindelig telefonsvarer optager en besked. En AI-telefonsvarer taler med kunden, svarer på spørgsmål ud fra jeres viden, afklarer behovet og kan booke en tid – og I får en skrevet opsummering."],
        ["Kan jeg bruge mit eget nummer?", "Ja. I viderestiller jeres nuværende nummer til Dialogbot, når I er optaget eller har lukket. I kan også få et nyt Dialogbot-nummer."],
        ["Forstår den dansk med dialekt?", "Dialogbot er bygget til dansk tale og bruger jeres egne fagord og navne fra den viden, I godkender, så den bedre genkender dem."],
        ["Hvad koster det?", "1.495 kr. om måneden i fast abonnement eller 149 kr. pr. godkendt henvendelse. Priserne er ekskl. moms."],
        ["Kan jeg høre den, før jeg køber?", "Ja. Skriv dit nummer på forsiden, vælg en stemme og din branche, så ringer Dialogbot dig op og viser det."],
      ]} />
  );
}
