import type { Metadata } from "next";
import Link from "next/link";
import { COMPANY, LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Kontakt og support | Dialogbot", description: "Sådan kontakter du Dialogbot om din konto, betaling eller dine data." };

export default function ContactPage() {
  return (
    <LegalPage label="Kontakt" title="Kontakt og support" updated="Opdateret 6. oktober 2026."
      intro="Har du spørgsmål til din konto, en faktura, din assistent eller dine data, så skriv til os. Vi svarer på hverdage, som regel inden for én arbejdsdag."
      sections={[
        ["E-mail", <p key="e">Skriv til <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>. Skriv gerne navnet på din virksomhed og den e-mail, du er logget ind med, så vi hurtigt kan finde din konto.</p>],
        ["Post", <p key="p">{COMPANY.name}, {COMPANY.address}.</p>],
        ["Betaling og fakturaer", <p key="b">Spørgsmål om en betaling eller en faktura fra Dialogbot: skriv til os, før du gør indsigelse hos din bank, så finder vi en løsning hurtigst. Dine fakturaer kan du altid se under Fakturering, når du er logget ind.</p>],
        ["Er du logget ind?", <p key="h">Så finder du svar på de fleste spørgsmål under Hjælp i appen, og du kan se din opsætning, dine samtaler og henvendelser direkte.</p>],
        ["Ambassadører", <p key="a">Spørgsmål om bonus, udbetalinger eller reglerne: skriv til samme adresse. Læs om programmet på <Link href="/ambassador/bliv">dialogbot.dk/ambassador/bliv</Link>.</p>],
        ["Persondata", <p key="d">Vil du have indsigt i, rettet eller slettet dine oplysninger, så læs <Link href="/privatliv">privatlivspolitikken</Link> og skriv til os.</p>],
      ]} />
  );
}
