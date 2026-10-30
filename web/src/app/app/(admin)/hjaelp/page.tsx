import Link from "next/link";
import { Icon } from "@/components/ui";

const SECTIONS: { icon: string; title: string; items: [string, string, string?][] }[] = [
  { icon: "rocket_launch", title: "Kom i gang", items: [
    ["Opsætningsguiden", "Guiden tager jer gennem virksomhed, mål, sprog og viden. Ved hvert trin foreslår AI'en indhold ud fra jeres hjemmeside – I retter til og gemmer.", "/app/setup"],
    ["Hent oplysninger fra hjemmesiden", "Virksomhedssiden læser jeres hjemmeside og udfylder beskrivelse, CVR, telefon og adresse, når de står på siden. Ydelser og åbningstider bliver kladder.", "/onboarding/business"],
  ] },
  { icon: "menu_book", title: "Viden", items: [
    ["Kun godkendt viden bruges", "Assistenten svarer udelukkende ud fra godkendte emner. Kladder og forslag bruges aldrig, før en ejer eller administrator har godkendt dem.", "/app/viden"],
    ["Priser", "Priser indtastes ekskl. moms. AI'en gætter aldrig en pris – står der en pris på hjemmesiden, citeres den i kladden, så I kan bekræfte den.", "/app/viden"],
    ["Slet eller ret", "Ret et emne og gem det som ny kladde, eller slet det. Sletter I godkendt viden, holder assistenten straks op med at bruge den.", "/app/viden"],
  ] },
  { icon: "support_agent", title: "Reception, telefon og chat", items: [
    ["Receptionsmanuskript", "Bestem hilsen, hvad assistenten spørger om, og hvornår en medarbejder overtager. Gælder både telefon og chat.", "/app/indstillinger?ark=hilsen"],
    ["Telefon og dansk stemme", "Behold jeres nummer og viderestil det til jeres Dialogbot-nummer. Vælg en dansk stemme, test forbindelsen og aktivér. Opkald lander under Opkald med udskrift.", "/app/indstillinger?ark=telefoni"],
    ["Webchat", "Slå widgetten til, godkend jeres domæner og indsæt koden på hjemmesiden. I kan overtage en samtale under Opkald.", "/app/indstillinger?ark=webchat"],
  ] },
  { icon: "contact_support", title: "Henvendelser og afregning", items: [
    ["Henvendelser og opgaver", "Kunder, der vil kontaktes, bliver til henvendelser med en opgave. Kvalificér, godkend og løs dem fra Opkald → Åbn henvendelse.", "/app/opkald?f=to_you"],
    ["Afregning", "Der er ét abonnement fra 2.495 kr. om måneden ekskl. moms, inkl. 300 minutters indgående opkald (derefter 1,50 kr. pr. minut). Udgående kampagneopkald koster 4 kr. pr. opkald plus 2 kr. pr. påbegyndt samtaleminut. Konto viser månedens forhåndsvisning.", "/app/konto"],
  ] },
  { icon: "group", title: "Team og sikkerhed", items: [
    ["Roller", "Ejer og administrator godkender viden og ændrer indstillinger. Medarbejdere arbejder med henvendelser og kladder. Læsere kan kun se.", "/app/konto"],
    ["Aktivitetslog", "Alle godkendelser, sletninger og ændringer af indstillinger logges med hvem og hvornår.", "/app/indstillinger?ark=log"],
  ] },
];

/** Help: short answers to the common questions, each linking to where it is done. */
export default function HelpPage() {
  return (
    <section className="flex flex-col gap-4 max-w-4xl">
      <div>
        <span className="eyebrow">Hjælp</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Sådan bruger I Dialogbot</h1>
      </div>
      {SECTIONS.map((s) => (
        <div key={s.title} className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
          <h2 className="font-display text-headline-sm text-ink flex items-center gap-1"><Icon name={s.icon} size={22} className="text-muted" />{s.title}</h2>
          <dl className="flex flex-col gap-2">
            {s.items.map(([q, a, href]) => (
              <div key={q} className="p-2 rounded-lg bg-panel">
                <dt className="text-label-lg text-ink font-bold">{q}</dt>
                <dd className="text-body-sm text-ink-soft mt-0.5">{a} {href && <Link href={href} className="text-ink underline whitespace-nowrap">Gå dertil</Link>}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </section>
  );
}
