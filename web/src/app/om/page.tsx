import type { Metadata } from "next";
import { COMPANY } from "@/components/legal-page";
import { FounderBlock } from "@/components/founder-block";
import { SeoPage } from "@/components/seo-page";
import { FOUNDER } from "@/lib/proof";

export const metadata: Metadata = {
  title: "Om Dialogbot – hvem der står bag",
  description: "Dialogbot er et dansk firma i Aarhus. Her kan du se, hvem der står bag, hvor vi sidder, og hvordan du kommer i kontakt med os.",
  alternates: { canonical: "/om" },
  openGraph: { url: "/om", title: "Om Dialogbot", images: ["/opengraph-image.png"] },
};

/** Who is behind Dialogbot (audit D3.3). The founder block fills in from src/lib/proof.ts; until then the page
 *  shows only what is already public: company, address, phone. */
export default function Page() {
  return (
    <SeoPage path="/om" kicker="Om os"
      title="Hvem står bag Dialogbot?"
      lead={FOUNDER ? `${FOUNDER.name} har bygget Dialogbot, så små virksomheder kan tage telefonen, også når de ikke kan.` : "Dialogbot er et dansk firma i Aarhus, og du kan altid ringe til os."}
      points={["Dansk firma i Aarhus", `CVR ${COMPANY.cvr}`, "Ring til os – vi tager telefonen i åbningstiden", "Ingen binding"]}
      sections={[
        { title: "Hvorfor Dialogbot findes", body: <>
          <p>Når telefonen ringer, mens du står på stigen eller har en kunde i stolen, mister du en kunde. Dialogbot tager telefonen for dig – på dansk, døgnet rundt, og kun med den viden, du selv har godkendt.</p>
          {FOUNDER && <FounderBlock />}
        </> },
        { title: "Sådan finder du os", body: <p>{COMPANY.name}, CVR-nr. {COMPANY.cvr}, {COMPANY.address}. Skriv til <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a> eller ring på <a href="tel:+4593703433">93 70 34 33</a>.</p> },
      ]}
      faq={[
        ["Kan jeg tale med et menneske?", "Ja. Ring til os på 93 70 34 33 i åbningstiden, eller skriv til info@dialogbot.dk."],
        ["Hvem passer på mine kunders oplysninger?", "Det står i almindeligt dansk på siden om GDPR og data."],
      ]} />
  );
}
