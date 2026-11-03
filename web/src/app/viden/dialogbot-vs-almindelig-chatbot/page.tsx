import type { Metadata } from "next";
import Link from "next/link";
import { CompareTable } from "@/components/compare-table";
import { SeoPage } from "@/components/seo-page";

const path = "/viden/dialogbot-vs-almindelig-chatbot";
export const metadata: Metadata = {
  title: "Dialogbot eller en almindelig chatbot – hvad er forskellen?",
  description: "En almindelig chatbot svarer på en hjemmeside. Dialogbot tager også telefonen, booker tider og svarer kun ud fra viden, I selv har godkendt. Se forskellene.",
  alternates: { canonical: path },
  openGraph: { url: path, type: "article", title: "Dialogbot eller en almindelig chatbot? | Dialogbot", images: ["/opengraph-image.png"] },
};

export default function Page() {
  return (
    <SeoPage path={path} kicker="Dialogbot eller en almindelig chatbot" article={{ published: "2026-11-03" }}
      title="Dialogbot eller en almindelig chatbot – hvad er forskellen?"
      lead="En almindelig chatbot svarer på hjemmesiden. Dialogbot tager også telefonen, booker tiderne og lader jer godkende alt, den må sige."
      points={["Chatbot: skriver på hjemmesiden", "Dialogbot: telefon, chat og booking med samme viden", "Dialogbot gætter aldrig – kun godkendt viden", "Ét abonnement: 2.495 kr./md."]}
      sections={[
        { title: "Overblik", body: <CompareTable other="Almindelig chatbot" rows={[
          ["Kanaler", "Telefon og webchat med samme viden", "Typisk kun chat på hjemmesiden"],
          ["Booking", "Finder ledige tider i jeres kalender og sender SMS-bekræftelse", "Sjældent – ofte kun et link eller en besked"],
          ["Hvad den svarer ud fra", "Kun viden, I selv har godkendt – og I ser hver ændring først", "Varierer: nogle svarer frit ud fra en AI-model"],
          ["Når den ikke kan svare", "Den siger det og tager en besked til jer", "Varierer"],
          ["Besked til jer", "Navn, nummer og hvad det drejede sig om – og en rapport hver dag", "Varierer"],
          ["Pris", "2.495 kr./md. – ingen pris pr. henvendelse", "Fra få hundrede kr./md. og opefter"],
        ]} /> },
        { title: "Hvornår er en almindelig chatbot nok?", body: <p>Hvis jeres kunder næsten kun skriver, og I ikke skal have booket tider eller have telefonen taget, kan en simpel chatbot være nok – og billigere.</p> },
        { title: "Hvornår giver Dialogbot mere?", body: <p>Når telefonen ringer, mens I står på stigen eller har en kunde i stolen, og et ubesvaret opkald er en tabt kunde. Dialogbot tager den inden for to sekunder, booker en tid og giver jer besked. Læs mere om <Link href="/ai-receptionist">AI-receptionisten</Link> og <Link href="/chatbot">chatbotten til hjemmesiden</Link>, som er en del af abonnementet.</p> },
        { title: "Hør den selv", body: <p><Link href="/proev">Lad Dialogbot ringe til jer</Link> – to minutter, ingen tilmelding.</p> },
      ]}
      faq={[
        ["Kan Dialogbot også bare være en chatbot?", "Ja. Webchatten er med i abonnementet, og den bruger samme godkendte viden som telefonen. Det er én kodelinje på hjemmesiden."],
        ["Gætter Dialogbot, hvis den ikke kender svaret?", "Nej. Den svarer kun ud fra godkendt viden og tager en besked til jer, hvis den ikke kan svare."],
        ["Hvad koster det?", "2.495 kr. om måneden ekskl. moms med 300 minutters indgående opkald. Ingen binding."],
      ]} />
  );
}
