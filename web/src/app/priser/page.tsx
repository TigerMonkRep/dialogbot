import type { Metadata } from "next";
import Link from "next/link";
import { SeoPage } from "@/components/seo-page";

export const metadata: Metadata = {
  title: "Priser – AI-receptionist fra 149 kr. pr. henvendelse",
  description: "Se priserne på Dialogbot: fast abonnement på 1.495 kr. om måneden eller 149 kr. pr. godkendt henvendelse. Telefon, chat, booking og personlig opsætning er med.",
  alternates: { canonical: "/priser" },
  openGraph: { url: "/priser", title: "Priser på AI-receptionist | Dialogbot", images: ["/opengraph-image.png"] },
};

export default function Page() {
  return (
    <SeoPage path="/priser" kicker="Priser"
      title="Enkle priser – vælg den model, der passer jer"
      lead="To måder at betale på, samme fulde Dialogbot: AI-receptionist på telefonen, chatbot på hjemmesiden, booking og en opsummering af hver henvendelse. Alle priser er ekskl. moms."
      points={["Model A: 1.495 kr. om måneden – fast pris", "Model B: 149 kr. pr. godkendt henvendelse – ingen fast pris", "Telefon, chat og booking er med i begge", "Ingen binding og intet opstartsgebyr", "Personlig opsætning er gratis"]}
      sections={[
        { title: "Model A – fast abonnement", body: <>
          <p><strong>1.495 kr. om måneden</strong> ekskl. moms. Ingen gebyr pr. henvendelse – I ved præcis, hvad det koster hver måned.</p>
          <p>Passer til virksomheder med mange opkald, fx håndværkere, klinikker og saloner, hvor telefonen ringer hver dag.</p>
        </> },
        { title: "Model B – betal pr. henvendelse", body: <>
          <p><strong>149 kr. pr. godkendt henvendelse</strong> ekskl. moms og ingen fast månedspris. En henvendelse er en kunde med et konkret behov, som I selv godkender i indbakken.</p>
          <p>Passer til virksomheder med færre, men værdifulde henvendelser, fx rådgivere og specialister.</p>
        </> },
        { title: "Det er med i begge modeller", body: <ul>
          <li>AI-receptionist og AI-telefonsvarer på dansk – døgnet rundt</li>
          <li>Chatbot til hjemmesiden med samme viden</li>
          <li>Booking, flytning og aflysning af tider samt SMS-bekræftelse</li>
          <li>Opsummering af hver henvendelse, opgaver og daglig rapport</li>
          <li>Personlig opsætning på cirka en halv time – vi guider jer hele vejen</li>
        </ul> },
        { title: "Kom i gang", body: <p>Hør først, hvordan det lyder: <Link href="/#demo">bliv ringet op af Dialogbot</Link>. Når I er klar, <Link href="/signup">opretter I en konto</Link>, og vi sætter det op sammen. Læs mere om <Link href="/ai-receptionist">AI-receptionisten</Link>.</p> },
      ]}
      faq={[
        ["Er der binding?", "Nej. Der er ingen binding og intet opstartsgebyr. I kan opsige til udgangen af den løbende måned."],
        ["Hvad er en godkendt henvendelse?", "En kunde med et konkret behov, som I selv har godkendt i indbakken. Opkald uden et reelt behov tæller ikke med."],
        ["Kan vi skifte model senere?", "Ja. Valget af prismodel gemmes som en ny version af jeres aftale."],
        ["Koster opsætningen noget?", "Nej, den personlige opsætning er gratis."],
      ]} />
  );
}
