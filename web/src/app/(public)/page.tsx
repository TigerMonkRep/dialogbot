import Link from "next/link";
import { Icon } from "@/components/ui";

/** P01 (minimal, honest): three entry points that carry product intent into signup (A01). Pricing, demo and help (P02–P09) follow in later milestones. */
export default function Home() {
  const cards: [string, string, string, string][] = [
    ["reception", "support_agent", "Reception", "Telefon, webchat og bestilt callback besvaret af en assistent, der kun bruger jeres godkendte viden."],
    ["campaigns", "campaign", "Kampagner", "Udgående opfølgning i forudbetalte kontaktpakker. Betaling starter aldrig opkald."],
    ["both", "hub", "Begge dele", "Reception og kampagner i samme arbejdsrum med én vidensbase."],
  ];
  return (
    <main className="min-h-dvh bg-surface">
      <header className="h-16 px-margin lg:px-margin-lg flex items-center justify-between">
        <span className="flex items-center gap-space-sm"><span className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center"><Icon name="support_agent" size={20} className="text-secondary-fixed" /></span><span className="font-display text-headline-sm text-primary font-bold tracking-tight">Dialogbot</span></span>
        <nav className="flex items-center gap-space-sm"><Link href="/login" className="px-space-md py-2 rounded-lg text-label-md text-on-surface-variant hover:bg-surface-container-low">Log ind</Link><Link href="/signup" className="px-space-lg py-2 rounded-xl bg-primary text-on-primary text-label-lg shadow-sm">Opret konto</Link></nav>
      </header>
      <section className="mx-auto max-w-5xl px-gutter py-margin-lg">
        <span className="text-secondary text-label-sm font-bold uppercase tracking-wider">AI-reception for danske virksomheder</span>
        <h1 className="mt-2 font-display text-display-lg text-primary max-w-3xl">Besvar alle henvendelser – kun med den viden, I selv har godkendt</h1>
        <p className="mt-space-md max-w-2xl text-body-lg text-on-surface-variant">Vælg, hvad I vil starte med. Valget følger med gennem oprettelsen og kan ændres i opsætningen.</p>
        <div className="mt-margin-lg grid gap-space-md md:grid-cols-3">
          {cards.map(([intent, icon, title, text]) => (
            <Link key={intent} href={`/signup?intent=${intent}`} className="group rounded-xl bg-surface-container-lowest p-space-xl shadow-sm hover:shadow-md transition-all flex flex-col gap-space-md">
              <span className="w-10 h-10 rounded-lg bg-surface-container-low text-primary flex items-center justify-center"><Icon name={icon} size={22} /></span>
              <h2 className="font-display text-headline-sm text-primary font-bold">{title}</h2>
              <p className="text-body-sm text-on-surface-variant flex-1">{text}</p>
              <span className="text-label-lg text-secondary flex items-center gap-1">Kom i gang <Icon name="arrow_forward" size={18} className="group-hover:translate-x-0.5 transition-transform" /></span>
            </Link>
          ))}
        </div>
        <p className="mt-margin-lg text-label-md text-on-surface-variant">Priser, demo, hjælpecenter og juridiske sider (P02–P09) kommer i de næste milepæle. Der vises ingen vilkår, garantier eller certificeringer, før de er godkendt.</p>
      </section>
    </main>
  );
}
