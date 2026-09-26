import Link from "next/link";
import { Icon } from "@/components/ui";

const SECTIONS: { icon: string; title: string; items: [string, string, string?][] }[] = [
  { icon: "rocket_launch", title: "Kom i gang", items: [
    ["Opsætningsguiden", "Guiden tager jer gennem virksomhed, mål, sprog og viden. Ved hvert trin foreslår AI'en indhold ud fra jeres hjemmeside – I retter til og gemmer.", "/app/setup"],
    ["Hent oplysninger fra hjemmesiden", "Virksomhedssiden læser jeres hjemmeside og udfylder beskrivelse, CVR, telefon og adresse, når de står på siden. Ydelser og åbningstider bliver kladder.", "/onboarding/business"],
  ] },
  { icon: "menu_book", title: "Viden", items: [
    ["Kun godkendt viden bruges", "Assistenten svarer udelukkende ud fra godkendte emner. Kladder og forslag bruges aldrig, før en ejer eller administrator har godkendt dem.", "/app/knowledge"],
    ["Priser", "Priser indtastes ekskl. moms. AI'en gætter aldrig en pris – står der en pris på hjemmesiden, citeres den i kladden, så I kan bekræfte den.", "/app/knowledge?tab=k03"],
    ["Slet eller ret", "Ret et emne og gem det som ny kladde, eller slet det. Sletter I godkendt viden, holder assistenten straks op med at bruge den.", "/app/knowledge"],
  ] },
  { icon: "support_agent", title: "Reception, telefon og chat", items: [
    ["Receptionsmanuskript", "Bestem hilsen, hvad assistenten spørger om, og hvornår en medarbejder overtager. Gælder både telefon og chat.", "/app/reception"],
    ["Telefon og dansk stemme", "Tilknyt jeres Vapi-nummer, vælg en dansk stemme og hør den, før I går live. Opkald lander i indbakken med transskription.", "/app/settings/telephony"],
    ["Webchat", "Slå widgetten til, godkend jeres domæner og indsæt koden på hjemmesiden. I kan overtage en samtale fra indbakken.", "/app/settings/webchat"],
  ] },
  { icon: "contact_support", title: "Henvendelser og afregning", items: [
    ["Henvendelser og opgaver", "Kunder, der vil kontaktes, bliver til henvendelser med en opgave. Kvalificér, godkend og løs dem på Henvendelser.", "/app/leads"],
    ["Afregning", "Model A er et fast abonnement; model B betaler pr. godkendt henvendelse. Fakturering viser månedens forhåndsvisning.", "/app/billing"],
  ] },
  { icon: "group", title: "Team og sikkerhed", items: [
    ["Roller", "Ejer og administrator godkender viden og ændrer indstillinger. Medarbejdere arbejder med henvendelser og kladder. Læsere kan kun se.", "/app/settings/team"],
    ["Aktivitetslog", "Alle godkendelser, sletninger og ændringer af indstillinger logges med hvem og hvornår.", "/app/settings/activity"],
  ] },
];

/** Help: short answers to the common questions, each linking to where it is done. */
export default function HelpPage() {
  return (
    <section className="flex flex-col gap-space-lg max-w-4xl">
      <div>
        <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Hjælp</span>
        <h1 className="font-headline-md text-headline-md text-primary font-bold">Sådan bruger I Dialogbot</h1>
      </div>
      {SECTIONS.map((s) => (
        <div key={s.title} className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
          <h2 className="font-headline-sm text-headline-sm text-primary flex items-center gap-space-xs"><Icon name={s.icon} size={22} className="text-secondary" />{s.title}</h2>
          <dl className="flex flex-col gap-space-sm">
            {s.items.map(([q, a, href]) => (
              <div key={q} className="p-space-sm rounded-lg bg-surface-container-low">
                <dt className="font-label-lg text-label-lg text-on-surface font-bold">{q}</dt>
                <dd className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">{a} {href && <Link href={href} className="text-primary underline whitespace-nowrap">Gå dertil</Link>}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </section>
  );
}
