import type { Metadata } from "next";
import Link from "next/link";
import { SeoPage } from "@/components/seo-page";

const path = "/viden/ai-telefonsvarer-eller-telefonpasning";
export const metadata: Metadata = {
  title: "AI-telefonsvarer eller telefonpasning?",
  description: "Telefonsvarer, telefonpasningsservice eller AI-telefonsvarer? Se forskellene på pris, tilgængelighed og kvalitet, så du kan vælge den rigtige løsning.",
  alternates: { canonical: path },
  openGraph: { url: path, type: "article", title: "AI-telefonsvarer eller telefonpasning? | Dialogbot", images: ["/opengraph-image.png"] },
};

export default function Page() {
  return (
    <SeoPage path={path} kicker="AI-telefonsvarer eller telefonpasning" article={{ published: "2026-10-07" }}
      title="AI-telefonsvarer eller telefonpasning – hvad passer til jer?"
      lead="Når du ikke selv kan tage telefonen, er der tre muligheder: en almindelig telefonsvarer, en telefonpasningsservice med mennesker, eller en AI-telefonsvarer. Her er forskellene."
      points={["Telefonsvarer: billig, men kunden lægger ofte på", "Telefonpasning: et menneske svarer, men typisk kun i åbningstid", "AI-telefonsvarer: svarer døgnet rundt og kan booke", "Vælg ud fra opkaldsmængde, åbningstid og behov"]}
      sections={[
        { title: "1. Den almindelige telefonsvarer", body: <p>Billig og enkel, men mange kunder lægger på i stedet for at lægge en besked – og ringer til en konkurrent. Du skal selv lytte beskederne igennem og ringe tilbage uden at vide, hvad sagen drejer sig om.</p> },
        { title: "2. Telefonpasningsservice", body: <p>Et menneske tager telefonen i dit navn og skriver en besked. Det giver en personlig oplevelse, men afregnes typisk pr. opkald eller pr. måned, og mange services har kun åbent i almindelig arbejdstid. Receptionisten kender sjældent dine ydelser og priser i detaljer.</p> },
        { title: "3. AI-telefonsvarer", body: <>
          <p>En AI-telefonsvarer som <Link href="/ai-telefonsvarer">Dialogbot</Link> taler med kunden på dansk døgnet rundt, svarer ud fra din egen godkendte viden og kan booke tider og sende SMS-bekræftelser. Du får en skrevet opsummering af hver samtale i stedet for en talebesked.</p>
          <p>Til gengæld er den ikke et menneske – den siger det ærligt og sender sager, den ikke kan svare på, videre til dig.</p>
        </> },
        { title: "Sådan vælger du", body: <ul>
          <li><strong>Få opkald og kun om dagen?</strong> En telefonsvarer kan være nok.</li>
          <li><strong>Vigtigt med et menneske i røret?</strong> Telefonpasning – men tjek åbningstiden.</li>
          <li><strong>Mange opkald, også om aftenen, og ønske om booking?</strong> En AI-telefonsvarer giver mest for pengene.</li>
        </ul> },
        { title: "Hør forskellen", body: <p><Link href="/#demo">Bliv ringet op af Dialogbot</Link> og hør, hvordan en AI-telefonsvarer lyder. Se også <Link href="/priser">priserne</Link>.</p> },
      ]}
      faq={[
        ["Kan en AI-telefonsvarer erstatte telefonpasning?", "For de fleste faste henvendelser ja: den svarer, afklarer behovet og booker. Komplekse sager sendes videre til jer."],
        ["Er en AI-telefonsvarer tilgængelig om natten?", "Ja, Dialogbot tager telefonen døgnet rundt."],
        ["Kan jeg beholde mit nummer?", "Ja. Du viderestiller dit nummer til Dialogbot, når du er optaget eller har lukket."],
      ]} />
  );
}
