import type { Metadata } from "next";
import Link from "next/link";
import { SeoPage } from "@/components/seo-page";

export const metadata: Metadata = {
  title: "Priser – AI-receptionist fra 2.495 kr. om måneden",
  description: "Se prisen på Dialogbot: ét abonnement fra 2.495 kr. om måneden ekskl. moms. Telefon, chat, booking og personlig opsætning er med. Udgående kampagneopkald koster 4 kr. pr. opkald.",
  alternates: { canonical: "/priser" },
  openGraph: { url: "/priser", title: "Priser på AI-receptionist | Dialogbot", images: ["/opengraph-image.png"] },
};

export default function Page() {
  return (
    <SeoPage path="/priser" kicker="Priser"
      title="Ét abonnement – fra 2.495 kr. om måneden"
      lead="Én pris, den fulde Dialogbot: AI-receptionist på telefonen, chatbot på hjemmesiden, booking og en opsummering af hver henvendelse. Alle priser er ekskl. moms."
      points={["Fra 2.495 kr. om måneden – ét abonnement", "Ingen pris pr. henvendelse", "Udgående kampagneopkald: 4 kr. pr. opkald", "Ingen binding og intet opstartsgebyr", "Personlig opsætning er gratis"]}
      sections={[
        { title: "Abonnementet", body: <>
          <p><strong>Fra 2.495 kr. om måneden</strong> ekskl. moms. Der er ingen pris pr. henvendelse eller pr. opkald, I selv modtager – I ved præcis, hvad det koster hver måned.</p>
          <p>Passer til virksomheder, hvor telefonen ringer, mens I har travlt: håndværkere, klinikker, saloner, værksteder og rådgivere.</p>
        </> },
        { title: "Det er med i abonnementet", body: <ul>
          <li>AI-receptionist og AI-telefonsvarer på dansk – døgnet rundt</li>
          <li>Chatbot til hjemmesiden med samme viden</li>
          <li>Booking, flytning og aflysning af tider samt SMS-bekræftelse</li>
          <li>Opsummering af hver henvendelse, opgaver og daglig rapport</li>
          <li>Personlig opsætning på cirka en halv time – vi guider jer hele vejen</li>
        </ul> },
        { title: "Udgående kampagneopkald", body: <>
          <p>Vil I have assistenten til at ringe ud til kontakter, der selv har sagt ja til at blive ringet op, koster det <strong>4 kr. pr. udgående opkald</strong> ekskl. moms.</p>
          <p>Hvert opkald, der ringes, tæller – også et nyt forsøg. En kontakt ringes højst 2 gange, og I ser den højeste pris, før I trykker Start.</p>
        </> },
        { title: "Kom i gang", body: <p>Hør først, hvordan det lyder: <Link href="/proev">bliv ringet op af Dialogbot</Link>. Når I er klar, <Link href="/signup">opretter I en konto</Link>, og vi sætter det op sammen. Læs mere om <Link href="/ai-receptionist">AI-receptionisten</Link>.</p> },
      ]}
      faq={[
        ["Er der binding?", "Nej. Der er ingen binding og intet opstartsgebyr. I kan opsige til udgangen af den løbende måned."],
        ["Hvad betyder \"fra\" 2.495 kr.?", "Det er prisen for abonnementet, ekskl. moms. Der er ingen ekstra pris pr. henvendelse."],
        ["Hvad koster udgående kampagneopkald?", "4 kr. pr. udgående opkald ekskl. moms. Kontakterne skal på forhånd have sagt ja til at blive ringet op, og en kampagne ringer først, når I selv trykker Start."],
        ["Koster opsætningen noget?", "Nej, den personlige opsætning er gratis og tager cirka en halv time."],
      ]} />
  );
}
