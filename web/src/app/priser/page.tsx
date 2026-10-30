import type { Metadata } from "next";
import Link from "next/link";
import { SeoPage } from "@/components/seo-page";

export const metadata: Metadata = {
  title: "Priser – AI-receptionist fra 2.495 kr. om måneden",
  description: "Se prisen på Dialogbot: ét abonnement fra 2.495 kr. om måneden ekskl. moms med 300 minutters indgående opkald. Telefon, chat, booking og personlig opsætning er med. Udgående kampagneopkald koster 4 kr. pr. opkald.",
  alternates: { canonical: "/priser" },
  openGraph: { url: "/priser", title: "Priser på AI-receptionist | Dialogbot", images: ["/opengraph-image.png"] },
};

export default function Page() {
  return (
    <SeoPage path="/priser" kicker="Priser"
      title="Ét abonnement – fra 2.495 kr. om måneden"
      lead="Én pris, den fulde Dialogbot: AI-receptionist på telefonen, chatbot på hjemmesiden, booking og en opsummering af hver henvendelse. Alle priser er ekskl. moms."
      points={["Fra 2.495 kr. om måneden – ét abonnement", "Ingen pris pr. henvendelse", "300 minutters indgående opkald om måneden er med", "Udgående kampagneopkald: 4 kr. pr. opkald + 2 kr. pr. minut", "Ingen binding", "Gør-det-selv-opsætning er med – specialist-opsætning 5.000 kr."]}
      sections={[
        { title: "Abonnementet", body: <>
          <p><strong>Fra 2.495 kr. om måneden</strong> ekskl. moms. Der er ingen pris pr. henvendelse, og <strong>300 minutters indgående opkald om måneden er med</strong> – det rækker til de fleste små virksomheder. Taler jeres kunder mere med assistenten end det, koster hvert påbegyndt minut derudover 1,50 kr. I kan altid se jeres forbrug i Dialogbot.</p>
          <p>Passer til virksomheder, hvor telefonen ringer, mens I har travlt: håndværkere, klinikker, saloner, værksteder og rådgivere.</p>
        </> },
        { title: "Det er med i abonnementet", body: <ul>
          <li>AI-receptionist og AI-telefonsvarer på dansk – døgnet rundt</li>
          <li>Chatbot til hjemmesiden med samme viden</li>
          <li>Booking, flytning og aflysning af tider samt SMS-bekræftelse</li>
          <li>Opsummering af hver henvendelse, opgaver og daglig rapport</li>
          <li>Gør-det-selv-opsætning: byggevejledningens tre trin, cirka en halv time, med assistenten ved hånden</li>
        </ul> },
        { title: "Opsætning fra vores specialister – 5.000 kr.", body: <>
          <p>I kan sætte Dialogbot op selv – byggevejledningens tre trin er med i abonnementet. Vil I hellere have det gjort, sætter vores egne specialister den op for <strong>5.000 kr.</strong> ekskl. moms, betalt én gang.</p>
          <p>Så får I en skræddersyet opsætning og integration til jeres egne systemer og behov: vi kobler kalender, CRM eller bookingsystem på, lægger jeres viden og priser ind, træner stemmen på jeres navne og tester det hele sammen med jer, før den tændes.</p>
        </> },
        { title: "Udgående kampagneopkald", body: <>
          <p>Vil I have assistenten til at ringe ud til kontakter, der selv har sagt ja til at blive ringet op, koster det <strong>4 kr. pr. udgående opkald</strong> plus <strong>2 kr. pr. påbegyndt samtaleminut</strong> ekskl. moms – ligesom en telefonregning.</p>
          <p>Hvert opkald, der ringes, tæller – også et nyt forsøg. Et ubesvaret opkald koster derfor 4 kr., og en samtale på 3 minutter 10 kr. En kontakt ringes højst 2 gange og taler højst 3 minutter i alt, og I ser den højeste pris, før I trykker Start.</p>
        </> },
        { title: "Kom i gang", body: <p>Hør først, hvordan det lyder: <Link href="/proev">bliv ringet op af Dialogbot</Link>. Når I er klar, <Link href="/signup">opretter I en konto</Link> og følger byggevejledningen – eller bestiller opsætning fra vores specialister. Læs mere om <Link href="/ai-receptionist">AI-receptionisten</Link>.</p> },
      ]}
      faq={[
        ["Er der binding?", "Nej. Der er ingen binding. I kan opsige til udgangen af den løbende måned."],
        ["Hvad betyder \"fra\" 2.495 kr.?", "Det er prisen for abonnementet, ekskl. moms. Der er ingen ekstra pris pr. henvendelse."],
        ["Hvad koster udgående kampagneopkald?", "4 kr. pr. udgående opkald plus 2 kr. pr. påbegyndt samtaleminut, ekskl. moms. Et ubesvaret opkald koster 4 kr., en samtale på 3 minutter 10 kr. Kontakterne skal på forhånd have sagt ja til at blive ringet op, og en kampagne ringer først, når I selv trykker Start."],
        ["Hvad sker der, hvis vi får mange indgående opkald?", "300 minutters indgående opkald om måneden er med i abonnementet. Derudover koster hvert påbegyndt minut 1,50 kr. ekskl. moms – det står på fakturaen som en særskilt linje, og I kan følge forbruget løbende i Dialogbot."],
        ["Koster opsætningen noget?", "Ikke hvis I gør det selv: byggevejledningens tre trin er med i abonnementet og tager cirka en halv time. Opsætning fra vores specialister koster 5.000 kr. ekskl. moms én gang og giver jer en skræddersyet opsætning og integration til jeres egne systemer og behov."],
      ]} />
  );
}
