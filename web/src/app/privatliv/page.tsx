import type { Metadata } from "next";
import Link from "next/link";
import { COMPANY, LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Privatliv | Dialogbot", description: "Sådan behandler Dialogbot personoplysninger om kunder, deres kunder, ambassadører og besøgende." };

/** Privacy policy. Keep it limited to what the product actually does (see docs and the code). */
export default function PrivacyPage() {
  return (
    <LegalPage label="Privatliv" title="Sådan behandler vi personoplysninger" updated="Opdateret 6. oktober 2026."
      intro="Her kan du se, hvilke oplysninger Dialogbot behandler, hvorfor, hvor længe og hvem der hjælper os med det. Siden dækker kunder, kundernes egne kunder, ambassadører og besøgende."
      sections={[
        ["Hvem er ansvarlig?", <p key="a">{COMPANY.name} (CVR-nr. {COMPANY.cvr}), {COMPANY.address}. Skriv til <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a> om alt, der handler om dine oplysninger.</p>],
        ["Kunder (virksomheder med en konto)", <>
          <p>Vi behandler navn, e-mail og adgangskode (gemt krypteret) for brugerne, virksomhedens oplysninger (navn, CVR, adresse, telefon, åbningstider, ydelser og priser) og den viden, I lægger ind til assistenten. Vi logger vigtige handlinger, fx godkendelser og ændringer af roller, af hensyn til sikkerhed.</p>
          <p>Formålet er at levere tjenesten og fakturere den. Retsgrundlaget er aftalen med jer (databeskyttelsesforordningens art. 6, stk. 1, litra b) og vores legitime interesse i sikkerhed og drift (litra f).</p></>],
        ["Betaling", <p key="b">Betalingskort håndteres af Stripe. Vi ser kun kortets type, de sidste fire cifre og udløbsdato. Fakturaer gemmes i 5 år efter bogføringsloven.</p>],
        ["Jeres kunder (samtaler, opkald og henvendelser)", <>
          <p>Når assistenten taler med jeres kunder i telefonen eller på hjemmesiden, behandler vi telefonnummer, navn, beskedens indhold, udskrift af samtalen, bookinger og de henvendelser, der opstår. Det gør vi som <strong>databehandler</strong> på vegne af den virksomhed, kunden har kontaktet – virksomheden er dataansvarlig. Se <Link href="/vilkaar">vilkårene</Link>.</p>
          <p>Opkald kan blive transskriberet til tekst. Assistenten oplyser i starten af samtalen, at den er en AI.</p></>],
        ["Ambassadører", <>
          <p>Er du ambassadør, behandler vi navn, e-mail, telefon, fødselsdato, din hilsen, de kunder du har henvist (kun firmanavn og status), din bonus og dine udbetalinger.</p>
          <p>Uden CVR behandler vi også dit <strong>CPR-nummer</strong> og dit <strong>bankkontonummer</strong>. CPR-nummeret bruges kun til at indberette din bonus som B-indkomst til Skattestyrelsen, som vi har pligt til; kontonummeret kun til udbetaling. Begge gemmes krypteret og kan kun ses af Dialogbots administratorer, og hver visning logges. Er du under 18, behandler vi også din forælders navn, e-mail og godkendelse.</p>
          <p>Retsgrundlaget er aftalen med dig (art. 6, stk. 1, litra b), vores retlige forpligtelse til at indberette (litra c og databeskyttelseslovens § 11 om CPR). Oplysningerne gemmes, så længe du er ambassadør, og derefter i 5 år af hensyn til bogføring og skat.</p></>],
        ["Venteliste og demo-opkald", <>
          <p><strong>Venteliste:</strong> e-mail, valgt branche og interesser samt tidspunkt for samtykke – kun for at give dig besked, når vi åbner. Gemmes højst 24 måneder.</p>
          <p><strong>"Ring mig op nu":</strong> telefonnummer, navn, virksomhed, tidspunkt og tekst for dit samtykke samt udskrift af samtalen, så vi kan ringe op og følge op. Siger du nej tak i opkaldet, kommer nummeret på vores spærreliste. Retsgrundlaget er dit samtykke, som du altid kan trække tilbage.</p></>],
        ["Cookies", <p key="c">Vi bruger kun nødvendige cookies: til at holde dig logget ind, huske dit valgte arbejdsrum, adgangskoden til forsiden og – hvis du kom via en ambassadørs link – hvilken ambassadør der anbefalede os (90 dage). Vi bruger ingen reklame- eller sporingscookies.</p>],
        ["Hvem hjælper os? (underdatabehandlere)", <>
          <p>Vi bruger disse leverandører, som behandler data på vores vegne under databehandleraftaler:</p>
          <ul className="list-disc pl-5 flex flex-col gap-1">
            <li>Supabase – database (EU, Irland)</li>
            <li>Render – server (EU, Frankfurt)</li>
            <li>Vercel – hjemmeside og app</li>
            <li>Resend – afsendelse af e-mails (EU, Irland)</li>
            <li>Stripe – betaling</li>
            <li>Anthropic – AI-model, der formulerer svarene</li>
            <li>Vapi og Twilio – telefoni</li>
            <li>Deepgram og ElevenLabs – tale til tekst og tekst til tale</li>
          </ul>
          <p>Nogle af dem kan behandle data i USA. Overførsel sker på grundlag af EU-U.S. Data Privacy Framework eller EU-Kommissionens standardkontrakter.</p></>],
        ["Dine rettigheder", <p key="r">Du har ret til indsigt, berigtigelse, sletning, begrænsning, dataportabilitet og til at gøre indsigelse – og til at trække et samtykke tilbage. Skriv til <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>. Gælder det en samtale med en af vores kunder, hjælper vi den virksomhed med at svare dig. Du kan klage til Datatilsynet (<a href="https://www.datatilsynet.dk" rel="noreferrer">datatilsynet.dk</a>).</p>],
      ]} />
  );
}
