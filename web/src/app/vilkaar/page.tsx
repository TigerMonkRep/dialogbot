import type { Metadata } from "next";
import Link from "next/link";
import { COMPANY, LegalPage } from "@/components/legal-page";

export const metadata: Metadata = {
  title: "Abonnements- og handelsbetingelser",
  description: "Vilkår for virksomheder, der opretter en konto og bruger Dialogbot: abonnement, betaling, opsigelse, data og ansvar. Dialogbot sælges kun til erhvervsdrivende.",
  alternates: { canonical: "/vilkaar" },
};

/** Terms of service for business customers (B2B). Prices match the billing code (app/modules/billing). */
export default function TermsPage() {
  return (
    <LegalPage path="/vilkaar" label="Vilkår" title="Abonnements- og handelsbetingelser" updated="Version 1 · gældende fra 6. oktober 2026."
      intro={`Disse vilkår gælder, når en virksomhed opretter en konto og bruger Dialogbot. Dialogbot sælges kun til erhvervsdrivende. "Vi" er ${COMPANY.name} (CVR-nr. ${COMPANY.cvr}), ${COMPANY.address}. "I" er den virksomhed, der har oprettet arbejdsrummet.`}
      sections={[
        ["1. Ydelsen", <>
          <p>Dialogbot er en AI-receptionist, der kan besvare opkald og beskeder på jeres hjemmeside, tage imod henvendelser, booke tider og – hvis I vælger det – ringe op til kontakter, der har givet samtykke. Assistenten svarer ud fra den viden, I selv har godkendt i jeres arbejdsrum.</p>
          <p>Vi udvikler løbende tjenesten. Funktioner, der er markeret som "på vej" eller "ikke tilgængelig", er ikke en del af aftalen, før de er lanceret.</p></>],
        ["2. Priser", <>
          <p>Alle priser er i danske kroner ekskl. moms. Moms (25 %) lægges til på fakturaen.</p>
          <ul className="list-disc pl-5 flex flex-col gap-1">
            <li><strong>Model A – abonnement:</strong> 1.495 kr. pr. måned for receptionen.</li>
            <li><strong>Model B – betal pr. henvendelse:</strong> 149 kr. pr. henvendelse, som I godkender som relevant. Henvendelser, I afviser, koster ikke noget.</li>
            <li><strong>Kampagner:</strong> 9 kr. pr. kontakt, der ringes op (højst 2 forsøg pr. kontakt).</li>
            <li>Et dansk telefonnummer til assistenten er inkluderet. Brugen skal ligge inden for normalt forbrug for en virksomhed af jeres størrelse (fair use); ved væsentligt højere forbrug kontakter vi jer om en tillægspris, før den opkræves.</li>
          </ul>
          <p>Kommer I via en ambassadør, får I 50 % rabat på jeres første fakturerede måned. Vi kan ændre priserne med mindst 30 dages varsel på e-mail; ændringen gælder fra den første hele måned efter varslet.</p></>],
        ["3. Betaling", <>
          <p>I gemmer et betalingskort hos vores betalingsudbyder Stripe. Vi fakturerer bagud én gang om måneden for den forrige måned, og beløbet trækkes automatisk på kortet. Vi gemmer ikke selv kortoplysninger.</p>
          <p>Kan betalingen ikke gennemføres, får I besked. Er en faktura ikke betalt 14 dage efter forfald, kan vi sætte assistenten på pause, indtil betalingen er på plads.</p>
          <p>Har I spørgsmål til en faktura, så <Link href="/kontakt">kontakt os</Link>, før I gør indsigelse hos jeres bank.</p></>],
        ["4. Opstart, løbetid og opsigelse", <>
          <p>Aftalen løber, indtil den opsiges. I kan opsige til udgangen af den løbende måned ved at skrive til os. Vi kan opsige med 30 dages varsel. Der er ingen binding og intet opstartsgebyr.</p>
          <p>Ved væsentlig misligholdelse – fx misbrug af tjenesten eller manglende betaling – kan vi lukke adgangen uden varsel.</p></>],
        ["5. Jeres ansvar", <>
          <p>I er ansvarlige for, at den viden, de priser, åbningstider og svar, I godkender, er korrekte, og for at følge op på de henvendelser, assistenten tager imod.</p>
          <p>Bruger I kampagner (udgående opkald), er I ansvarlige for, at hver kontakt har givet et forudgående, dokumenterbart samtykke til at blive ringet op af et automatisk system, jf. markedsføringsloven § 10, og for at reklamebeskyttede virksomheder ikke kontaktes. Tjenesten må ikke bruges til ulovligt, vildledende eller krænkende indhold.</p>
          <p>I skal holde jeres login fortroligt og give adgang til de rette personer i jeres team.</p></>],
        ["6. AI og ansvarsbegrænsning", <>
          <p>Assistenten bruger kunstig intelligens. Den er instrueret i kun at svare ud fra jeres godkendte viden og i at sige det, hvis den ikke kender svaret, men den kan tage fejl eller misforstå. Den oplyser altid, at den er en AI.</p>
          <p>Vi er ikke ansvarlige for indirekte tab, fx tabt omsætning, tabte kunder eller følgeskader. Vores samlede ansvar er begrænset til det beløb, I har betalt for tjenesten i de seneste 3 måneder før skaden. Vi er ikke ansvarlige for nedbrud hos tredjeparter som teleselskaber og cloududbydere eller for forhold uden for vores kontrol.</p></>],
        ["7. Data og persondata", <>
          <p>Jeres data tilhører jer. Når assistenten taler med jeres kunder, behandler vi persondata på jeres vegne som databehandler. Vi behandler kun data efter jeres instruks og efter vores databehandleraftale, som indgår i disse vilkår. Den liste over underdatabehandlere, vi bruger (bl.a. hosting, telefoni, tale og AI), fremgår af <Link href="/privatliv">privatlivspolitikken</Link>.</p>
          <p>Ved opsigelse kan I inden for 30 dage bede om en kopi af jeres data. Derefter sletter vi dem, medmindre loven kræver, at vi gemmer dem (fx fakturaer i 5 år).</p></>],
        ["8. Ændringer af vilkårene", <p key="c">Vi kan ændre vilkårene med 30 dages varsel på e-mail. Væsentlige ændringer til jeres ugunst giver jer ret til at opsige med virkning fra ændringsdatoen.</p>],
        ["9. Lovvalg og tvister", <p key="l">Aftalen er underlagt dansk ret. Uenigheder forsøges løst i dialog; ellers afgøres de ved Retten i Aarhus.</p>],
        ["Kontakt", <p key="k">{COMPANY.name}, CVR-nr. {COMPANY.cvr}, {COMPANY.address} · <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a> · <Link href="/kontakt">Kontakt og support</Link></p>],
      ]} />
  );
}
