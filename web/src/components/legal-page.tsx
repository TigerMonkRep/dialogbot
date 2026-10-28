import Link from "next/link";
import { LogoMark } from "./ui";

/** Shared frame for the public legal and contact pages (privatliv, vilkår, kontakt). Server component. */
export const COMPANY = {
  name: "Dialogbot",
  cvr: "25632710",
  address: "Abildgade 18, 8200 Aarhus, Danmark",
  email: "info@dialogbot.dk",
};

export function LegalPage({ label, title, intro, updated, sections }: {
  label: string; title: string; intro?: React.ReactNode; updated: string; sections: [string, React.ReactNode][];
}) {
  return (
    <div className="min-h-dvh bg-panel text-ink">
      <header className="bg-paper border-b-2 border-ink">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 min-h-16 flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-2.5"><LogoMark size={32} /><span className="font-display font-extrabold text-[20px] tracking-[-0.3px] text-ink">Dialogbot</span></Link>
          <nav className="flex items-center gap-1" aria-label="Juridisk">
            <Link href="/vilkaar" className="inline-flex items-center min-h-[44px] px-3 rounded-xl text-[14px] font-semibold text-ink hover:bg-panel">Vilkår</Link>
            <Link href="/privatliv" className="inline-flex items-center min-h-[44px] px-3 rounded-xl text-[14px] font-semibold text-ink hover:bg-panel">Privatliv</Link>
            <Link href="/kontakt" className="inline-flex items-center min-h-[44px] px-3 rounded-xl text-[14px] font-semibold text-ink hover:bg-panel">Kontakt</Link>
          </nav>
        </div>
      </header>
      <main id="main" className="max-w-3xl mx-auto px-4 sm:px-6 py-8 md:py-10 flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <span className="eyebrow">{label}</span>
          <h1 className="font-display text-headline-lg-mobile md:text-[40px] md:leading-[1.05] md:tracking-[-1px] text-ink">{title}</h1>
          {intro && <p className="text-body-lg text-ink-soft max-w-[70ch]">{intro}</p>}
          <p className="text-body-sm text-muted">{updated}</p>
        </div>
        {sections.map(([h, body], i) => (
          <section key={h} className="bg-paper rounded-2xl border-2 border-ink p-5 sm:p-6 flex gap-4">
            <span className="hidden sm:inline-flex w-10 h-10 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-[20px] text-ink flex-shrink-0" aria-hidden>{i + 1}</span>
            <div className="min-w-0 flex-1">
              <h2 className="font-display text-headline-sm text-ink mb-2">{h}</h2>
              <div className="text-body-md text-ink-soft flex flex-col gap-2 [&_a]:underline [&_a]:text-accent">{body}</div>
            </div>
          </section>
        ))}
        <p className="text-body-sm text-muted">{COMPANY.name} · CVR-nr. {COMPANY.cvr} · {COMPANY.address} · <a className="underline text-accent" href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a></p>
      </main>
    </div>
  );
}
