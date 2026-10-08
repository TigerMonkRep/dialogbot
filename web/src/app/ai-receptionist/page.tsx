import type { Metadata } from "next";
import Link from "next/link";
import { SeoPage } from "@/components/seo-page";

export const metadata: Metadata = {
  title: "AI-receptionist til danske virksomheder",
  description: "Dansk AI-receptionist, der tager telefonen, når I er optaget eller har lukket – svarer ud fra jeres egen viden, booker tider og sender jer hver henvendelse.",
  alternates: { canonical: "/ai-receptionist" },
  openGraph: { url: "/ai-receptionist", title: "AI-receptionist til danske virksomheder | Dialogbot", images: ["/opengraph-image.png"] },
};

export default function Page() {
  return (
    <SeoPage path="/ai-receptionist" kicker="AI-receptionist"
      title="En AI-receptionist, der tager telefonen, når I ikke kan"
      lead="Dialogbot er en digital receptionist på dansk. Den tager imod opkald og chats døgnet rundt, svarer kun ud fra den viden, I selv har godkendt, og sørger for, at ingen kunde går tabt."
      points={["Svarer på dansk med en naturlig stemme", "Kender jeres ydelser, priser og åbningstider", "Booker, flytter og aflyser tider", "Sender jer en kort opsummering af hver henvendelse", "Vi guider jer gennem hele opsætningen"]}
      sections={[
        { title: "Hvad er en AI-receptionist?", body: <>
          <p>En AI-receptionist er en digital assistent, der passer telefonen og chatten for jeres virksomhed. Den tager imod kunden, finder ud af hvad de har brug for, svarer på de faste spørgsmål og samler navn, nummer og behov, så I kan ringe tilbage til en varm kunde.</p>
          <p>Med Dialogbot bestemmer I selv, hvad assistenten må sige. Al viden starter som en kladde, og den bliver først brugt, når en ejer eller administrator har godkendt den. Assistenten gætter aldrig – hvis noget ikke fremgår af jeres viden, siger den det ærligt og lover, at en medarbejder vender tilbage.</p>
        </> },
        { title: "Det kan Dialogbot gøre for jer", body: <ul>
          <li><strong>Tage telefonen</strong>, når I er optaget, er ude hos en kunde eller har lukket – også om aftenen og i weekenden.</li>
          <li><strong>Afklare behovet</strong> med de spørgsmål, I har godkendt, og sende jer en opsummering med navn og nummer.</li>
          <li><strong>Booke tider</strong> ud fra jeres åbningstider og bookingregler – og sende kunden en bekræftelse på SMS.</li>
          <li><strong>Svare i chatten</strong> på jeres hjemmeside med den samme viden som på telefonen.</li>
          <li><strong>Følge op</strong> på tilbud, I har sendt, og give jer en daglig rapport over alle henvendelser.</li>
        </ul> },
        { title: "Til håndværkere, klinikker, saloner, restauranter og rådgivere", body: <>
          <p>Dialogbot sættes op efter jeres egne ydelser og arbejdsgange. Håndværkeren slipper for at tage telefonen fra stigen, klinikken aflaster receptionen i morgentimerne, salonen kan blive ved kunden i stolen, og restauranten mister ikke bordbestillinger i myldretiden.</p>
          <p>I kan beholde jeres nuværende nummer og viderestille til Dialogbot, når I er optaget eller har lukket – eller bruge et nyt Dialogbot-nummer.</p>
        </> },
        { title: "Pris og opsætning", body: <>
          <p>Der er to prismodeller: et fast abonnement på <strong>1.495 kr. om måneden</strong>, eller <strong>149 kr. pr. godkendt henvendelse</strong> uden fast pris. Alle priser er ekskl. moms.</p>
          <p>I skal ikke kunne noget teknisk. En fra Dialogbot sætter assistenten op sammen med jer på cirka en halv time. Har I en hjemmeside, henter Dialogbot det meste automatisk, og I kan prøve assistenten af, før den tager et eneste rigtigt opkald. Læs også om <Link href="/ai-telefonsvarer">AI-telefonsvareren</Link> og <Link href="/chatbot">chatbotten til hjemmesiden</Link>.</p>
        </> },
      ]}
      faq={[
        ["Hvad koster en AI-receptionist hos Dialogbot?", "Enten 1.495 kr. om måneden i fast abonnement eller 149 kr. pr. godkendt henvendelse uden fast pris. Priserne er ekskl. moms."],
        ["Lyder den som en robot?", "Dialogbot taler naturligt dansk med en stemme, I selv vælger, fx Camilla eller Peter. Den siger altid ærligt, at den er en digital assistent, hvis kunden spørger."],
        ["Kan jeg beholde mit telefonnummer?", "Ja. I viderestiller jeres nuværende nummer til Dialogbot, når I er optaget eller har lukket, og beholder jeres teleudbyder."],
        ["Hvad sker der, hvis assistenten ikke kender svaret?", "Den gætter ikke. Den svarer kun ud fra godkendt viden og lover, at en medarbejder vender tilbage, og I får henvendelsen med det samme."],
        ["Hvor lang tid tager opsætningen?", "Typisk omkring en halv time sammen med en fra Dialogbot. Vi guider jer gennem det hele."],
      ]} />
  );
}
