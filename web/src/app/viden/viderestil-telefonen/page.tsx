import type { Metadata } from "next";
import Link from "next/link";
import { SeoPage } from "@/components/seo-page";

const path = "/viden/viderestil-telefonen";
export const metadata: Metadata = {
  title: "Sådan viderestiller du telefonen, når du er optaget",
  description: "Viderestil din mobil ved optaget, ingen svar eller altid med standardkoderne **67*, **61* og **21* – og slå det fra igen med ##002#. Guide til danske virksomheder.",
  alternates: { canonical: path },
  openGraph: { url: path, type: "article", title: "Sådan viderestiller du telefonen | Dialogbot", images: ["/opengraph-image.png"] },
};

const code = "rounded-md bg-surface-container px-2 py-0.5 font-mono text-on-surface whitespace-nowrap";

export default function Page() {
  return (
    <SeoPage path={path} kicker="Viderestil telefonen" article={{ published: "2026-10-07" }}
      title="Sådan viderestiller du telefonen, når du er optaget"
      lead="Med viderestilling går opkald videre til et andet nummer – fx din AI-receptionist – når du ikke selv kan tage dem. Her er standardkoderne, du taster på mobilen."
      points={["Ved optaget: **67*nummer#", "Ved ingen svar: **61*nummer#", "Når telefonen er slukket: **62*nummer#", "Altid: **21*nummer#", "Slå al viderestilling fra: ##002#"]}
      sections={[
        { title: "Koderne", body: <>
          <p>Koderne er standard på mobilnettet og virker hos de fleste danske teleselskaber. Skriv nummeret med +45 foran, og tryk opkald efter koden.</p>
          <ul>
            <li><strong>Når du er optaget:</strong> <span className={code}>**67*+4512345678#</span></li>
            <li><strong>Når du ikke svarer:</strong> <span className={code}>**61*+4512345678#</span> – nogle selskaber lader dig angive antal sekunder: <span className={code}>**61*+4512345678**20#</span></li>
            <li><strong>Når telefonen er slukket eller uden dækning:</strong> <span className={code}>**62*+4512345678#</span></li>
            <li><strong>Alle opkald, altid:</strong> <span className={code}>**21*+4512345678#</span></li>
            <li><strong>Slå al viderestilling fra:</strong> <span className={code}>##002#</span></li>
          </ul>
          <p>Virker en kode ikke, eller har du et fastnet- eller IP-telefonianlæg, så slå viderestilling til i teleselskabets app eller selvbetjening, eller spørg dit teleselskab.</p>
        </> },
        { title: "Den smarte opsætning", body: <p>De fleste virksomheder bruger <strong>optaget + ingen svar + slukket</strong>. Så tager du selv telefonen, når du kan, og alle andre opkald går til din AI-receptionist i stedet for telefonsvareren.</p> },
        { title: "Viderestil til Dialogbot", body: <p>Når du opretter dig hos Dialogbot, får du et Dialogbot-nummer, som du viderestiller til – og vi hjælper dig med det under opsætningen. Læs mere om <Link href="/ai-telefonsvarer">AI-telefonsvareren</Link> eller <Link href="/#demo">hør den selv</Link>.</p> },
      ]}
      faq={[
        ["Koster viderestilling noget?", "Det afhænger af dit abonnement hos teleselskabet. Tjek prisen på viderestillede opkald hos dit selskab."],
        ["Hvordan tjekker jeg, om viderestilling er slået til?", "Tast fx *#67# eller *#61# og tryk opkald – så viser telefonen status."],
        ["Kan jeg beholde mit eget nummer?", "Ja. Kunderne ringer stadig til dit nummer; opkaldene viderestilles kun, når du ikke selv tager dem."],
      ]} />
  );
}
