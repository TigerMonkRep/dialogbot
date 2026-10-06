import Link from "next/link";
import { Icon } from "./ui";

/** Shared frame for the public legal and contact pages (privatliv, vilkår, kontakt). Server component. */
export const COMPANY = {
  name: "Dialogbot",
  address: "Abildgade 18, 8200 Aarhus, Danmark",
  email: "info@dialogbot.dk",
};

export function LegalPage({ label, title, intro, updated, sections }: {
  label: string; title: string; intro?: React.ReactNode; updated: string; sections: [string, React.ReactNode][];
}) {
  return (
    <div className="min-h-dvh bg-surface">
      <header className="bg-surface/85 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.03)]">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-space-md">
          <Link href="/" className="flex items-center gap-2.5"><span className="w-9 h-9 rounded-lg bg-primary flex items-center justify-center text-secondary-fixed"><Icon name="support_agent" size={22} /></span><span className="font-headline-sm text-headline-sm text-primary font-bold">Dialogbot</span></Link>
          <nav className="flex items-center gap-space-md font-label-md text-label-md" aria-label="Juridisk">
            <Link href="/vilkaar" className="text-primary hover:underline">Vilkår</Link>
            <Link href="/privatliv" className="text-primary hover:underline">Privatliv</Link>
            <Link href="/kontakt" className="text-primary hover:underline">Kontakt</Link>
          </nav>
        </div>
      </header>
      <main id="main" className="max-w-3xl mx-auto px-4 sm:px-6 py-space-xl flex flex-col gap-space-lg">
        <div>
          <span className="font-label-sm text-label-sm uppercase tracking-wider text-secondary font-bold">{label}</span>
          <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary">{title}</h1>
          {intro && <p className="font-body-md text-body-md text-on-surface-variant mt-space-xs max-w-[70ch]">{intro}</p>}
          <p className="font-body-sm text-body-sm text-on-surface-variant mt-space-xs">{updated}</p>
        </div>
        {sections.map(([h, body]) => (
          <section key={h} className="bg-surface-container-lowest rounded-xl p-space-md sm:p-space-lg shadow-sm">
            <h2 className="font-headline-sm text-headline-sm text-primary mb-space-xs">{h}</h2>
            <div className="font-body-md text-body-md text-on-surface-variant flex flex-col gap-space-xs [&_a]:underline [&_a]:text-primary">{body}</div>
          </section>
        ))}
        <p className="font-body-sm text-body-sm text-on-surface-variant">{COMPANY.name} · {COMPANY.address} · <a className="underline text-primary" href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a></p>
      </main>
    </div>
  );
}
