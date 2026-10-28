import Link from "next/link";
import { Icon, LogoMark } from "./ui";

/** Auth layout (Byggevejledning): paper header with 2 px ink line, back link and "Sikker" pill;
 *  an intro card (blue icon tile, code, Outfit title) and the form card. Centered column on desktop. */
export function AuthFrame({ title, subtitle, children, code, icon = "lock", aside, back = "/" }: {
  title: string; subtitle?: string; children: React.ReactNode; code?: string; icon?: string; aside?: React.ReactNode; back?: string;
}) {
  return (
    <div className="min-h-dvh bg-panel text-ink flex flex-col">
      <header className="sticky top-0 z-40 bg-paper border-b-2 border-ink">
        <div className="max-w-[1280px] mx-auto min-h-16 px-4 md:px-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Link href={back} aria-label="Tilbage" className="w-11 h-11 -ml-2 rounded-xl flex items-center justify-center text-ink hover:bg-panel"><Icon name="arrow_back" size={24} /></Link>
            <Link href="/" className="flex items-center gap-2.5">
              <LogoMark size={32} />
              <span className="font-display font-extrabold text-[20px] tracking-[-0.3px] text-ink">Dialogbot</span>
            </Link>
          </div>
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border-[1.5px] border-ink bg-paper text-[12px] font-semibold" title="Forbindelsen er krypteret, og sessionen gemmes i en httpOnly-cookie">
            <Icon name="lock" size={16} className="text-accent" />Sikker
          </span>
        </div>
      </header>
      <main id="main" className="flex-1 flex justify-center px-4 py-6 md:py-10">
        <div className="w-full max-w-md flex flex-col gap-4">
          <section className="bg-paper rounded-2xl border-2 border-ink p-5 md:p-6 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="w-11 h-11 rounded-xl bg-accent flex items-center justify-center text-white"><Icon name={icon} size={22} /></span>
              {code && <span className="eyebrow inline-flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-highlight border border-ink" />{code}</span>}
            </div>
            <h1 className="font-display text-headline-lg-mobile md:text-[34px] md:leading-[1.05] md:tracking-[-0.8px] text-ink">{title}</h1>
            {subtitle && <p className="text-body-md text-ink-soft">{subtitle}</p>}
          </section>
          <section className="bg-paper rounded-2xl border-2 border-ink p-5 md:p-6 shadow-block">{children}</section>
          {aside}
        </div>
      </main>
    </div>
  );
}

/** Supporting card below the form ("Har du problemer med linket?"). */
export function AuthAside({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) {
  return (
    <section className="bg-paper rounded-2xl border-[1.5px] border-ink p-4 flex items-start gap-3">
      <span className="w-9 h-9 rounded-lg bg-panel border-[1.5px] border-ink text-ink flex items-center justify-center flex-shrink-0"><Icon name={icon} size={20} /></span>
      <div className="space-y-1 min-w-0"><p className="text-[15px] font-semibold text-ink">{title}</p><div className="text-body-sm text-ink-soft">{children}</div></div>
    </section>
  );
}
