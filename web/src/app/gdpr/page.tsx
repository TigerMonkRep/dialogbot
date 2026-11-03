import type { Metadata } from "next";
import Link from "next/link";
import { COMPANY } from "@/components/legal-page";
import { SeoPage } from "@/components/seo-page";

export const metadata: Metadata = {
  title: "GDPR og data – sådan passer Dialogbot på jeres kunders oplysninger",
  description: "Hvad Dialogbot gemmer om opkald og SMS, hvor data ligger, hvordan databehandleraftalen fungerer, og hvad der sker, når I opsiger. Kort og på almindeligt dansk.",
  alternates: { canonical: "/gdpr" },
  openGraph: { url: "/gdpr", title: "GDPR og data | Dialogbot", images: ["/opengraph-image.png"] },
};

/** Plain-Danish data-handling statement (audit D3.4). Every sentence mirrors /privatliv and /vilkaar – change those
 *  first if the facts change. */
export default function Page() {
  return (
    <SeoPage path="/gdpr" kicker="GDPR og data"
      title="GDPR og data: hvad vi gemmer, og hvor"
      lead="Jeres kunder ringer og skriver med personlige oplysninger. Her står det i almindeligt dansk, hvad Dialogbot gør ved dem."
      points={["I er dataansvarlige – Dialogbot er jeres databehandler", "Databasen ligger i EU", "Databehandleraftale er en del af vilkårene", "Opkald kan transskriberes til tekst", "Dialogbot siger ærligt, at den er en AI", "Opsiger I, kan I få en kopi af data, og så sletter vi"]}
      sections={[
        { title: "Hvem er ansvarlig for hvad?", body: <>
          <p>Det er jer, der er <strong>dataansvarlige</strong> for jeres kunders oplysninger. Dialogbot er <strong>databehandler</strong> og behandler kun oplysningerne efter jeres instruks. Det gælder også, hvis jeres kunder er patienter, klienter eller private.</p>
        </> },
        { title: "Hvad gemmer vi?", body: <ul>
          <li>Telefonnummer, navn og beskedens indhold, når nogen ringer eller skriver til jer</li>
          <li>En udskrift af samtalen – opkald kan blive transskriberet til tekst</li>
          <li>Bookinger og SMS-bekræftelser</li>
          <li>Den opsummering af hver henvendelse, I får fra Dialogbot</li>
          <li>Den viden og de priser, I selv har godkendt til assistenten</li>
        </ul> },
        { title: "Hvor ligger data?", body: <>
          <p>Databasen ligger i EU (Irland), og serveren i EU (Frankfurt). Telefoni, tale og AI kører hos underleverandører, og nogle af dem kan behandle data i USA. Det sker på grundlag af EU-U.S. Data Privacy Framework eller EU-Kommissionens standardkontrakter. Den fulde liste over underdatabehandlere står i <Link href="/privatliv">privatlivspolitikken</Link>.</p>
        </> },
        { title: "Databehandleraftale", body: <>
          <p>Vores databehandleraftale indgår i <Link href="/vilkaar">vilkårene</Link>, så I behøver ikke bede om en separat. Skriv til <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>, hvis I har brug for en underskrevet kopi til jeres egen dokumentation.</p>
        </> },
        { title: "Hvad fortæller assistenten kunderne?", body: <>
          <p>Dialogbot siger ærligt, at den er en digital assistent, hvis kunden spørger, og den oplyser det i samtalen. Den svarer kun ud fra viden, I selv har godkendt.</p>
        </> },
        { title: "Når I opsiger", body: <>
          <p>Jeres data tilhører jer. Inden for 30 dage efter opsigelsen kan I bede om en kopi. Derefter sletter vi dem, medmindre loven kræver, at vi gemmer dem – fx fakturaer i 5 år.</p>
        </> },
        { title: "Spørgsmål eller indsigt", body: <p>Vil en af jeres kunder have indsigt i eller slettet sine oplysninger, hjælper vi jer med at svare. Skriv til <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>. Kunder kan også klage til <a href="https://www.datatilsynet.dk" rel="noreferrer">Datatilsynet</a>.</p> },
      ]}
      faq={[
        ["Kan jeg få en databehandleraftale?", "Ja. Den indgår i vilkårene. Skriv til info@dialogbot.dk, hvis I vil have en underskrevet kopi."],
        ["Ligger data i EU?", "Databasen ligger i EU (Irland) og serveren i EU (Frankfurt). Nogle underleverandører til telefoni, tale og AI kan behandle data i USA på grundlag af EU-U.S. Data Privacy Framework eller standardkontrakter."],
        ["Hvad sker der med data, når jeg opsiger?", "I kan inden for 30 dage bede om en kopi. Derefter sletter vi data, medmindre loven kræver, at vi gemmer dem."],
      ]} />
  );
}
