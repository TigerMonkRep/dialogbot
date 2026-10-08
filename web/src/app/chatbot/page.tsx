import type { Metadata } from "next";
import Link from "next/link";
import { SeoPage } from "@/components/seo-page";

export const metadata: Metadata = {
  title: "Chatbot til hjemmesiden – dansk AI-chatbot",
  description: "Dansk AI-chatbot til jeres hjemmeside, der svarer ud fra jeres egne ydelser, priser og åbningstider, samler henvendelser og kan booke tider.",
  alternates: { canonical: "/chatbot" },
  openGraph: { url: "/chatbot", title: "Chatbot til hjemmesiden på dansk | Dialogbot", images: ["/opengraph-image.png"] },
};

export default function Page() {
  return (
    <SeoPage path="/chatbot" kicker="Chatbot til hjemmesiden"
      title="En dansk chatbot, der kender jeres forretning"
      lead="Dialogbots chatbot svarer jeres besøgende på dansk – døgnet rundt – ud fra den viden, I selv har godkendt. Den samler henvendelser, kan booke tider, og en medarbejder kan overtage samtalen når som helst."
      points={["Svarer kun ud fra jeres godkendte viden", "Samler navn, kontakt og behov", "Booker tider direkte i chatten", "En medarbejder kan overtage samtalen", "Samme viden som på telefonen"]}
      sections={[
        { title: "En chatbot, der ikke gætter", body: <>
          <p>Mange chatbots finder på svar. Dialogbot gør ikke. Den svarer kun ud fra de ydelser, priser, åbningstider og regler, I selv har godkendt – og siger ærligt, når noget ikke fremgår, så en medarbejder kan følge op.</p>
          <p>Har I en hjemmeside, henter Dialogbot det meste automatisk derfra som kladder, som I gennemgår og godkender. Så er chatbotten klar på kort tid.</p>
        </> },
        { title: "Det kan chatbotten", body: <ul>
          <li><strong>Svare på spørgsmål</strong> om ydelser, priser, åbningstider og praktiske forhold.</li>
          <li><strong>Samle henvendelser</strong> med navn, kontaktoplysninger og behov – og sende dem til jeres indbakke.</li>
          <li><strong>Booke tider</strong> ud fra jeres åbningstider og bookingregler.</li>
          <li><strong>Lade jer tage over:</strong> en medarbejder kan svare kunden direkte i samtalen, mens assistenten holder pause.</li>
          <li><strong>Tilbyde et opkald tilbage</strong> i et tidsrum, der passer kunden.</li>
        </ul> },
        { title: "Chat og telefon med én og samme viden", body: <p>Chatbotten bruger den samme godkendte viden som Dialogbots <Link href="/ai-receptionist">AI-receptionist</Link> og <Link href="/ai-telefonsvarer">AI-telefonsvarer</Link>. Retter I en pris ét sted, er den rettet både i chatten og på telefonen. Chatten sættes på jeres hjemmeside med en lille indlejringskode, som vi hjælper jer med.</p> },
        { title: "Pris", body: <p>Chatbotten er en del af Dialogbot: fast abonnement på <strong>1.495 kr. om måneden</strong>, eller <strong>149 kr. pr. godkendt henvendelse</strong> – ekskl. moms. Vi guider jer gennem hele opsætningen.</p> },
      ]}
      faq={[
        ["Hvordan kommer chatbotten på min hjemmeside?", "I indsætter en lille indlejringskode på hjemmesiden. Vi hjælper jer med det under opsætningen, og I bestemmer selv, på hvilke domæner chatten må vises."],
        ["Kan en medarbejder overtage samtalen?", "Ja. En medarbejder kan svare kunden direkte i samtalen, og assistenten holder pause imens."],
        ["Finder chatbotten selv på svar?", "Nej. Den svarer kun ud fra den viden, I har godkendt, og siger ærligt, når noget ikke fremgår."],
        ["Kan den både chatte og tage telefonen?", "Ja. Dialogbot bruger den samme viden i chatten og på telefonen."],
        ["Hvad koster chatbotten?", "Den er en del af Dialogbot: 1.495 kr. om måneden eller 149 kr. pr. godkendt henvendelse, ekskl. moms."],
      ]} />
  );
}
