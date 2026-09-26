import Link from "next/link";
import { Icon } from "./ui";

/** Auth layout after Stitch "a04_a05_nulstilling_af_adgangskode_teaminvitation": header with back link
 *  and "Sikker" pill, an intro card (icon, code, title) and the form card. Centered column on desktop. */
export function AuthFrame({ title, subtitle, children, code, icon = "lock", aside, back = "/" }: {
  title: string; subtitle?: string; children: React.ReactNode; code?: string; icon?: string; aside?: React.ReactNode; back?: string;
}) {
  return (
    <div className="min-h-dvh bg-surface flex flex-col">
      <header className="sticky top-0 z-40 h-16 px-margin md:px-margin-lg flex items-center justify-between bg-surface/85 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.03)]">
        <div className="flex items-center gap-space-sm">
          <Link href={back} aria-label="Tilbage" className="w-10 h-10 -ml-2 rounded-lg flex items-center justify-center text-primary hover:bg-surface-container"><Icon name="arrow_back" size={24} /></Link>
          <Link href="/" className="flex items-center gap-space-sm">
            <div className="w-8 h-8 rounded-lg bg-primary-container flex items-center justify-center"><Icon name="smart_toy" size={20} className="text-secondary-fixed" /></div>
            <span className="font-headline-sm text-headline-sm text-primary font-bold tracking-tight">Dialogbot</span>
          </Link>
        </div>
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm" title="Forbindelsen er krypteret, og sessionen gemmes i en httpOnly-cookie">
          <Icon name="lock" size={16} className="text-primary" />Sikker
        </span>
      </header>
      <main id="main" className="flex-1 flex justify-center px-margin py-space-lg md:py-margin-lg">
        <div className="w-full max-w-md flex flex-col gap-space-md">
          <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
            <div className="flex items-center justify-between">
              <div className="w-11 h-11 rounded-full bg-primary-container flex items-center justify-center text-secondary-fixed"><Icon name={icon} size={22} /></div>
              {code && <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-container-high text-primary font-label-sm text-label-sm font-bold"><span className="w-1.5 h-1.5 rounded-full bg-primary" />{code}</span>}
            </div>
            <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary tracking-tight">{title}</h1>
            {subtitle && <p className="font-body-md text-body-md text-on-surface-variant">{subtitle}</p>}
          </section>
          <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm">{children}</section>
          {aside}
        </div>
      </main>
    </div>
  );
}

/** Supporting card below the form (Stitch "Har du problemer med linket?"). */
export function AuthAside({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) {
  return (
    <section className="bg-surface-container-low rounded-xl p-space-md flex items-start gap-space-sm">
      <div className="w-9 h-9 rounded-full bg-error-container/70 text-error flex items-center justify-center flex-shrink-0"><Icon name={icon} size={20} /></div>
      <div className="space-y-1 min-w-0"><p className="font-label-lg text-label-lg text-primary">{title}</p><div className="font-body-sm text-body-sm text-on-surface-variant">{children}</div></div>
    </section>
  );
}
