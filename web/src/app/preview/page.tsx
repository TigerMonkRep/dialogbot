import type { Metadata } from "next";
import Link from "next/link";
import { Icon } from "@/components/ui";
import { safeNext } from "@/lib/safe-next";
import { UnlockForm, WaitlistForm } from "./forms";

export const metadata: Metadata = {
  title: "Dialogbot – privat preview",
  description: "Dialogbot er en dansk AI-assistent til telefon, webchat og opfølgning. Skriv dig op til tidlig adgang.",
};

/** P00 — temporary landing page with access control (Stitch "p00_midlertidig_landing_page_adgangskontrol").
 *  Honest: no invented metrics, no demo code on the page, no audio sample that does not exist. */
export default async function PreviewPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  const target = safeNext(next, "/");
  const highlights: [string, string, string, string][] = [
    ["call_log", "01 / Telefoni", "Intelligent reception", "Tager telefonen, når I er optaget, stiller de rigtige spørgsmål og samler behov og kontaktoplysninger til jer."],
    ["cycle", "02 / Opfølgning", "Aktiv opfølgning", "Følger op på sendte tilbud med jeres godkendte manuskript, så varme henvendelser ikke bliver glemt."],
    ["shield_person", "03 / Kontrol", "Fuld kontrol & sandkasse", "I godkender viden, regler, priser og svar og tester assistenten, før den må tale med en eneste kunde."],
  ];
  return (
    <div className="min-h-dvh bg-surface flex flex-col selection:bg-secondary-container selection:text-on-secondary-fixed">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-space-md focus:py-2 focus:rounded-lg focus:bg-primary focus:text-on-primary">Spring til indhold</a>
      <header className="fixed top-0 w-full z-50 bg-surface/85 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.03)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-12 flex items-center justify-between h-16">
          <div className="flex items-center gap-space-sm">
            <span className="flex items-center gap-2.5">
              <span className="w-9 h-9 rounded-lg bg-primary flex items-center justify-center text-secondary-fixed shadow-sm"><Icon name="support_agent" size={22} /></span>
              <span className="font-headline-sm text-headline-sm text-primary font-bold tracking-tight">Dialogbot</span>
            </span>
            <span className="inline-flex items-center gap-space-xs px-space-sm py-0.5 rounded-full bg-secondary-fixed text-on-secondary-fixed sm:bg-surface-container-high sm:text-on-surface-variant font-label-sm text-label-sm sm:ml-2">
              <span className="w-1.5 h-1.5 rounded-full bg-secondary sm:bg-secondary-fixed-dim animate-pulse" /><span className="sm:hidden">Preview</span><span className="hidden sm:inline">Tidlig adgang (privat preview)</span>
            </span>
          </div>
          <nav className="flex items-center gap-space-md sm:gap-space-lg" aria-label="Hovedmenu">
            <a href="#venteliste" className="hidden sm:inline font-label-md text-label-md text-primary font-semibold">Tilmeld</a>
            <Link href="/login" aria-label="Log ind" title="Log ind" className="w-9 h-9 rounded-full bg-primary flex items-center justify-center text-on-primary hover:bg-primary-container transition-colors"><Icon name="person" size={20} /></Link>
          </nav>
        </div>
      </header>

      <main id="main" className="w-full flex-1 pt-16">
        <section className="relative w-full overflow-hidden px-4 sm:px-6 lg:px-12 pt-6 pb-12 lg:pt-14 lg:pb-24">
          <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[780px] h-[380px] bg-gradient-to-b from-secondary-container/40 via-surface-container/30 to-transparent blur-3xl pointer-events-none rounded-full" />
          <div className="absolute top-1/3 -right-24 w-96 h-96 bg-primary-fixed/20 blur-3xl pointer-events-none rounded-full" />
          <div className="max-w-6xl mx-auto flex flex-col items-start lg:items-center relative z-10">
            <div className="inline-flex items-center gap-space-sm px-4 py-1.5 rounded-full bg-surface-container-high shadow-sm mb-4 lg:mb-6">
              <span className="w-2.5 h-2.5 rounded-full bg-secondary-fixed-dim inline-block shadow-[0_0_8px_#bbd06c]" />
              <span className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-semibold">Privat preview<span className="hidden sm:inline"> &amp; udvikling</span></span>
              <span className="hidden sm:inline text-outline-variant font-body-sm">•</span>
              <span className="hidden sm:inline font-label-sm text-label-sm text-primary font-medium">Lukket pilotfase</span>
            </div>
            <h1 className="font-headline-lg-mobile text-headline-lg-mobile sm:font-display-lg sm:text-display-lg text-primary lg:text-center max-w-4xl tracking-tight">Vi bygger fremtidens intelligente kundetelefoni og opfølgning.</h1>
            <p className="mt-3 lg:mt-6 font-body-md text-body-md sm:font-body-lg sm:text-body-lg text-on-surface-variant lg:text-center max-w-2xl">Dialogbot er en dansk AI-assistent, der skal tage telefonen, besvare webchat og følge op på tilbud for travle virksomheder — med jeres egen viden og bookingregler. Vi finpudser detaljerne før offentlig åbning.</p>
            <div className="my-5 lg:my-8 w-full sm:w-auto flex items-center justify-between sm:justify-start gap-2 bg-surface-container-low px-5 py-2.5 rounded-full shadow-sm">
              <span className="flex items-center gap-1.5"><Icon name="graphic_eq" size={18} className="text-primary" />
                <span aria-hidden className="flex items-center gap-1 h-4">{[2, 4, 3, 5, 2].map((h, i) => <span key={i} className={`w-1 rounded-full ${i % 2 ? "bg-secondary" : "bg-primary"}`} style={{ height: h * 4 }} />)}</span>
              </span>
              <span className="font-label-sm text-label-sm text-primary font-medium">Telefon · webchat · opfølgning — under udvikling</span>
            </div>

            <div className="w-full grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-8 mt-2 lg:mt-4 items-stretch">
              <div className="lg:col-span-5 bg-surface-container-lowest rounded-xl p-5 sm:p-8 lg:p-10 shadow-md flex flex-col justify-between gap-6">
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div className="w-12 h-12 rounded-lg bg-surface-container-low flex items-center justify-center"><Icon name="key" size={26} className="text-primary" /></div>
                    <span className="px-3 py-1 rounded-full bg-surface-container font-label-sm text-label-sm text-on-surface-variant font-medium">Betatestere</span>
                  </div>
                  <h2 className="font-headline-md text-headline-md sm:font-headline-lg sm:text-headline-lg text-primary tracking-tight">Lås op med forhåndskode</h2>
                  <p className="font-body-md text-body-md text-on-surface-variant mt-2 mb-6">Indtast den invitationskode, du har fået, for at se forsiden og oprette en konto.</p>
                  <UnlockForm next={target} />
                </div>
                <div className="bg-surface-container-low/60 rounded-lg p-3 flex items-center gap-2">
                  <Icon name="verified_user" size={18} className="text-outline" />
                  <p className="font-body-sm text-body-sm text-on-surface-variant">Koder udleveres til pilotvirksomheder og udvalgte partnere. Har du allerede en konto, så <Link href="/login" className="text-primary font-semibold underline">log ind</Link>.</p>
                </div>
              </div>

              <div id="venteliste" className="lg:col-span-7 bg-surface-container-lowest rounded-xl p-5 sm:p-8 lg:p-10 shadow-md flex flex-col justify-between gap-6 scroll-mt-24">
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div className="w-12 h-12 rounded-lg bg-secondary-container/40 flex items-center justify-center"><Icon name="forward_to_inbox" size={26} className="text-secondary" /></div>
                    <span className="px-3 py-1 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-semibold">Venteliste</span>
                  </div>
                  <h2 className="font-headline-md text-headline-md sm:font-headline-lg sm:text-headline-lg text-primary tracking-tight">Skriv dig op til tidlig adgang</h2>
                  <p className="font-body-md text-body-md text-on-surface-variant mt-2 mb-6">Få besked i din indbakke, så snart vi åbner for nye virksomheder.</p>
                  <WaitlistForm />
                </div>
                <div className="flex flex-wrap items-center gap-y-2 gap-x-4 bg-surface-container-low/60 rounded-lg p-3">
                  {["Ingen spam — kun besked ved åbning", "Slet dig når som helst"].map((t) => (
                    <span key={t} className="flex items-center gap-1.5 font-label-sm text-label-sm text-on-surface-variant"><Icon name="check_circle" size={16} className="text-primary" />{t}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="w-full bg-surface-container-lowest py-10 lg:py-14 px-4 sm:px-6 lg:px-12 shadow-sm">
          <div className="max-w-6xl mx-auto">
            <div className="mb-6 lg:mb-8">
              <span className="font-label-sm text-label-sm uppercase tracking-wider text-secondary font-bold block mb-1">Det vi bygger</span>
              <h2 className="font-headline-md text-headline-md text-primary font-bold">Designet til hverdagen i danske SMV&apos;er</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 md:gap-8">
              {highlights.map(([icon, tag, title, text]) => (
                <div key={title} className="bg-surface-container-low/40 rounded-xl p-4 md:p-6 hover:bg-surface-container-low transition-colors flex md:block gap-4">
                  <div className="w-12 h-12 shrink-0 rounded-lg bg-surface-container flex items-center justify-center text-primary md:mb-5 shadow-sm"><Icon name={icon} size={26} /></div>
                  <div>
                    <span className="font-label-sm text-label-sm text-outline font-semibold tracking-wider uppercase block mb-1">{tag}</span>
                    <h3 className="font-headline-sm text-headline-sm text-primary font-bold mb-2">{title}</h3>
                    <p className="font-body-md text-body-md text-on-surface-variant">{text}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="w-full bg-surface-container-low">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-12 py-6 flex flex-col md:flex-row items-center justify-between gap-3 font-body-sm text-body-sm text-on-surface-variant">
          <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-primary" />© {new Date().getFullYear()} Dialogbot. Under udvikling i Danmark.</span>
          <Link href="/login" className="font-label-md text-label-md text-primary hover:underline">Log ind for teamet</Link>
        </div>
      </footer>
    </div>
  );
}
