import type { Metadata } from "next";
import Link from "next/link";
import { CompareTable } from "@/components/compare-table";
import { SeoPage } from "@/components/seo-page";

const path = "/viden/dialogbot-vs-vocalis";
export const metadata: Metadata = {
  title: "Dialogbot eller Vocalis – fast pris eller minutpakker?",
  description: "Sammenlign Dialogbot og Vocalis: fast månedspris eller minutpakker, godkendt viden, booking og hvordan I kommer i gang. Priser ekskl. moms.",
  alternates: { canonical: path },
  openGraph: { url: path, type: "article", title: "Dialogbot eller Vocalis? | Dialogbot", images: ["/opengraph-image.png"] },
};

/** Comparison page (audit D5.3). Competitor figures are the published list prices noted in the 2026-11 site audit –
 *  re-check them on vocalis.dk before changing or republishing. */
export default function Page() {
  return (
    <SeoPage path={path} kicker="Dialogbot eller Vocalis" article={{ published: "2026-11-03" }}
      title="Dialogbot eller Vocalis – fast pris eller minutpakker?"
      lead="Begge bygger AI-medarbejdere til danske virksomheder. Forskellen er især, hvordan I betaler, og hvordan I kommer i gang."
      points={["Dialogbot: 2.495 kr./md., 300 minutter med, derefter 1,50 kr./min.", "Vocalis: fra 899 kr./md. for 100 minutter, derefter minutpakker", "Dialogbot: kun godkendt viden – og I godkender hver ændring", "Dialogbot: hør den først, uden tilmelding"]}
      sections={[
        { title: "Overblik", body: <CompareTable other="Vocalis" rows={[
          ["Pris pr. måned (ekskl. moms)", "2.495 kr. – ét abonnement", "Fra 899 kr. for 100 minutter (Basis)"],
          ["Når minutterne er brugt", "1,50 kr. pr. påbegyndt minut efter de 300 inkluderede", "Automatiske minutpakker op til 3.995 kr./md."],
          ["Svar ud fra", "Viden, I selv har godkendt – og I ser hver ændring først (før → efter, «Godkend?»)", "Se Vocalis' egen beskrivelse"],
          ["Booking", "Google Kalender eller Microsoft 365, med SMS-bekræftelse", "Se Vocalis' egen beskrivelse"],
          ["Sådan kommer I i gang", "Hør den først: den ringer til jer, uden tilmelding. Opsæt selv på ca. en halv time", "Gratis konsultation og tilbagekald"],
          ["Binding", "Ingen – opsig måned til måned", "Se Vocalis' egen beskrivelse"],
        ]} /> },
        { title: "Pris: fast eller målt", body: <>
          <p>Vocalis starter lavere, men prisen følger forbruget: går I over de 100 minutter, tilkøbes pakker automatisk. Dialogbot koster mere som udgangspunkt, men 300 minutter er med, og minutter derudover koster 1,50 kr. Regningen er til at forudsige, og I kan altid se jeres forbrug.</p>
          <p>Er der kun få opkald om måneden, kan en lavere startpris passe bedre. Er telefonen i gang hele dagen, er en fast pris det trygge. Se <Link href="/priser">alle priser</Link>.</p>
        </> },
        { title: "Den store forskel: godkendt viden", body: <p>Dialogbot svarer kun ud fra de ydelser, priser og åbningstider, I selv har godkendt, og siger det, hvis den ikke kender svaret. Hver ændring vises først som før → efter med «Godkend?». Det er den mekanik, der gør, at den ikke gætter.</p> },
        { title: "Hør forskellen selv", body: <p><Link href="/proev">Lad Dialogbot ringe til jer</Link> – det tager to minutter og kræver ingen tilmelding.</p> },
      ]}
      faq={[
        ["Er Dialogbot dyrere end Vocalis?", "Som udgangspunkt ja: 2.495 kr. om måneden mod fra 899 kr. for 100 minutter. Til gengæld er 300 minutter med, og prisen springer ikke, hvis I får flere opkald."],
        ["Kan jeg skifte fra Vocalis til Dialogbot?", "Ja. I beholder jeres nuværende telefonnummer og viderestiller til Dialogbot, og der er ingen binding."],
        ["Hvor kan jeg se Vocalis' aktuelle priser?", "Hos Vocalis selv. Priserne her er de offentliggjorte listepriser, da siden blev skrevet, og de kan have ændret sig."],
      ]} />
  );
}
