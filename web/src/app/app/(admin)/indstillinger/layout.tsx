import { SubNav } from "../subnav";

const ITEMS: [string, string][] = [
  ["/app/indstillinger", "Overblik"], ["/app/indstillinger/telefoni", "Telefon"], ["/app/indstillinger/hilsen", "Hilsen"], ["/app/indstillinger/stemmer", "Stemmer"],
  ["/app/indstillinger/webchat", "Webchat"], ["/app/indstillinger/integrationer", "Systemer"], ["/app/indstillinger/virksomhed", "Virksomhed"], ["/app/indstillinger/log", "Historik"],
];

/** Alle indstillinger: the spare-parts list. Everything that is not one of the four pages lives here. */
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-6">
      <div>
        <span className="eyebrow">Bagerst i hæftet</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Alle indstillinger</h1>
        <p className="text-[15px] text-ink-soft max-w-[560px] mt-1">Alt, Dialogbot ved og gør – ét sted. Intet markeres som klar, før det virker.</p>
      </div>
      <SubNav label="Indstillinger" items={ITEMS} />
      {children}
    </section>
  );
}
